// Gus world: sets, props, lighting moods and prop animations.
// Pure registry module: nothing touches the DOM at import time, so plain node can import it
// (catalog.js, tests). Painted textures need a canvas; without a DOM materials stay untextured.
//   buildSet({type, mood, ...opts}) -> THREE.Group   (userData.fog = the mood's THREE.Fog)
//   spawnProp(spec, t) -> THREE.Group                (userData.tick(t, spec?) poses it each frame; spec = this frame's
//                                                     event-applied copy: track / kick / hidden, see placeProp)
//   propPosAt(spec, t, now), muzzle(spec, now) / muzzleAt   positions for the camera follow and the actions
//   propFace(obj, expr)                              (cartoon face on a prop's front, +z)
// Conventions: ground at y = 0, the action stays near the origin, a prop's front faces +z,
// story rotations are degrees, a character is about 2.34 units tall (cast.CHAR_HEIGHT).
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { toonMat, inked, canvasTex, hash, clamp01, easeIO, INK } from "./core.js";

const HAS_DOM = typeof document !== "undefined";
const PI = Math.PI;
const deg = (d) => (d * PI) / 180;

// ---------- palette ----------
const C = {
  wood: "#B9783F", woodDark: "#8C5A2B", woodDeep: "#5E3A1C", hullRed: "#C4532F", sea: "#1FA3C8",
  sky: "#7CC8F2", jungle: "#3E9B45", jungleDark: "#2B7A38", jungleLight: "#62BC4E", rock: "#E3B47A",
  stone: "#CFC7B8", brick: "#C9572F", iron: "#3A3D46", steel: "#9AA3AF", gold: "#F2BE3A", rope: "#D8B47E",
  cream: "#F3E7C9", grass: "#6CC24A", sand: "#F0D9A0", fire: "#FF8A2A",
};

// ---------- moods ----------
// sky: dome gradient bottom -> (mid, optional) -> top; sun: key light (shadows); ambient: hemisphere sky/ground;
// fog: depth haze; tint: bounce fill light from the side opposite the sun (furnace orange, sunset purple, moon teal).
// Look v2 (spec §11): warm bright day; night is moonlit and readable (blue-teal sky, sets lit, not navy); sunset is
// purple over gold with the ground clearly darker and redder than the low sky. Characters are not lit by these
// (cast.SPRITE_TINT: at most a 10 % hint), so heads stay white in every mood.
export const MOODS = {
  day: {
    skyTop: "#3A96EA", skyMid: "#86C9F2", skyBottom: "#EAF4E6",
    sun: { color: "#FFEDCC", intensity: 3.0, pos: [-9, 16, 11] },
    ambient: { sky: "#F2F4EE", ground: "#C79A66", intensity: 1.3 },
    fog: { color: "#E4ECE6", near: 80, far: 440 },
    tint: { color: "#FFC583", intensity: 0.6 },
  },
  interior_glow: {
    skyTop: "#4A2414", skyBottom: "#E0813A",
    sun: { color: "#FFC27A", intensity: 1.9, pos: [7, 13, 9] },
    ambient: { sky: "#FFD0A0", ground: "#6A3218", intensity: 1.25 },
    fog: { color: "#7A3C1C", near: 50, far: 300 },
    tint: { color: "#FF7A2A", intensity: 1.2 },
  },
  sunset: {
    skyTop: "#3F2F8C", skyMid: "#B95A9C", skyBottom: "#FFC05E",
    sun: { color: "#FFB067", intensity: 2.6, pos: [12, 7, 6] },
    ambient: { sky: "#C59AE0", ground: "#5A2F52", intensity: 1.05 },
    fog: { color: "#F1A27C", near: 90, far: 460 },
    tint: { color: "#9A6BE6", intensity: 0.85 },
  },
  night: {
    skyTop: "#18346E", skyMid: "#2C6496", skyBottom: "#58AEB6",
    sun: { color: "#D2E8FF", intensity: 2.0, pos: [-8, 14, 8] },
    ambient: { sky: "#A9C8EE", ground: "#3A4C72", intensity: 1.45 },
    fog: { color: "#3F7896", near: 70, far: 420 },
    tint: { color: "#62C9D2", intensity: 0.7 },
  },
  steel: {
    skyTop: "#5E6C7C", skyBottom: "#BCC6D0",
    sun: { color: "#EEF3F8", intensity: 1.8, pos: [-6, 15, 10] },
    ambient: { sky: "#D2DBE4", ground: "#5A616C", intensity: 1.35 },
    fog: { color: "#A3AEB9", near: 40, far: 300 },
    tint: { color: "#8EA4BC", intensity: 0.6 },
  },
};

// ---------- small helpers ----------
function rng(seed) {
  let s = (seed * 2654435761) >>> 0 || 1;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}
function hexRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const rgba = (hex, a) => `rgba(${hexRgb(hex).join(",")},${a})`;
function shade(hex, k) { // k < 0 darkens, k > 0 lightens
  const c = hexRgb(hex).map((v) => Math.round(k < 0 ? v * (1 + k) : v + (255 - v) * k));
  return `rgb(${c.join(",")})`;
}

// Cached painted texture (repeat-wrapped); null without a DOM.
const texCache = new Map();
function paint(key, w, h, draw, repeat = [1, 1]) {
  if (!HAS_DOM) return null;
  let t = texCache.get(key);
  if (!t) {
    t = canvasTex(w, h, draw);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    texCache.set(key, t);
  }
  if (repeat[0] === 1 && repeat[1] === 1) return t;
  const r = t.clone();
  r.repeat.set(repeat[0], repeat[1]);
  r.needsUpdate = true;
  return r;
}
const texMat = (map, color = "#ffffff", o = {}) => (map ? toonMat(color, { map, ...o }) : toonMat(color, o));
const glowMat = (color) => new THREE.MeshBasicMaterial({ color, fog: false });

function mesh(geom, material, o = {}) {
  const m = new THREE.Mesh(geom, typeof material === "string" ? toonMat(material) : material);
  if (o.pos) m.position.set(...o.pos);
  if (o.rot) m.rotation.set(...o.rot);
  if (o.scale !== undefined) (Array.isArray(o.scale) ? m.scale.set(...o.scale) : m.scale.setScalar(o.scale));
  m.castShadow = o.cast !== false;
  m.receiveShadow = o.receive !== false;
  return o.ink ? inked(m, o.ink === true ? undefined : o.ink) : m;
}
const rbox = (w, h, d, c, o = {}) =>
  mesh(new RoundedBoxGeometry(w, h, d, 3, Math.min(o.r ?? 0.07, Math.min(w, h, d) / 2 - 0.002)), c, o);
const cyl = (rt, rb, h, c, o = {}) => mesh(new THREE.CylinderGeometry(rt, rb, h, o.seg || 22, 1, !!o.open), c, o);
const sph = (r, c, o = {}) => mesh(new THREE.SphereGeometry(r, o.seg || 22, Math.round((o.seg || 22) * 0.7)), c, o);
const lathe = (pts, c, o = {}) => mesh(new THREE.LatheGeometry(pts.map(([r, y]) => new THREE.Vector2(r, y)), o.seg || 24), c, o);
function plane(w, h, material, o = {}) {
  return mesh(new THREE.PlaneGeometry(w, h, o.sx || 1, o.sy || 1), material, { cast: false, ...o });
}
// Horizontal floor plane (top at y), w along x, d along z.
const floor = (w, d, material, o = {}) => plane(w, d, material, { rot: [-PI / 2, 0, 0], ...o });
// A stick between two points.
function beam(a, b, r, c, o = {}) {
  const A = new THREE.Vector3(...a), B = new THREE.Vector3(...b);
  const m = cyl(r, r, A.distanceTo(B), c, { seg: 8, ...o });
  m.position.copy(A).add(B).multiplyScalar(0.5);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), B.clone().sub(A).normalize());
  return m;
}
function group(...kids) {
  const g = new THREE.Group();
  kids.flat().forEach((k) => k && g.add(k));
  return g;
}
function at(obj, pos, rotY = 0, scale = 1) {
  obj.position.set(...pos);
  obj.rotation.y = rotY;
  obj.scale.setScalar(scale);
  return obj;
}

// ---------- painted textures ----------
// Look v2: surfaces are painted, not flat: each board / stone / brick has a lit top edge and a shaded lower one,
// translucent brush streaks, grain or speckle, worn light chips on its edges and soft darkening (AO) into its seams.
// Line widths scale with the canvas (k = canvas width / 512), so a texture can be painted at any size.

// translucent brush streaks inside a box: light and dark, along x (a painted, not flat, fill)
function streaks(x, R, X, Y, W, H, n, dark, k, alpha = 0.09) {
  x.lineCap = "round";
  for (let i = 0; i < n; i++) {
    const y = Y + H * (0.1 + R() * 0.8), x0 = X + R() * W * 0.5, L = W * (0.2 + R() * 0.6), ph = R() * 6;
    x.strokeStyle = rgba(R() < 0.5 ? "#FFF6E0" : dark, alpha * (0.6 + R() * 0.8));
    x.lineWidth = (3 + R() * 7) * k;
    x.beginPath();
    for (let j = 0; j <= 6; j++) x.lineTo(x0 + (L * j) / 6, y + Math.sin(j * 0.8 + ph) * 1.5 * k);
    x.stroke();
  }
}
// small light chips worn into an edge from (X, Y) along W
function chips(x, R, X, Y, W, n, k, color = "#FFF1D6", alpha = 0.45) {
  x.fillStyle = rgba(color, alpha);
  for (let i = 0; i < n; i++) {
    const cx = X + R() * W, cw = (4 + R() * 12) * k, ch = (1.5 + R() * 2.5) * k;
    x.beginPath(); x.ellipse(cx, Y, cw / 2, ch, 0, 0, 2 * PI); x.fill();
  }
}
// grit: tiny dark and light dots
function speckle(x, R, w, h, n, k, dark = "#3a2212", alpha = 0.18) {
  for (let i = 0; i < n; i++) {
    x.fillStyle = rgba(R() < 0.6 ? dark : "#FFFFFF", alpha * (0.5 + R()));
    const r = (0.8 + R() * 1.8) * k;
    x.beginPath(); x.arc(R() * w, R() * h, r, 0, 2 * PI); x.fill();
  }
}
// a box shaded top-lit: lighter top band, darker bottom band
function litBox(x, X, Y, W, H, c, top = 0.14, bottom = -0.22) {
  const g = x.createLinearGradient(0, Y, 0, Y + H);
  g.addColorStop(0, shade(c, top)); g.addColorStop(0.18, c); g.addColorStop(0.75, c); g.addColorStop(1, shade(c, bottom));
  x.fillStyle = g;
}

