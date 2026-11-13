// Cartoon effects: puffy, chunky, ink-outlined sprites (no realistic particles).
// Pure registry module: nothing touches the DOM at import time; painted textures are made on first use when a
// document exists, so plain node can build and step every effect (tests, catalog.js).
//   makeFx(type, at, seed?, scale = 1, opts = {}) -> THREE.Group   (seed defaults to a hash of type + at;
//                                                   opts.period: beam's seconds per full sweep, default 4)
//   updateFx(g, localT)                                 (poses every sprite for the effect's local time)
// Stateless per t: a sprite's state at localT is a function of (seed, sprite, localT) alone, so seeking == stepping
// and a re-render is identical. localT < 0 hides the effect. Continuous effects (smoke, fire, sparks, steam, glow,
// bubbles, question, beam) run for as long as they exist; bursts (splinters, explosion, splash, flash, debris, gunsmoke) end on
// their own, and splinters / debris come to rest on the ground (world y = 0).
import * as THREE from "three";
import { canvasTex, hash, clamp01, easeOut, INK } from "./core.js";

const HAS_DOM = typeof document !== "undefined";
const PI = Math.PI, TAU = 2 * PI;

// ---------- painted textures (cached; null under node) ----------
const PUFF = [[0.5, 0.58, 0.27], [0.28, 0.62, 0.19], [0.72, 0.62, 0.2], [0.4, 0.38, 0.21], [0.63, 0.4, 0.18]];

function blob(ctx, w, h, circles, grow = 0) {
  ctx.beginPath();
  for (const [x, y, r] of circles) { ctx.moveTo(x * w + (r * w + grow), y * h); ctx.arc(x * w, y * h, r * w + grow, 0, TAU); }
}

// a bumpy cloud: ink rim, a shaded underside, a lit body and a highlight on the top bumps
function paintPuff(base, mid, light, rim = INK) {
  return (ctx, w, h) => {
    blob(ctx, w, h, PUFF, w * 0.035); ctx.fillStyle = rim; ctx.fill();
    blob(ctx, w, h, PUFF); ctx.fillStyle = base; ctx.fill();
    ctx.save(); blob(ctx, w, h, PUFF); ctx.clip();
    ctx.fillStyle = mid;
    for (const [x, y, r] of PUFF) { ctx.beginPath(); ctx.arc((x - 0.04) * w, (y - 0.06) * h, r * w * 0.9, 0, TAU); ctx.fill(); }
    ctx.fillStyle = light;
    for (const [x, y, r] of [PUFF[3], PUFF[4], PUFF[1]]) {
      ctx.beginPath(); ctx.ellipse((x - r * 0.3) * w, (y - r * 0.36) * h, r * w * 0.5, r * w * 0.3, -0.5, 0, TAU); ctx.fill();
    }
    ctx.restore();
  };
}

function flamePath(ctx, cx, by, w, h) {
  ctx.beginPath();
  ctx.moveTo(cx, by);
  ctx.bezierCurveTo(cx - w * 0.62, by, cx - w * 0.66, by - h * 0.42, cx - w * 0.3, by - h * 0.62);
  ctx.quadraticCurveTo(cx - w * 0.34, by - h * 0.76, cx - w * 0.44, by - h * 0.84); // left tongue
  ctx.quadraticCurveTo(cx - w * 0.06, by - h * 0.74, cx - w * 0.04, by - h * 0.6);
  ctx.quadraticCurveTo(cx + w * 0.02, by - h * 0.86, cx + w * 0.02, by - h); // tip
  ctx.quadraticCurveTo(cx + w * 0.3, by - h * 0.78, cx + w * 0.22, by - h * 0.62);
  ctx.quadraticCurveTo(cx + w * 0.4, by - h * 0.66, cx + w * 0.46, by - h * 0.76); // right tongue
  ctx.bezierCurveTo(cx + w * 0.7, by - h * 0.4, cx + w * 0.6, by, cx, by);
  ctx.closePath();
}

