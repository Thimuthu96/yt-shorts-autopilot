// Gus world cast: round-head characters drawn as 2D canvas sprites on a camera-facing plane.
// Pure registry module: nothing touches the DOM at import time (catalog.js and tests import it under node);
// a Char only gets its canvas when a DOM exists.
//   resolveLook("gus" | {costume?, ...COSTUME_KEYS}) -> full look
//   new Char(id, look); c.born = beatStart (c.beatStart for a kept char); c.frame(spec, t, mouth) -> state (poses the sprite, redraws on change)
//   spec.motionStart (set by a motion event, events.js): the motion runs from then instead of the beat's start
//   spec.act / spec.squash / spec.runs / spec.holding (set by actions.js acts): offsets {x, y, sx, sy, tilt} for t, run_to
//   paths, and "a 3D prop is in the hand" (the look's own held prop is then not drawn)
//   handAt(spec, t), charPosAt(spec, t), runAt(runs, t): positions for actions (a held prop rides handAt)
//   c.faceCamera(camera)   yaw-only billboard
//   drawChar(ctx, look, state)   the sprite, in a CW x CH design space scaled to the canvas
// Design: big white round head (~45 % of the height) with ink outline, dot eyes with a glint, line brows that carry
// the expression, rosy cheeks, stick limbs with mitten hands and little shoes, a short bell torso for the costume.
// Gus: teal jumper, mustard knit scarf with a fluttering tail, round glasses, a question-mark curl on top.
import * as THREE from "three";
import { INK, hash, clamp01, easeIO, easeOut } from "./core.js";

const HAS_DOM = typeof document !== "undefined";
const PI = Math.PI;

// design space (canvas pixels before the resolution scale); feet rest on y = FOOT
export const CW = 640, CH = 800;
const RES = 1.6, FOOT = 762, HEIGHT = 1.8; // world units from sole to the top of the head
const cx = CW / 2, HX = cx, HY = 212, HR = 165, HRY = 158;
const TOP = 362, BOT = 566; // torso
const HEAD = "#FFFDF8", MOUTH = "#6B1E2E", TONGUE = "#F27A86", BLUSH = "rgba(255,112,124,0.32)", SHOE = "#2B2633";

// ---------- looks ----------
export const COSTUME_KEYS = ["costume", "shirt", "stripes", "pants", "hat", "hatColor", "bandana", "coat", "apron", "crown",
  "helmet", "glasses", "mustache", "beard", "badge", "prop"];
// style-valued keys (true = the default style)
const HATS = ["cap", "tricorn", "captain", "bowler", "top", "hardhat", "chef", "straw", "beret", "sailor", "beanie"];
const GLASSES = ["round", "square", "goggles"];
const HELD = ["wrench", "flask", "clipboard", "sword", "pitchfork", "ladle", "scepter", "spyglass", "book", "hammer"];

export const COSTUMES = {
  sailor: { shirt: "#FFFFFF", stripes: "#2F6FD6", pants: "#1F2A44", hat: "sailor", hatColor: "#FFFFFF" },
  pirate: { shirt: "#F3E7C9", stripes: "#3B2E4A", pants: "#5A3B2A", bandana: "#2E8B57", coat: "#7A2431", prop: "spyglass" },
  officer: { shirt: "#FFFFFF", coat: "#23356B", pants: "#E9E2CF", hat: "captain", hatColor: "#23356B", badge: "#F2BE3A" },
  worker: { shirt: "#E8742C", pants: "#3A5A8C", hat: "hardhat", hatColor: "#FFC93C", prop: "wrench" },
  scientist: { shirt: "#7FB7E6", coat: "#FFFFFF", pants: "#3D4458", glasses: "square", prop: "flask" },
  suit: { shirt: "#FFFFFF", coat: "#2F3440", pants: "#2F3440" },
  king: { shirt: "#F2BE3A", coat: "#8E2A4E", pants: "#5B2140", crown: "#F2BE3A", beard: "#EDE8DC", prop: "scepter" },
  knight: { shirt: "#B7C0CC", pants: "#6B7380", helmet: "#B7C0CC", badge: "#D9483B", prop: "sword" },
  farmer: { shirt: "#D9483B", pants: "#3E6FB0", apron: "#3E6FB0", hat: "straw", hatColor: "#E9C46A", prop: "pitchfork" },
  chef: { shirt: "#FFFFFF", apron: "#FFFFFF", pants: "#3D4458", hat: "chef", hatColor: "#FFFFFF", mustache: "#3B2A20", prop: "ladle" },
  doctor: { shirt: "#78C6B5", coat: "#FFFFFF", pants: "#78C6B5", badge: "#E8413C", prop: "clipboard" },
  plain: { shirt: "#E36B5B", pants: "#2D3047" },
};

// Gus is fixed: stories can only ask for "gus", and his scarf and curl are not costume keys.
export const GUS_LOOK = Object.freeze({
  gus: true, shirt: "#2A9D8F", pants: "#2B2D42", scarf: "#F2B33D", scarfStripe: "#D98E1E", glasses: "round", curl: "#5A3B2A",
});

const checkStyle = (look, key, list) => {
  const v = look[key];
  if (v === undefined || v === null || v === false || v === true) return;
  if (!list.includes(v)) throw new Error(`unknown ${key}: ${v}`);
};

export function resolveLook(look) {
  if (look === "gus") return { ...GUS_LOOK };
  if (typeof look === "string") throw new Error(`unknown look: ${look}`);
  if (!look || typeof look !== "object") throw new Error(`unknown look: ${JSON.stringify(look)}`);
  for (const k of Object.keys(look)) if (!COSTUME_KEYS.includes(k)) throw new Error(`unknown look key: ${k}`);
  const name = look.costume || "plain";
  if (!COSTUMES[name]) throw new Error(`unknown costume: ${name}`);
  const out = { costume: name, ...COSTUMES[name], ...look };
  out.costume = name;
  checkStyle(out, "hat", HATS);
  checkStyle(out, "glasses", GLASSES);
  checkStyle(out, "prop", HELD);
  return out;
}

