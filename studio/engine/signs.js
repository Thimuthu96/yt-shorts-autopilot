// In-world signs: names and numbers painted onto things in the scene (a plank, a barrel label, a banner, a
// chalkboard, a metal plate, a pinned paper), never screen overlays. Uppercase, heavy Fredoka.
// Pure registry module: nothing touches the DOM at import time; without a document the sign keeps its size and
// shape but no painted texture (plain node: tests, catalog.js).
//   signPlane(text, style) -> THREE.Group      (centred on its origin, facing +z; userData.size = {w, h} in units)
//   spawnSign({text, pos, style, delay, rot?}, t) -> THREE.Group   (userData.tick(now): hidden until t + delay,
//                                                 then pops in; a banner keeps waving)
import * as THREE from "three";
import { canvasTex, toonMat, hash, clamp01, INK } from "./core.js";

const HAS_DOM = typeof document !== "undefined";
const PX = 480; // canvas pixels per world unit (a style may set its own `px`)
const FONT = 110; // px: about 0.23 units of text height
const WRAP = 16; // characters per line before a line wraps at a space

function rounded(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

// deterministic speckles (chalk dust, wood knots, rust)
function speckle(ctx, w, h, n, color, size, seed) {
  ctx.fillStyle = color;
  for (let k = 0; k < n; k++) {
    const r = size * (0.4 + hash(seed + k * 3.3));
    ctx.beginPath(); ctx.arc(hash(seed + k * 1.7) * w, hash(seed + k * 2.9) * h, r, 0, Math.PI * 2); ctx.fill();
  }
}

function roughEdge(ctx, w, h, inset, amp, seed) {
  const pts = [];
  const step = 26;
  for (let x = inset; x <= w - inset; x += step) pts.push([x, inset + amp * hash(seed + x)]);
  for (let y = inset; y <= h - inset; y += step) pts.push([w - inset - amp * hash(seed + y * 1.3), y]);
  for (let x = w - inset; x >= inset; x -= step) pts.push([x, h - inset - amp * hash(seed + x * 1.7)]);
  for (let y = h - inset; y >= inset; y -= step) pts.push([inset + amp * hash(seed + y * 2.1), y]);
  ctx.beginPath();
  pts.forEach(([x, y], k) => ctx[k ? "lineTo" : "moveTo"](x, y));
  ctx.closePath();
}

// text: lines centred in the box (x0, y0, w, h); `paint(ctx, line, x, y)` draws one line
function lines(ctx, L, box, weight, paint) {
  ctx.font = `${weight} ${FONT}px Fredoka`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
  const lh = FONT * 1.04, top = box.y + box.h / 2 - (lh * (L.length - 1)) / 2;
  L.forEach((line, k) => paint(ctx, line, box.x + box.w / 2, top + k * lh + FONT * 0.04, box.w));
}

// SIGN_STYLES[style] = {pad: [x, y], depth (0 = a flat sheet), side colour, weight, px, tilt (deg), wave, wrap (radius:
// bent round a barrel, its middle at the origin), paint(ctx, w, h, L)}
export const SIGN_STYLES = {
  plank: {
    pad: [70, 52], depth: 0.09, side: "#8C5A2B", weight: 700,
    paint(ctx, w, h, L) {
      rounded(ctx, 4, 4, w - 8, h - 8, 26); ctx.fillStyle = INK; ctx.fill();
      rounded(ctx, 14, 14, w - 28, h - 28, 18); ctx.fillStyle = "#C2824A"; ctx.fill();
      ctx.save(); ctx.clip();
      ctx.strokeStyle = "#9C6534"; ctx.lineWidth = 4;
      for (let y = 38; y < h - 20; y += 34) {
        ctx.beginPath(); ctx.moveTo(14, y);
        for (let x = 14; x < w; x += 60) ctx.lineTo(x + 60, y + 5 * Math.sin(x * 0.02 + y));
        ctx.stroke();
      }
      ctx.fillStyle = "rgba(255,230,190,0.35)"; ctx.fillRect(14, 14, w - 28, 16);
      ctx.restore();
      speckle(ctx, w, h, 4, "#7A4B23", 7, 3.1);
      for (const [x, y] of [[34, 34], [w - 34, 34], [34, h - 34], [w - 34, h - 34]]) {
        ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2); ctx.fillStyle = "#4A4D55"; ctx.fill();
        ctx.beginPath(); ctx.arc(x - 2, y - 2, 3.5, 0, Math.PI * 2); ctx.fillStyle = "#A9AEB8"; ctx.fill();
      }
      lines(ctx, L, { x: 0, y: 0, w, h }, 700, (c, s, x, y, mw) => {
        c.fillStyle = "#F0C890"; c.fillText(s, x + 3, y + 4, mw - 120);
        c.fillStyle = "#3B220F"; c.fillText(s, x, y, mw - 120);
      });
    },
  },
  barrel_label: {
    pad: [64, 46], depth: 0, weight: 700, px: 760, wrap: 0.46,
    paint(ctx, w, h, L) {
      roughEdge(ctx, w, h, 6, 10, 7.7); ctx.fillStyle = "#5A3A1A"; ctx.fill();
      roughEdge(ctx, w, h, 13, 9, 7.7);
      const g = ctx.createRadialGradient(w / 2, h / 2, h * 0.2, w / 2, h / 2, w * 0.6);
      g.addColorStop(0, "#F2DFAE"); g.addColorStop(0.7, "#E2C385"); g.addColorStop(1, "#B98A4C");
      ctx.fillStyle = g; ctx.fill();
      ctx.strokeStyle = "#6B4321"; ctx.lineWidth = 4; rounded(ctx, 30, 26, w - 60, h - 52, 10); ctx.stroke();
      lines(ctx, L, { x: 0, y: 0, w, h }, 700, (c, s, x, y, mw) => { c.fillStyle = "#4A2A14"; c.fillText(s, x, y, mw - 100); });
    },
  },
  banner: {
    pad: [130, 50], depth: 0, weight: 700, wave: true,
    paint(ctx, w, h, L) {
      const notch = 70;
      const path = (i) => {
        ctx.beginPath();
        ctx.moveTo(i, i); ctx.lineTo(w - i, i); ctx.lineTo(w - notch, h / 2); ctx.lineTo(w - i, h - i);
        ctx.lineTo(i, h - i); ctx.lineTo(notch, h / 2); ctx.closePath();
      };
      path(4); ctx.fillStyle = INK; ctx.fill();
      path(13); ctx.fillStyle = "#CC3A2E"; ctx.fill();
      ctx.save(); ctx.clip();
      for (let x = notch; x < w; x += 120) { ctx.fillStyle = "rgba(90,10,20,0.18)"; ctx.fillRect(x, 0, 46, h); }
      ctx.fillStyle = "#F2BE3A"; ctx.fillRect(0, 26, w, 9); ctx.fillRect(0, h - 35, w, 9);
      ctx.restore();
      lines(ctx, L, { x: 0, y: 0, w, h }, 700, (c, s, x, y, mw) => {
        c.lineWidth = 14; c.strokeStyle = "#5C1410"; c.strokeText(s, x, y, mw - 2 * notch - 40);
        c.fillStyle = "#FFF1D0"; c.fillText(s, x, y, mw - 2 * notch - 40);
      });
    },
  },
  chalk: {
    pad: [86, 64], depth: 0.07, side: "#6B4321", weight: 600,
    paint(ctx, w, h, L) {
      rounded(ctx, 2, 2, w - 4, h - 4, 14); ctx.fillStyle = INK; ctx.fill();
      rounded(ctx, 10, 10, w - 20, h - 20, 10); ctx.fillStyle = "#9C6534"; ctx.fill();
      ctx.fillStyle = "#2C4436"; ctx.fillRect(34, 34, w - 68, h - 68);
      ctx.fillStyle = "rgba(255,255,255,0.05)";
      for (let k = 0; k < 6; k++) ctx.fillRect(34 + hash(k * 5.1) * (w - 200), 40 + hash(k * 2.3) * (h - 100), 160, 40);
      lines(ctx, L, { x: 0, y: 0, w, h }, 600, (c, s, x, y, mw) => { c.fillStyle = "rgba(246,246,238,0.94)"; c.fillText(s, x, y, mw - 140); });
      // chalk grain: tiny gaps in the strokes
      ctx.save(); ctx.beginPath(); ctx.rect(34, 34, w - 68, h - 68); ctx.clip();
      speckle(ctx, w, h, Math.round((w * h) / 260), "rgba(44,68,54,0.75)", 2.2, 1.9);
      ctx.restore();
      ctx.fillStyle = "#F6F6EE"; ctx.fillRect(w - 120, h - 30, 50, 12);
    },
  },
  metal: {
    pad: [80, 52], depth: 0.05, side: "#6F7884", weight: 700,
    paint(ctx, w, h, L) {
      rounded(ctx, 4, 4, w - 8, h - 8, 18); ctx.fillStyle = INK; ctx.fill();
      rounded(ctx, 12, 12, w - 24, h - 24, 12);
      const g = ctx.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, "#DCE2E9"); g.addColorStop(0.5, "#AEB7C2"); g.addColorStop(1, "#8A94A1");
      ctx.fillStyle = g; ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,0.7)"; ctx.lineWidth = 4; rounded(ctx, 22, 22, w - 44, h - 44, 8); ctx.stroke();
      for (const [x, y] of [[36, 36], [w - 36, 36], [36, h - 36], [w - 36, h - 36]]) {
        ctx.beginPath(); ctx.arc(x, y, 11, 0, Math.PI * 2); ctx.fillStyle = "#6F7884"; ctx.fill();
        ctx.beginPath(); ctx.arc(x - 3, y - 3, 4.5, 0, Math.PI * 2); ctx.fillStyle = "#F2F5F8"; ctx.fill();
      }
      lines(ctx, L, { x: 0, y: 0, w, h }, 700, (c, s, x, y, mw) => {
        c.fillStyle = "rgba(255,255,255,0.8)"; c.fillText(s, x + 2, y + 3, mw - 130);
        c.fillStyle = "#1F2733"; c.fillText(s, x, y, mw - 130);
      });
    },
  },
  paper: {
    pad: [70, 64], depth: 0, weight: 700, tilt: -3,
    paint(ctx, w, h, L) {
      ctx.fillStyle = INK; ctx.fillRect(6, 10, w - 12, h - 16);
      ctx.fillStyle = "#FBF6E9"; ctx.fillRect(13, 17, w - 26, h - 30);
      ctx.strokeStyle = "rgba(90,140,200,0.35)"; ctx.lineWidth = 3;
      for (let y = 60; y < h - 24; y += 40) { ctx.beginPath(); ctx.moveTo(20, y); ctx.lineTo(w - 20, y); ctx.stroke(); }
      ctx.fillStyle = "rgba(200,60,60,0.35)"; ctx.fillRect(56, 17, 3, h - 30);
      lines(ctx, L, { x: 0, y: 6, w, h }, 700, (c, s, x, y, mw) => { c.fillStyle = "#2A2440"; c.fillText(s, x, y, mw - 110); });
      ctx.beginPath(); ctx.arc(w / 2, 26, 14, 0, Math.PI * 2); ctx.fillStyle = INK; ctx.fill();
      ctx.beginPath(); ctx.arc(w / 2, 26, 10, 0, Math.PI * 2); ctx.fillStyle = "#E0453A"; ctx.fill();
      ctx.beginPath(); ctx.arc(w / 2 - 3, 23, 3.5, 0, Math.PI * 2); ctx.fillStyle = "#FFC2B8"; ctx.fill();
    },
  },
};