function star(ctx, cx, cy, n, r0, r1, jitter = 0) {
  ctx.beginPath();
  for (let k = 0; k < 2 * n; k++) {
    const r = k % 2 ? r1 : r0 * (1 - jitter * hash(k * 3.1));
    const a = (k / (2 * n)) * TAU - PI / 2;
    ctx[k ? "lineTo" : "moveTo"](cx + Math.cos(a) * r, cy + Math.sin(a) * r);
  }
  ctx.closePath();
}

function poly(ctx, pts) {
  ctx.beginPath();
  pts.forEach(([x, y], k) => ctx[k ? "lineTo" : "moveTo"](x, y));
  ctx.closePath();
}

const PAINT = {
  // greyscale, tinted per sprite (smoke dark, steam / foam white)
  puff: [256, 256, paintPuff("#9C9C9C", "#C9C9C9", "#FFFFFF")],
  // white water: splash crowns, foam, steam
  foam: [256, 256, paintPuff("#A9DCF0", "#FFFFFF", "#FFFFFF", "#2B5C8A")],
  // explosion fireball: red-orange base, orange body, yellow highlights; tinted toward black as it burns out
  firepuff: [256, 256, paintPuff("#E4512A", "#FF9A2E", "#FFE45C")],
  flame: [128, 256, (ctx, w, h) => {
    flamePath(ctx, w / 2, h - 6, w * 0.92, h - 12);
    ctx.fillStyle = "#E8452C"; ctx.fill();
    ctx.lineWidth = 5; ctx.strokeStyle = "#8E1F12"; ctx.stroke();
    flamePath(ctx, w / 2, h - 10, w * 0.66, (h - 12) * 0.72); ctx.fillStyle = "#FF8A2A"; ctx.fill();
    flamePath(ctx, w / 2, h - 12, w * 0.38, (h - 12) * 0.42); ctx.fillStyle = "#FFD54A"; ctx.fill();
  }],
  splinter: [128, 40, (ctx) => {
    const pts = [[4, 21], [26, 11], [58, 14], [92, 9], [124, 19], [98, 27], [62, 31], [30, 29]];
    poly(ctx, pts); ctx.lineJoin = "round"; ctx.lineWidth = 7; ctx.strokeStyle = INK; ctx.stroke();
    ctx.fillStyle = "#D9A066"; ctx.fill();
    ctx.strokeStyle = "#9C6534"; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(18, 20); ctx.lineTo(108, 19); ctx.moveTo(40, 25); ctx.lineTo(84, 24); ctx.stroke();
  }],
  spark: [64, 64, (ctx, w) => {
    star(ctx, w / 2, w / 2, 4, w * 0.47, w * 0.13); ctx.fillStyle = "#FF8A2A"; ctx.fill();
    star(ctx, w / 2, w / 2, 4, w * 0.33, w * 0.09); ctx.fillStyle = "#FFF3A6"; ctx.fill();
  }],
  glow: [128, 128, (ctx, w) => {
    const g = ctx.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
    g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.35, "rgba(255,255,255,0.45)"); g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, w);
  }],
  burst: [512, 512, (ctx, w) => {
    star(ctx, w / 2, w / 2, 14, w * 0.49, w * 0.25, 0.35);
    ctx.lineJoin = "round"; ctx.lineWidth = 12; ctx.strokeStyle = "#FF9A2E"; ctx.stroke();
    ctx.fillStyle = "#FFE45C"; ctx.fill();
    star(ctx, w / 2, w / 2, 14, w * 0.34, w * 0.18, 0.3); ctx.fillStyle = "#FFFBE6"; ctx.fill();
  }],
  droplet: [64, 96, (ctx, w, h) => {
    const drop = () => {
      ctx.beginPath(); ctx.moveTo(w / 2, 6);
      ctx.bezierCurveTo(w * 0.62, h * 0.32, w - 8, h * 0.5, w - 8, h * 0.66);
      ctx.arc(w / 2, h * 0.66, w / 2 - 8, 0, PI);
      ctx.bezierCurveTo(8, h * 0.5, w * 0.38, h * 0.32, w / 2, 6); ctx.closePath();
    };
    drop(); ctx.lineWidth = 7; ctx.lineJoin = "round"; ctx.strokeStyle = INK; ctx.stroke();
    ctx.fillStyle = "#FFFFFF"; ctx.fill();
    ctx.save(); drop(); ctx.clip();
    ctx.fillStyle = "#BDE9F7"; ctx.beginPath(); ctx.arc(w * 0.78, h * 0.74, w * 0.36, 0, TAU); ctx.fill(); ctx.restore();
  }],
  rock: [64, 64, (ctx) => {
    const pts = [[10, 22], [26, 7], [46, 10], [58, 28], [52, 50], [30, 58], [9, 44]];
    poly(ctx, pts); ctx.lineJoin = "round"; ctx.lineWidth = 7; ctx.strokeStyle = INK; ctx.stroke();
    ctx.fillStyle = "#8B7F72"; ctx.fill();
    ctx.fillStyle = "#B3A797"; poly(ctx, [[14, 23], [27, 12], [44, 14], [36, 30], [18, 36]]); ctx.fill();
    ctx.fillStyle = "#6A6057"; poly(ctx, [[52, 32], [48, 48], [32, 53], [42, 40]]); ctx.fill();
  }],
  bubble: [64, 64, (ctx, w) => {
    ctx.beginPath(); ctx.arc(w / 2, w / 2, w / 2 - 4, 0, TAU);
    ctx.fillStyle = "rgba(200,240,255,0.35)"; ctx.fill();
    ctx.lineWidth = 3; ctx.strokeStyle = INK; ctx.stroke();
    ctx.beginPath(); ctx.arc(w / 2, w / 2, w / 2 - 8, 0, TAU); ctx.lineWidth = 4; ctx.strokeStyle = "#FFFFFF"; ctx.stroke();
    ctx.beginPath(); ctx.arc(w / 2, w / 2, w / 2 - 15, PI * 1.05, PI * 1.45); ctx.lineWidth = 6; ctx.lineCap = "round"; ctx.stroke();
  }],
  question: [128, 160, (ctx, w, h) => {
    ctx.font = "700 150px Fredoka"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.lineJoin = "round"; ctx.lineWidth = 18; ctx.strokeStyle = INK; ctx.strokeText("?", w / 2, h / 2 + 6);
    ctx.fillStyle = "#FFD400"; ctx.fillText("?", w / 2, h / 2 + 6);
  }],
};
const ASPECT = Object.fromEntries(Object.entries(PAINT).map(([k, [w, h]]) => [k, w / h]));
const texCache = new Map();
function tex(name) {
  if (!HAS_DOM) return null;
  if (!texCache.has(name)) { const [w, h, draw] = PAINT[name]; texCache.set(name, canvasTex(w, h, draw)); }
  return texCache.get(name);
}