// ---------- poses ----------
// x offsets are toward the facing side (+) in the right-facing drawing; the canvas is mirrored for "left".
// arms: [elbow x, elbow y, hand x, hand y, layer] (layer: back = behind torso, mid = over torso, over = over face)
// legs: [knee x, knee y, foot x, foot y]; lean: radians about the feet (+ = forward); busy: the front hand is
// used by the pose, so a held prop goes to the back hand; both: the prop is held between the hands.
const LEGS = [[-30, 662, -40, FOOT], [30, 662, 40, FOOT]];
const DOWN0 = [-88, 470, -92, 560, "back"], DOWN1 = [88, 470, 92, 560, "back"];
export const POSES = {
  idle: () => ({ arms: [DOWN0, DOWN1] }),
  point: () => ({ arms: [DOWN0, [140, 400, 215, 372, "mid"]], finger: true, busy: true }),
  wave: (t) => ({ arms: [DOWN0, [190, 360, 225 + Math.sin(t * 12) * 26, 205, "back"]], busy: true }),
  armsUp: () => ({ arms: [[-140, 300, -190, 150, "back"], [140, 300, 190, 150, "back"]] }),
  shrug: () => ({ arms: [[-125, 480, -175, 385, "mid"], [125, 480, 175, 385, "mid"]] }),
  think: () => ({ arms: [[-40, 520, 30, 478, "mid"], [125, 470, 48, 318, "over"]], busy: true }),
  hold: () => ({ arms: [[-105, 470, -40, 460, "mid"], [105, 470, 40, 460, "mid"]], both: true }),
  cross: () => ({ arms: [[-95, 470, 62, 438, "mid"], [95, 488, -62, 456, "mid"]], busy: true }),
  facepalm: () => ({ arms: [DOWN0, [130, 420, 34, 232, "over"]], busy: true }),
  present: () => ({ arms: [DOWN0, [120, 470, 205, 452, "mid"]], palm: true, busy: true }),
  scared: () => ({ arms: [[-140, 430, -118, 300, "over"], [140, 430, 118, 300, "over"]],
    legs: [[-10, 668, -46, FOOT], [10, 668, 46, FOOT]], lean: -0.06 }),
  run: (t) => {
    const p = t * 11, s0 = Math.sin(p), s1 = Math.sin(p + PI);
    const leg = (s) => [s * 40 + 18, 660 - Math.max(0, s) * 20, s * 78, FOOT - Math.max(0, s) * 34];
    return {
      arms: [[-30 - s0 * 50, 480, -20 - s0 * 85, 520 - Math.abs(s0) * 30, s0 > 0 ? "back" : "mid"],
        [30 - s1 * 50, 480, 20 - s1 * 85, 520 - Math.abs(s1) * 30, s1 > 0 ? "back" : "mid"]],
      legs: [leg(s0), leg(s1)], lean: 0.14,
    };
  },
  fall: (t) => ({
    arms: [[-150, 330, -200 + Math.sin(t * 14) * 18, 200, "back"], [150, 330, 210, 215 + Math.cos(t * 14) * 18, "back"]],
    legs: [[-30, 662, -48, FOOT], [70, 630, 135, 600]], lean: -0.22,
  }),
  cheer: () => ({ arms: [[-150, 290, -175, 125, "back"], [150, 290, 175, 125, "back"]], fists: true,
    legs: [[-46, 662, -66, FOOT], [46, 662, 66, FOOT]] }),
  // action poses (actions.js acts); a held 3D prop sits in the front hand (arms[1])
  carry: () => ({ arms: [DOWN0, [120, 480, 150, 432, "mid"]] }),
  drink: () => ({ arms: [DOWN0, [175, 420, 92, 300, "over"]], lean: -0.05 }),
  toast: () => ({ arms: [[-118, 476, -66, 528, "mid"], [165, 300, 196, 118, "back"]] }),
  throw_wind: () => ({ arms: [[85, 476, 132, 446, "mid"], [-95, 300, -205, 222, "back"]], lean: -0.1 }),
  throw: () => ({ arms: [[-110, 470, -160, 528, "back"], [160, 380, 238, 318, "mid"]], lean: 0.12 }),
  duck: () => ({ arms: [[-128, 250, -46, 74, "over"], [128, 250, 46, 74, "over"]],
    legs: [[-72, 690, -46, FOOT], [72, 690, 46, FOOT]] }),
  cower: () => ({ arms: [[-150, 450, -112, 282, "over"], [150, 450, 112, 282, "over"]],
    legs: [[-4, 694, -52, FOOT], [4, 694, 52, FOOT]], lean: -0.1 }),
  grab: () => ({ arms: [DOWN0, [158, 468, 236, 498, "mid"]], lean: 0.1 }),
};

export const EXPRS = ["neutral", "happy", "excited", "smug", "sly", "shocked", "scared", "sad", "worried", "angry", "pain"];
const FACINGS = ["right", "left", "front"];

// ---------- drawing ----------
const line = (x, pts, w, color = INK) => {
  x.lineWidth = w; x.strokeStyle = color; x.beginPath(); x.moveTo(...pts[0]);
  for (const p of pts.slice(1)) x.lineTo(...p);
  x.stroke();
};
const fillStroke = (x, fill, w = 8) => { x.fillStyle = fill; x.fill(); x.lineWidth = w; x.strokeStyle = INK; x.stroke(); };
const rrect = (x, X, Y, w, h, r) => { x.beginPath(); x.roundRect(X, Y, w, h, r); };

function torsoPath(x, flare = 0) {
  x.beginPath();
  x.moveTo(cx - 70, TOP + 30);
  x.quadraticCurveTo(cx, TOP - 10, cx + 70, TOP + 30);
  x.lineTo(cx + 88 + flare, BOT - 26 + flare);
  x.quadraticCurveTo(cx + 92 + flare, BOT + flare, cx + 60, BOT + flare);
  x.lineTo(cx - 60, BOT + flare);
  x.quadraticCurveTo(cx - 92 - flare, BOT + flare, cx - 88 - flare, BOT - 26 + flare);
  x.closePath();
}

function drawTorso(x, look) {
  torsoPath(x);
  x.fillStyle = look.shirt || "#E36B5B"; x.fill();
  x.save(); torsoPath(x); x.clip();
  if (look.stripes) { x.fillStyle = look.stripes; for (let y = TOP + 22; y < BOT - 40; y += 34) x.fillRect(cx - 120, y, 240, 16); }
  if (look.gus) { // jumper ribbing
    x.strokeStyle = "rgba(0,0,0,0.13)"; x.lineWidth = 4;
    for (let X = cx - 80; X <= cx + 80; X += 14) { x.beginPath(); x.moveTo(X, BOT - 40); x.lineTo(X, BOT); x.stroke(); }
  }
  x.fillStyle = look.pants || "#2D3047"; x.fillRect(cx - 120, BOT - 44, 240, 60);
  line(x, [[cx - 120, BOT - 44], [cx + 120, BOT - 44]], 5);
  if (look.helmet) { // armour plates
    x.fillStyle = "rgba(255,255,255,0.45)"; x.beginPath(); x.ellipse(cx + 30, TOP + 70, 20, 44, -0.3, 0, 2 * PI); x.fill();
    line(x, [[cx - 90, TOP + 110], [cx + 90, TOP + 110]], 4, "rgba(23,20,43,0.5)");
  }
  x.restore();
  torsoPath(x); x.lineWidth = 9; x.strokeStyle = INK; x.stroke();

  if (look.apron) {
    rrect(x, cx - 58, TOP + 64, 116, BOT - TOP - 44, 18); fillStroke(x, look.apron, 6);
    line(x, [[cx - 50, TOP + 66], [cx - 30, TOP + 20]], 5); line(x, [[cx + 50, TOP + 66], [cx + 30, TOP + 20]], 5);
    rrect(x, cx - 26, TOP + 120, 52, 34, 8); x.lineWidth = 5; x.stroke();
  }
  if (look.coat) {
    const coat = look.coat;
    for (const s of [-1, 1]) {
      x.beginPath();
      x.moveTo(cx + s * 22, TOP + 2);
      x.quadraticCurveTo(cx + s * 60, TOP + 6, cx + s * 74, TOP + 34);
      x.lineTo(cx + s * 100, BOT + 34);
      x.quadraticCurveTo(cx + s * 60, BOT + 42, cx + s * 6, BOT + 34);
      x.lineTo(cx + s * 6, TOP + 128);
      x.closePath(); fillStroke(x, coat, 8);
      // lapel
      x.beginPath(); x.moveTo(cx + s * 22, TOP + 2); x.lineTo(cx + s * 52, TOP + 64); x.lineTo(cx + s * 30, TOP + 70);
      x.lineTo(cx + s * 6, TOP + 128); x.lineWidth = 5; x.stroke();
    }
    x.fillStyle = INK; for (const y of [TOP + 150, TOP + 185]) { x.beginPath(); x.arc(cx + 22, y, 5, 0, 2 * PI); x.fill(); }
    if (coat === "#FFFFFF") { rrect(x, cx - 82, TOP + 130, 40, 30, 6); x.lineWidth = 5; x.stroke(); }
  }
  if (look.costume === "suit") { // tie
    x.beginPath(); x.moveTo(cx - 11, TOP + 22); x.lineTo(cx + 11, TOP + 22); x.lineTo(cx + 15, TOP + 102); x.lineTo(cx, TOP + 118);
    x.lineTo(cx - 15, TOP + 102); x.closePath(); fillStroke(x, "#D9483B", 5);
  }
  if (look.costume === "doctor") { // stethoscope
    x.lineWidth = 7; x.strokeStyle = "#3D4458"; x.beginPath(); x.moveTo(cx - 30, TOP + 16);
    x.quadraticCurveTo(cx - 40, TOP + 110, cx, TOP + 116); x.quadraticCurveTo(cx + 40, TOP + 110, cx + 30, TOP + 16); x.stroke();
    x.beginPath(); x.arc(cx, TOP + 122, 11, 0, 2 * PI); fillStroke(x, "#9AA3AF", 5);
  }
  if (look.badge) star(x, cx + 44, TOP + 74, 20, look.badge === true ? "#F2BE3A" : look.badge);
}

