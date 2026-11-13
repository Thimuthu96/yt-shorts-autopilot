// Action library (story v2): compound actions tied to words, joined into events.js EVENT_TYPES.
// Pure module: nothing touches the DOM at import time.
//   fire    {who: cannon|pistol prop, projectile?, to?, dur?, surface?, impact?, stay?, scale?}
//           recoil (RECOIL s), the gunsmoke fx (flash, fireball, smoke) at the muzzle; with `projectile` + `to` it launches
//           that prop
//   launch  {who: prop, to, dur?, surface?, impact?, stay?, scale?}   ballistic arc from where the prop is to `to`
//           over `dur` (default flightDur by distance); on arrival an impact fx chosen by `surface` (SURFACES) or
//           named by `impact` ("none" = no fx); the prop then stays at `to` (debris / none) or is gone (`stay` overrides)
//   impact  {at, surface? | impact?, scale?}   an impact burst on its word
//   fly_off {who: prop, dir, dist? (5), dur? (0.9)}   the prop tumbles away from where it is (out of a hand too)
//   act     {who: character, act, expr?, ...}   ACTS below; `expr` overrides the act's own expression
// Every impact (launch arrival or impact event) squashes and stretches the characters within SQUASH_R units.
// Effects reach the engine through the per-frame ctx (events.js applyEvents), never through stored state:
//   prop spec: track(now) / kick(now) (world.js placeProp), chained by time so any past moment can be asked for;
//   char spec: acts [{t0, fn}] folded by actState(); pose / facing / act (offsets) / holding / runs / squash for t;
//   ctx.fx: [{key, shot, type, at, born, scale, rotY?}] fx the engine draws, each hidden until its `born`.
import { EXPRS, handAt, charPosAt } from "./cast.js";
import { propPosAt, muzzle, restHeight } from "./world.js";
import { clamp01, easeOut } from "./core.js";

export const RECOIL = 0.25; // seconds for a gun to kick back and settle
export const RELEASE = 0.18; // seconds from a throw's word to the prop leaving the hand
export const SQUASH_R = 1.5, SQUASH_DUR = 0.45;
const RUN_SPEED = 4, GRAVITY = 9.8, PI = Math.PI;
export const SURFACES = { wood: "splinters", water: "splash", stone: "debris", ground: "debris", powder: "explosion" };
const IMPACTS = ["splinters", "splash", "debris", "explosion", "none"];

// ---------- checks ----------
const need = (ev, key, label = "") => { if (ev[key] == null || ev[key] === "") throw new Error(label ? `${label} needs ${key}` : `needs ${key}`); };
const isVec = (v) => Array.isArray(v) && v.length === 3 && v.every((x) => typeof x === "number" && Number.isFinite(x));
function vec(ev, key, label = "") {
  if (ev[key] == null) throw new Error(label ? `${label}: ${key} must be [x, y, z]` : `needs ${key}`);
  if (!isVec(ev[key])) throw new Error(`${label ? label + ": " : ""}${key} must be [x, y, z]`);
}
const positive = (ev, key) => { if (ev[key] != null && !(typeof ev[key] === "number" && ev[key] > 0)) throw new Error(`${key} must be a number > 0`); };
function landing(ev) {
  if (ev.surface != null && !SURFACES[ev.surface]) throw new Error(`unknown surface: ${ev.surface}`);
  if (ev.impact != null && !IMPACTS.includes(ev.impact)) throw new Error(`unknown impact: ${ev.impact}`);
  positive(ev, "dur"); positive(ev, "scale");
}
const impactType = (ev) => ev.impact ?? SURFACES[ev.surface ?? "ground"];