// ---------- motion helpers (all pure in local time) ----------
const easeBack = (v) => { v = clamp01(v); const c = 1.70158; return 1 + (c + 1) * Math.pow(v - 1, 3) + c * Math.pow(v - 1, 2); };
// continuous emitter: sprite i of n is first born at i/n of its life, then repeats; -1 until its first birth
const cycle = (lt, i, n, life) => { const t0 = (i / n) * life; return lt < t0 ? -1 : (lt - t0) % life; };
// grows in over `inT`, holds, shrinks to nothing over the last `outT` of `life`
const swell = (a, life, inT, outT) => clamp01(a / inT) * clamp01((life - a) / outT);
const mix = (c1, c2, k) => new THREE.Color(c1).lerp(new THREE.Color(c2), clamp01(k));

// ballistic flight from the origin; comes to rest at y = floor (local) and stays there
function thrown(a, vx, vy, vz, g, floor) {
  const land = (vy + Math.sqrt(vy * vy + 2 * g * -floor)) / g;
  const t = Math.min(a, land);
  return { p: [vx * t, vy * t - 0.5 * g * t * t, vz * t], landed: a >= land, t };
}

// a burst of chunks (splinters, rocks): thrown out, spinning, then lying on the ground until they shrink away
function chunks(r, a, env, { up, out, size, rest = 3.6 }) {
  if (a < 0 || a > rest + 0.6) return null;
  const th = r(0) * TAU;
  const f = thrown(a, Math.cos(th) * out * (0.5 + r(2)), up * (0.55 + 0.45 * r(1)), Math.sin(th) * out * (0.5 + r(2)) * 0.7, 16, env.floor);
  if (f.landed) f.p[1] += 0.02 + 0.01 * r(6);
  return { p: f.p, s: size * (0.7 + 0.6 * r(5)) * clamp01(a / 0.06) * clamp01((rest + 0.6 - a) / 0.6),
    rot: r(3) * TAU + f.t * (r(4) - 0.5) * 26 };
}