// uppercase lines: "\n" breaks a line, and a line longer than WRAP characters wraps at a space
export function signLines(text) {
  const out = [];
  for (const raw of String(text).toUpperCase().split("\n")) {
    let cur = "";
    for (const word of raw.trim().split(/\s+/)) {
      if (cur && (cur + " " + word).length > WRAP) { out.push(cur); cur = word; } else cur = cur ? cur + " " + word : word;
    }
    if (cur) out.push(cur);
  }
  return out;
}

let measureCtx = null;
function textWidth(s, weight) {
  if (!HAS_DOM) return s.length * FONT * 0.66;
  measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
  measureCtx.font = `${weight} ${FONT}px Fredoka`;
  return measureCtx.measureText(s).width;
}

export function signPlane(text, style) {
  const S = SIGN_STYLES[style];
  if (!S) throw new Error(`unknown sign style: ${style}`);
  const L = signLines(text);
  if (!L.length) throw new Error("empty sign text");
  const tw = Math.max(...L.map((s) => textWidth(s, S.weight)));
  const cw = Math.ceil(Math.max(tw + 2 * S.pad[0], FONT * 2.4)), ch = Math.ceil(FONT * 1.04 * L.length + 2 * S.pad[1]);
  const w = cw / (S.px || PX), h = ch / (S.px || PX);
  const map = HAS_DOM ? canvasTex(cw, ch, (ctx) => S.paint(ctx, cw, ch, L)) : null;
  const face = map ? toonMat("#FFFFFF", { map, transparent: !S.depth, alphaTest: 0.5 }) : toonMat("#E9D3A0");
  let mesh;
  if (S.depth) {
    const side = toonMat(S.side);
    mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, S.depth), [side, side, side, side, face, side]);
    mesh.position.z = S.depth / 2;
  } else {
    const geo = new THREE.PlaneGeometry(w, h, S.wave || S.wrap ? 16 : 1, 1);
    if (S.wrap) { // bend round a cylinder of radius `wrap` whose front touches z = 0
      const p = geo.attributes.position;
      for (let k = 0; k < p.count; k++) {
        const a = p.getX(k) / S.wrap;
        p.setXYZ(k, S.wrap * Math.sin(a), p.getY(k), S.wrap * (Math.cos(a) - 1));
      }
      geo.computeVertexNormals();
    }
    mesh = new THREE.Mesh(geo, face);
    mesh.position.z = 0.01;
  }
  mesh.castShadow = true;
  const g = new THREE.Group();
  g.name = `sign:${style}`;
  g.add(mesh);
  if (S.tilt) mesh.rotation.z = (S.tilt * Math.PI) / 180;
  g.userData = { size: { w, h }, style, lines: L, mesh };
  return g;
}