function star(x, X, Y, r, color) {
  x.beginPath();
  for (let i = 0; i < 10; i++) {
    const a = -PI / 2 + (i * PI) / 5, rr = i % 2 ? r * 0.45 : r;
    x.lineTo(X + Math.cos(a) * rr, Y + Math.sin(a) * rr);
  }
  x.closePath(); fillStroke(x, color, 5);
}

function drawLegs(x, legs, facing) {
  const fw = facing === "front" ? 0 : 1;
  for (const [i, [kx, ky, fx, fy]] of legs.entries()) {
    const hip = [cx + (i ? 32 : -32), BOT - 6];
    x.lineCap = "round"; x.lineWidth = 13; x.strokeStyle = INK;
    x.beginPath(); x.moveTo(...hip); x.quadraticCurveTo(cx + kx, ky, cx + fx, fy - 8); x.stroke();
    // little shoe, toe toward the facing side
    x.beginPath(); x.ellipse(cx + fx + 10 * fw, fy - 4, 26, 15, 0, 0, 2 * PI); fillStroke(x, SHOE, 5);
    x.fillStyle = "rgba(255,255,255,0.35)"; x.beginPath(); x.ellipse(cx + fx + 16 * fw, fy - 10, 9, 4, 0, 0, 2 * PI); x.fill();
  }
}

const SHOULDERS = [[cx - 60, TOP + 40], [cx + 60, TOP + 40]];
function drawArm(x, i, arm, pose) {
  const [ex, ey, hx, hy] = arm;
  x.lineCap = "round"; x.lineWidth = 13; x.strokeStyle = INK;
  x.beginPath(); x.moveTo(...SHOULDERS[i]); x.quadraticCurveTo(cx + ex, ey, cx + hx, hy); x.stroke();
  if (i === 1 && pose.finger) { // index finger along the forearm direction
    const dx = hx - ex, dy = hy - ey, n = Math.hypot(dx, dy) || 1;
    line(x, [[cx + hx, hy], [cx + hx + (dx / n) * 34, hy + (dy / n) * 34]], 12);
  }
  x.beginPath();
  if (i === 1 && pose.palm) x.ellipse(cx + hx, hy, 22, 15, -0.2, 0, 2 * PI);
  else x.arc(cx + hx, hy, pose.fists ? 19 : 17, 0, 2 * PI);
  fillStroke(x, "#FFFFFF", 7);
}

function drawHeld(x, prop, X, Y, ang = 0) {
  x.save(); x.translate(X, Y); x.rotate(ang); x.lineCap = "round"; x.lineJoin = "round";
  const stick = (y0, y1, c, w = 12) => { line(x, [[0, y0], [0, y1]], w + 8); line(x, [[0, y0], [0, y1]], w, c); };
  switch (prop) {
    case "wrench":
      stick(40, -60, "#9AA3AF", 14);
      x.beginPath(); x.arc(0, -78, 24, 0.35 * PI, 2.65 * PI); x.lineTo(-8, -98); x.lineTo(8, -98); x.closePath(); fillStroke(x, "#9AA3AF", 6);
      break;
    case "flask":
      rrect(x, -12, -100, 24, 50, 4); fillStroke(x, "#E8F4FF", 6);
      x.beginPath(); x.arc(0, -30, 36, 0, 2 * PI); fillStroke(x, "#E8F4FF", 6);
      x.save(); x.beginPath(); x.arc(0, -30, 32, 0, 2 * PI); x.clip(); x.fillStyle = "#5DD39E"; x.fillRect(-40, -34, 80, 40); x.restore();
      x.fillStyle = "#FFFFFF"; x.beginPath(); x.arc(-12, -42, 7, 0, 2 * PI); x.fill();
      break;
    case "clipboard":
      rrect(x, -44, -110, 88, 116, 8); fillStroke(x, "#B9783F", 6);
      rrect(x, -34, -96, 68, 92, 4); fillStroke(x, "#FFFFFF", 4);
      for (const y of [-78, -62, -46, -30]) line(x, [[-24, y], [24, y]], 4, "#9AA3AF");
      rrect(x, -16, -118, 32, 16, 4); fillStroke(x, "#9AA3AF", 4);
      break;
    case "sword":
      x.beginPath(); x.moveTo(-10, -30); x.lineTo(-10, -170); x.lineTo(0, -192); x.lineTo(10, -170); x.lineTo(10, -30); x.closePath();
      fillStroke(x, "#DCE3EA", 6);
      rrect(x, -36, -36, 72, 14, 6); fillStroke(x, "#F2BE3A", 5); stick(-22, 26, "#5A3B2A", 10);
      break;
    case "pitchfork":
      stick(80, -150, "#B9783F", 10);
      x.lineWidth = 8; x.strokeStyle = "#9AA3AF";
      x.beginPath(); x.moveTo(-28, -210); x.lineTo(-28, -160); x.quadraticCurveTo(0, -140, 28, -160); x.lineTo(28, -210);
      x.moveTo(0, -215); x.lineTo(0, -150); x.stroke();
      break;
    case "ladle":
      stick(30, -90, "#9AA3AF", 9);
      x.beginPath(); x.arc(0, -100, 26, 0, PI); x.closePath(); fillStroke(x, "#9AA3AF", 6);
      break;
    case "scepter":
      stick(40, -110, "#F2BE3A", 11);
      x.beginPath(); x.arc(0, -126, 20, 0, 2 * PI); fillStroke(x, "#D9483B", 6);
      x.fillStyle = "#FFFFFF"; x.beginPath(); x.arc(-6, -132, 6, 0, 2 * PI); x.fill();
      break;
    case "spyglass":
      x.rotate(PI / 2 - ang * 2);
      rrect(x, -20, -14, 120, 28, 8); fillStroke(x, "#C99A3E", 6);
      rrect(x, 80, -18, 40, 36, 6); fillStroke(x, "#8C5A2B", 6);
      break;
    case "book":
      rrect(x, -40, -70, 80, 100, 8); fillStroke(x, "#C4532F", 6);
      line(x, [[-26, -70], [-26, 30]], 5); line(x, [[-10, -40], [26, -40]], 5, "#F2BE3A");
      break;
    case "hammer":
      stick(40, -80, "#B9783F", 11);
      rrect(x, -42, -112, 84, 36, 8); fillStroke(x, "#6B7380", 6);
      break;
    default: break;
  }
  x.restore();
}