// ---------- the registry ----------
// FX[type] = { layers: [{tex, n, blend? ("add"), center?, part(lt, i, r, env) -> {p, s, sx?, rot?, op?, c?} | null}], light? }
// r(k) is the sprite's k-th fixed random number in [0, 1); env.floor = the ground's local y.
export const FX = {
  // dark curly billows: each puff rises on a widening curl, grows, then shrinks away (cartoon dissolve)
  smoke: {
    layers: [{ tex: "puff", n: 14, part: (lt, i, r) => {
      const life = 3.2, a = cycle(lt, i, 14, life);
      if (a < 0) return null;
      const k = a / life;
      return {
        p: [(r(0) - 0.5) * 0.3 + Math.sin(a * 1.7 + r(1) * TAU) * 0.55 * k, 0.15 + a * 1.1, (r(2) - 0.5) * 0.3],
        s: (0.5 + 1.5 * k) * (0.8 + 0.4 * r(3)) * swell(a, life, 0.25, life * 0.22),
        rot: r(4) * TAU + a * (r(5) - 0.5) * 0.8, c: mix("#3B3438", "#77707A", k),
      };
    } }],
  },
  fire: {
    layers: [
      { tex: "flame", n: 3, center: [0.5, 0.04], part: (lt, i, r) => ({
        p: [(i - 1) * 0.32, 0, (r(0) - 0.5) * 0.1 + (i === 1 ? 0.05 : 0)],
        s: (i === 1 ? 1.5 : 1.1) * (1 + 0.08 * Math.sin(lt * 13 + i * 2.1)) * easeBack(lt / 0.3),
        sx: 1 + 0.1 * Math.sin(lt * 17 + i), rot: 0.12 * Math.sin(lt * 5 + i * 1.7) - (i - 1) * 0.15,
      }) },
      { tex: "flame", n: 9, center: [0.5, 0.04], part: (lt, i, r) => {
        const life = 0.75, a = cycle(lt, i, 9, life);
        if (a < 0) return null;
        const k = a / life;
        return { p: [(r(0) - 0.5) * 0.85 * (1 - 0.5 * k), 0.1 + a * 1.1, (r(1) - 0.5) * 0.4],
          s: (0.55 + 0.4 * r(2)) * swell(a, life, 0.12, life * 0.7), sx: 1 + 0.15 * Math.sin(lt * 21 + i),
          rot: (r(3) - 0.5) * 0.5 };
      } },
    ],
    light: { color: "#FF8A3A", dist: 7, i: (lt) => clamp01(lt / 0.3) * (9 + 2 * Math.sin(lt * 11) + 1.5 * Math.sin(lt * 17.3)) },
  },
  splinters: {
    layers: [
      { tex: "splinter", n: 22, part: (lt, i, r, env) => chunks(r, lt, env, { up: 7.5, out: 3.6, size: 0.22 }) },
      { tex: "puff", n: 5, part: (lt, i, r) => {
        if (lt > 0.45) return null;
        const th = (i / 5) * TAU + r(0);
        return { p: [Math.cos(th) * lt * 1.6, Math.sin(th) * lt * 1.2 + 0.1, 0.1], s: 0.7 * swell(lt, 0.45, 0.08, 0.3),
          rot: r(1) * TAU, c: "#EED9B8" };
      } },
    ],
  },
  sparks: {
    layers: [{ tex: "spark", n: 18, part: (lt, i, r) => {
      const life = 0.8, a = cycle(lt, i, 18, life);
      if (a < 0) return null;
      const th = r(0) * TAU, out = 1 + 2 * r(2), up = 2.2 + 3 * r(1);
      return { p: [Math.cos(th) * out * a, up * a - 4.5 * a * a, Math.sin(th) * out * a],
        s: 0.1 + 0.26 * (1 - a / life), rot: th + a * 9 };
    } }],
    light: { color: "#FFC060", dist: 4, i: (lt) => (lt < 0 ? 0 : 3 + Math.sin(lt * 29)) },
  },
  explosion: {
    layers: [
      { tex: "burst", n: 1, part: (lt) => (lt > 0.4 ? null : {
        p: [0, 0.9, -0.4], s: 4.6 * easeOut(lt / 0.1) * clamp01((0.4 - lt) / 0.25), rot: lt * 0.8 }) },
      { tex: "firepuff", n: 15, part: (lt, i, r) => {
        const life = 1.1 + 0.6 * r(5);
        if (lt > life) return null;
        const th = r(0) * TAU, ph = Math.acos(1 - 2 * r(1));
        const d = (0.5 + 1.3 * r(2)) * easeOut(lt / 0.45);
        return { p: [Math.cos(th) * Math.sin(ph) * d, 0.9 + Math.abs(Math.cos(ph)) * d * 0.9 + lt * 0.45, Math.sin(th) * Math.sin(ph) * d * 0.6],
          s: (1.05 + 0.9 * r(3)) * easeBack(lt / 0.22) * clamp01((life - lt) / (life * 0.45)),
          rot: r(4) * TAU, c: mix("#FFFFFF", "#D2603C", (lt - 0.25) / 0.7) };
      } },
      { tex: "puff", n: 8, part: (lt, i, r) => {
        const a = lt - (0.25 + 0.25 * r(0)), life = 2.6;
        if (a < 0 || a > life) return null;
        return { p: [(r(1) - 0.5) * 2.2, 1.9 + a * 0.75 + r(2) * 0.6, (r(3) - 0.5) * 0.8 - 0.3],
          s: (1.1 + 0.9 * a / life) * (0.8 + 0.4 * r(4)) * swell(a, life, 0.3, 0.9), rot: r(5) * TAU + a * 0.3,
          c: "#2E2A30" };
      } },
      { tex: "spark", n: 12, part: (lt, i, r) => {
        if (lt > 1.1) return null;
        const th = r(0) * TAU, out = 3 + 3 * r(1), up = 3 + 4 * r(2);
        return { p: [Math.cos(th) * out * lt, 0.9 + up * lt - 6 * lt * lt, Math.sin(th) * out * lt * 0.6],
          s: 0.3 * (1 - lt / 1.1), rot: th + lt * 8 };
      } },
    ],
    light: { color: "#FFB050", dist: 16, i: (lt) => (lt < 0 ? 0 : 70 * Math.exp(-lt * 2.6)) },
  },
  splash: {
    layers: [
      { tex: "droplet", n: 20, part: (lt, i, r, env) => {
        const th = r(0) * TAU, out = 0.9 + 1.6 * r(1), up = 4.5 + 3 * r(2), life = 1.45;
        if (lt > life) return null;
        const vx = Math.cos(th) * out, vz = Math.sin(th) * out * 0.6, vy = up - 9 * lt;
        const y = up * lt - 4.5 * lt * lt;
        if (lt > 0.3 && y < env.floor - 0.2) return null;
        return { p: [vx * lt, y, vz * lt], s: (0.24 + 0.18 * r(3)) * clamp01(lt / 0.05) * clamp01((life - lt) / 0.3),
          rot: Math.atan2(vx, vy) };
      } },
      { tex: "foam", n: 7, part: (lt, i, r) => {
        const life = 1.15;
        if (lt > life) return null;
        const th = (i / 7) * TAU + r(0) * 0.4, rad = 0.35 + 0.55 * easeOut(lt / 0.5);
        return { p: [Math.cos(th) * rad, 0.15 + 1.3 * Math.sin(PI * clamp01(lt / life)) * (0.6 + 0.4 * r(1)), Math.sin(th) * rad * 0.5],
          s: (0.75 + 0.3 * r(2)) * swell(lt, life, 0.12, 0.45), rot: r(3) * TAU, c: "#FFFFFF" };
      } },
      { tex: "foam", n: 8, part: (lt, i, r) => {
        const life = 1.6;
        if (lt > life) return null;
        const th = (i / 8) * TAU + r(0) * 0.3, rad = 0.6 + 1.0 * easeOut(lt / 0.8);
        return { p: [Math.cos(th) * rad, 0.05, Math.sin(th) * rad * 0.55], s: (0.6 + 0.25 * r(1)) * swell(lt, life, 0.15, 0.6),
          sx: 1.4, rot: (r(2) - 0.5) * 0.4, c: "#FFFFFF" };
      } },
    ],
  },
  steam: {
    layers: [{ tex: "foam", n: 10, part: (lt, i, r) => {
      const life = 1.6, a = cycle(lt, i, 10, life);
      if (a < 0) return null;
      const k = a / life;
      return { p: [(r(0) - 0.5) * 0.25 + Math.sin(a * 3 + r(1) * TAU) * 0.18 * k, 0.1 + a * 1.5, (r(2) - 0.5) * 0.2],
        s: (0.3 + 0.8 * k) * (0.85 + 0.3 * r(3)) * clamp01(a / 0.15), op: 0.9 * (1 - k * k), rot: r(4) * TAU,
        c: "#FFFFFF" };
    } }],
  },
  glow: {
    layers: [
      { tex: "glow", n: 1, blend: "add", part: (lt) => ({ p: [0, 0, 0], s: 3.4 * (1 + 0.06 * Math.sin(lt * 3)),
        op: 0.7 * clamp01(lt / 0.3), c: "#FFB347" }) },
      { tex: "glow", n: 1, blend: "add", part: (lt) => ({ p: [0, 0, 0.01], s: 1.4 * (1 + 0.05 * Math.sin(lt * 4.3 + 1)),
        op: 0.9 * clamp01(lt / 0.3), c: "#FFF0C0" }) },
    ],
    light: { color: "#FFB347", dist: 9, i: (lt) => clamp01(lt / 0.3) * 6 * (1 + 0.1 * Math.sin(lt * 3)) },
  },
  flash: {
    layers: [
      { tex: "glow", n: 1, blend: "add", part: (lt) => (lt > 0.6 ? null : { p: [0, 0, -0.05], s: 9 * easeOut(lt / 0.08),
        op: clamp01((0.6 - lt) / 0.45), c: "#FFFFFF" }) },
      { tex: "burst", n: 1, part: (lt) => (lt > 0.6 ? null : { p: [0, 0, 0], s: 3.6 * easeBack(lt / 0.12),
        op: clamp01((0.6 - lt) / 0.3), rot: lt * 1.2 }) },
    ],
    light: { color: "#FFFFFF", dist: 20, i: (lt) => (lt < 0 ? 0 : 80 * Math.exp(-lt * 7)) },
  },
  debris: {
    layers: [
      { tex: "rock", n: 14, part: (lt, i, r, env) => chunks(r, lt, env, { up: 6, out: 2.4, size: 0.34 }) },
      { tex: "puff", n: 6, part: (lt, i, r) => {
        const life = 1.3;
        if (lt > life) return null;
        const th = (i / 6) * TAU + r(0);
        return { p: [Math.cos(th) * (0.3 + lt * 1.2), 0.25 + lt * 0.5, Math.sin(th) * 0.3], s: (0.8 + 0.5 * r(1)) * swell(lt, life, 0.12, 0.6),
          rot: r(2) * TAU, c: "#C9B79C" };
      } },
    ],
  },
  bubbles: {
    layers: [{ tex: "bubble", n: 12, part: (lt, i, r) => {
      const life = 2.2, a = cycle(lt, i, 12, life);
      if (a < 0 || a > life * 0.94) return null;
      return { p: [(r(0) - 0.5) * 0.8 + Math.sin(a * 4 + r(1) * TAU) * 0.12, a * 1.1, (r(2) - 0.5) * 0.4],
        s: (0.14 + 0.16 * r(3)) * (1 + 0.4 * a / life) * clamp01(a / 0.12) };
    } }],
  },
  question: {
    layers: [{ tex: "question", n: 3, part: (lt, i) => {
      const a = lt - [0, 0.2, 0.32][i];
      if (a < 0) return null;
      return { p: [[0, -0.55, 0.5][i], [0, -0.25, -0.15][i] + 0.1 * Math.sin(a * 3 + i), 0], s: [0.9, 0.45, 0.4][i] * easeBack(a / 0.35),
        rot: [0, 0.35, -0.3][i] + 0.14 * Math.sin(a * 2.3 + i * 1.3) };
    } }],
  },
  // a gun's muzzle blast: a flash burst, a fireball punching out along local +x, then white smoke clouds bloom down
  // the line and hang (the engine turns the group to the barrel's direction)
  gunsmoke: {
    layers: [
      { tex: "burst", n: 1, part: (lt) => (lt > 0.16 ? null : { p: [0.35, 0, 0], s: 1.9 * easeBack(lt / 0.05) * clamp01((0.16 - lt) / 0.08),
        rot: lt * 2 }) },
      { tex: "firepuff", n: 4, part: (lt, i, r) => (lt > 0.22 ? null : {
        p: [0.15 + i * 0.32 * easeOut(lt / 0.08), (r(0) - 0.5) * 0.15, (r(1) - 0.5) * 0.15],
        s: (0.75 - i * 0.12) * easeBack(lt / 0.06) * clamp01((0.22 - lt) / 0.12), rot: r(2) * TAU,
        c: mix("#FFFFFF", "#FF9A2E", lt / 0.15) }) },
      { tex: "puff", n: 9, part: (lt, i, r) => {
        const a = lt - 0.03 * i, life = 1.7 + 0.5 * r(0);
        if (a < 0 || a > life) return null;
        const d = (0.25 + i * 0.3) * easeOut(a / 0.35);
        return { p: [d, (r(1) - 0.5) * 0.35 + a * 0.22, (r(2) - 0.5) * 0.35],
          s: (0.6 + 0.1 * i + 0.5 * a / life) * (0.85 + 0.3 * r(3)) * swell(a, life, 0.12, 0.6),
          rot: r(4) * TAU + a * 0.4, c: mix("#FFFFFF", "#D8D4DA", a / life) };
      } },
    ],
    light: { color: "#FFC070", dist: 6, i: (lt) => (lt < 0 ? 0 : 10 * Math.exp(-lt * 14)) },
  },
  // a lighthouse beam: a soft cone of light from its point (local +x at the start), sweeping round the vertical axis
  // once per `period` seconds (opts.period, default 4), with a glowing core at the source
  beam: {
    layers: [
      { tex: "glow", n: 1, blend: "add", part: (lt) => ({ p: [0, 0, 0.02], s: 1.2 * (1 + 0.05 * Math.sin(lt * 5)), op: 0.75, c: "#FFE28A" }) },
      { tex: "glow", n: 1, blend: "add", part: (lt) => ({ p: [0, 0, 0.03], s: 0.5 * (1 + 0.04 * Math.sin(lt * 7 + 1)), op: 1, c: "#FFFFFF" }) },
    ],
    cone: { length: 26, radius: 2.4, color: "#FFF0B0", strength: 0.5 },
    light: { color: "#FFE9A8", dist: 9, i: (lt) => (lt < 0 ? 0 : 3) },
  },
};