function drawPlanks(x, w, h, { base = C.wood, dark = C.woodDark, rows = 8, seed = 1, vertical = false } = {}) {
  const R = rng(seed);
  if (vertical) { x.translate(w, 0); x.rotate(PI / 2); [w, h] = [h, w]; }
  const bh = h / rows, k = Math.max(w, h) / 512, seam = "#3a2212";
  for (let r = 0; r < rows; r++) {
    const y0 = r * bh;
    let px = -R() * w * 0.4;
    while (px < w) {
      const len = w * (0.35 + R() * 0.45), c = shade(base, (R() - 0.5) * 0.2);
      litBox(x, px, y0, len, bh, c);
      x.fillRect(px, y0, len, bh);
      streaks(x, R, px, y0, len, bh, 7, dark, k);
      x.strokeStyle = rgba(dark, 0.55); // grain: long wavy lines, some bending round a knot
      x.lineCap = "round";
      const knotX = R() < 0.45 ? px + len * (0.2 + R() * 0.6) : null, knotY = y0 + bh * (0.35 + R() * 0.3);
      for (let g = 0; g < 4; g++) {
        const gy = y0 + bh * (0.18 + g * 0.2 + R() * 0.08), ph = R() * 6;
        x.lineWidth = (1 + R() * 1.4) * k;
        x.beginPath();
        for (let st = 0; st <= 16; st++) {
          const X = px + (len * st) / 16;
          let Y = gy + Math.sin(st * 0.7 + ph) * 1.6 * k;
          if (knotX != null) { const d = (X - knotX) / (bh * 0.9); Y += Math.sign(gy - knotY || 1) * bh * 0.16 * Math.exp(-d * d); }
          x.lineTo(X, Y);
        }
        x.stroke();
      }
      if (knotX != null) {
        x.fillStyle = rgba(seam, 0.55);
        x.beginPath(); x.ellipse(knotX, knotY, 6 * k, 3.4 * k, 0, 0, 2 * PI); x.fill();
        x.strokeStyle = rgba(dark, 0.6); x.lineWidth = 1.2 * k;
        x.beginPath(); x.ellipse(knotX, knotY, 10 * k, 5.5 * k, 0, 0, 2 * PI); x.stroke();
      }
      chips(x, R, px, y0 + 4 * k, len, 4, k); // worn top edge
      chips(x, R, px, y0 + bh - 4 * k, len, 3, k, seam, 0.35); // dented lower edge
      const ao = x.createLinearGradient(px + len - 16 * k, 0, px + len, 0); // the end butts into the next board
      ao.addColorStop(0, rgba(seam, 0)); ao.addColorStop(1, rgba(seam, 0.35));
      x.fillStyle = ao; x.fillRect(px + len - 16 * k, y0, 16 * k, bh);
      x.fillStyle = rgba(seam, 0.85);
      x.fillRect(px + len - 1.5 * k, y0, 3 * k, bh);
      for (const ny of [0.28, 0.72]) {
        x.fillStyle = rgba(seam, 0.85); x.beginPath(); x.arc(px + len - 10 * k, y0 + bh * ny, 2.8 * k, 0, 2 * PI); x.fill();
        x.fillStyle = rgba("#FFFFFF", 0.35); x.beginPath(); x.arc(px + len - 10.8 * k, y0 + bh * ny - 0.8 * k, 1 * k, 0, 2 * PI); x.fill();
      }
      px += len;
    }
    x.fillStyle = rgba(seam, 0.9); // the gap between rows, with a soft shadow under the board above
    x.fillRect(0, y0, w, 3 * k);
    const sh = x.createLinearGradient(0, y0 + 3 * k, 0, y0 + 12 * k);
    sh.addColorStop(0, rgba(seam, 0.3)); sh.addColorStop(1, rgba(seam, 0));
    x.fillStyle = sh; x.fillRect(0, y0 + 3 * k, w, 9 * k);
  }
  x.fillStyle = rgba(seam, 0.8);
  x.fillRect(0, 0, 3 * k, h);
}
function drawBricks(x, w, h, { base = C.brick, mortar = "#F0D8B8", rows = 12, cols = 4, seed = 2 } = {}) {
  const R = rng(seed), k = w / 512;
  x.fillStyle = mortar; x.fillRect(0, 0, w, h);
  speckle(x, R, w, h, 300, k, "#8A6A4A", 0.25);
  const bh = h / rows, bw = w / cols;
  for (let r = 0; r < rows; r++) for (let c = -1; c <= cols; c++) {
    const X = c * bw + (r % 2 ? bw / 2 : 0), Y = r * bh, col = shade(base, (R() - 0.5) * 0.24);
    x.fillStyle = rgba("#3a1a0a", 0.28); // shadow the brick throws on the mortar under it
    x.beginPath(); x.roundRect(X + 4 * k, Y + 6 * k, bw - 6 * k, bh - 6 * k, 5 * k); x.fill();
    litBox(x, X, Y + 3 * k, bw, bh - 6 * k, col, 0.16, -0.2);
    x.beginPath(); x.roundRect(X + 3 * k, Y + 3 * k, bw - 6 * k, bh - 6 * k, 5 * k); x.fill();
    x.save(); x.beginPath(); x.roundRect(X + 3 * k, Y + 3 * k, bw - 6 * k, bh - 6 * k, 5 * k); x.clip();
    streaks(x, R, X, Y, bw, bh, 4, "#5A1E0C", k, 0.12);
    for (let i = 0; i < 10; i++) { x.fillStyle = rgba(R() < 0.5 ? "#3a1a0a" : "#FFE2C8", 0.25); x.fillRect(X + R() * bw, Y + R() * bh, 2 * k, 2 * k); }
    x.restore();
    chips(x, R, X + 6 * k, Y + 6 * k, bw - 14 * k, 2, k, "#FFE6CC", 0.4);
  }
}
function drawFlags(x, w, h, { base = C.stone, line = "#7E7568", rows = 4, cols = 4, seed = 3, round = 14 } = {}) {
  const R = rng(seed), k = w / 512;
  x.fillStyle = line; x.fillRect(0, 0, w, h);
  const th = h / rows, tw = w / cols, rr = round * k;
  for (let r = 0; r < rows; r++) for (let c = -1; c <= cols; c++) {
    const X = c * tw + (r % 2 ? tw / 2 : 0), Y = r * th, col = shade(base, (R() - 0.5) * 0.16);
    const shape = () => { x.beginPath(); x.roundRect(X + 5 * k, Y + 5 * k, tw - 10 * k, th - 10 * k, rr); };
    litBox(x, X, Y + 5 * k, tw, th - 10 * k, col, 0.12, -0.2);
    shape(); x.fill();
    x.save(); shape(); x.clip();
    streaks(x, R, X, Y, tw, th, 5, "#5E564A", k, 0.1);
    for (let i = 0; i < 26; i++) { // grit
      x.fillStyle = rgba(R() < 0.6 ? "#4E473D" : "#FFFFFF", 0.22);
      x.beginPath(); x.arc(X + R() * tw, Y + R() * th, (0.8 + R() * 1.6) * k, 0, 2 * PI); x.fill();
    }
    if (R() < 0.4) { // a hairline crack
      x.strokeStyle = rgba("#4E473D", 0.5); x.lineWidth = 1.4 * k; x.beginPath();
      let cx = X + tw * (0.2 + R() * 0.6), cy = Y + 6 * k;
      x.moveTo(cx, cy);
      for (let i = 0; i < 5; i++) { cx += (R() - 0.5) * tw * 0.18; cy += th * 0.12; x.lineTo(cx, cy); }
      x.stroke();
    }
    const ao = x.createLinearGradient(0, Y + th - 22 * k, 0, Y + th - 5 * k); // soft dark into the joint below
    ao.addColorStop(0, rgba("#2E2820", 0)); ao.addColorStop(1, rgba("#2E2820", 0.28));
    x.fillStyle = ao; x.fillRect(X, Y + th - 22 * k, tw, 17 * k);
    x.restore();
    x.fillStyle = rgba("#FFFFFF", 0.22); // worn lit lip
    x.beginPath(); x.roundRect(X + 10 * k, Y + 8 * k, tw - 22 * k, 5 * k, 3 * k); x.fill();
    chips(x, R, X + 8 * k, Y + 8 * k, tw - 16 * k, 3, k, "#FFFFFF", 0.35);
  }
}
function drawCobbles(x, w, h, { base = "#B9AE9C", line = "#6F665A", seed = 4 } = {}) {
  const R = rng(seed), k = w / 512;
  x.fillStyle = line; x.fillRect(0, 0, w, h);
  const n = 9, s = w / n;
  for (let r = 0; r < n; r++) for (let c = -1; c <= n; c++) {
    const X = c * s + (r % 2 ? s / 2 : 0) + (R() - 0.5) * 6 * k, Y = r * s + (R() - 0.5) * 6 * k, rot = R();
    const cx = X + s / 2, cy = Y + s / 2, col = shade(base, (R() - 0.5) * 0.22);
    x.fillStyle = rgba("#2E2820", 0.35); // contact shadow
    x.beginPath(); x.ellipse(cx + 2 * k, cy + 4 * k, s * 0.45, s * 0.41, rot, 0, 2 * PI); x.fill();
    const g = x.createRadialGradient(cx - s * 0.15, cy - s * 0.18, s * 0.05, cx, cy, s * 0.5);
    g.addColorStop(0, shade(col, 0.22)); g.addColorStop(0.6, col); g.addColorStop(1, shade(col, -0.25));
    x.fillStyle = g;
    x.beginPath(); x.ellipse(cx, cy, s * 0.44, s * 0.4, rot, 0, 2 * PI); x.fill();
    for (let i = 0; i < 6; i++) { x.fillStyle = rgba(R() < 0.6 ? "#3E372E" : "#FFFFFF", 0.22); x.fillRect(cx + (R() - 0.5) * s * 0.6, cy + (R() - 0.5) * s * 0.5, 2 * k, 2 * k); }
  }
}
function drawSea(x, w, h, { base = C.sea, seed = 5 } = {}) {
  const R = rng(seed), k = w / 512;
  x.fillStyle = base; x.fillRect(0, 0, w, h);
  for (let i = 0; i < 60; i++) { // painted swells: deep and bright patches
    const deep = i % 3 === 0;
    x.fillStyle = rgba(deep ? "#0F7FA8" : i % 3 === 1 ? "#3BBEDF" : "#1694BF", deep ? 0.4 : 0.32);
    x.beginPath(); x.ellipse(R() * w, R() * h, (30 + R() * 70) * k, (8 + R() * 16) * k, (R() - 0.5) * 0.2, 0, 2 * PI); x.fill();
  }
  x.lineCap = "round";
  for (let i = 0; i < 46; i++) { // swirl strokes in a darker blue
    const X = R() * w, Y = R() * h, L = (20 + R() * 40) * k;
    x.strokeStyle = rgba("#0B6E96", 0.35); x.lineWidth = (2 + R() * 2) * k;
    x.beginPath(); x.moveTo(X - L, Y); x.bezierCurveTo(X - L / 3, Y - 8 * k, X + L / 3, Y + 8 * k, X + L, Y); x.stroke();
  }
  for (let i = 0; i < 80; i++) { // white wave arcs (the reference's little cupped crests)
    const X = R() * w, Y = R() * h, L = (8 + R() * 18) * k;
    x.strokeStyle = rgba("#E9FBFF", 0.75 + R() * 0.25); x.lineWidth = (2 + R() * 2.5) * k;
    x.beginPath(); x.moveTo(X - L, Y - 3 * k); x.quadraticCurveTo(X, Y + 6 * k, X + L, Y - 5 * k); x.stroke();
  }
}
function drawGrass(x, w, h, { base = C.grass, seed = 6, flowers = false } = {}) {
  const R = rng(seed), k = w / 512;
  x.fillStyle = base; x.fillRect(0, 0, w, h);
  for (let i = 0; i < 70; i++) {
    x.fillStyle = rgba(i % 3 === 0 ? "#3F9431" : i % 3 === 1 ? "#8BD65E" : "#5DB43F", 0.35);
    x.beginPath(); x.ellipse(R() * w, R() * h, (20 + R() * 50) * k, (12 + R() * 30) * k, R() * 3, 0, 2 * PI); x.fill();
  }
  x.lineCap = "round";
  for (let i = 0; i < 420; i++) { // tufts: a dark blade with a light one beside it
    const X = R() * w, Y = R() * h, L = (7 + R() * 7) * k, lean = (R() - 0.5) * 6 * k;
    x.strokeStyle = rgba("#2F7A27", 0.55); x.lineWidth = 2 * k;
    x.beginPath(); x.moveTo(X, Y); x.lineTo(X + lean, Y - L); x.stroke();
    if (i % 2) { x.strokeStyle = rgba("#B4EC7C", 0.5); x.beginPath(); x.moveTo(X + 3 * k, Y); x.lineTo(X + 3 * k + lean, Y - L * 0.7); x.stroke(); }
  }
  if (flowers) for (let i = 0; i < 26; i++) {
    x.fillStyle = ["#FFF6D8", "#FFD84A", "#FF8FB1"][i % 3];
    x.beginPath(); x.arc(R() * w, R() * h, (3 + R() * 2) * k, 0, 2 * PI); x.fill();
  }
}
function drawSand(x, w, h, { base = C.sand, seed = 7 } = {}) {
  const R = rng(seed), k = w / 512;
  x.fillStyle = base; x.fillRect(0, 0, w, h);
  for (let i = 0; i < 50; i++) {
    x.fillStyle = rgba(i % 2 ? "#DDB874" : "#FFF0C4", 0.4);
    x.beginPath(); x.ellipse(R() * w, R() * h, (20 + R() * 40) * k, (8 + R() * 14) * k, 0, 0, 2 * PI); x.fill();
  }
  x.lineCap = "round";
  for (let i = 0; i < 40; i++) { // wind ripples: a shaded line with a lit one above it
    const X = R() * w, Y = R() * h, L = (20 + R() * 40) * k;
    x.lineWidth = 2 * k;
    x.strokeStyle = rgba("#C49A58", 0.45);
    x.beginPath(); x.moveTo(X - L, Y); x.quadraticCurveTo(X, Y - 5 * k, X + L, Y); x.stroke();
    x.strokeStyle = rgba("#FFF6DA", 0.5);
    x.beginPath(); x.moveTo(X - L, Y - 3 * k); x.quadraticCurveTo(X, Y - 8 * k, X + L, Y - 3 * k); x.stroke();
  }
  speckle(x, R, w, h, 400, k, "#9C7A44", 0.3);
}
function drawRock(x, w, h, { base = C.rock, seed = 8 } = {}) {
  const g = x.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, shade(base, 0.1)); g.addColorStop(0.6, base); g.addColorStop(1, shade(base, -0.12));
  x.fillStyle = g; x.fillRect(0, 0, w, h);
  for (const off of [-w, 0, w]) { // same features at ±w so the texture wraps around the pillar
    x.save(); x.translate(off, 0);
    rockFeatures(x, w, h, rng(seed));
    x.restore();
  }
}
function rockFeatures(x, w, h, R) {
  for (let i = 0; i < 14; i++) { // broad light / dark vertical facets
    const X = R() * w, ww = 10 + R() * 26;
    x.fillStyle = rgba(i % 2 ? "#FFF1D2" : "#B98552", 0.22 + R() * 0.12);
    x.beginPath(); x.moveTo(X, 0);
    for (let y = 0; y <= h; y += 40) x.lineTo(X + Math.sin(y * 0.02 + i) * 6, y);
    for (let y = h; y >= 0; y -= 40) x.lineTo(X + ww + Math.sin(y * 0.025 + i) * 6, y);
    x.fill();
  }
  x.lineCap = "round";
  for (let i = 0; i < 16; i++) { // crevices
    const X = R() * w, y0 = R() * h * 0.7, L = h * (0.1 + R() * 0.35);
    x.strokeStyle = rgba("#7A5233", 0.55); x.lineWidth = 2 + R() * 2.5;
    x.beginPath(); x.moveTo(X, y0);
    for (let y = y0; y <= y0 + L; y += 18) x.lineTo(X + (R() - 0.5) * 8, y);
    x.stroke();
  }
  for (let i = 0; i < 9; i++) { // short broken ledges: a dark underside with a lit lip
    const X = R() * w, Y = h * (0.15 + R() * 0.8), L = 30 + R() * 80, ph = R() * 6;
    const lip = (dy, c, lw) => {
      x.strokeStyle = c; x.lineWidth = lw; x.beginPath();
      for (let k = 0; k <= 8; k++) x.lineTo(X + (L * k) / 8, Y + dy + Math.sin(k + ph) * 3);
      x.stroke();
    };
    lip(4, rgba("#8A5E38", 0.5), 6);
    lip(-1, rgba("#FFF4DA", 0.55), 3);
  }
  for (let i = 0; i < 34; i++) { // moss runs from the top
    const X = R() * w, L = h * (0.03 + R() * 0.12);
    x.fillStyle = i % 2 ? C.jungle : "#5DB04A";
    x.beginPath(); x.ellipse(X, L / 2, 7 + R() * 10, L / 2 + 4, 0, 0, 2 * PI); x.fill();
  }
  for (let i = 0; i < 9; i++) { // moss patches on the face
    x.fillStyle = rgba(i % 2 ? "#4E9E44" : "#6BBF52", 0.85);
    x.beginPath(); x.ellipse(R() * w, h * (0.25 + R() * 0.6), 7 + R() * 9, 4 + R() * 5, 0, 0, 2 * PI); x.fill();
  }
}
function drawStaves(x, w, h, { base = C.wood, dark = C.woodDark, n = 14, seed = 9 } = {}) {
  const R = rng(seed), sw = w / n;
  for (let i = 0; i < n; i++) {
    const g = x.createLinearGradient(i * sw, 0, (i + 1) * sw, 0), c = shade(base, (R() - 0.5) * 0.2);
    g.addColorStop(0, shade(c, 0.1)); g.addColorStop(0.5, c); g.addColorStop(1, shade(c, -0.16));
    x.fillStyle = g; x.fillRect(i * sw, 0, sw, h);
    x.strokeStyle = rgba(dark, 0.45); x.lineWidth = 1.5;
    for (let k = 0; k < 3; k++) { const X = i * sw + sw * (0.2 + R() * 0.6); x.beginPath(); x.moveTo(X, 0); x.quadraticCurveTo(X + (R() - 0.5) * 6, h / 2, X + 2, h); x.stroke(); }
    x.fillStyle = rgba("#FFF1D6", 0.3);
    for (let k = 0; k < 3; k++) x.fillRect(i * sw + 2, R() * h, sw * 0.3, 2);
    x.fillStyle = rgba("#3a2212", 0.75); x.fillRect(i * sw, 0, 2.5, h);
  }
  for (const [y0, y1] of [[0, 0.16], [1, 0.84]]) { // darker toward the rims (soft AO under the hoops and lids)
    const g = x.createLinearGradient(0, y0 * h, 0, y1 * h);
    g.addColorStop(0, rgba("#2a160a", 0.4)); g.addColorStop(1, rgba("#2a160a", 0));
    x.fillStyle = g; x.fillRect(0, Math.min(y0, y1) * h, w, Math.abs(y1 - y0) * h);
  }
}
function drawStripes(x, w, h, { a, b, n = 6, horizontal = true }) {
  for (let i = 0; i < n; i++) {
    x.fillStyle = i % 2 ? b : a;
    horizontal ? x.fillRect(0, (i * h) / n, w, h / n + 1) : x.fillRect((i * w) / n, 0, w / n + 1, h);
  }
}
function drawTiles(x, w, h, { a = "#F4F7F2", line = "#BFD8CF", n = 4 } = {}) {
  x.fillStyle = line; x.fillRect(0, 0, w, h);
  const s = w / n;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    x.fillStyle = a; x.beginPath(); x.roundRect(i * s + 3, j * s + 3, s - 6, s - 6, 6); x.fill();
    x.fillStyle = rgba("#ffffff", 0.5); x.fillRect(i * s + 8, j * s + 7, s * 0.5, 4);
  }
}
function drawChecker(x, w, h, { a = "#E9EEF2", b = "#7FA5C2", n = 4 } = {}) {
  const s = w / n;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) { x.fillStyle = (i + j) % 2 ? b : a; x.fillRect(i * s, j * s, s, s); }
}
function drawSail(x, w, h) {
  x.fillStyle = C.cream; x.fillRect(0, 0, w, h);
  x.fillStyle = rgba("#C9B68E", 0.6);
  for (let i = 1; i < 5; i++) x.fillRect((i * w) / 5 - 1, 0, 2, h);
  x.fillStyle = rgba("#ffffff", 0.35); x.fillRect(0, 0, w, h * 0.12);
  x.strokeStyle = rgba("#A8916A", 0.9); x.lineWidth = 6; x.strokeRect(3, 3, w - 6, h - 6);
}