function drawHead(x) {
  x.beginPath(); x.ellipse(HX, HY, HR, HRY, 0, 0, 2 * PI); fillStroke(x, HEAD, 11);
  // soft shade on the back-lower side
  x.save(); x.beginPath(); x.ellipse(HX, HY, HR - 6, HRY - 6, 0, 0, 2 * PI); x.clip();
  x.fillStyle = "rgba(120,110,170,0.12)"; x.beginPath(); x.rect(HX - HR, HY - HRY, 2 * HR, 2 * HRY);
  x.ellipse(HX + 26, HY - 22, HR, HRY, 0, 0, 2 * PI); x.fill("evenodd");
  x.restore();
}

// brow [inner dy, outer dy] (negative = up)
const BROWS = {
  neutral: [0, 0], happy: [-10, -6], excited: [-24, -16], smug: [6, 2], sly: [10, -6], shocked: [-30, -26],
  scared: [-26, 2], sad: [-20, 6], worried: [-22, 0], angry: [18, -12], pain: [12, -8],
};

function drawFace(x, look, st) {
  const e = st.expr, f = st.facing === "front" ? 0 : 18;
  const ey = HY + 6, by = ey - 52, my = HY + 82, mx = HX + f * 1.2;
  const eyes = [HX + f - 56, HX + f + 56];
  // cheeks
  x.fillStyle = BLUSH;
  for (const X of eyes) { x.beginPath(); x.ellipse(X + (X < HX + f ? -34 : 34), HY + 54, 28, 16, 0, 0, 2 * PI); x.fill(); }
  // eyes
  const look2 = st.facing === "front" ? 0 : 5;
  for (const [k, X] of eyes.entries()) {
    const s = k ? 1 : -1;
    x.lineCap = "round";
    if (e === "pain") { line(x, [[X - 20 * -s, ey - 18], [X + 16 * -s, ey], [X - 20 * -s, ey + 18]], 11); continue; }
    if (e === "happy") { x.lineWidth = 11; x.strokeStyle = INK; x.beginPath(); x.arc(X, ey + 12, 20, PI * 1.12, PI * 1.88); x.stroke(); continue; }
    if (st.blink) { x.lineWidth = 10; x.strokeStyle = INK; x.beginPath(); x.arc(X, ey - 8, 18, PI * 0.18, PI * 0.82); x.stroke(); continue; }
    if (e === "shocked" || e === "scared") {
      x.beginPath(); x.arc(X, ey, 30, 0, 2 * PI); fillStroke(x, "#FFFFFF", 8);
      x.fillStyle = INK; x.beginPath(); x.arc(X + (e === "scared" ? 0 : look2), ey + (e === "scared" ? 6 : 0), e === "scared" ? 8 : 11, 0, 2 * PI); x.fill();
      continue;
    }
    const r = e === "excited" ? 20 : 16, px = e === "sly" ? 9 : look2;
    x.fillStyle = INK; x.beginPath(); x.ellipse(X + px, ey, r, r * 1.12, 0, 0, 2 * PI); x.fill();
    x.fillStyle = "#FFFFFF"; x.beginPath(); x.arc(X + px - r * 0.32, ey - r * 0.4, r * 0.34, 0, 2 * PI); x.fill();
    if (e === "excited") { x.beginPath(); x.arc(X + px + r * 0.35, ey + r * 0.35, r * 0.16, 0, 2 * PI); x.fill(); }
    if (e === "smug" || e === "sly") { // heavy upper lid (and a lower one for sly)
      x.fillStyle = HEAD; x.fillRect(X - 26, ey - 32, 52, 30);
      line(x, [[X - 24, ey - 3], [X + 24, ey - 3]], 9);
      if (e === "sly") { x.fillStyle = HEAD; x.fillRect(X - 26, ey + 11, 52, 20); line(x, [[X - 20, ey + 11], [X + 20, ey + 11]], 6); }
    }
  }
  // brows
  const [bi, bo] = BROWS[e];
  for (const [k, X] of eyes.entries()) {
    const s = k ? 1 : -1; // inner end is toward the face centre
    let inner = bi, outer = bo;
    if (e === "smug" && k === 0) { inner = -22; outer = -28; } // one raised brow
    line(x, [[X - s * 24, by + inner], [X + s * 26, by + outer]], 12);
  }
  // beard under the mouth
  if (look.beard) {
    const c = look.beard === true ? "#5A3B2A" : look.beard;
    x.beginPath(); x.moveTo(HX - 128, HY + 50); x.quadraticCurveTo(HX - 110, HY + 200, HX + f * 0.5, HY + 212);
    x.quadraticCurveTo(HX + 110, HY + 200, HX + 128, HY + 50); x.quadraticCurveTo(HX + 60, HY + 120, mx, my + 34);
    x.quadraticCurveTo(HX - 60, HY + 120, HX - 128, HY + 50); fillStroke(x, c, 8);
  }
  drawMouth(x, e, st.mouth, mx, my);
  if (look.mustache) {
    const c = look.mustache === true ? "#3B2A20" : look.mustache;
    x.beginPath(); x.moveTo(mx, my - 26); x.quadraticCurveTo(mx - 46, my - 46, mx - 72, my - 10); x.quadraticCurveTo(mx - 40, my - 16, mx, my - 12);
    x.quadraticCurveTo(mx + 40, my - 16, mx + 72, my - 10); x.quadraticCurveTo(mx + 46, my - 46, mx, my - 26); fillStroke(x, c, 6);
  }
  if (look.glasses === "round" || look.glasses === true) {
    for (const X of eyes) { x.beginPath(); x.arc(X, ey, 42, 0, 2 * PI); x.fillStyle = "rgba(190,225,255,0.18)"; x.fill(); x.lineWidth = 9; x.strokeStyle = INK; x.stroke(); }
    x.lineWidth = 8; x.beginPath(); x.arc((eyes[0] + eyes[1]) / 2, ey - 2, 16, PI * 1.15, PI * 1.85); x.stroke();
    line(x, [[eyes[1] + 42, ey - 6], [HX + HR - 6, ey - 14]], 7); line(x, [[eyes[0] - 42, ey - 6], [HX - HR + 6, ey - 14]], 7);
    x.lineWidth = 5; x.strokeStyle = "rgba(255,255,255,0.9)";
    for (const X of eyes) { x.beginPath(); x.arc(X, ey, 32, PI * 1.15, PI * 1.45); x.stroke(); }
  } else if (look.glasses === "square") {
    for (const X of eyes) { rrect(x, X - 40, ey - 32, 80, 64, 14); x.fillStyle = "rgba(190,225,255,0.18)"; x.fill(); x.lineWidth = 9; x.strokeStyle = INK; x.stroke(); }
    line(x, [[eyes[0] + 40, ey - 6], [eyes[1] - 40, ey - 6]], 8);
  }
  if (e === "scared") sweat(x, HX + f + 128, HY - 62);
  if (e === "angry") { // anger mark on the forehead
    x.lineWidth = 7; x.strokeStyle = "#E8413C";
    const X = HX + f + 98, Y = HY - 92;
    for (const [a, b] of [[[-14, -4], [-4, -4]], [[4, -4], [14, -4]], [[-14, 4], [-4, 4]], [[4, 4], [14, 4]]]) {
      x.beginPath(); x.moveTo(X + a[0], Y + a[1]); x.quadraticCurveTo(X, Y, X + b[0], Y + b[1]); x.stroke();
    }
  }
}