// the beam's cone: narrow at the origin, opening along +x; brightest along its axis and near its source, soft at its
// silhouette (additive, so it brightens what it crosses and never hides it)
function beamCone({ length, radius, color, strength }) {
  const geo = new THREE.CylinderGeometry(0.1, radius, length, 40, 8, true);
  geo.translate(0, -length / 2, 0); // the narrow end (uv.y = 1) at the origin
  geo.rotateZ(PI / 2); // opens along +x
  const m = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, fog: false,
    uniforms: { color: { value: new THREE.Color(color) }, strength: { value: strength } },
    vertexShader: "varying vec2 vUv; varying vec3 vN; varying vec3 vV;\n" +
      "void main(){ vUv = uv; vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);\n" +
      "  gl_Position = projectionMatrix * mv; }",
    fragmentShader: "uniform vec3 color; uniform float strength; varying vec2 vUv; varying vec3 vN; varying vec3 vV;\n" +
      "void main(){ float along = pow(vUv.y, 2.0); float edge = pow(abs(dot(normalize(vN), normalize(vV))), 2.6);\n" +
      "  gl_FragColor = vec4(color * strength * along * edge, 1.0);\n#include <colorspace_fragment>\n}",
  });
  const cone = new THREE.Mesh(geo, m);
  cone.name = "beam-cone";
  cone.renderOrder = 2;
  return cone;
}