// Textured materials (cached textures, per-use repeat).
const T = {
  planks: (rep, o = {}) => texMat(paint(`planks${JSON.stringify(o)}`, 1024, 1024, (x, w, h) => drawPlanks(x, w, h, o), rep)),
  bricks: (rep, o = {}) => texMat(paint(`bricks${JSON.stringify(o)}`, 1024, 1024, (x, w, h) => drawBricks(x, w, h, o), rep)),
  flags: (rep, o = {}) => texMat(paint(`flags${JSON.stringify(o)}`, 1024, 1024, (x, w, h) => drawFlags(x, w, h, o), rep)),
  cobbles: (rep) => texMat(paint("cobbles", 512, 512, drawCobbles, rep)),
  sea: (rep) => texMat(paint("sea", 1024, 1024, drawSea, rep)),
  grass: (rep, o = {}) => texMat(paint(`grass${JSON.stringify(o)}`, 512, 512, (x, w, h) => drawGrass(x, w, h, o), rep)),
  sand: (rep) => texMat(paint("sand", 512, 512, drawSand, rep)),
  rock: (seed) => texMat(paint(`rock${seed % 3}`, 256, 512, (x, w, h) => drawRock(x, w, h, { seed: seed % 3 + 8 }))),
  staves: (rep, o = {}) => texMat(paint(`staves${JSON.stringify(o)}`, 512, 256, (x, w, h) => drawStaves(x, w, h, o), rep)),
  stripes: (o, rep) => texMat(paint(`stripes${JSON.stringify(o)}`, 64, 256, (x, w, h) => drawStripes(x, w, h, o), rep)),
  tiles: (rep, o = {}) => texMat(paint(`tiles${JSON.stringify(o)}`, 256, 256, (x, w, h) => drawTiles(x, w, h, o), rep)),
  checker: (rep, o = {}) => texMat(paint(`checker${JSON.stringify(o)}`, 256, 256, (x, w, h) => drawChecker(x, w, h, o), rep)),
  sail: () => texMat(paint("sail", 256, 256, drawSail), HAS_DOM ? "#ffffff" : C.cream, { side: THREE.DoubleSide }),
};

// ---------- props ----------
// Each builder takes the prop spec (type, color, … extras) and returns a Group at the origin.
export const PROPS = {};
const P = PROPS;

P.cannonball = () => group(sph(0.22, "#2B2D35", { ink: true, pos: [0, 0.22, 0] }));

P.cannon = (o) => {
  const g = new THREE.Group();
  const carriage = o.color || "#D0602F";
  const barrel = lathe([[0.01, -1.15], [0.13, -1.2], [0.2, -1.12], [0.36, -1.0], [0.37, -0.75], [0.33, -0.7], [0.32, 0.2],
    [0.29, 0.25], [0.27, 0.95], [0.31, 1.0], [0.31, 1.12], [0.2, 1.14], [0.19, 1.0], [0.01, 0.98]], "#A9B2BE", { ink: true });
  barrel.rotation.z = -PI / 2 + 0.06;
  barrel.position.set(0.1, 0.92, 0);
  g.add(barrel);
  g.add(sph(0.11, "#A9B2BE", { pos: [-1.2, 0.86, 0] }));
  for (const z of [-0.33, 0.33]) {
    g.add(rbox(1.7, 0.55, 0.16, carriage, { pos: [-0.25, 0.62, z], ink: true }));
    for (const x of [-0.85, 0.45]) {
      g.add(cyl(0.3, 0.3, 0.12, C.woodDeep, { pos: [x, 0.3, z * 1.45], rot: [PI / 2, 0, 0], ink: true }));
      g.add(cyl(0.09, 0.09, 0.14, "#E3A23C", { pos: [x, 0.3, z * 1.6], rot: [PI / 2, 0, 0] }));
    }
  }
  g.add(rbox(0.25, 0.3, 0.8, carriage, { pos: [-0.95, 0.5, 0], ink: true }));
  g.add(cyl(0.06, 0.06, 1.15, C.iron, { pos: [-0.85, 0.3, 0], rot: [PI / 2, 0, 0] }));
  g.add(cyl(0.06, 0.06, 1.15, C.iron, { pos: [0.45, 0.3, 0], rot: [PI / 2, 0, 0] }));
  return g;
};

// held props (actions.js `hold`): the origin is the grip, the point that sits in the hand
P.mug = (o) => {
  const g = new THREE.Group(), c = o.color || "#E2A53C";
  g.add(cyl(0.16, 0.15, 0.36, c, { ink: true }));
  for (const y of [-0.13, 0.13]) g.add(cyl(0.165, 0.165, 0.045, "#9A6420", { pos: [0, y, 0] }));
  g.add(mesh(new THREE.TorusGeometry(0.1, 0.035, 8, 18, PI), c, { pos: [-0.16, 0, 0], rot: [0, 0, PI / 2], ink: 0.02 }));
  // a foamy top spilling over the rim
  for (const [x, z, r] of [[0, 0, 0.14], [0.08, 0.05, 0.08], [-0.07, -0.05, 0.08], [0.06, -0.08, 0.07]])
    g.add(sph(r, "#FFF6E0", { pos: [x, 0.2, z], scale: [1, 0.55, 1] }));
  return g;
};

P.pistol = () => {
  const g = new THREE.Group();
  const grip = rbox(0.11, 0.26, 0.08, C.woodDark, { pos: [-0.04, -0.08, 0], ink: 0.02 });
  grip.rotation.z = 0.35;
  g.add(grip);
  g.add(rbox(0.22, 0.09, 0.09, C.wood, { pos: [0.04, 0.05, 0], ink: 0.02 }));
  g.add(cyl(0.035, 0.04, 0.42, C.iron, { pos: [0.3, 0.07, 0], rot: [0, 0, PI / 2], ink: 0.015 }));
  g.add(cyl(0.05, 0.05, 0.04, C.gold, { pos: [0.5, 0.07, 0], rot: [0, 0, PI / 2] }));
  return g;
};

// where a prop that can `fire` shoots from, in its own frame (the barrel points along +x)
export const MUZZLES = { cannon: [1.25, 0.99, 0], pistol: [0.53, 0.07, 0] };
// height of a grip-origin prop's origin above the ground it rests on (others stand on their origin)
const GRIP_REST = { mug: 0.18, pistol: 0.06 };
export const restHeight = (spec) => (GRIP_REST[spec.type] || 0) * (spec.scale || 1);

P.barrel = (o) => {
  const g = new THREE.Group();
  const body = mesh(new THREE.LatheGeometry([[0.01, 0], [0.34, 0], [0.4, 0.2], [0.44, 0.55], [0.4, 0.9], [0.34, 1.1], [0.01, 1.1]]
    .map(([r, y]) => new THREE.Vector2(r, y)), 26), T.staves([1, 1], { base: o.color || C.wood }), { ink: true });
  g.add(body);
  for (const [y, r] of [[0.14, 0.385], [0.36, 0.43], [0.74, 0.43], [0.96, 0.385]])
    g.add(mesh(new THREE.TorusGeometry(r, 0.028, 6, 30), "#3F3B44", { pos: [0, y, 0], rot: [PI / 2, 0, 0] }));
  g.add(cyl(0.31, 0.31, 0.03, C.woodDark, { pos: [0, 1.1, 0] }));
  return g;
};

P.crate = (o) => {
  const g = new THREE.Group(), s = 0.9;
  g.add(rbox(s, s, s, T.planks([1, 1], { rows: 4, base: o.color || "#C98A4B", seed: 11 }), { pos: [0, s / 2, 0], ink: true, r: 0.04 }));
  const f = C.woodDark;
  for (const z of [-1, 1]) {
    for (const y of [0.06, s - 0.06]) g.add(rbox(s + 0.04, 0.12, 0.06, f, { pos: [0, y, (z * s) / 2] }));
    for (const x of [-1, 1]) g.add(rbox(0.12, s, 0.06, f, { pos: [(x * (s - 0.12)) / 2, s / 2, (z * s) / 2] }));
  }
  const brace = rbox(0.1, s * 1.2, 0.06, f, { pos: [0, s / 2, s / 2 + 0.01] });
  brace.rotation.z = PI / 4;
  g.add(brace);
  return g;
};

P.rope_coil = () => {
  const g = new THREE.Group();
  [[0.42, 0.06], [0.38, 0.16], [0.33, 0.26]].forEach(([r, y]) =>
    g.add(mesh(new THREE.TorusGeometry(r, 0.07, 8, 32), C.rope, { pos: [0, y, 0], rot: [PI / 2, 0, 0], ink: 0.02 })));
  g.add(beam([0.3, 0.3, 0.1], [0.75, 0.05, 0.5], 0.06, C.rope));
  return g;
};

P.lantern = (o) => {
  const g = new THREE.Group();
  g.add(cyl(0.2, 0.22, 0.08, C.iron, { pos: [0, 0.04, 0], ink: true }));
  g.add(cyl(0.15, 0.15, 0.4, o.glow === false ? "#9fb7c9" : "#FFD27A", { pos: [0, 0.3, 0], seg: 6 }));
  if (o.glow !== false) g.children[1].material = glowMat("#FFD27A");
  for (let i = 0; i < 4; i++) {
    const a = (i * PI) / 2 + PI / 4;
    g.add(cyl(0.022, 0.022, 0.42, C.iron, { pos: [Math.cos(a) * 0.17, 0.3, Math.sin(a) * 0.17], seg: 6 }));
  }
  g.add(cyl(0.04, 0.22, 0.16, C.iron, { pos: [0, 0.58, 0], ink: true }));
  g.add(mesh(new THREE.TorusGeometry(0.09, 0.02, 6, 16), C.iron, { pos: [0, 0.72, 0] }));
  if (o.glow !== false) {
    const l = new THREE.PointLight("#FFB55A", 6, 7, 1.4);
    l.position.set(0, 0.35, 0.3);
    g.add(l);
  }
  return g;
};

// Ship hull lofted from U-shaped sections; length along x (bow at +x), deck at y ~ 0.
function hullGeometry(L, W, D) {
  const n = 22, m = 12, pos = [], col = [], idx = [];
  const half = (u) => (W / 2) * Math.pow(Math.sin(PI * Math.min(1, 0.18 + u * 0.95)), 0.55) * (u > 0.97 ? 0.2 : 1);
  const top = (u) => 0.35 * Math.pow(Math.abs(u - 0.45) * 2, 2) + (u < 0.14 ? (0.14 - u) * 4 : 0);
  const depth = (u) => D * (1 - Math.pow(Math.max(0, u - 0.6) / 0.4, 2) * 0.55);
  const band = [new THREE.Color("#5E351E"), new THREE.Color("#2A2328"), new THREE.Color(C.hullRed), new THREE.Color("#F1E7CF")];
  for (let i = 0; i <= n; i++) {
    const u = i / n, x = -L / 2 + u * L, hw = Math.max(0.03, half(u)), t = top(u), d = depth(u);
    for (let j = 0; j <= m; j++) {
      const a = (PI * j) / m, s = Math.sin(a), cz = Math.cos(a);
      const y = t - d * Math.pow(s, 0.45);
      pos.push(x, y, -hw * Math.sign(cz) * Math.pow(Math.abs(cz), 0.35));
      const below = t - y;
      col.push(...(below < 0.3 ? band[0] : below < 0.75 ? band[1] : below < d * 0.92 ? band[2] : band[3]).toArray());
    }
  }
  for (let i = 0; i < n; i++) for (let j = 0; j < m; j++) {
    const a = i * (m + 1) + j, b = a + m + 1;
    idx.push(a, b, a + 1, b, b + 1, a + 1);
  }
  // transom at the stern: fan from the section centre
  const c0 = pos.length / 3;
  pos.push(-L / 2, top(0) - depth(0) * 0.5, 0); col.push(...band[0].toArray());
  for (let j = 0; j < m; j++) idx.push(c0, j, j + 1);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  return { geom: g, half, top };
}
function deckGeometry(L, half, top) {
  const n = 22, pos = [], uv = [], idx = [];
  for (let i = 0; i <= n; i++) {
    const u = i / n, x = -L / 2 + u * L, hw = Math.max(0.03, half(u)) * 0.97, y = top(u) - 0.12;
    pos.push(x, y, -hw, x, y, hw);
    uv.push(u * L * 0.35, 0, u * L * 0.35, 1);
  }
  for (let i = 0; i < n; i++) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}
function sail(w, h, bulge) {
  const geo = new THREE.PlaneGeometry(w, h, 8, 6);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const u = p.getX(i) / w + 0.5, v = p.getY(i) / h + 0.5;
    p.setZ(i, bulge * Math.sin(PI * u) * (0.55 + 0.45 * Math.sin(PI * v)));
  }
  geo.computeVertexNormals();
  return mesh(geo, T.sail(), { cast: true });
}
P.ship = (o) => {
  const L = 10, W = 2.8, D = 1.9;
  const g = new THREE.Group();
  const { geom, half, top } = hullGeometry(L, W, D);
  g.add(mesh(geom, toonMat("#ffffff", { vertexColors: true, side: THREE.DoubleSide }), { ink: 0.05 }));
  g.add(mesh(deckGeometry(L, half, top), T.planks([1, 1], { vertical: true, rows: 6 }), { cast: false }));
  for (const side of [-1, 1]) for (let k = 0; k < 7; k++) {
    const u = 0.22 + k * 0.085, x = -L / 2 + u * L, hw = half(u);
    g.add(rbox(0.32, 0.26, 0.05, "#1A1416", { pos: [x, top(u) - 0.5, side * (hw + 0.01)], rot: [0, 0, 0] }));
    g.add(rbox(0.38, 0.06, 0.06, "#E9B04A", { pos: [x, top(u) - 0.34, side * (hw + 0.02)] }));
  }
  const masts = [[-2.6, 7.2, 3], [0.4, 8.6, 3], [2.9, 6.8, 2]];
  for (const [x, h, nSails] of masts) {
    g.add(cyl(0.11, 0.15, h, C.woodDark, { pos: [x, h / 2, 0], seg: 10 }));
    for (let k = 0; k < nSails; k++) {
      const sw = 3.0 - k * 0.55, sh = 1.7 - k * 0.2, y = 1.9 + k * 1.95 + sh / 2;
      const s = sail(sw, sh, 0.45);
      s.rotation.y = PI / 2;
      s.position.set(x + 0.1, y, 0);
      g.add(s);
      g.add(cyl(0.05, 0.05, sw + 0.4, C.woodDark, { pos: [x + 0.05, y + sh / 2 + 0.05, 0], rot: [PI / 2, 0, 0], seg: 6 }));
    }
    g.add(beam([x, h, 0], [x - 0.9, top(0.5) + 0.1, half(0.5)], 0.02, "#3B2B22", { cast: false }));
    g.add(beam([x, h, 0], [x - 0.9, top(0.5) + 0.1, -half(0.5)], 0.02, "#3B2B22", { cast: false }));
  }
  const fl = P.flag({ color: o.color || "#E2483D", pole: 0 });
  fl.position.set(0.4, 8.6, 0);
  fl.scale.setScalar(0.8);
  g.add(fl);
  g.add(beam([L / 2 - 0.3, top(1) + 0.1, 0], [L / 2 + 2.2, top(1) + 1.4, 0], 0.08, C.woodDark));
  g.add(beam([L / 2 + 2.1, top(1) + 1.35, 0], [2.9, 6.6, 0], 0.02, "#3B2B22", { cast: false }));
  g.add(rbox(1.8, 0.7, W * 0.7, "#6B3A22", { pos: [-L / 2 + 1.0, top(0.05) + 0.25, 0] }));
  g.position.y = D * 0.62; // the prop's origin is the waterline
  return group(g);
};