function sweat(x, X, Y) {
  x.beginPath(); x.moveTo(X, Y - 34); x.quadraticCurveTo(X + 24, Y + 2, X, Y + 12); x.quadraticCurveTo(X - 24, Y + 2, X, Y - 34);
  fillStroke(x, "#8FD8FF", 6);
  x.fillStyle = "#FFFFFF"; x.beginPath(); x.ellipse(X - 6, Y - 2, 4, 7, 0, 0, 2 * PI); x.fill();
}

function drawMouth(x, e, open, mx, my) {
  x.lineCap = "round"; x.lineJoin = "round"; x.strokeStyle = INK; x.lineWidth = 10;
  if (open > 0) { // talking: closed / open-small / open-wide by the envelope's thirds
    const w = open < 0.5 ? 24 : open < 0.9 ? 34 : 40, h = open < 0.5 ? 13 : open < 0.9 ? 28 : 40;
    const off = e === "smug" || e === "sly" ? 10 : 0;
    x.beginPath(); x.ellipse(mx + off, my + 4, w, h, 0, 0, 2 * PI); fillStroke(x, MOUTH, 8);
    if (h > 20) { x.save(); x.beginPath(); x.ellipse(mx + off, my + 4, w - 4, h - 4, 0, 0, 2 * PI); x.clip();
      x.fillStyle = TONGUE; x.beginPath(); x.ellipse(mx + off, my + 4 + h * 0.7, w * 0.7, h * 0.45, 0, 0, 2 * PI); x.fill(); x.restore(); }
    return;
  }
  x.beginPath();
  switch (e) {
    case "happy": case "excited": {
      const w = e === "excited" ? 50 : 42, d = e === "excited" ? 66 : 50;
      x.moveTo(mx - w, my - 6); x.quadraticCurveTo(mx, my - 14, mx + w, my - 6); x.quadraticCurveTo(mx + w * 0.6, my + d, mx, my + d * 0.86);
      x.quadraticCurveTo(mx - w * 0.6, my + d, mx - w, my - 6); fillStroke(x, MOUTH, 9);
      x.save(); x.clip(); x.fillStyle = TONGUE; x.beginPath(); x.ellipse(mx, my + d * 0.85, w * 0.55, d * 0.32, 0, 0, 2 * PI); x.fill(); x.restore();
      return;
    }
    case "shocked": x.ellipse(mx, my + 10, 22, 32, 0, 0, 2 * PI); fillStroke(x, MOUTH, 9); return;
    case "scared": // trembling open mouth
      x.moveTo(mx - 34, my + 8); for (let i = 1; i <= 6; i++) x.lineTo(mx - 34 + i * 11.3, my + (i % 2 ? -4 : 8));
      x.lineTo(mx + 34, my + 26); x.quadraticCurveTo(mx, my + 34, mx - 34, my + 26); x.closePath(); fillStroke(x, MOUTH, 8); return;
    case "sad": x.moveTo(mx - 34, my + 22); x.quadraticCurveTo(mx, my - 8, mx + 34, my + 22); x.stroke(); return;
    case "worried": x.moveTo(mx - 30, my + 12); for (let i = 1; i <= 4; i++) x.lineTo(mx - 30 + i * 15, my + (i % 2 ? 2 : 12)); x.stroke(); return;
    case "angry": x.moveTo(mx - 36, my + 18); x.quadraticCurveTo(mx, my, mx + 36, my + 18); x.stroke(); return;
    case "pain": // gritted teeth
      rrect(x, mx - 42, my - 6, 84, 34, 12); fillStroke(x, "#FFFFFF", 8);
      line(x, [[mx - 40, my + 11], [mx + 40, my + 11]], 5);
      for (const X of [-20, 0, 20]) line(x, [[mx + X, my - 4], [mx + X, my + 26]], 5);
      return;
    case "smug": case "sly":
      x.moveTo(mx - 30, my + 8); x.quadraticCurveTo(mx + 12, my + 24, mx + 44, my - 8); x.stroke(); return;
    default: x.moveTo(mx - 28, my + 4); x.quadraticCurveTo(mx, my + 20, mx + 28, my + 4); x.stroke();
  }
}