// ---------- build and pose ----------
const typeSeed = (type, at) => [...type].reduce((s, ch) => s + ch.charCodeAt(0) * 31, 0) + at[0] * 7.13 + at[1] * 3.31 + at[2] * 5.77;

export function makeFx(type, at = [0, 0, 0], seed = null, scale = 1, opts = {}) {
  const def = FX[type];
  if (!def) throw new Error(`unknown fx: ${type}`);
  const period = (opts && opts.period) ?? 4;
  if (def.cone && !(period > 0)) throw new Error(`beam period must be > 0 (got ${period})`);
  const g = new THREE.Group();
  g.name = `fx:${type}`;
  g.position.set(...at);
  g.scale.setScalar(scale);
  const parts = [];
  def.layers.forEach((L, li) => {
    for (let i = 0; i < L.n; i++) {
      const add = L.blend === "add";
      const m = new THREE.SpriteMaterial({ map: tex(L.tex), transparent: true, depthWrite: false, alphaTest: 0.02, fog: false,
        blending: add ? THREE.AdditiveBlending : THREE.NormalBlending });
      const s = new THREE.Sprite(m);
      if (L.center) s.center.set(...L.center);
      s.visible = false;
      s.userData = { li, i };
      g.add(s);
      parts.push(s);
    }
  });
  let light = null;
  if (def.light) {
    light = new THREE.PointLight(def.light.color, 0, def.light.dist * scale, 1.3);
    light.position.set(0, 0.6, 0.4);
    g.add(light);
  }
  let beam = null; // the cone's pivot: turned about y by updateFx
  if (def.cone) {
    beam = new THREE.Group();
    beam.add(beamCone(def.cone));
    g.add(beam);
  }
  g.userData = { type, seed: seed ?? typeSeed(type, at), parts, light, beam, period, floor: Math.min(0, -at[1] / scale) };
  return g;
}