P.lighthouse = () => {
  const g = new THREE.Group();
  const stripes = T.stripes({ a: "#F4F1EA", b: "#E0463C", n: 6 });
  g.add(mesh(new THREE.LatheGeometry([[1.25, 0], [1.2, 0.3], [0.85, 6.6], [0.8, 6.8]].map(([r, y]) => new THREE.Vector2(r, y)), 28),
    stripes, { ink: 0.05 }));
  g.add(cyl(1.3, 1.45, 0.5, "#9D9387", { pos: [0, 0.2, 0] }));
  g.add(cyl(1.15, 1.15, 0.18, "#2E3440", { pos: [0, 6.85, 0] }));
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * 2 * PI;
    g.add(cyl(0.025, 0.025, 0.45, "#2E3440", { pos: [Math.cos(a) * 1.08, 7.15, Math.sin(a) * 1.08], seg: 4 }));
  }
  g.add(mesh(new THREE.TorusGeometry(1.08, 0.035, 6, 32), "#2E3440", { pos: [0, 7.38, 0], rot: [PI / 2, 0, 0] }));
  g.add(cyl(0.62, 0.62, 0.95, "#FFE58A", { pos: [0, 7.45, 0] }));
  g.children[g.children.length - 1].material = glowMat("#FFE27A");
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * 2 * PI;
    g.add(cyl(0.035, 0.035, 0.95, "#2E3440", { pos: [Math.cos(a) * 0.63, 7.45, Math.sin(a) * 0.63], seg: 4 }));
  }
  g.add(cyl(0.05, 0.85, 0.75, "#D2463C", { pos: [0, 8.3, 0], ink: 0.05 }));
  g.add(sph(0.12, "#2E3440", { pos: [0, 8.72, 0] }));
  g.add(rbox(0.5, 0.9, 0.1, "#3A6EA5", { pos: [0, 0.8, 1.18] }));
  return g;
};

// a lighthouse's Fresnel lens: a beehive of stacked glass prism rings on a brass drum, a glowing lamp at its core
// (about 1.9 tall; o.glow === false leaves the lamp dark). Pair it with the `beam` FX at [0, 1.05, 0] above its origin.
P.fresnel_lens = (o) => {
  const g = new THREE.Group(), brass = "#A87A2C", lit = o.glow !== false;
  g.add(cyl(0.62, 0.7, 0.22, brass, { pos: [0, 0.11, 0], ink: true }));
  g.add(cyl(0.5, 0.56, 0.12, shade(brass, -0.2), { pos: [0, 0.28, 0] }));
  // cyan prism glass, lit a little from inside; the rings round the lamp catch its light
  const glass = toonMat("#8FDDF2", { transparent: true, opacity: 0.62, emissive: new THREE.Color(lit ? "#2F7F9A" : "#000000") });
  const rim = toonMat(lit ? "#FFE9A6" : "#E9FBFF", { transparent: true, opacity: 0.9 });
  const core = 1.05, n = 11; // rings bulge out at the lamp's height and close in at the top and bottom
  for (let i = 0; i < n; i++) {
    const u = i / (n - 1), y = 0.38 + u * 1.32, r = 0.24 + 0.36 * Math.sin(PI * (0.08 + 0.84 * u));
    const ring = mesh(new THREE.TorusGeometry(r, 0.065, 8, 40), Math.abs(y - core) < 0.2 ? rim : glass,
      { pos: [0, y, 0], rot: [PI / 2, 0, 0], scale: [1, 1, 1.6], cast: false, ink: 0.015 });
    g.add(ring);
  }
  g.add(cyl(0.5, 0.5, 0.3, toonMat("#CFF3FB", { transparent: true, opacity: 0.3, depthWrite: false }),
    { pos: [0, core, 0], cast: false, seg: 28 })); // the bull's-eye drum
  for (let i = 0; i < 8; i++) { // brass frame ribs
    const a = (i / 8) * 2 * PI;
    g.add(beam([Math.cos(a) * 0.3, 0.36, Math.sin(a) * 0.3], [Math.cos(a) * 0.62, core, Math.sin(a) * 0.62], 0.018, brass, { cast: false }));
    g.add(beam([Math.cos(a) * 0.62, core, Math.sin(a) * 0.62], [Math.cos(a) * 0.26, 1.72, Math.sin(a) * 0.26], 0.018, brass, { cast: false }));
  }
  g.add(cyl(0.12, 0.26, 0.12, brass, { pos: [0, 1.78, 0], ink: true }));
  g.add(sph(0.07, shade(brass, 0.2), { pos: [0, 1.88, 0] }));
  const lamp = sph(0.16, lit ? glowMat("#FFF6C8") : "#9FB7C9", { pos: [0, core, 0], cast: false });
  g.add(lamp);
  if (lit) {
    const halo = sph(0.26, new THREE.MeshBasicMaterial({ color: "#FFD86A", transparent: true, opacity: 0.4, depthWrite: false, fog: false }),
      { pos: [0, core, 0], cast: false });
    g.add(halo);
    const l = new THREE.PointLight("#FFE29A", 3, 6, 1.3); // inside the glass: it lights the room, not the rings' fronts
    l.position.set(0, core, 0);
    g.add(l);
  }
  return g;
};

P.sign_post = (o) => {
  const g = new THREE.Group();
  g.add(rbox(0.16, 2.4, 0.16, C.woodDark, { pos: [0, 1.2, 0], ink: true }));
  const arrow = (y, dir, c) => {
    const s = new THREE.Shape();
    s.moveTo(-0.55, -0.18); s.lineTo(0.38, -0.18); s.lineTo(0.6, 0); s.lineTo(0.38, 0.18); s.lineTo(-0.55, 0.18); s.closePath();
    const m = mesh(new THREE.ExtrudeGeometry(s, { depth: 0.07, bevelEnabled: true, bevelSize: 0.025, bevelThickness: 0.02, bevelSegments: 2 }),
      c, { pos: [dir * 0.42, y, 0.08], ink: true });
    m.rotation.y = dir < 0 ? PI : 0;
    if (dir < 0) m.position.z = 0.15;
    return m;
  };
  g.add(arrow(2.05, 1, o.color || C.wood), arrow(1.6, -1, "#C98A4B"));
  return g;
};

P.table = (o) => {
  const g = new THREE.Group(), w = o.w || 2, d = o.d || 1.1, c = o.color || C.wood;
  g.add(rbox(w, 0.16, d, T.planks([1, 1], { rows: 3, base: c, seed: 12 }), { pos: [0, 0.92, 0], ink: true }));
  for (const [a, b] of [[-1, -1], [1, -1], [-1, 1], [1, 1]])
    g.add(rbox(0.14, 0.86, 0.14, C.woodDark, { pos: [a * (w / 2 - 0.16), 0.43, b * (d / 2 - 0.14)], ink: 0.02 }));
  return g;
};

P.chair = (o) => {
  const g = new THREE.Group(), c = o.color || C.wood;
  g.add(rbox(0.7, 0.12, 0.66, c, { pos: [0, 0.55, 0], ink: true }));
  g.add(rbox(0.7, 0.8, 0.1, c, { pos: [0, 1.0, -0.3], ink: true }));
  for (const [a, b] of [[-1, -1], [1, -1], [-1, 1], [1, 1]])
    g.add(rbox(0.1, 0.55, 0.1, C.woodDark, { pos: [a * 0.28, 0.27, b * 0.26] }));
  return g;
};

P.bed = (o) => {
  const g = new THREE.Group(), c = o.color || "#3E7FD6";
  g.add(rbox(1.4, 0.35, 2.4, C.woodDark, { pos: [0, 0.3, 0], ink: true }));
  g.add(rbox(1.5, 1.2, 0.16, C.wood, { pos: [0, 0.6, -1.2], ink: true }));
  g.add(rbox(1.5, 0.7, 0.14, C.wood, { pos: [0, 0.35, 1.2] }));
  g.add(rbox(1.3, 0.22, 2.25, "#FBF6EC", { pos: [0, 0.58, 0], r: 0.1 }));
  g.add(rbox(1.36, 0.16, 1.5, c, { pos: [0, 0.68, 0.4], r: 0.08, ink: 0.02 }));
  g.add(rbox(0.9, 0.2, 0.45, "#FFFFFF", { pos: [0, 0.78, -0.82], r: 0.09 }));
  return g;
};

P.door = (o) => {
  const g = new THREE.Group();
  g.add(rbox(1.2, 2.3, 0.12, T.planks([1, 1], { rows: 4, vertical: true, base: o.color || C.wood, seed: 13 }), { pos: [0, 1.15, 0], ink: true }));
  g.add(rbox(0.16, 2.5, 0.22, C.woodDeep, { pos: [-0.68, 1.25, 0] }));
  g.add(rbox(0.16, 2.5, 0.22, C.woodDeep, { pos: [0.68, 1.25, 0] }));
  g.add(rbox(1.52, 0.18, 0.22, C.woodDeep, { pos: [0, 2.42, 0] }));
  for (const y of [0.45, 1.85]) g.add(rbox(0.7, 0.08, 0.04, C.iron, { pos: [-0.2, y, 0.08] }));
  g.add(sph(0.07, C.gold, { pos: [0.4, 1.1, 0.1] }));
  return g;
};

P.bell = () => {
  const g = new THREE.Group();
  g.add(lathe([[0.01, 0], [0.48, 0], [0.5, 0.06], [0.4, 0.2], [0.3, 0.55], [0.28, 0.75], [0.15, 0.82], [0.01, 0.84]], "#E0A93E",
    { ink: true, pos: [0, 1.25, 0] }));
  g.add(mesh(new THREE.TorusGeometry(0.1, 0.035, 6, 16), "#B7822C", { pos: [0, 2.13, 0] }));
  g.add(sph(0.09, "#6B4A1E", { pos: [0, 1.2, 0] }));
  g.add(rbox(1.6, 0.18, 0.18, C.woodDark, { pos: [0, 2.28, 0], ink: true }));
  for (const x of [-0.72, 0.72]) g.add(rbox(0.16, 2.35, 0.16, C.woodDark, { pos: [x, 1.17, 0], ink: true }));
  return g;
};

P.coffin = (o) => {
  const s = new THREE.Shape();
  s.moveTo(-0.3, -1.05); s.lineTo(0.3, -1.05); s.lineTo(0.48, 0.5); s.lineTo(0.32, 1.05); s.lineTo(-0.32, 1.05); s.lineTo(-0.48, 0.5); s.closePath();
  const g = new THREE.Group();
  const body = mesh(new THREE.ExtrudeGeometry(s, { depth: 0.42, bevelEnabled: true, bevelSize: 0.04, bevelThickness: 0.04, bevelSegments: 2 }),
    o.color || "#6E4224", { ink: true, rot: [-PI / 2, 0, 0], pos: [0, 0.04, 0] });
  g.add(body);
  const lid = mesh(new THREE.ExtrudeGeometry(s, { depth: 0.08, bevelEnabled: true, bevelSize: 0.03, bevelThickness: 0.02, bevelSegments: 2 }),
    "#8A5631", { rot: [-PI / 2, 0, 0], pos: [0, 0.5, 0], scale: [0.92, 0.95, 1] });
  g.add(lid);
  for (const x of [-0.5, 0.5]) g.add(rbox(0.06, 0.08, 0.4, C.gold, { pos: [x * 0.98, 0.25, 0.1] }));
  return g;
};

P.jar = (o) => {
  const g = new THREE.Group();
  g.add(cyl(0.24, 0.26, 0.42, o.color || "#E9A23B", { pos: [0, 0.23, 0] }));
  const glass = new THREE.MeshToonMaterial({ color: "#CFEFFF", transparent: true, opacity: 0.45, depthWrite: false });
  g.add(mesh(new THREE.LatheGeometry([[0.01, 0], [0.3, 0], [0.32, 0.08], [0.32, 0.6], [0.24, 0.7], [0.22, 0.78], [0.01, 0.78]]
    .map(([r, y]) => new THREE.Vector2(r, y)), 24), glass, { cast: false }));
  g.add(cyl(0.25, 0.25, 0.14, "#C88E52", { pos: [0, 0.82, 0], ink: true }));
  return g;
};

P.coin = () => {
  const g = new THREE.Group();
  g.add(cyl(0.32, 0.32, 0.08, C.gold, { rot: [PI / 2, 0, 0], pos: [0, 0.32, 0], seg: 28, ink: 0.025 }));
  g.add(mesh(new THREE.TorusGeometry(0.28, 0.025, 6, 28), "#D99A22", { pos: [0, 0.32, 0.045] }));
  g.add(cyl(0.14, 0.14, 0.03, "#FFD86A", { rot: [PI / 2, 0, 0], pos: [0, 0.32, 0.05], seg: 20 }));
  return g;
};

P.lever = (o) => {
  const g = new THREE.Group();
  g.add(rbox(0.9, 0.3, 0.6, "#6E7684", { pos: [0, 0.15, 0], ink: true }));
  g.add(rbox(0.12, 0.06, 0.5, "#2A2E36", { pos: [0, 0.31, 0] }));
  const arm = new THREE.Group();
  arm.add(cyl(0.05, 0.05, 1.1, "#9AA3AF", { pos: [0, 0.55, 0], seg: 10, ink: 0.02 }));
  arm.add(sph(0.13, o.color || "#E2483D", { pos: [0, 1.12, 0], ink: true }));
  arm.position.set(0, 0.3, 0);
  arm.rotation.z = -0.55;
  g.add(arm);
  return g;
};

P.gear = (o) => {
  const teeth = o.teeth || 10, R1 = 0.6, R2 = 0.76, s = new THREE.Shape();
  for (let i = 0; i < teeth; i++) {
    const a0 = (i / teeth) * 2 * PI, da = (2 * PI) / teeth;
    const pts = [[R1, a0], [R2, a0 + da * 0.12], [R2, a0 + da * 0.45], [R1, a0 + da * 0.57]];
    pts.forEach(([r, a], k) => (i === 0 && k === 0 ? s.moveTo(r * Math.cos(a), r * Math.sin(a)) : s.lineTo(r * Math.cos(a), r * Math.sin(a))));
  }
  s.closePath();
  const hole = new THREE.Path();
  hole.absarc(0, 0, 0.18, 0, 2 * PI, true);
  s.holes.push(hole);
  const g = new THREE.Group();
  const m = mesh(new THREE.ExtrudeGeometry(s, { depth: 0.18, bevelEnabled: true, bevelSize: 0.03, bevelThickness: 0.03, bevelSegments: 2, curveSegments: 6 }),
    o.color || "#C9A34A", { ink: true });
  m.position.set(0, R2 + 0.03, -0.09);
  g.add(m);
  for (let i = 0; i < 4; i++) {
    const a = (i / 4) * 2 * PI + PI / 4;
    g.add(sph(0.06, shade(o.color || "#C9A34A", -0.25), { pos: [Math.cos(a) * 0.38, R2 + 0.03 + Math.sin(a) * 0.38, 0.12], seg: 8 }));
  }
  return g;
};