function drawHeadwear(x, look, st) {
  const f = st.facing === "front" ? 0 : 1, hc = look.hatColor || "#3A3346", top = HY - HRY;
  const hat = look.hat === true ? "cap" : look.hat;
  if (look.bandana) { // solid knit-edged wrap, knot and tails at the back
    const c = look.bandana === true ? "#D9483B" : look.bandana;
    x.beginPath(); x.ellipse(HX, HY - 18, HR + 6, HRY + 4, 0, PI * 1.02, PI * 1.98); x.quadraticCurveTo(HX, HY - 100, HX - HR - 5, HY - 30);
    fillStroke(x, c, 10);
    line(x, [[HX - HR + 10, HY - 52], [HX + HR - 10, HY - 52]], 5, "rgba(0,0,0,0.25)");
    const kx = HX - HR + 6; // knot on the back side
    x.beginPath(); x.ellipse(kx, HY - 48, 20, 16, 0, 0, 2 * PI); fillStroke(x, c, 7);
    for (const [dx, dy] of [[-56, 4], [-44, 40]]) {
      x.beginPath(); x.moveTo(kx - 6, HY - 52); x.quadraticCurveTo(kx + dx * 0.6, HY - 50 + dy * 0.4, kx + dx, HY - 48 + dy);
      x.lineTo(kx + dx + 16, HY - 40 + dy); x.quadraticCurveTo(kx + dx * 0.4, HY - 40, kx + 6, HY - 40); x.closePath(); fillStroke(x, c, 6);
    }
  }
  if (look.helmet) {
    const c = look.helmet === true ? "#B7C0CC" : look.helmet;
    x.beginPath(); x.ellipse(HX, HY - 6, HR + 12, HRY + 12, 0, PI * 0.88, PI * 2.12);
    x.lineTo(HX + HR - 40, HY + 70); x.lineTo(HX + HR - 40, HY - 88); x.quadraticCurveTo(HX, HY - 112, HX - HR + 40, HY - 88);
    x.lineTo(HX - HR + 40, HY + 70); x.closePath(); fillStroke(x, c, 10);
    x.fillStyle = "rgba(255,255,255,0.5)"; x.beginPath(); x.ellipse(HX - 70, HY - 120, 30, 12, -0.4, 0, 2 * PI); x.fill();
    line(x, [[HX, top - 10], [HX, HY - 108]], 5, "rgba(23,20,43,0.5)");
    // plume
    x.beginPath(); x.moveTo(HX - 10, top - 8); x.quadraticCurveTo(HX - 70, top - 90, HX - 140, top - 60);
    x.quadraticCurveTo(HX - 60, top - 40, HX + 14, top - 6); x.closePath(); fillStroke(x, "#D9483B", 7);
  }
  switch (hat) {
    case "cap":
      x.beginPath(); x.ellipse(HX, top + 66, HR - 4, 90, 0, PI, 2 * PI); x.closePath(); fillStroke(x, hc, 10);
      rrect(x, f ? HX + 20 : HX - 110, top + 50, f ? 180 : 220, 30, 15); fillStroke(x, hc, 9);
      break;
    case "sailor":
      x.beginPath(); x.ellipse(HX, top + 40, 112, 62, 0, PI, 2 * PI); x.closePath(); fillStroke(x, hc, 9);
      rrect(x, HX - 130, top + 24, 260, 36, 18); fillStroke(x, hc, 9);
      break;
    case "tricorn":
      x.beginPath(); x.moveTo(HX - 200, top + 46); x.quadraticCurveTo(HX - 110, top - 20, HX, top - 76);
      x.quadraticCurveTo(HX + 110, top - 20, HX + 200, top + 46); x.quadraticCurveTo(HX, top + 4, HX - 200, top + 46);
      fillStroke(x, hc, 10);
      line(x, [[HX - 170, top + 34], [HX, top + 0], [HX + 170, top + 34]], 6, "#F2BE3A");
      break;
    case "captain":
      x.beginPath(); x.moveTo(HX - 150, top + 6); x.quadraticCurveTo(HX, top - 70, HX + 150, top + 6); x.lineTo(HX + 120, top + 56);
      x.lineTo(HX - 120, top + 56); x.closePath(); fillStroke(x, hc, 10);
      rrect(x, HX - 124, top + 36, 248, 26, 8); fillStroke(x, "#1A1A2A", 8);
      x.beginPath(); x.ellipse(f ? HX + 70 : HX, top + 70, f ? 100 : 120, 20, f ? 0.08 : 0, 0, PI); x.closePath(); fillStroke(x, "#1A1A2A", 8);
      star(x, HX, top + 8, 18, "#F2BE3A");
      break;
    case "bowler":
      rrect(x, HX - 190, top + 40, 380, 34, 17); fillStroke(x, hc, 10);
      x.beginPath(); x.ellipse(HX, top + 44, 128, 104, 0, PI, 2 * PI); x.closePath(); fillStroke(x, hc, 10);
      break;
    case "top":
      rrect(x, HX - 180, top + 36, 360, 36, 17); fillStroke(x, hc, 10);
      rrect(x, HX - 108, top - 160, 216, 200, 14); fillStroke(x, hc, 10);
      x.fillStyle = "#D9483B"; x.fillRect(HX - 102, top - 2, 204, 30);
      break;
    case "hardhat":
      x.beginPath(); x.ellipse(HX, top + 70, HR + 6, 120, 0, PI, 2 * PI); x.closePath(); fillStroke(x, hc, 10);
      rrect(x, HX - HR - 36, top + 56, 2 * HR + 72, 28, 14); fillStroke(x, hc, 9);
      rrect(x, HX - 22, top - 52, 44, 100, 18); fillStroke(x, hc, 7);
      break;
    case "chef":
      rrect(x, HX - 116, top - 6, 232, 60, 10); fillStroke(x, hc, 9);
      for (const [dx, dy, r] of [[-80, -50, 62], [80, -50, 62], [0, -90, 72]]) { x.beginPath(); x.arc(HX + dx, top + dy, r, 0, 2 * PI); fillStroke(x, hc, 9); }
      x.fillStyle = hc; x.fillRect(HX - 108, top - 40, 216, 80);
      line(x, [[HX - 116, top - 6], [HX + 116, top - 6]], 6);
      break;
    case "straw":
      x.beginPath(); x.ellipse(HX, top + 52, 230, 38, 0, 0, 2 * PI); fillStroke(x, hc, 9);
      x.beginPath(); x.ellipse(HX, top + 40, 120, 96, 0, PI, 2 * PI); x.closePath(); fillStroke(x, hc, 9);
      x.fillStyle = "#D9483B"; x.fillRect(HX - 116, top + 16, 232, 22);
      line(x, [[HX - 117, top + 38], [HX + 117, top + 38]], 6);
      break;
    case "beret":
      x.beginPath(); x.ellipse(HX - 24, top + 20, 170, 58, -0.12, 0, 2 * PI); fillStroke(x, hc, 9);
      line(x, [[HX - 24, top - 36], [HX - 18, top - 58]], 9);
      break;
    case "beanie":
      x.beginPath(); x.ellipse(HX, top + 80, HR - 2, 112, 0, PI, 2 * PI); x.closePath(); fillStroke(x, hc, 10);
      rrect(x, HX - HR + 2, top + 54, 2 * HR - 4, 40, 16); fillStroke(x, hc, 9);
      x.beginPath(); x.arc(HX, top - 36, 22, 0, 2 * PI); fillStroke(x, hc, 8);
      break;
    default: break;
  }
  if (look.crown) {
    const c = look.crown === true ? "#F2BE3A" : look.crown;
    x.beginPath(); x.moveTo(HX - 92, top + 40);
    [[-92, -50], [-46, 0], [0, -66], [46, 0], [92, -50], [92, 40]].forEach(([dx, dy]) => x.lineTo(HX + dx, top + dy));
    x.closePath(); fillStroke(x, c, 9);
    for (const [dx, col] of [[-50, "#D9483B"], [0, "#2F6FD6"], [50, "#3E9B45"]]) { x.beginPath(); x.arc(HX + dx, top + 18, 10, 0, 2 * PI); fillStroke(x, col, 5); }
  }
  if (look.glasses === "goggles") { // pushed up on the forehead
    rrect(x, HX - HR + 4, HY - 112, 2 * HR - 8, 20, 8); fillStroke(x, "#5A3B2A", 6);
    for (const dx of [-50, 50]) { x.beginPath(); x.arc(HX + dx, HY - 102, 30, 0, 2 * PI); fillStroke(x, "#9FD8E8", 8); }
  }
}

// Gus: the question-mark curl that sprouts from the crown
function drawCurl(x, look) {
  const top = HY - HRY + 6, c = look.curl;
  const path = () => {
    x.beginPath(); x.moveTo(HX - 12, top + 4);
    x.bezierCurveTo(HX - 30, top - 60, HX + 40, top - 108, HX + 70, top - 66);
    x.bezierCurveTo(HX + 90, top - 34, HX + 50, top - 14, HX + 34, top - 40);
  };
  x.lineCap = "round";
  path(); x.lineWidth = 38; x.strokeStyle = INK; x.stroke();
  path(); x.lineWidth = 21; x.strokeStyle = c; x.stroke();
}

// Gus: knit scarf. back tail flutters behind the body; the wrap and the front tail sit over the torso
function scarfTail(x, look, t) {
  const w = Math.sin(t * 5) * 14;
  x.beginPath(); x.moveTo(cx - 40, TOP + 4);
  x.quadraticCurveTo(cx - 110, TOP + 6 + w * 0.4, cx - 168, TOP + 30 + w); x.lineTo(cx - 160, TOP + 70 + w);
  x.quadraticCurveTo(cx - 100, TOP + 46 + w * 0.4, cx - 40, TOP + 44); x.closePath(); fillStroke(x, look.scarf, 8);
  for (const k of [0.45, 0.75]) line(x, [[cx - 40 - 128 * k, TOP + 8 + 26 * k + w * k], [cx - 40 - 120 * k, TOP + 44 + 26 * k + w * k]], 6, look.scarfStripe);
}
function scarfWrap(x, look) {
  x.beginPath(); x.moveTo(cx - 92, TOP - 18); x.quadraticCurveTo(cx, TOP + 14, cx + 92, TOP - 18);
  x.quadraticCurveTo(cx + 108, TOP + 20, cx + 86, TOP + 40); x.quadraticCurveTo(cx, TOP + 66, cx - 86, TOP + 40);
  x.quadraticCurveTo(cx - 108, TOP + 20, cx - 92, TOP - 18); fillStroke(x, look.scarf, 9);
  for (const dx of [-54, -18, 18, 54]) line(x, [[cx + dx, TOP + 2 + Math.abs(dx) * -0.12], [cx + dx, TOP + 44 - Math.abs(dx) * 0.1]], 6, look.scarfStripe);
  // front tail hanging down the chest
  x.beginPath(); x.moveTo(cx + 24, TOP + 36); x.lineTo(cx + 70, TOP + 40); x.lineTo(cx + 78, TOP + 150); x.lineTo(cx + 34, TOP + 156); x.closePath();
  fillStroke(x, look.scarf, 8);
  for (const y of [TOP + 80, TOP + 118]) line(x, [[cx + 30, y + 2], [cx + 74, y - 2]], 7, look.scarfStripe);
  for (let k = 0; k < 4; k++) line(x, [[cx + 40 + k * 11, TOP + 156], [cx + 40 + k * 11, TOP + 172]], 5);
}