export function updateFx(g, lt) {
  const { type, seed, parts, light, floor, beam, period } = g.userData;
  const def = FX[type];
  g.visible = lt >= 0;
  if (light) light.intensity = lt >= 0 ? def.light.i(lt) : 0;
  if (beam) beam.rotation.y = lt >= 0 ? (TAU * lt) / period : 0;
  if (!g.visible) return g;
  const env = { floor };
  for (const s of parts) {
    const { li, i } = s.userData, L = def.layers[li];
    const r = (k) => hash(seed * 0.1371 + li * 91.7 + i * 13.13 + k * 1.711);
    const st = L.part(lt, i, r, env);
    s.visible = !!st && st.s > 1e-3;
    if (!s.visible) { // a hidden sprite is reset too, so the whole group is a function of localT alone
      s.position.set(0, 0, 0); s.scale.set(1, 1, 1); s.material.rotation = 0; s.material.opacity = 1;
      continue;
    }
    s.position.set(...st.p);
    s.scale.set(st.s * ASPECT[L.tex] * (st.sx || 1), st.s, 1);
    s.material.rotation = st.rot || 0;
    s.material.opacity = st.op ?? 1;
    s.material.color.set(st.c || "#FFFFFF");
  }
  return g;
}

export function catalog() {
  return { fx: Object.keys(FX) };
}