P.rail = (o) => {
  const g = new THREE.Group(), len = o.len || 10;
  g.add(rbox(len, 0.14, 1.9, "#9C8E7C", { pos: [0, 0.07, 0], cast: false }));
  for (let x = -len / 2 + 0.3; x < len / 2; x += 0.65) g.add(rbox(0.28, 0.1, 1.6, C.woodDark, { pos: [x, 0.17, 0], cast: false }));
  for (const z of [-0.5, 0.5]) g.add(rbox(len, 0.1, 0.09, "#A7AFBA", { pos: [0, 0.27, z], ink: 0.02 }));
  return g;
};

P.train_car = (o) => {
  const g = new THREE.Group(), c = o.color || "#2E8B57";
  g.add(rbox(3.2, 1.4, 1.5, c, { pos: [0, 1.35, 0], ink: true, r: 0.14 }));
  g.add(mesh(new THREE.CylinderGeometry(0.85, 0.85, 3.3, 24, 1, false, 0, PI), "#3B3F4A", { rot: [0, 0, PI / 2], pos: [0, 2.02, 0], scale: [0.4, 1, 0.95], ink: true }));
  g.add(rbox(3.0, 0.12, 1.55, "#F2E3BE", { pos: [0, 1.85, 0] }));
  for (const x of [-1.05, 0, 1.05]) for (const z of [-1, 1]) {
    g.add(rbox(0.62, 0.55, 0.06, "#F8F1DC", { pos: [x, 1.5, z * 0.76] }));
    g.add(rbox(0.5, 0.43, 0.07, "#6EC3F0", { pos: [x, 1.5, z * 0.77] }));
  }
  g.add(rbox(3.0, 0.3, 1.1, "#2A2D35", { pos: [0, 0.55, 0] }));
  for (const x of [-1.05, 1.05]) for (const z of [-0.5, 0.5]) {
    g.add(cyl(0.3, 0.3, 0.12, "#2A2D35", { pos: [x, 0.62, z * 1.02], rot: [PI / 2, 0, 0], ink: true }));
    g.add(cyl(0.12, 0.12, 0.14, "#C9CED6", { pos: [x, 0.62, z * 1.06], rot: [PI / 2, 0, 0] }));
  }
  for (const x of [-1.75, 1.75]) g.add(rbox(0.3, 0.16, 0.3, "#2A2D35", { pos: [x, 0.7, 0] }));
  return g;
};

P.flag = (o) => {
  const g = new THREE.Group(), c = o.color || "#E2483D";
  const pole = o.pole ?? 3.2;
  if (pole) {
    g.add(cyl(0.05, 0.06, pole, C.woodDark, { pos: [0, pole / 2, 0], seg: 10, ink: 0.02 }));
    g.add(sph(0.09, C.gold, { pos: [0, pole + 0.05, 0] }));
  }
  const geo = new THREE.PlaneGeometry(1.4, 0.9, 10, 4);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) { const u = p.getX(i) / 1.4 + 0.5; p.setZ(i, Math.sin(u * 5.5) * 0.12 * u); p.setY(i, p.getY(i) - u * 0.08); }
  geo.computeVertexNormals();
  g.add(mesh(geo, toonMat(c, { side: THREE.DoubleSide }), { pos: [0.72, (pole || 0) - 0.5, 0] }));
  return g;
};

function flame(scale = 1) {
  const g = new THREE.Group();
  const outer = mesh(new THREE.SphereGeometry(0.2, 14, 10), glowMat("#FF8A2A"), { cast: false, scale: [1, 1.7, 1] });
  outer.position.y = 0.2;
  const inner = mesh(new THREE.SphereGeometry(0.12, 12, 8), glowMat("#FFE07A"), { cast: false, scale: [1, 1.6, 1] });
  inner.position.set(0, 0.14, 0.06);
  g.add(outer, inner);
  g.scale.setScalar(scale);
  g.userData.flame = true;
  return g;
}
P.torch = () => {
  const g = new THREE.Group();
  g.add(cyl(0.07, 0.05, 1.5, C.woodDark, { pos: [0, 0.75, 0], seg: 10, ink: 0.02 }));
  g.add(cyl(0.2, 0.1, 0.25, C.iron, { pos: [0, 1.6, 0], ink: true }));
  const f = flame(1.1);
  f.position.y = 1.68;
  g.add(f);
  const l = new THREE.PointLight("#FF9A40", 7, 8, 1.4);
  l.position.set(0, 2.0, 0.3);
  g.add(l);
  return g;
};

P.tongs = () => {
  const g = new THREE.Group();
  for (const s of [-1, 1]) {
    const arm = new THREE.Group();
    arm.add(rbox(0.06, 1.5, 0.05, "#3A3D46", { pos: [0, 0.75, 0], ink: 0.015 }));
    arm.add(rbox(0.16, 0.06, 0.05, "#3A3D46", { pos: [s * 0.06, 0.02, 0] }));
    arm.rotation.z = s * 0.1;
    arm.position.x = s * 0.04;
    g.add(arm);
  }
  g.add(cyl(0.05, 0.05, 0.12, C.steel, { pos: [0, 0.55, 0], rot: [PI / 2, 0, 0], seg: 8 }));
  g.position.y = 0.05;
  return group(g);
};

P.furnace = (o) => {
  const g = new THREE.Group();
  const brick = T.bricks([2, 1.4], { base: o.color || C.brick });
  g.add(rbox(3.2, 2.4, 2.2, brick, { pos: [0, 1.2, 0], ink: true, r: 0.12 }));
  const dome = mesh(new THREE.SphereGeometry(1.6, 24, 12, 0, 2 * PI, 0, PI / 2), T.bricks([3, 1], { base: o.color || C.brick }),
    { pos: [0, 2.35, 0], scale: [1, 0.7, 0.7], ink: true });
  g.add(dome);
  g.add(rbox(0.8, 3.8, 0.8, T.bricks([1, 3], { base: shade(o.color || C.brick, -0.12) }), { pos: [0.6, 4.2, -0.3], ink: true }));
  g.add(rbox(1.0, 0.25, 1.0, "#5E3B2C", { pos: [0.6, 6.1, -0.3] }));
  // arched mouth: dark frame, then the glowing fire bed
  const arch = new THREE.Shape();
  arch.moveTo(-0.85, 0); arch.lineTo(0.85, 0); arch.lineTo(0.85, 0.75); arch.absarc(0, 0.75, 0.85, 0, PI, false); arch.closePath();
  const frame = mesh(new THREE.ShapeGeometry(arch, 16), "#3B2A26", { pos: [0, 0.45, 1.11], scale: 1.12, cast: false });
  g.add(frame);
  const fire = mesh(new THREE.ShapeGeometry(arch, 16), glowMat("#FF7A1F"), { pos: [0, 0.5, 1.12], cast: false });
  g.add(fire);
  const core = mesh(new THREE.ShapeGeometry(arch, 16), glowMat("#FFD45A"), { pos: [0, 0.5, 1.13], scale: [0.7, 0.55, 1], cast: false });
  g.add(core);
  for (let i = 0; i < 5; i++) {
    const f = flame(0.9 + hash(i) * 0.6);
    f.position.set(-0.5 + i * 0.25, 0.55, 1.05);
    g.add(f);
  }
  g.add(rbox(2.0, 0.18, 0.35, "#5E3B2C", { pos: [0, 0.38, 1.2] }));
  const l = new THREE.PointLight(C.fire, 30, 14, 1.3);
  l.position.set(0, 1.2, 2.2);
  g.add(l);
  return g;
};

// The recurring "Gus world" backdrop: a tall rock pillar with a jungle top.
function pillarRock({ h = 30, r = 5, seed = 1, waterfall = false } = {}) {
  const g = new THREE.Group();
  const prof = [[1.35, 0], [1.18, 0.06], [1.0, 0.2], [0.88, 0.4], [0.92, 0.55], [1.02, 0.72], [0.9, 0.86], [1.04, 0.96], [1.0, 1.0], [0.5, 1.02], [0.01, 1.03]];
  const geo = new THREE.LatheGeometry(prof.map(([k, y]) => new THREE.Vector2(k * r, y * h)), 18, 0, 2 * PI);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const X = p.getX(i), Z = p.getZ(i), Y = p.getY(i), a = Math.atan2(Z, X);
    const v = Y / h;
    const k = 1 + 0.11 * Math.sin(3 * a + seed * 1.7 + v * 4) + 0.07 * Math.sin(5 * a - seed + v * 9) + 0.05 * Math.sin(2 * a + v * 13 + seed);
    p.setX(i, X * k); p.setZ(i, Z * k);
  }
  geo.computeVertexNormals();
  g.add(mesh(geo, T.rock(seed), { cast: false }));
  const R = rng(seed + 40);
  const greens = [C.jungle, C.jungleDark, C.jungleLight];
  for (let i = 0; i < 15; i++) { // canopy overhanging the rim
    const a = (i / 10) * 2 * PI + R() * 0.4, rr = i < 10 ? r * (0.85 + R() * 0.3) : r * R() * 0.45, s = r * (0.4 + R() * 0.25);
    g.add(sph(s, greens[i % 3], { pos: [Math.cos(a) * rr, h * 1.0 + s * 0.2 + (i >= 10 ? s * 0.45 : -s * 0.15), Math.sin(a) * rr], scale: [1, 0.72, 1], seg: 14, cast: false }));
  }
  for (let i = 0; i < 3; i++) { // bushes on ledges
    const a = R() * 2 * PI, y = h * (0.35 + R() * 0.4), s = r * 0.2;
    g.add(sph(s, greens[i % 3], { pos: [Math.cos(a) * r * 0.98, y, Math.sin(a) * r * 0.98], scale: [1.4, 0.7, 1.4], seg: 10, cast: false }));
  }
  if (waterfall) {
    const map = paint("waterfall", 64, 256, (x, w, H) => {
      x.fillStyle = "#EAF8FF"; x.fillRect(0, 0, w, H);
      const Rw = rng(3);
      for (let i = 0; i < 12; i++) { x.fillStyle = rgba("#8FD3F0", 0.6); x.fillRect(Rw() * w, Rw() * H * 0.5, 2 + Rw() * 3, H * (0.3 + Rw() * 0.5)); }
    });
    const wf = plane(r * 0.45, h * 0.98, new THREE.MeshBasicMaterial({ color: "#ffffff", map, fog: true }), { pos: [0, h * 0.5, r * 1.08] });
    g.add(wf);
    for (let i = 0; i < 5; i++) g.add(sph(r * 0.22, "#FFFFFF", { pos: [(i - 2) * r * 0.2, r * 0.05, r * 1.15], seg: 10, cast: false, scale: [1, 0.6, 1] }));
  }
  return g;
}
P.pillar_rock = (o) => pillarRock({ h: o.h || 14, r: o.r || 2.4, seed: o.seed || 3, waterfall: !!o.waterfall });

P.palm = (o) => {
  const g = new THREE.Group(), h = o.h || 4.2, R = rng(o.seed || 5);
  let x = 0, y = 0;
  const segs = 7;
  for (let i = 0; i < segs; i++) {
    const nx = x + 0.07 * i, ny = y + h / segs;
    const s = cyl(0.17 - i * 0.012, 0.2 - i * 0.012, h / segs + 0.05, i % 2 ? "#9C6B3E" : "#B07D4A", { seg: 10 });
    s.position.set((x + nx) / 2, (y + ny) / 2, 0);
    s.rotation.z = -0.07 * 1.2;
    g.add(s);
    x = nx; y = ny;
  }
  const leaf = new THREE.Shape();
  leaf.moveTo(0, 0); leaf.quadraticCurveTo(0.9, 0.35, 2.0, 0.02); leaf.quadraticCurveTo(0.9, -0.35, 0, 0);
  for (let i = 0; i < 8; i++) {
    const geo = new THREE.ShapeGeometry(leaf, 10);
    const p = geo.attributes.position;
    for (let k = 0; k < p.count; k++) { const lx = p.getX(k); p.setZ(k, p.getY(k)); p.setY(k, -0.32 * lx * lx); }
    geo.computeVertexNormals();
    const m = mesh(geo, toonMat(i % 2 ? C.jungle : C.jungleLight, { side: THREE.DoubleSide }), { cast: true });
    m.rotation.y = (i / 8) * 2 * PI + R() * 0.3;
    m.position.set(x, y, 0);
    g.add(m);
  }
  for (let i = 0; i < 3; i++) g.add(sph(0.14, "#6B4A2A", { pos: [x + Math.cos(i * 2.1) * 0.18, y - 0.15, Math.sin(i * 2.1) * 0.18], seg: 10 }));
  return g;
};

P.cloud = (o) => {
  const g = new THREE.Group(), R = rng(o.seed || 2);
  const m = toonMat("#FFFFFF", { fog: false });
  const puffs = [[0, 0, 0, 1], [1.05, -0.2, 0.1, 0.78], [-1.05, -0.22, 0, 0.75], [0.45, 0.5, 0, 0.72], [-0.5, 0.42, 0.1, 0.62], [1.8, -0.35, 0, 0.5], [-1.75, -0.38, 0, 0.48]];
  for (const [x, y, z, r] of puffs) g.add(mesh(new THREE.SphereGeometry(r * (0.9 + R() * 0.2), 16, 12), m, { pos: [x, y, z], cast: false, scale: [1, 0.86, 0.8] }));
  return g;
};