export function drawChar(ctx, look, st) {
  const pose = POSES[st.pose](st.t || 0);
  const legs = pose.legs || LEGS;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height); ctx.restore();
  const x = ctx;
  x.save();
  const k = x.canvas.width / CW;
  x.scale(k, k);
  if (st.facing === "left") { x.translate(CW, 0); x.scale(-1, 1); }
  x.lineJoin = "round"; x.lineCap = "round";
  if (pose.lean) { x.translate(cx, FOOT); x.rotate(pose.lean); x.translate(-cx, -FOOT); }
  const layer = (name) => pose.arms.forEach((a, i) => { if (a[4] === name) { drawArm(x, i, a, pose); held(name, i, a); } });
  const propHand = !look.prop || st.holding ? -1 : pose.both ? 2 : pose.busy ? 0 : 1;
  function held(name, i, a) {
    if (propHand === i) drawHeld(x, look.prop, cx + a[2], a[3] + 4, i ? 0.12 : -0.12);
    if (propHand === 2 && i === 1) drawHeld(x, look.prop, cx, (a[3] + pose.arms[0][3]) / 2 - 4, 0);
    if (propHand === i || (propHand === 2 && i === 1)) { // re-draw the gripping hand over the handle
      for (const j of propHand === 2 ? [0, 1] : [i]) { const b = pose.arms[j]; x.beginPath(); x.arc(cx + b[2], b[3], 17, 0, 2 * PI); fillStroke(x, "#FFFFFF", 7); }
    }
  }
  if (look.gus) scarfTail(x, look, st.t || 0);
  layer("back");
  drawLegs(x, legs, st.facing);
  drawTorso(x, look);
  layer("mid");
  drawHead(x);
  drawFace(x, look, st);
  drawHeadwear(x, look, st);
  if (look.gus) { scarfWrap(x, look); drawCurl(x, look); }
  layer("over");
  x.restore();
}

// ---------- motion ----------
const easeOutBack = (v) => { const c = 1.9; v = clamp01(v) - 1; return 1 + (c + 1) * v * v * v + c * v * v; };
const dirOf = (facing) => (facing === "left" ? -1 : 1);

export const ENTERS = {
  left: (lt) => ({ x: -6 * (1 - easeOut(lt / 0.8)), walking: lt < 0.8 }),
  right: (lt) => ({ x: 6 * (1 - easeOut(lt / 0.8)), walking: lt < 0.8 }),
  drop: (lt) => {
    const f = clamp01(lt / 0.45);
    const land = lt > 0.45 && lt < 0.65 ? Math.sin(((lt - 0.45) / 0.2) * PI) : 0;
    return { y: 5 * (1 - f * f), sy: 1 - 0.18 * land, sx: 1 + 0.14 * land };
  },
  pop: (lt) => ({ scale: Math.max(0.001, easeOutBack(lt / 0.4)) }),
};

export const MOTIONS = {
  bob: (lt, t) => ({ y: (Math.sin(t * 6) * 0.5 + 0.5) * 0.12 }),
  hop: (lt) => ({ y: Math.abs(Math.sin(lt * 7)) * 0.38 }),
  shake: (lt, t) => ({ x: Math.sin(t * 55) * 0.05 }),
  flinch: (lt, t, dir) => {
    const f = clamp01(lt / 0.4), k = Math.sin(f * PI);
    return { x: -dir * 0.3 * k, tilt: dir * 0.18 * k, sy: 1 - 0.1 * k };
  },
  run_across: (lt, t, dir) => ({ x: dir * (-4 + lt * 3.4), y: Math.abs(Math.sin(lt * 11)) * 0.08, walking: true }),
  fall_over: (lt, t, dir) => {
    const f = clamp01((lt - 0.1) / 0.45);
    const bounce = lt > 0.55 && lt < 0.8 ? Math.sin(((lt - 0.55) / 0.25) * PI) * 0.06 : 0;
    return { tilt: dir * (PI / 2) * (f * f) - dir * bounce, falling: true };
  },
  spin: (lt) => ({ spin: 2 * PI * easeIO(lt / 0.7) }),
};

// mood → sprite tint (the sprite is unlit, so it takes the light colour by hand)
export const SPRITE_TINT = { day: "#FFFFFF", interior_glow: "#FFE3C8", sunset: "#FFD9D2", night: "#9FB1DC", steel: "#E1E5EC" };

// ---------- positions for actions (actions.js) ----------
// world units per design pixel: the sprite's CH pixels span its plane height
export const UNIT = HEIGHT / (FOOT - (HY - HRY));

// spec.runs = [{t0, from, to, dur}] (run_to acts, in time order): the latest run started by t sets the position
export function runAt(runs, t) {
  let run = null;
  for (const r of runs || []) if (r.t0 <= t) run = r;
  if (!run) return null;
  const u = clamp01((t - run.t0) / run.dur);
  return { pos: run.from.map((v, k) => v + (run.to[k] - v) * u), moving: u < 1 };
}

// where the character stands at t: its spec pos, or its run (walks into a kept beat and motions not included)
export function charPosAt(spec, t) {
  const r = runAt(spec.runs, t);
  return r ? r.pos : [...(spec.pos || [0, 0, 0])];
}

// world position of the hand that holds a 3D prop: the front hand (the back one when the pose is busy, between both
// when it holds with both); x follows the facing (the sprite is drawn facing right), a little in front of the sprite.
// spec.act offsets ({x, y, sx, sy}) are included; lean and motions are not.
export function handAt(spec, t) {
  const pose = POSES[spec.pose || "idle"](t), arms = pose.arms;
  const hand = pose.both ? [(arms[0][2] + arms[1][2]) / 2, (arms[0][3] + arms[1][3]) / 2] : pose.busy ? arms[0].slice(2, 4) : arms[1].slice(2, 4);
  const dir = dirOf(spec.facing), a = spec.act || {}, [x, y, z] = charPosAt(spec, t);
  return [x + (a.x || 0) + dir * hand[0] * UNIT * (a.sx ?? 1), y + (a.y || 0) + (FOOT - hand[1]) * UNIT * (a.sy ?? 1), z + 0.12];
}

const seedOf = (id) => [...String(id)].reduce((a, ch) => a * 31 + ch.charCodeAt(0), 7) % 9973;