// ---------- ctx helpers ----------
function propOf(ctx, id) {
  const p = ctx.props.get(id);
  if (!p) throw new Error(`no prop ${id} on stage`);
  return p;
}
function charOf(ctx, id) {
  const s = ctx.chars.get(id);
  if (!s) throw new Error(`no character ${id} on stage`);
  return s;
}
const posOf = (p, now) => propPosAt(p, p.spawnT || 0, now);
function targetPos(ctx, id, t) {
  if (ctx.chars.has(id)) return charPosAt(ctx.chars.get(id), t);
  if (ctx.props.has(id)) return posOf(ctx.props.get(id), t);
  throw new Error(`no character or prop ${id} on stage`);
}
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const lerp3 = (a, b, k) => a.map((v, i) => v + (b[i] - v) * k);
const rad = (rot) => (rot || [0, 0, 0]).map((d) => (d * PI) / 180);
const dirOf = (facing) => (facing === "left" ? -1 : 1);
// a track that takes over from `t0` on; before it the earlier one answers
const chain = (prev, t0, mine) => (now) => (now < t0 ? (prev ? prev(now) : null) : mine(now));

// ---------- flights ----------
export const flightDur = (from, to) => Math.min(2.5, 0.45 + dist(from, to) / 16);
// the arc rises h above the straight line at its middle, so its apex is above both ends
export function flight(from, to, t0, dur) {
  const h = Math.max(0.6, 0.1 * dist(from, to), Math.abs(to[1] - from[1]) / 2 + 0.5);
  return { from: [...from], to: [...to], t0, dur, h };
}
export function flightPos(f, now) {
  const u = clamp01((now - f.t0) / f.dur);
  const p = lerp3(f.from, f.to, u);
  p[1] += 4 * f.h * u * (1 - u);
  return p;
}

// squash then stretch then settle, for u seconds after an impact
function squash(s, u) {
  const k = Math.sin((2 * PI * u) / SQUASH_DUR) * (1 - u / SQUASH_DUR);
  const q = s.squash || { sx: 1, sy: 1 };
  s.squash = { sx: q.sx * (1 + 0.22 * k), sy: q.sy * (1 - 0.3 * k) };
}

// an impact burst at `at` from `born` on (fx key: this event's key + n), and the squash of characters near it
function impact(ctx, { type, at, born, scale }, n) {
  if (type !== "none") ctx.fx.push({ key: `${ctx.key}:${n}`, shot: ctx.shot, type, at: [...at], born, scale: scale ?? 1 });
  const u = ctx.t - born;
  if (!(u >= 0 && u < SQUASH_DUR)) return;
  ctx.chars.forEach((s) => {
    const p = charPosAt(s, born);
    if (Math.hypot(p[0] - at[0], p[2] - at[2]) <= SQUASH_R) squash(s, u);
  });
}

// prop p flies from `from` (at t0) to ev.to; the arrival makes its impact
function launchProp(ctx, p, from, t0, ev, n) {
  const dur = ev.dur ?? flightDur(from, ev.to), f = flight(from, ev.to, t0, dur);
  const type = impactType(ev), stay = ev.stay ?? (type === "debris" || type === "none"), r0 = rad(p.rot);
  p.track = chain(p.track, t0, (now) => {
    const a = Math.min(now, t0 + dur) - t0;
    return { pos: flightPos(f, now), rot: [r0[0] + a * 5, r0[1], r0[2] - a * 9], visible: now < t0 + dur || stay };
  });
  impact(ctx, { type, at: ev.to, born: t0 + dur, scale: ev.scale }, n);
  return f;
}