// ---------- prop faces ----------
const FACE_EXPRS = ["neutral", "happy", "excited", "smug", "sly", "shocked", "scared", "sad", "worried", "angry", "pain"];
function drawFace(x, w, h, expr) {
  x.lineCap = "round"; x.lineJoin = "round";
  x.strokeStyle = INK; x.fillStyle = INK; x.lineWidth = 9;
  const ey = 108, ex = [84, 172];
  const big = expr === "shocked" || expr === "scared" || expr === "worried";
  for (const [k, X] of ex.entries()) {
    if (expr === "pain") { // >_<
      const d = k ? -1 : 1;
      x.beginPath(); x.moveTo(X - 16 * d, ey - 16); x.lineTo(X + 14 * d, ey); x.lineTo(X - 16 * d, ey + 16); x.stroke();
      continue;
    }
    if (expr === "happy") { x.beginPath(); x.arc(X, ey + 8, 16, PI * 1.1, PI * 1.9); x.stroke(); continue; }
    if (big) {
      x.fillStyle = "#ffffff"; x.beginPath(); x.arc(X, ey, 24, 0, 2 * PI); x.fill(); x.stroke();
      x.fillStyle = INK; x.beginPath(); x.arc(X, ey + 3, 8, 0, 2 * PI); x.fill();
      continue;
    }
    if (expr === "smug" || expr === "sly") { // heavy lids: only the lower half of the eye shows under a lid line
      x.save(); x.beginPath(); x.rect(X - 30, ey - 2, 60, 40); x.clip();
      x.fillStyle = INK; x.beginPath(); x.arc(X, ey, 15, 0, 2 * PI); x.fill();
      x.fillStyle = "#ffffff"; x.beginPath(); x.arc(X - 5, ey + 4, 4, 0, 2 * PI); x.fill();
      x.restore();
      x.beginPath(); x.moveTo(X - 21, ey - 1 + (expr === "sly" ? (k ? 4 : -4) : 0)); x.lineTo(X + 21, ey - 1 - (expr === "sly" ? (k ? 4 : -4) : 0)); x.stroke();
      continue;
    }
    x.fillStyle = INK; x.beginPath(); x.arc(X, ey, 15, 0, 2 * PI); x.fill();
    x.fillStyle = "#ffffff"; x.beginPath(); x.arc(X - 5, ey - 6, 5, 0, 2 * PI); x.fill();
  }
  const brow = (X, tilt, lift = 0) => {
    x.beginPath(); x.moveTo(X - 22, ey - 40 - lift + tilt); x.lineTo(X + 22, ey - 40 - lift - tilt); x.stroke();
  };
  const tilts = { angry: 9, sad: -8, worried: -8, scared: -6, shocked: 0, smug: 0, sly: 4 };
  if (expr in tilts) {
    brow(ex[0], tilts[expr], expr === "shocked" ? 10 : 0);
    brow(ex[1], -tilts[expr], expr === "shocked" ? 10 : expr === "smug" ? 10 : 0); // smug: one raised brow
  }
  const my = 182;
  x.beginPath();
  switch (expr) {
    case "happy": case "excited":
      x.moveTo(90, my - 8); x.quadraticCurveTo(128, my + 40, 166, my - 8); x.closePath();
      x.fillStyle = expr === "excited" ? "#E2483D" : INK; x.fill(); x.stroke(); break;
    case "shocked": x.ellipse(128, my + 4, 18, 24, 0, 0, 2 * PI); x.fill(); break;
    case "scared": case "worried":
      x.moveTo(92, my); for (let i = 1; i <= 6; i++) x.lineTo(92 + i * 12, my + (i % 2 ? -8 : 6)); x.stroke(); break;
    case "sad": x.moveTo(96, my + 12); x.quadraticCurveTo(128, my - 14, 160, my + 12); x.stroke(); break;
    case "angry": x.moveTo(98, my + 8); x.quadraticCurveTo(128, my - 6, 158, my + 8); x.stroke(); break;
    case "smug": case "sly": x.moveTo(100, my + 4); x.quadraticCurveTo(140, my + 16, 166, my - 10); x.stroke(); break;
    case "pain":
      x.moveTo(88, my); for (let i = 1; i <= 8; i++) x.lineTo(88 + i * 10, my + (i % 2 ? -10 : 10)); x.stroke(); break;
    default: x.moveTo(104, my); x.lineTo(152, my); x.stroke();
  }
  if (expr === "scared") { // sweat drop
    x.fillStyle = "#7FD3FF"; x.beginPath(); x.moveTo(214, 60); x.quadraticCurveTo(232, 92, 214, 100); x.quadraticCurveTo(196, 92, 214, 60); x.fill();
    x.lineWidth = 5; x.stroke();
  }
}
export function propFace(obj, expr) {
  if (!FACE_EXPRS.includes(expr)) throw new Error(`unknown expr: ${expr}`);
  obj.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
  const s = Math.min(size.x, size.y) * 0.62;
  const map = paint(`face_${expr}`, 256, 256, (x, w, h) => drawFace(x, w, h, expr));
  const m = new THREE.MeshBasicMaterial({ map, transparent: true, depthWrite: false, color: map ? "#ffffff" : INK, polygonOffset: true, polygonOffsetFactor: -2 });
  const face = new THREE.Mesh(new THREE.PlaneGeometry(s, s), m);
  face.position.set(c.x, c.y + size.y * 0.06, box.max.z + 0.02);
  face.name = "face";
  obj.add(face);
  return face;
}

// ---------- prop animations ----------
// Each poses the prop's root for `age` seconds after it appeared, on top of its base pose.
export const ANIMS = {
  spin: (o, age) => { o.rotation.y += age * 2.6; },
  float: (o, age) => { o.position.y += 0.25 + 0.22 * Math.sin(age * 2.4); o.rotation.z += 0.06 * Math.sin(age * 1.7); },
  drop: (o, age) => {
    const fall = 0.55;
    if (age < fall) o.position.y += 6 * (1 - Math.pow(age / fall, 2));
    else o.position.y += Math.abs(Math.sin((age - fall) * 9)) * 0.35 * Math.exp(-(age - fall) * 5);
  },
  wobble: (o, age) => { o.rotation.z += 0.14 * Math.sin(age * 8); },
  fly: (o, age, spec) => {
    const from = new THREE.Vector3(...(spec.pos || [0, 0, 0]));
    const to = new THREE.Vector3(...(spec.to || [from.x + 8, from.y, from.z]));
    const p = clamp01(age / (spec.dur || 1.2));
    o.position.lerpVectors(from, to, p);
    o.position.y += Math.sin(PI * p) * (spec.arc ?? 2.5);
    o.rotation.z -= age * 6;
  },
  sink: (o, age) => { o.position.y -= Math.min(4, age * 0.9); o.rotation.x += Math.min(0.5, age * 0.2); },
};

const popIn = (age) => (age >= 0.3 ? 1 : 1 + Math.sin((age / 0.3) * PI) * 0.18 - (1 - easeIO(age / 0.3)) * 1);

// base pose + anim for `age` seconds after the prop appeared. Only a delayed prop pops in: one with no delay is
// already standing there when its beat opens (a cut never lands on an empty set).
// Event-applied specs (actions.js) may carry, as functions of the story time `now`:
//   track(now) -> null (no say yet) | {pos, rot? (radians), visible?}   replaces position (and rotation): held, flying
//   kick(now)  -> {pos: [dx, dy, dz], rotZ}                             added on top (a gun's recoil)
// spec.hidden: the prop is invisible until a track shows it (a cannonball waiting in the barrel).
function placeProp(o, spec, age, now) {
  o.position.set(...(spec.pos || [0, 0, 0]));
  o.rotation.set(...(spec.rot || [0, 0, 0]).map(deg));
  const pops = (spec.delay || 0) > 0 && spec.anim !== "drop" && spec.anim !== "fly";
  o.scale.setScalar((spec.scale || 1) * Math.max(0.01, pops ? popIn(age) : 1));
  if (spec.anim) ANIMS[spec.anim](o, age, spec);
  let shown = !spec.hidden;
  const tr = now != null && spec.track ? spec.track(now) : null;
  if (tr) {
    o.position.set(...tr.pos);
    if (tr.rot) o.rotation.set(...tr.rot);
    shown = tr.visible !== false;
  }
  const k = now != null && spec.kick ? spec.kick(now) : null;
  if (k) { o.position.x += k.pos[0]; o.position.y += k.pos[1]; o.position.z += k.pos[2]; o.rotation.z += k.rotZ || 0; }
  return shown;
}

// Where a prop spawned at `t` is at `now` (its spawn position before it appears); no geometry is built.
// The camera's `follow` move and the actions use it.
export function propPosAt(spec, t, now) {
  const age = now - (t + (spec.delay || 0));
  if (age < 0) return [...(spec.pos || [0, 0, 0])];
  const o = new THREE.Object3D();
  placeProp(o, spec, age, now);
  return [o.position.x, o.position.y, o.position.z];
}

// A firing prop's muzzle at `now` (base pose when now is null): {pos, dir} in world space, dir a unit vector.
export function muzzle(spec, now = null) {
  const local = MUZZLES[spec.type];
  if (!local) throw new Error(`${spec.id || spec.type} (${spec.type}) cannot fire`);
  const o = new THREE.Object3D();
  placeProp(o, spec, now == null ? 0 : now - (spec.spawnT || 0) - (spec.delay || 0), now);
  o.updateMatrix();
  const pos = new THREE.Vector3(...local).applyMatrix4(o.matrix);
  const dir = new THREE.Vector3(1, 0, 0).applyQuaternion(o.quaternion).normalize();
  return { pos: pos.toArray(), dir: dir.toArray() };
}
export const muzzleAt = (spec, now = null) => muzzle(spec, now).pos;

export function spawnProp(spec, t = 0) {
  const make = PROPS[spec.type];
  if (!make) throw new Error(`unknown prop: ${spec.type}`);
  if (spec.anim && !ANIMS[spec.anim]) throw new Error(`unknown anim: ${spec.anim}`);
  const model = make(spec);
  if (spec.face) propFace(model, spec.face);
  const root = new THREE.Group();
  root.name = spec.id || spec.type;
  root.add(model);
  const contact = NO_CONTACT.has(spec.type) ? null : contactShadow(model);
  if (contact) root.add(contact);
  const born = t + (spec.delay || 0);
  root.userData = {
    spec, born, spawnT: t,
    // cur: this frame's spec with its events applied (events.js applyEvents); the story spec by default
    tick(now, cur = spec) {
      const age = now - born;
      root.visible = age >= 0;
      if (!root.visible) return;
      root.visible = placeProp(root, cur, age, now);
      // the contact shadow belongs on the ground: gone while the prop is carried, flying or off its base height
      if (contact) contact.visible = !(cur.track && cur.track(now)) && Math.abs(root.position.y - (cur.pos || [0, 0, 0])[1]) < 0.05;
      root.traverse((k) => { if (k.userData.flame) k.scale.y = 1 + 0.12 * Math.sin(now * 13 + k.id); });
    },
  };
  root.userData.tick(t + Math.max(0.3, spec.delay || 0));
  return root;
}

// ---------- ambient occlusion (soft dark at bases) ----------
// a dark gradient fading upward (or, sideways, along x) from its lower edge: wall bases, corners
function aoMat(sideways = false) {
  const map = paint(`ao${sideways}`, 64, 64, (x, w, h) => {
    const g = sideways ? x.createLinearGradient(0, 0, w, 0) : x.createLinearGradient(0, h, 0, 0);
    g.addColorStop(0, "rgba(20,10,4,0.55)"); g.addColorStop(0.35, "rgba(20,10,4,0.22)"); g.addColorStop(1, "rgba(20,10,4,0)");
    x.fillStyle = g; x.fillRect(0, 0, w, h);
  });
  return new THREE.MeshBasicMaterial({ map, color: map ? "#ffffff" : "#000000", transparent: true, opacity: map ? 1 : 0.2, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -2, fog: false });
}
// a soft dark blob on the ground under a prop's footprint (a painted contact shadow), named "contact"
const NO_CONTACT = new Set(["cloud", "ship", "mug", "pistol", "pillar_rock", "flag"]);
function contactShadow(model) {
  const box = new THREE.Box3().setFromObject(model), size = box.getSize(new THREE.Vector3());
  const map = paint("contact", 128, 128, (x, w) => {
    const g = x.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
    g.addColorStop(0, "rgba(20,10,4,0.6)"); g.addColorStop(0.55, "rgba(20,10,4,0.32)"); g.addColorStop(1, "rgba(20,10,4,0)");
    x.fillStyle = g; x.fillRect(0, 0, w, w);
  });
  const m = new THREE.MeshBasicMaterial({ map, color: map ? "#ffffff" : "#000000", transparent: true, opacity: map ? 1 : 0.25,
    depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 });
  const c = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), m);
  c.rotation.x = -PI / 2;
  c.scale.set(Math.max(0.3, size.x * 1.25), Math.max(0.3, size.z * 1.25), 1);
  c.position.set((box.min.x + box.max.x) / 2, 0.012, (box.min.z + box.max.z) / 2);
  c.name = "contact";
  c.renderOrder = 1;
  return c;
}