const easeBack = (v) => { v = clamp01(v); const c = 1.70158; return 1 + (c + 1) * Math.pow(v - 1, 3) + c * Math.pow(v - 1, 2); };

export function spawnSign(spec, t = 0) {
  const g = signPlane(spec.text, spec.style || "plank");
  const root = new THREE.Group();
  root.name = "sign";
  root.add(g);
  root.position.set(...(spec.pos || [0, 2, 0]));
  root.rotation.set(...(spec.rot || [0, 0, 0]).map((d) => (d * Math.PI) / 180));
  const born = t + (spec.delay || 0);
  const wave = SIGN_STYLES[spec.style || "plank"].wave;
  const geo = g.userData.mesh.geometry, base = wave ? Float32Array.from(geo.attributes.position.array) : null;
  root.userData = {
    spec, born,
    tick(now) {
      const age = now - born;
      root.visible = age >= 0;
      if (!root.visible) return;
      root.scale.setScalar(age >= 0.35 ? 1 : Math.max(0.01, easeBack(age / 0.35)));
      if (wave) {
        const pos = geo.attributes.position;
        for (let k = 0; k < pos.count; k++) {
          const x = base[3 * k];
          pos.setZ(k, 0.07 * Math.sin(x * 2.4 + age * 3.2) + 0.03 * Math.sin(x * 5.1 - age * 2.1));
        }
        pos.needsUpdate = true;
        geo.computeVertexNormals();
      }
    },
  };
  root.userData.tick(born - 1);
  return root;
}

export function catalog() {
  return { sign_styles: Object.keys(SIGN_STYLES) };
}