// ---------- characters ----------
// acts fold in time order; each fn(u, before) returns the fields it sets: pose, facing, off (offsets; null clears)
export function pushAct(s, t0, fn) {
  if (!s.acts) s.base = { pose: s.pose, facing: s.facing };
  s.acts = [...(s.acts || []), { t0, fn }];
}
export function actState(s, now) {
  if (!s.acts) return { pose: s.pose, facing: s.facing, off: s.act || null };
  let st = { pose: s.base.pose, facing: s.base.facing, off: null };
  for (const a of s.acts) if (a.t0 <= now) st = { ...st, ...a.fn(now - a.t0, st) };
  return st;
}
// this frame's pose / facing / offsets from the acts
export function refresh(s, now) {
  const st = actState(s, now);
  s.pose = st.pose; s.facing = st.facing;
  if (st.off) s.act = st.off; else delete s.act;
}
// where a prop held by character spec s is at `now` (the prop's origin is its grip)
export function heldPos(s, now) {
  const st = actState(s, now);
  return handAt({ ...s, pose: st.pose, facing: st.facing, act: st.off || undefined }, now);
}
function heldRot(s, now, r0) {
  const st = actState(s, now);
  const tilt = st.pose === "drink" ? 1.1 : st.pose === "toast" ? -0.25 : 0;
  return [r0[0], r0[1] + (st.facing === "left" ? PI : 0), r0[2] + tilt];
}
// prop `id` rides s's hand from t0 (+ reach: it stays put, then flies to the hand over 0.15 s)
function holdProp(ctx, s, id, t0, reach = 0) {
  const p = propOf(ctx, id), start = posOf(p, t0), r0 = rad(p.rot);
  p.track = chain(p.track, t0, (now) => {
    const k = clamp01((now - t0 - reach) / 0.15);
    if (reach && k <= 0) return { pos: start };
    const h = heldPos(s, now);
    return { pos: reach && k < 1 ? lerp3(start, h, easeOut(k)) : h, rot: heldRot(s, now, r0) };
  });
  if (ctx.t - t0 >= reach) s.holding = id;
}
const facingTo = (ctx, s, id, t0) => (targetPos(ctx, id, t0)[0] < charPosAt(s, t0)[0] ? "left" : "right");