// ---------- set pieces ----------
// gradient dome: bottom at the horizon, through `mid` (when given) at a third of the way up, to top
function skyDome(top, bottom, mid = null) {
  const m = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { top: { value: new THREE.Color(top) }, bottom: { value: new THREE.Color(bottom) },
      mid: { value: new THREE.Color(mid || bottom) }, hasMid: { value: mid ? 1 : 0 } },
    vertexShader: "varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: "uniform vec3 top; uniform vec3 bottom; uniform vec3 mid; uniform float hasMid; varying vec3 vP;\n" +
      "void main(){ float h = pow(clamp(vP.y * 1.5 + 0.03, 0.0, 1.0), 0.55);\n" +
      "  vec3 c = hasMid > 0.5 ? (h < 0.42 ? mix(bottom, mid, smoothstep(0.0, 0.42, h)) : mix(mid, top, smoothstep(0.42, 1.0, h))) : mix(bottom, top, h);\n" +
      "  gl_FragColor = vec4(c, 1.0);\n#include <colorspace_fragment>\n}",
  });
  const d = new THREE.Mesh(new THREE.SphereGeometry(450, 32, 16), m);
  d.renderOrder = -1;
  d.name = "sky";
  return d;
}
function stars(seed = 1) {
  const R = rng(seed), pts = [];
  for (let i = 0; i < 260; i++) {
    const a = R() * 2 * PI, e = 0.08 + R() * 1.3;
    pts.push(Math.cos(a) * Math.cos(e) * 420, Math.sin(e) * 420, Math.sin(a) * Math.cos(e) * 420);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  return new THREE.Points(g, new THREE.PointsMaterial({ color: "#FFF6D8", size: 2.4, sizeAttenuation: false, fog: false }));
}
function lights(g, m) {
  g.add(new THREE.HemisphereLight(m.ambient.sky, m.ambient.ground, m.ambient.intensity));
  const sun = new THREE.DirectionalLight(m.sun.color, m.sun.intensity);
  sun.position.set(...m.sun.pos);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -14, right: 14, top: 14, bottom: -14, near: 1, far: 70 });
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.03;
  g.add(sun, sun.target);
  const fill = new THREE.DirectionalLight(m.tint.color, m.tint.intensity);
  fill.position.set(-m.sun.pos[0], 6, -m.sun.pos[2] * 0.4 + 6);
  g.add(fill, fill.target);
}
function clouds(g, seed, n = 7, y = 26, r = [90, 160]) {
  const R = rng(seed);
  for (let i = 0; i < n; i++) {
    const a = -PI / 2 + (i / n - 0.5) * 2.6 + (R() - 0.5) * 0.3, d = r[0] + R() * (r[1] - r[0]);
    const c = P.cloud({ seed: i + seed });
    at(c, [Math.cos(a) * d, y + R() * 22, Math.sin(a) * d], R(), 5 + R() * 4);
    g.add(c);
  }
  // one nearer cloud bank behind the action
  g.add(at(P.cloud({ seed: seed + 9 }), [-14, 14, -60], 0.3, 4));
}
// Ring of pillars around the origin, densest behind it (-z); base at y.
function gusBackdrop(g, { seed = 1, y = 0, n = 14, r = [85, 170], waterfall = true } = {}) {
  const R = rng(seed);
  for (let i = 0; i < n; i++) {
    const back = i < n * 0.65;
    const a = back ? -PI / 2 + (i / (n * 0.65) - 0.5) * 2.4 + (R() - 0.5) * 0.25 : R() * 2 * PI;
    const d = r[0] + R() * (r[1] - r[0]);
    const h = 22 + R() * 24, rad = 4 + R() * 3.5;
    const p = pillarRock({ h, r: rad, seed: i + seed * 7, waterfall: waterfall && i === 1 });
    p.position.set(Math.cos(a) * d, y - 1, Math.sin(a) * d);
    p.rotation.y = Math.atan2(-p.position.x, -p.position.z) + PI; // waterfall side faces the origin
    g.add(p);
    if (R() < 0.6) { // a small companion rock
      const q = pillarRock({ h: h * 0.4, r: rad * 0.55, seed: i + 50 });
      q.position.set(p.position.x + (R() - 0.5) * rad * 4, y - 1, p.position.z + rad * 1.4);
      g.add(q);
    }
  }
}
function seaPlane(y, opts = {}) {
  return floor(1000, 1000, T.sea([60, 60]), { pos: [0, y, 0], ...opts });
}
function room(g, { w = 14, d = 12, hgt = 7.5, wall, floorMat, back = -5, ceiling = true }) {
  g.add(floor(w, d, floorMat, { pos: [0, 0, back + d / 2] }));
  g.add(plane(w, hgt, wall, { pos: [0, hgt / 2, back] }));
  g.add(plane(d, hgt, wall, { pos: [-w / 2, hgt / 2, back + d / 2], rot: [0, PI / 2, 0] }));
  g.add(plane(d, hgt, wall, { pos: [w / 2, hgt / 2, back + d / 2], rot: [0, -PI / 2, 0] }));
  if (ceiling) {
    g.add(floor(w, d, toonMat("#7A5233", { side: THREE.DoubleSide }), { pos: [0, hgt, back + d / 2], rot: [PI / 2, 0, 0] }));
    for (let x = -w / 2 + 1; x < w / 2; x += 2.4) g.add(rbox(0.35, 0.4, d, C.woodDark, { pos: [x, hgt - 0.2, back + d / 2], cast: false }));
  }
  g.add(rbox(w, 0.3, 0.12, C.woodDark, { pos: [0, 0.15, back + 0.06], cast: false }));
  // soft darkening where the walls meet the floor (AO), on the walls and on the floor
  const ao = aoMat();
  g.add(plane(w, 1.4, ao, { pos: [0, 0.7, back + 0.13], cast: false, receive: false }));
  g.add(floor(w, 1.2, ao, { pos: [0, 0.01, back + 0.6], rot: [-PI / 2, 0, PI], cast: false, receive: false }));
  for (const sx of [-1, 1]) {
    g.add(plane(d, 1.4, ao, { pos: [sx * (w / 2 - 0.02), 0.7, back + d / 2], rot: [0, -sx * PI / 2, 0], cast: false, receive: false }));
    g.add(floor(1.2, d, aoMat(true), { pos: [sx * (w / 2 - 0.6), 0.012, back + d / 2], rot: [-PI / 2, 0, sx > 0 ? PI : 0], cast: false, receive: false }));
  }
}
function windowPane(w, h, sky = "#8FD4F5") {
  const g = new THREE.Group();
  g.add(rbox(w + 0.3, h + 0.3, 0.16, "#F6EEDC"));
  g.add(rbox(w, h, 0.18, glowMat(sky), { cast: false }));
  g.add(rbox(0.1, h, 0.22, "#F6EEDC"), rbox(w, 0.1, 0.22, "#F6EEDC"));
  g.add(rbox(w + 0.5, 0.14, 0.4, "#F6EEDC", { pos: [0, -h / 2 - 0.2, 0.1] }));
  return g;
}
function house(o) {
  const g = new THREE.Group(), w = o.w, h = o.h, d = 3.4;
  g.add(rbox(w, h, d, o.color, { pos: [0, h / 2, 0], r: 0.1 }));
  const rr = (w + 0.5) / 1.732; // triangular prism roof, apex up, flattened
  g.add(mesh(new THREE.CylinderGeometry(rr, rr, d + 0.5, 3, 1), o.roof, { rot: [-PI / 2, 0, 0], pos: [0, h + rr * 0.3, 0], scale: [1, 1, 0.6] }));
  const rows = Math.max(1, Math.floor((h - 0.6) / 1.6)), cols = Math.max(1, Math.round(w / 1.6));
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const x = -w / 2 + (w / cols) * (c + 0.5), y = 1.6 + r * 1.6;
    if (r === 0 && c === Math.floor(cols / 2)) {
      g.add(rbox(0.8, 1.5, 0.1, o.door || "#7A4A2A", { pos: [x, 0.75, d / 2 + 0.03] }));
      continue;
    }
    g.add(rbox(0.75, 0.9, 0.1, "#FFFFFF", { pos: [x, y, d / 2 + 0.02] }));
    g.add(rbox(0.58, 0.73, 0.12, hash(r * 7 + c + o.seed) > 0.4 ? "#7FC8EE" : "#FFE58A", { pos: [x, y, d / 2 + 0.03] }));
    g.add(rbox(0.14, 0.9, 0.08, o.shutter || "#3D7F6B", { pos: [x - 0.48, y, d / 2 + 0.04] }), rbox(0.14, 0.9, 0.08, o.shutter || "#3D7F6B", { pos: [x + 0.48, y, d / 2 + 0.04] }));
  }
  return g;
}
function crenellatedWall(len, h, mat) {
  const g = new THREE.Group();
  g.add(rbox(len, h, 1.6, mat, { pos: [0, h / 2, 0], r: 0.05 }));
  for (let x = -len / 2 + 0.5; x <= len / 2 - 0.4; x += 1.4) g.add(rbox(0.8, 0.8, 1.6, mat, { pos: [x, h + 0.4, 0] }));
  return g;
}
function tower(h, r, mat, roof) {
  const g = new THREE.Group();
  g.add(cyl(r, r * 1.08, h, mat, { pos: [0, h / 2, 0], seg: 20 }));
  g.add(cyl(r * 1.15, r * 1.15, 0.6, mat, { pos: [0, h + 0.3, 0], seg: 20 }));
  g.add(cyl(0.02, r * 1.3, r * 1.9, roof, { pos: [0, h + 0.6 + r * 0.95, 0], seg: 20, ink: 0.06 }));
  for (let i = 0; i < 3; i++) g.add(rbox(0.3, 0.6, 0.1, "#2A2730", { pos: [Math.sin(i) * 0.1, h * (0.35 + i * 0.2), r * 1.04] }));
  return g;
}
function tree(c = C.jungle, s = 1) {
  const g = new THREE.Group();
  g.add(cyl(0.18, 0.26, 1.6, "#8A5A34", { pos: [0, 0.8, 0], seg: 10 }));
  g.add(sph(1.1, c, { pos: [0, 2.3, 0], seg: 14 }), sph(0.8, shade(c, 0.12), { pos: [0.6, 1.95, 0.3], seg: 12 }), sph(0.75, shade(c, -0.1), { pos: [-0.6, 2.0, -0.1], seg: 12 }));
  g.scale.setScalar(s);
  return g;
}
const place = (g, type, spec, pos, rotY = 0, scale = 1) => g.add(at(PROPS[type](spec || {}), pos, rotY, scale));