export class Char {
  constructor(id, look) {
    this.id = id;
    this.look = resolveLook(look);
    const seed = seedOf(id);
    this.phase = hash(seed) * 10;
    this.blinkEvery = 2.8 + hash(seed + 1) * 2.2;
    // born: first appearance (enter, visibility); beatStart: the current beat (motions restart each beat)
    this.born = 0; this.beatStart = null; this.from = null; this.moveStart = 0; this.key = ""; this.spec = null;
    // sprite plane: canvas y = FOOT sits on y = 0
    const h = HEIGHT * CH / (FOOT - (HY - HRY)), w = h * (CW / CH);
    const geom = new THREE.PlaneGeometry(w, h);
    geom.translate(0, h / 2 - h * (CH - FOOT) / CH, 0);
    this.canvas = null;
    let map = null;
    if (HAS_DOM) {
      this.canvas = document.createElement("canvas");
      this.canvas.width = CW * RES; this.canvas.height = CH * RES;
      this.ctx = this.canvas.getContext("2d");
      map = new THREE.CanvasTexture(this.canvas);
      map.colorSpace = THREE.SRGBColorSpace;
      map.anisotropy = 4;
    }
    this.tex = map;
    this.plane = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({ map, transparent: true, alphaTest: 0.05, fog: false, color: map ? "#ffffff" : INK }));
    this.plane.name = "sprite";
    this.tilt = new THREE.Group(); // rotates about the feet for fall_over / lean
    this.tilt.add(this.plane);
    const shadow = new THREE.Mesh(new THREE.CircleGeometry(w * 0.26, 24),
      new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.22, depthWrite: false }));
    shadow.rotation.x = -PI / 2; shadow.position.y = 0.02; shadow.scale.y = 0.45;
    this.shadow = shadow;
    this.group = new THREE.Group();
    this.group.name = `char:${id}`;
    this.group.add(this.tilt, shadow);
  }

  setTint(mood) { this.plane.material.color.set(this.tex ? SPRITE_TINT[mood] || "#ffffff" : INK); }

  // spec: a story chars[] entry; t: story time (s); mouth: the timeline's mouth value for this frame (0..1)
  frame(spec, t, mouth = 0) {
    const pose0 = spec.pose || "idle", expr = spec.expr || "neutral", facing = spec.facing || "right";
    if (!POSES[pose0]) throw new Error(`unknown pose: ${pose0}`);
    if (!EXPRS.includes(expr)) throw new Error(`unknown expr: ${expr}`);
    if (!FACINGS.includes(facing)) throw new Error(`unknown facing: ${facing}`);
    if (spec.motion && !MOTIONS[spec.motion]) throw new Error(`unknown motion: ${spec.motion}`);
    if (spec.enter && !ENTERS[spec.enter]) throw new Error(`unknown enter: ${spec.enter}`);
    const lt = t - this.born, dir = dirOf(facing);
    const base = spec.pos || [0, 0, 0];
    let [px, py, pz] = base;
    let walking = false;
    if (this.from) { // kept from the last beat with a new pos: walk there
      const f = clamp01((t - this.moveStart) / 0.8), e = easeIO(f);
      px = this.from[0] + (base[0] - this.from[0]) * e; py = this.from[1] + (base[1] - this.from[1]) * e;
      pz = this.from[2] + (base[2] - this.from[2]) * e; walking = f < 1;
    }
    const run = runAt(spec.runs, t); // a run_to act moves the character from its own start
    if (run) { [px, py, pz] = run.pos; walking = run.moving; }
    const m = { x: 0, y: 0, tilt: 0, spin: 0, scale: 1, sx: 1, sy: 1 };
    const add = (o) => {
      m.x += o.x || 0; m.y += o.y || 0; m.tilt += o.tilt || 0; m.spin += o.spin || 0;
      m.scale *= o.scale ?? 1; m.sx *= o.sx ?? 1; m.sy *= o.sy ?? 1;
      if (o.walking) walking = true;
      if (o.falling) m.falling = true;
    };
    if (spec.enter) add(ENTERS[spec.enter](Math.max(0, lt)));
    if (spec.motion) add(MOTIONS[spec.motion](Math.max(0, t - (spec.motionStart ?? this.beatStart ?? this.born)), t, dir));
    if (spec.act) add(spec.act); // the current act's offsets (actions.js), already for time t
    if (spec.squash) add(spec.squash); // squash & stretch from a nearby impact
    let pose = pose0;
    if (pose === "idle" && walking) pose = "run";
    if (pose === "idle" && m.falling) pose = "fall";
    if (walking) m.y += Math.abs(Math.sin(t * 11)) * 0.1;
    const talk = spec.talk ? Math.round(clamp01(mouth) * 3) / 3 : 0;
    const breathe = Math.sin(t * 3.1 + this.phase) * 0.012 + talk * 0.025;
    const state = {
      pose, expr, facing, mouth: talk, t, holding: !!spec.holding,
      blink: ((t + this.phase) % this.blinkEvery) < 0.12,
      x: px + m.x, y: py + m.y, z: pz, tilt: m.tilt + Math.sin(t * 1.6 + this.phase) * 0.02, spin: m.spin,
      scale: m.scale, sx: m.sx * (1 - breathe * 0.6), sy: m.sy * (1 + breathe), visible: lt >= 0,
    };
    // pose
    this.group.visible = state.visible;
    this.group.position.set(state.x, state.y, state.z);
    this.group.scale.setScalar(state.scale);
    this.tilt.rotation.z = state.tilt;
    this.plane.rotation.y = state.spin;
    this.plane.scale.set(state.sx, state.sy, 1);
    this.shadow.scale.set(1 / (1 + state.y * 0.4), 0.45 / (1 + state.y * 0.4), 1);
    this.shadow.position.y = 0.02 - state.y;
    // redraw only on change; animated poses and Gus's scarf tick at a capped rate and draw at their bucket's
    // time, so a frame looks the same whether it was reached by seeking or by stepping
    if (this.canvas && state.visible) {
      const rate = pose === "wave" || pose === "run" || pose === "fall" ? 15 : this.look.gus ? 10 : 0;
      const anim = rate ? Math.round(t * rate) : 0;
      const key = `${pose}|${expr}|${facing}|${talk}|${state.blink}|${anim}|${state.holding}`;
      if (key !== this.key) {
        this.draw({ ...state, t: rate ? anim / rate : 0 });
        this.key = key;
      }
    }
    return state;
  }

  draw(state) {
    drawChar(this.ctx, this.look, state);
    this.tex.needsUpdate = true;
  }

  // A beat lists this character again (kept): returns the spec to frame with. A spec without `pos` keeps the
  // last one; a new pos is walked to (0.8 s) from where the character stood when this beat started.
  keep(spec, start) {
    const prev = this.spec;
    const next = { ...spec, pos: spec.pos || (prev && prev.pos) || [0, 0, 0] };
    this.beatStart = start;
    if (prev) {
      const at = this.basePos(start);
      if (next.pos.some((v, k) => v !== at[k])) { this.from = at; this.moveStart = start; } else this.from = null;
    }
    this.spec = next;
    return next;
  }

  // the spec position (walk included, motions and enters not) at time t
  basePos(t) {
    const to = (this.spec && this.spec.pos) || [0, 0, 0];
    if (!this.from) return [...to];
    const e = easeIO(clamp01((t - this.moveStart) / 0.8));
    return to.map((v, k) => this.from[k] + (v - this.from[k]) * e);
  }

  faceCamera(camera) {
    const p = this.group.position;
    this.group.rotation.y = Math.atan2(camera.position.x - p.x, camera.position.z - p.z);
  }

  dispose() {
    this.group.traverse((k) => { if (k.geometry) k.geometry.dispose(); if (k.material) k.material.dispose(); });
    if (this.tex) this.tex.dispose();
  }
}

// Names this registry adds to studio/catalog.json.
export function catalog() {
  return {
    poses: Object.keys(POSES), exprs: [...EXPRS], motions: Object.keys(MOTIONS), enters: Object.keys(ENTERS),
    costume_keys: [...COSTUME_KEYS], costumes: Object.keys(COSTUMES), looks: ["gus"],
    hats: [...HATS], glasses: [...GLASSES], held_props: [...HELD],
  };
}