// ACTS[name] = {expr?: default expression, validate?(ev), apply(ctx, ev, dt, s, t0)}; s = the character's spec
export const ACTS = {
  hold: {
    validate: (ev) => need(ev, "prop", "hold"),
    apply: (ctx, ev, dt, s, t0) => { holdProp(ctx, s, ev.prop, t0); pushAct(s, t0, () => ({ pose: "carry", off: null })); },
  },
  drink: {
    expr: "happy",
    apply: (ctx, ev, dt, s, t0) => {
      if (ev.prop) holdProp(ctx, s, ev.prop, t0);
      pushAct(s, t0, (u, st) => (u >= 0.15 && u < 1.3 ? { pose: "drink", off: { tilt: 0.08 * dirOf(st.facing) } } : { pose: "carry", off: null }));
    },
  },
  toast: {
    expr: "happy",
    apply: (ctx, ev, dt, s, t0) => {
      if (ev.prop) holdProp(ctx, s, ev.prop, t0);
      pushAct(s, t0, (u) => ({ pose: "toast", off: { y: 0.07 * Math.abs(Math.sin(u * 10)) * Math.exp(-u * 3) } }));
    },
  },
  throw: {
    validate: (ev) => { vec(ev, "to", "throw"); landing(ev); },
    apply: (ctx, ev, dt, s, t0) => {
      const id = ev.prop || s.holding;
      if (!id) throw new Error("throw needs prop (or a held one)");
      if (s.holding !== id) holdProp(ctx, s, id, t0);
      pushAct(s, t0, (u) => ({ pose: u < RELEASE ? "throw_wind" : u < 0.7 ? "throw" : "idle", off: null }));
      const rel = t0 + RELEASE;
      launchProp(ctx, propOf(ctx, id), heldPos(s, rel), rel, ev, 0);
      if (ctx.t >= rel) delete s.holding;
    },
  },
  duck: {
    expr: "scared",
    apply: (ctx, ev, dt, s, t0) => pushAct(s, t0, (u) => {
      const e = easeOut(u / 0.12);
      return { pose: "duck", off: { sy: 1 - 0.2 * e, sx: 1 + 0.08 * e } };
    }),
  },
  cower: {
    expr: "scared",
    apply: (ctx, ev, dt, s, t0) => pushAct(s, t0, (u) => ({ pose: "cower", off: { sy: 1 - 0.1 * easeOut(u / 0.1), x: 0.025 * Math.sin(u * 47) } })),
  },
  grab: {
    validate: (ev) => need(ev, "prop", "grab"),
    apply: (ctx, ev, dt, s, t0) => {
      holdProp(ctx, s, ev.prop, t0, 0.12);
      pushAct(s, t0, (u) => ({ pose: u < 0.3 ? "grab" : "carry", off: null }));
    },
  },
  run_to: {
    validate: (ev) => { vec(ev, "pos", "run_to"); positive(ev, "speed"); },
    apply: (ctx, ev, dt, s, t0) => {
      const from = charPosAt(s, t0);
      s.runs = [...(s.runs || []), { t0, from, to: [...ev.pos], dur: Math.max(0.25, dist(from, ev.pos) / (ev.speed ?? RUN_SPEED)) }];
      const dx = ev.pos[0] - from[0];
      if (Math.abs(dx) > 1e-6) pushAct(s, t0, () => ({ facing: dx < 0 ? "left" : "right" }));
    },
  },
  point_at: {
    validate: (ev) => need(ev, "id", "point_at"),
    apply: (ctx, ev, dt, s, t0) => { const facing = facingTo(ctx, s, ev.id, t0); pushAct(s, t0, () => ({ pose: "point", facing, off: null })); },
  },
  look_at: {
    validate: (ev) => need(ev, "id", "look_at"),
    apply: (ctx, ev, dt, s, t0) => { const facing = facingTo(ctx, s, ev.id, t0); pushAct(s, t0, () => ({ facing })); },
  },
  jump: {
    expr: "excited",
    apply: (ctx, ev, dt, s, t0) => pushAct(s, t0, (u) => {
      if (u < 0.08) return { off: { sy: 1 - 0.15 * Math.sin((u / 0.08) * (PI / 2)), sx: 1.06 } };
      if (u < 0.63) { const v = (u - 0.08) / 0.55; return { pose: "armsUp", off: { y: 2.8 * v * (1 - v), sy: 1.06, sx: 0.96 } }; }
      if (u < 0.8) return { off: { sy: 1 - 0.15 * Math.sin(((u - 0.63) / 0.17) * PI), sx: 1.06 } };
      return {}; // landed: back to whatever came before
    }),
  },
  fall: {
    expr: "shocked",
    apply: (ctx, ev, dt, s, t0) => pushAct(s, t0, (u, st) => {
      const d = dirOf(st.facing), f = clamp01((u - 0.1) / 0.45);
      const bounce = u > 0.55 && u < 0.8 ? Math.sin(((u - 0.55) / 0.25) * PI) * 0.06 : 0;
      return { pose: "fall", off: { tilt: d * (PI / 2) * f * f - d * bounce } };
    }),
  },
};