// ---------- sets ----------
// A builder fills `g` for the set; `o` = the beat's set spec (opts such as color).
export const SETS = {
  ship_deck(g, o) {
    g.add(floor(14, 18, T.planks([5, 6], { vertical: true }), { pos: [0, 0, 4] }));
    g.add(rbox(14.4, 0.6, 18.4, C.woodDeep, { pos: [0, -0.31, 4], cast: false }));
    // bulwark: low painted wall, posts, cap rail; gaps show the sea
    const paint = T.planks([3, 0.5], { base: C.hullRed, dark: "#8A3018", rows: 8, seed: 21 });
    for (const [w, pos, rot] of [[14, [0, 0, -5], 0], [18, [-7, 0, 4], PI / 2], [18, [7, 0, 4], -PI / 2]]) {
      const b = new THREE.Group();
      b.add(rbox(w, 0.75, 0.25, paint, { pos: [0, 0.38, 0] }));
      for (let x = -w / 2 + 0.3; x <= w / 2; x += 1.15) b.add(rbox(0.22, 1.5, 0.28, C.hullRed, { pos: [x, 0.75, 0] }));
      b.add(rbox(w + 0.3, 0.2, 0.55, C.wood, { pos: [0, 1.55, 0], ink: 0.02 }));
      b.add(rbox(w + 0.4, 4, 0.3, T.planks([3, 1], { base: "#7A3E22", dark: "#4A2412", rows: 10, seed: 22 }), { pos: [0, -2, -0.2], cast: false }));
      b.add(rbox(w + 0.5, 0.35, 0.45, "#2A2328", { pos: [0, -0.6, -0.25], cast: false }));
      b.position.set(...pos); b.rotation.y = rot;
      g.add(b);
    }
    // mast + shrouds with ratlines
    const mx = 3.2, mz = -3.2;
    g.add(cyl(0.32, 0.38, 26, C.woodDark, { pos: [mx, 13, mz], seg: 14 }));
    g.add(cyl(0.55, 0.6, 0.35, C.woodDeep, { pos: [mx, 0.17, mz] }));
    const anchors = [4.4, 5.3, 6.2];
    for (const ax of anchors) g.add(beam([ax, 1.6, -5], [mx + 0.2, 15, mz], 0.035, "#3B2B22", { cast: false }));
    for (let k = 1; k < 9; k++) {
      const f = k / 10, y = 1.6 + f * 13.4;
      const l = [anchors[0] + (mx + 0.2 - anchors[0]) * f, y, -5 + (mz + 5) * f];
      const r = [anchors[2] + (mx + 0.2 - anchors[2]) * f, y, -5 + (mz + 5) * f];
      g.add(beam(l, r, 0.03, "#3B2B22", { cast: false }));
    }
    // deck dressing at the edges
    g.add(rbox(1.6, 0.25, 1.6, "#4A3020", { pos: [-4.6, 0.12, -1.5] }));
    for (let i = 0; i < 4; i++) g.add(rbox(1.4, 0.06, 0.12, "#2B1C12", { pos: [-4.6, 0.26, -2.1 + i * 0.4] }));
    place(g, "barrel", {}, [-5.6, 0, -4.2]);
    place(g, "barrel", {}, [-4.7, 0, -4.4], 1);
    g.add(seaPlane(-3.5));
    gusBackdrop(g, { seed: 3, y: -3.5 });
    place(g, "ship", { color: "#2C2C34" }, [-38, -3.5, -70], 0.5, 1.6);
    clouds(g, 2);
  },
  open_sea(g, o) {
    g.add(seaPlane(0));
    place(g, "ship", o, [0.5, 0, -12], 0.25, 1);
    place(g, "ship", { color: "#2C2C34" }, [-30, 0, -80], -0.7, 1.4);
    for (const [x, z, s] of [[16, -40, 1], [-22, -34, 0.8]]) {
      g.add(at(mesh(new THREE.SphereGeometry(3, 16, 8, 0, 2 * PI, 0, PI / 2), T.sand([2, 1]), { scale: [1.6, 0.35, 1] }), [x, -0.2, z], 0, s));
      place(g, "palm", { seed: x }, [x, 0.6 * s, z], 0, s);
      place(g, "palm", { seed: z, h: 3.4 }, [x + 1.4 * s, 0.5 * s, z + 0.6], 2, s);
    }
    gusBackdrop(g, { seed: 5, y: 0, r: [60, 140] });
    clouds(g, 4);
  },
  harbour(g, o) {
    // stone quay in front, harbour water behind, fort wall on the right, lighthouse on the far mole
    g.add(floor(40, 14, T.flags([10, 3.5], { base: "#D8CDBA" }), { pos: [0, 0, 2] }));
    g.add(rbox(40, 2.4, 0.8, T.flags([10, 0.6], { base: "#BDB2A0", rows: 2, round: 6 }), { pos: [0, -1.2, -5.1], cast: false }));
    for (let x = -9; x <= 9; x += 3) {
      g.add(cyl(0.22, 0.26, 3.2, C.woodDark, { pos: [x, -0.4, -5.7], seg: 10, ink: 0.02 }));
      g.add(cyl(0.2, 0.26, 0.5, "#2E3440", { pos: [x + 1.5, 0.25, -4.4], seg: 12 }));
    }
    g.add(seaPlane(-1.6));
    place(g, "ship", o, [-3, -1.6, -13], 0.12, 1);
    const fort = T.flags([4, 1.2], { base: "#D9C9A6", rows: 3, cols: 3, round: 8 });
    const wall = crenellatedWall(18, 5, fort);
    at(wall, [14, -1.6, -18], -0.5);
    g.add(wall);
    g.add(at(tower(9, 2.2, fort, "#3A6EA5"), [7.5, -1.6, -24]));
    g.add(at(tower(7, 1.8, fort, "#3A6EA5"), [21, -1.6, -11]));
    g.add(rbox(3, 2.5, 30, "#B9AE9C", { pos: [-18, -1.4, -30], cast: false }));
    place(g, "lighthouse", {}, [-18, -0.2, -42], 0, 1.3);
    for (const [x, c] of [[-9, "#F2C46B"], [-5, "#E77A5A"]]) g.add(at(house({ w: 3.4, h: 4, color: c, roof: "#B5452E", seed: x }), [x, 0, -2.6 + 30], PI));
    gusBackdrop(g, { seed: 7, y: -1.6 });
    clouds(g, 6);
  },
  coast(g, o) {
    // a beach whose shoreline runs just behind the action, palms, rocks, a headland lighthouse
    g.add(mesh(new THREE.CylinderGeometry(22, 24, 1.2, 64), T.sand([6, 6]), { pos: [0, -0.6, 16], cast: false }));
    g.add(at(mesh(new THREE.CylinderGeometry(22.6, 24.6, 0.08, 64), "#F6F8F2", { cast: false }), [0, -0.3, 16]));
    g.add(mesh(new THREE.CylinderGeometry(12, 13, 1.5, 40), T.grass([4, 4]), { pos: [-14, -0.45, 24], cast: false }));
    g.add(seaPlane(-0.35));
    place(g, "palm", {}, [-3.6, 0, -2.5], 0.3);
    place(g, "palm", { h: 3.6, seed: 9 }, [-5.2, 0, 0.5], 2.1);
    place(g, "palm", { h: 4.6, seed: 4 }, [4.8, 0, -3.5], 1.4);
    for (const [x, z, s] of [[2.8, -4.2, 0.7], [3.6, -3.6, 0.45], [-1.8, -6.2, 0.5], [-9, -14, 1.4], [7, -16, 1.1]])
      g.add(at(sph(1, "#A89A88", { scale: [1.2, 0.7, 1], seg: 12 }), [x, -0.3, z], 0, s));
    const head = group(
      mesh(new THREE.SphereGeometry(1, 20, 10, 0, 2 * PI, 0, PI / 2), T.rock(4), { scale: [9, 6, 7], cast: false }),
      mesh(new THREE.SphereGeometry(1, 20, 8, 0, 2 * PI, 0, PI / 2), T.grass([2, 2]), { scale: [6.5, 1.6, 5], pos: [0, 5.2, 0], cast: false }));
    g.add(at(head, [9, -0.6, -32]));
    place(g, "lighthouse", {}, [9, 6.3, -32], 0, 1.1);
    gusBackdrop(g, { seed: 9, y: -0.35 });
    clouds(g, 8);
  },
  furnace_room(g, o) {
    room(g, { wall: T.bricks([5, 3], { base: o.color || "#B84E2C" }), floorMat: T.flags([5, 4], { base: "#B3A48E" }), hgt: 8 });
    place(g, "furnace", {}, [1.6, 0, -3.6]);
    for (let i = 0; i < 12; i++) g.add(sph(0.2, "#25242A", { pos: [-1.2 + (i % 4) * 0.36 - hash(i) * 0.1, 0.18 + Math.floor(i / 4) * 0.25, -3.6 + Math.floor(i / 4) * 0.12], seg: 10 }));
    place(g, "tongs", {}, [-2.6, 0, -4.7], 0.1);
    g.add(at(PROPS.tongs({}), [-2.95, 0, -4.7], -0.1));
    g.add(rbox(2.4, 0.15, 0.6, C.woodDark, { pos: [-4, 3.2, -4.7] }));
    for (let i = 0; i < 3; i++) place(g, "jar", { color: ["#E9A23B", "#5BB0E0", "#9DD45A"][i] }, [-4.6 + i * 0.6, 3.28, -4.7], 0, 0.6);
    place(g, "torch", {}, [-5.8, 2.4, -4.6], 0, 0.9);
    place(g, "barrel", {}, [5.4, 0, -4.2]);
  },
  town_street(g, o) {
    g.add(floor(80, 30, T.cobbles([20, 7.5]), { pos: [0, 0, 6] }));
    g.add(rbox(80, 0.3, 2.2, "#D9D0C1", { pos: [0, 0.15, -5.2], cast: false }));
    const cols = ["#F6D57A", "#F29B7A", "#8FD1C4", "#F5EAD2", "#A9C8F0", "#F7B7C4", "#C9E38C"];
    const roofs = ["#C8513A", "#3E6FA8", "#8B4B2E", "#C8513A", "#5C7F3A"];
    let x = -24;
    for (let i = 0; x < 24; i++) {
      const w = 3.4 + hash(i) * 1.4, h = 4.2 + hash(i + 3) * 3.4;
      g.add(at(house({ w, h, color: cols[i % cols.length], roof: roofs[i % roofs.length], seed: i, shutter: i % 2 ? "#3D7F6B" : "#7A4A8C" }), [x + w / 2, 0, -8]));
      x += w + 0.15;
    }
    for (let lx = -10; lx <= 10; lx += 5) {
      const lamp = group(cyl(0.07, 0.1, 3.4, "#2F3442", { pos: [0, 1.7, 0], seg: 8 }), P.lantern({}));
      lamp.children[1].position.y = 3.35;
      g.add(at(lamp, [lx + 2.5, 0.3, -4.6]));
    }
    for (let i = 0; i < 3; i++) g.add(at(tree(C.jungle, 0.8), [-30 + i * 30, 0, -16]));
    gusBackdrop(g, { seed: 11, y: 0, n: 8, r: [80, 160] });
    clouds(g, 10);
  },
  room(g, o) {
    room(g, { wall: T.planks([3, 2.2], { rows: 8, base: o.color || "#C7864A", seed: 31 }), floorMat: T.planks([4, 3.5], { vertical: true, seed: 32 }) });
    const win = windowPane(1.9, 1.6);
    at(win, [3.2, 3.6, -4.9]);
    g.add(win);
    const port = group(mesh(new THREE.TorusGeometry(0.7, 0.14, 10, 28), "#E3A23C"), mesh(new THREE.CircleGeometry(0.7, 28), glowMat("#8FD4F5"), { cast: false }));
    g.add(at(port, [-6.9, 3.6, -1.5], PI / 2));
    g.add(at(group(rbox(1.4, 1.1, 0.08, "#E3A23C"), rbox(1.15, 0.85, 0.1, "#5DA7C8"), sph(0.22, "#FFE27A", { pos: [-0.25, 0.1, 0.06], scale: [1, 1, 0.3] })), [-1.6, 4.1, -4.92]));
    g.add(mesh(new THREE.CircleGeometry(2.4, 32), "#B8443A", { rot: [-PI / 2, 0, 0], pos: [0, 0.02, 0.4], scale: [1.3, 0.8, 1], cast: false }));
    g.add(mesh(new THREE.RingGeometry(1.9, 2.15, 32), "#F2C46B", { rot: [-PI / 2, 0, 0], pos: [0, 0.03, 0.4], scale: [1.3, 0.8, 1], cast: false }));
    g.add(rbox(2.2, 0.14, 0.5, C.woodDark, { pos: [-4.3, 2.9, -4.75] }));
    place(g, "lantern", {}, [-4.8, 2.97, -4.75], 0, 0.8);
    place(g, "jar", { color: "#9DD45A" }, [-3.8, 2.97, -4.75], 0, 0.6);
  },
  office(g, o) {
    const wall = o.color || "#BFE0D6";
    room(g, { wall: T.stripes({ a: wall, b: shade(wall, -0.06), n: 16, horizontal: false }, [3, 1]), floorMat: T.planks([5, 4], { vertical: true, base: "#B27846", seed: 41 }), ceiling: false, hgt: 8 });
    g.add(rbox(14, 1.3, 0.14, T.planks([3, 0.4], { vertical: true, base: "#8C5A2B", seed: 42 }), { pos: [0, 0.65, -4.92], cast: false }));
    g.add(rbox(14, 0.12, 0.25, C.woodDeep, { pos: [0, 1.32, -4.86], cast: false }));
    const win = windowPane(2.6, 2.2);
    g.add(at(win, [2.8, 4.0, -4.88]));
    const shelf = new THREE.Group();
    shelf.add(rbox(2.4, 4.2, 0.6, C.woodDark, { pos: [0, 2.1, 0] }));
    for (let r = 0; r < 4; r++) {
      shelf.add(rbox(2.2, 0.08, 0.5, C.wood, { pos: [0, 0.4 + r * 1.0, 0.06] }));
      for (let b = 0; b < 8; b++) {
        const bh = 0.6 + hash(r * 9 + b) * 0.25;
        shelf.add(rbox(0.22, bh, 0.42, ["#E2483D", "#3E7FD6", "#F2BE3A", "#3E9B45", "#7A4A8C"][(r + b) % 5], { pos: [-0.9 + b * 0.25, 0.44 + r * 1.0 + bh / 2, 0.08], r: 0.03 }));
      }
    }
    g.add(at(shelf, [-3.4, 0, -4.6]));
    const clock = group(cyl(0.55, 0.55, 0.12, "#F6EEDC", { rot: [PI / 2, 0, 0], ink: 0.03 }), beam([0, 0, 0.08], [0, 0.4, 0.08], 0.035, INK), beam([0, 0, 0.08], [0.28, 0, 0.08], 0.035, INK));
    g.add(at(clock, [0, 5.6, -4.85]));
    const cab = group(rbox(1.0, 1.6, 0.8, "#9AA6B4", { pos: [0, 0.8, 0] }), rbox(0.6, 0.08, 0.05, "#5A6270", { pos: [0, 1.3, 0.42] }), rbox(0.6, 0.08, 0.05, "#5A6270", { pos: [0, 0.6, 0.42] }));
    g.add(at(cab, [5.4, 0, -4.4]));
    const plant = group(cyl(0.32, 0.25, 0.6, "#C9683C", { pos: [0, 0.3, 0] }), sph(0.55, C.jungle, { pos: [0, 1.0, 0] }), sph(0.4, C.jungleLight, { pos: [0.3, 1.3, 0.1] }));
    g.add(at(plant, [4.6, 0, -4.3]));
  },
  lab(g, o) {
    room(g, { wall: T.tiles([7, 4], { a: o.color || "#EAF6F1" }), floorMat: T.checker([6, 5]), ceiling: false, hgt: 8 });
    const bench = new THREE.Group();
    bench.add(rbox(8, 1.1, 1.2, "#5E7FA3", { pos: [0, 0.55, 0] }));
    bench.add(rbox(8.2, 0.14, 1.35, "#2E3440", { pos: [0, 1.15, 0.02] }));
    for (let i = 0; i < 4; i++) bench.add(rbox(1.6, 0.8, 0.06, "#6E91B5", { pos: [-3 + i * 2, 0.55, 0.62] }));
    g.add(at(bench, [0, 0, -4.2]));
    const liquids = ["#5BD0A0", "#F06292", "#5BB0E0", "#FFD45A", "#B07AE8"];
    for (let i = 0; i < 5; i++) {
      const fl = new THREE.Group();
      fl.add(sph(0.3, liquids[i], { pos: [0, 0.3, 0], seg: 16, scale: [1, 0.85, 1] }));
      fl.add(cyl(0.08, 0.08, 0.5, "#DDF3FF", { pos: [0, 0.75, 0], seg: 10 }));
      g.add(at(fl, [-3.4 + i * 1.6, 1.22, -4.2], 0, 0.9 + hash(i) * 0.3));
    }
    const board = group(rbox(4.2, 2.4, 0.12, "#7A4A2A"), rbox(3.9, 2.1, 0.14, "#2F5A46"));
    if (HAS_DOM) board.children[1].material = texMat(paint("chalk", 512, 256, (x, w, h) => {
      x.fillStyle = "#2F5A46"; x.fillRect(0, 0, w, h);
      x.strokeStyle = "rgba(255,255,255,.8)"; x.lineWidth = 5; x.lineCap = "round";
      x.beginPath(); x.arc(110, 128, 60, 0, 2 * PI); x.stroke();
      for (let i = 0; i < 3; i++) { x.beginPath(); x.ellipse(110, 128, 90, 30, i, 0, 2 * PI); x.stroke(); }
      x.beginPath(); x.moveTo(250, 80); x.lineTo(460, 80); x.moveTo(250, 130); x.lineTo(420, 130); x.moveTo(250, 180); x.lineTo(450, 180); x.stroke();
    }));
    g.add(at(board, [-2.8, 4.3, -4.9]));
    g.add(rbox(3.2, 0.12, 0.45, "#5E7FA3", { pos: [3.2, 3.6, -4.75] }));
    for (let i = 0; i < 4; i++) place(g, "jar", { color: liquids[i] }, [2.1 + i * 0.75, 3.66, -4.75], 0, 0.55);
    place(g, "gear", { color: "#9AA3AF" }, [5.6, 0, -4.4], -0.4, 0.9);
  },
  field(g, o) {
    g.add(floor(1000, 1000, T.grass([140, 140], { flowers: true }), { pos: [0, 0, 0] }));
    const R = rng(3);
    for (let i = 0; i < 7; i++) {
      const hill = mesh(new THREE.SphereGeometry(1, 20, 10, 0, 2 * PI, 0, PI / 2), ["#5DB548", "#78C850", "#4FA83C"][i % 3], { cast: false });
      at(hill, [-60 + i * 20 + R() * 8, -1, -45 - R() * 25], 0, 1);
      hill.scale.set(16 + R() * 10, 5 + R() * 5, 12);
      g.add(hill);
    }
    g.add(floor(2.4, 60, T.sand([1, 20]), { pos: [1.5, 0.02, -20], rot: [-PI / 2, 0, 0.1] }));
    for (let x = -12; x <= 12; x += 1.8) {
      if (Math.abs(x - 1.4) < 1.6) continue;
      g.add(rbox(0.16, 1.1, 0.16, C.wood, { pos: [x, 0.55, -4.5] }));
    }
    for (const y of [0.45, 0.85]) {
      g.add(rbox(10.5, 0.1, 0.08, C.wood, { pos: [-5.2, y, -4.45] }), rbox(10, 0.1, 0.08, C.wood, { pos: [7.4, y, -4.45] }));
    }
    for (const [x, z, s] of [[-6, -9, 1.2], [7, -12, 1.5], [-12, -18, 1.4], [14, -22, 1.2], [-3.5, -16, 0.9]]) g.add(at(tree([C.jungle, C.jungleLight][x > 0 ? 1 : 0], s), [x, 0, z]));
    gusBackdrop(g, { seed: 13, y: 0, waterfall: true });
    clouds(g, 12);
  },
  castle_yard(g, o) {
    const stone = T.flags([5, 2.2], { base: o.color || "#CFC2A8", rows: 3, cols: 3, round: 8 });
    g.add(floor(60, 40, T.flags([14, 10], { base: "#D8CDBA" }), { pos: [0, 0, 6] }));
    const back = crenellatedWall(28, 6.5, stone);
    at(back, [0, 0, -9]);
    g.add(back);
    for (const s of [-1, 1]) g.add(at(crenellatedWall(16, 6.5, stone), [s * 14, 0, -1], PI / 2));
    // gate: dark arch in the back wall with a portcullis
    const arch = new THREE.Shape();
    arch.moveTo(-1.6, 0); arch.lineTo(1.6, 0); arch.lineTo(1.6, 2.4); arch.absarc(0, 2.4, 1.6, 0, PI, false); arch.closePath();
    g.add(mesh(new THREE.ShapeGeometry(arch, 16), "#2A2530", { pos: [0, 0, -8.18], cast: false }));
    for (let x = -1.3; x <= 1.31; x += 0.43) g.add(rbox(0.1, 3.8, 0.1, "#4A4552", { pos: [x, 1.9, -8.1] }));
    for (const s of [-1, 1]) {
      g.add(at(tower(10, 2.4, stone, "#3E6FA8"), [s * 14, 0, -9]));
      place(g, "flag", { color: s < 0 ? "#E2483D" : "#F2BE3A" }, [s * 14, 13.7, -9], 0, 1);
      place(g, "torch", {}, [s * 2.4, 2.6, -8.1], 0, 0.8);
    }
    g.add(at(tower(13, 3, stone, "#C8513A"), [6, 0, -20]));
    gusBackdrop(g, { seed: 15, y: 0, n: 9 });
    clouds(g, 14);
  },
  cutaway(g, o) {
    // the inside of an object, cut open: a half pipe with a lit cut edge, on a gradient
    const inner = o.color || "#C9743A", cut = o.cut || "#F2C14E";
    g.add(skyDome(o.bgTop || "#FFE3B8", o.bgBottom || "#F08A4B"));
    const R = 5.2, len = 30;
    const shell = mesh(new THREE.CylinderGeometry(R, R, len, 40, 1, true, PI * 0.25, PI * 1.5), toonMat(inner, { side: THREE.DoubleSide }), { cast: false });
    shell.rotation.x = -PI / 2; // the open side faces up
    shell.position.set(0, R - 0.6, -len / 2 + 6);
    g.add(shell);
    for (let k = 0; k < 6; k++) { // ribs give the inside depth
      const rib = mesh(new THREE.TorusGeometry(R - 0.05, 0.12, 8, 40, PI * 1.5), shade(inner, -0.22), { cast: false });
      rib.rotation.set(0, 0, PI * 0.75);
      rib.position.set(0, R - 0.6, 4 - k * 4.5);
      g.add(rib);
    }
    const lip = mesh(new THREE.TorusGeometry(R + 0.2, 0.32, 10, 40, PI * 1.5), cut, { cast: false, ink: 0.04 });
    lip.rotation.set(0, 0, PI * 0.75);
    lip.position.set(0, R - 0.6, 6);
    g.add(lip);
    g.add(floor(5.4, len, toonMat(shade(inner, 0.12)), { pos: [0, 0, -len / 2 + 6] }));
    for (let i = 0; i < 9; i++) g.add(sph(0.12 + hash(i) * 0.12, "#FFF2D0", { pos: [(hash(i + 4) - 0.5) * 7, 1 + hash(i + 9) * 7, -6 - hash(i + 1) * 14], seg: 8, cast: false }));
  },
};

export function buildSet(spec = {}) {
  const build = SETS[spec.type];
  if (!build) throw new Error(`unknown set: ${spec.type}`);
  const moodName = spec.mood || "day";
  const m = MOODS[moodName];
  if (!m) throw new Error(`unknown mood: ${moodName}`);
  const g = new THREE.Group();
  g.name = `set:${spec.type}`;
  if (spec.type !== "cutaway") g.add(skyDome(m.skyTop, m.skyBottom, m.skyMid));
  if (moodName === "night") g.add(stars(7));
  lights(g, m);
  build(g, spec);
  g.userData.fog = new THREE.Fog(m.fog.color, m.fog.near, m.fog.far);
  g.userData.mood = moodName;
  return g;
}

// Names this registry adds to studio/catalog.json.
export function catalog() {
  return { sets: Object.keys(SETS), moods: Object.keys(MOODS), props: Object.keys(PROPS), anims: Object.keys(ANIMS) };
}