// ---------- event types (events.js merges these into EVENT_TYPES) ----------
export const ACTION_TYPES = {
  fire: {
    scope: "prop",
    validate: (ev) => { need(ev, "who"); if (ev.projectile != null) { vec(ev, "to"); landing(ev); } },
    apply: (ctx, ev, dt) => {
      const p = propOf(ctx, ev.who), t0 = ctx.t - dt, m = muzzle(p, t0), k = p.scale || 1;
      const prev = p.kick;
      p.kick = (now) => {
        const before = prev ? prev(now) : null, u = now - t0;
        const r = u < 0 || u >= RECOIL ? 0 : 0.38 * k * (u < 0.04 ? u / 0.04 : Math.pow(1 - (u - 0.04) / (RECOIL - 0.04), 2));
        const pos = m.dir.map((v, i) => -v * r + (before ? before.pos[i] : 0));
        return { pos, rotZ: (before ? before.rotZ : 0) + 0.32 * r };
      };
      const rotY = Math.atan2(-m.dir[2], m.dir[0]);
      ctx.fx.push({ key: `${ctx.key}:0`, shot: ctx.shot, type: "gunsmoke", at: m.pos, born: t0, scale: k, rotY });
      if (ev.projectile != null) launchProp(ctx, propOf(ctx, ev.projectile), m.pos, t0, ev, 2);
    },
  },
  launch: {
    scope: "prop",
    validate: (ev) => { need(ev, "who"); vec(ev, "to"); landing(ev); },
    apply: (ctx, ev, dt) => { const p = propOf(ctx, ev.who), t0 = ctx.t - dt; launchProp(ctx, p, posOf(p, t0), t0, ev, 0); },
  },
  impact: {
    scope: "scene",
    validate: (ev) => { vec(ev, "at"); landing(ev); },
    apply: (ctx, ev, dt) => impact(ctx, { type: impactType(ev), at: ev.at, born: ctx.t - dt, scale: ev.scale }, 0),
  },
  fly_off: {
    scope: "prop",
    validate: (ev) => { need(ev, "who"); vec(ev, "dir"); if (Math.hypot(...ev.dir) < 1e-9) throw new Error("dir must not be zero"); positive(ev, "dist"); positive(ev, "dur"); },
    apply: (ctx, ev, dt) => {
      const p = propOf(ctx, ev.who), t0 = ctx.t - dt, start = posOf(p, t0), r0 = rad(p.rot);
      ctx.chars.forEach((s) => { if (s.holding === ev.who) delete s.holding; });
      const n = Math.hypot(...ev.dir), speed = (ev.dist ?? 5) / (ev.dur ?? 0.9);
      const v = ev.dir.map((x) => (x / n) * speed);
      v[1] += 2.5; // a little hop up before it falls
      const floor = restHeight(p), drop = Math.max(0, start[1] - floor);
      const land = (v[1] + Math.sqrt(v[1] * v[1] + 2 * GRAVITY * drop)) / GRAVITY;
      p.track = chain(p.track, t0, (now) => {
        const a = Math.min(now - t0, land);
        return { pos: [start[0] + v[0] * a, start[1] + v[1] * a - 0.5 * GRAVITY * a * a, start[2] + v[2] * a],
          rot: [r0[0] + a * 7, r0[1] + a * 3, r0[2] + a * 11] };
      });
    },
  },
  act: {
    scope: "char",
    validate: (ev) => {
      need(ev, "who"); need(ev, "act");
      const a = ACTS[ev.act];
      if (!a) throw new Error(`unknown act: ${ev.act}`);
      if (ev.expr != null && !EXPRS.includes(ev.expr)) throw new Error(`unknown expr: ${ev.expr}`);
      if (a.validate) a.validate(ev);
    },
    apply: (ctx, ev, dt) => {
      const s = charOf(ctx, ev.who), a = ACTS[ev.act], t0 = ctx.t - dt;
      a.apply(ctx, ev, dt, s, t0);
      const expr = ev.expr ?? a.expr;
      if (expr) s.expr = expr;
      refresh(s, ctx.t);
    },
  },
};

// Fields per event / act for the catalog (need = required, opt = optional); events.js adds ACTION_FIELDS to its own.
const LANDING = ["dur", "surface", "impact", "stay", "scale"];
export const ACTION_FIELDS = {
  fire: { need: ["who"], opt: ["projectile", "to", ...LANDING] }, // `to` is required with a projectile
  launch: { need: ["who", "to"], opt: LANDING },
  impact: { need: ["at"], opt: ["surface", "impact", "scale"] },
  fly_off: { need: ["who", "dir"], opt: ["dist", "dur"] },
  act: { need: ["who", "act"], opt: ["expr"] }, // plus the act's own fields (act_fields)
};
const ACT_FIELDS = {
  hold: { need: ["prop"] }, drink: { opt: ["prop"] }, toast: { opt: ["prop"] }, throw: { need: ["to"], opt: ["prop", ...LANDING] },
  duck: {}, cower: {}, grab: { need: ["prop"] }, run_to: { need: ["pos"], opt: ["speed"] },
  point_at: { need: ["id"] }, look_at: { need: ["id"] }, jump: {}, fall: {},
};

// Names this registry adds to studio/catalog.json (events.js lists the event types).
export function catalog() {
  return { acts: Object.keys(ACTS), act_fields: ACT_FIELDS, surfaces: Object.keys(SURFACES) };
}
