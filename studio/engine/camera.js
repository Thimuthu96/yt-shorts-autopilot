// Camera registry: one continuously moving camera (spec §5 "Camera") and the iris transition. Pure, no DOM.
//   CAM_MOVES[move](base, e, env) -> {pos, look, fov}   the beat's own pose at eased progress e (0..1)
//   framing(cam)                  -> the beat's own pose at p = 0 (a cut lands here; `dist` is the story's dist)
//   camPose(cam, prev, p, env)    -> {pos:[x,y,z], look:[x,y,z], fov}; p = 0..1 through the beat
//   irisMask(t, dur)              -> visible radius 0..1 (1 = whole frame) across an iris boundary
// Story cam: {target:[x,y,z], dist, height, angle (deg, orbit about the target), move, cut, follow (prop id)}.
// env.follow: the followed prop's position at this moment (the engine resolves cam.follow to it).
// Framing rule: fov 42 on a 9:16 frame shows a half-width of about 0.22 x dist at the target.

import { easeIO, easeOut } from "./core.js";

const FOV = 42;
const BLEND = 0.25; // a continuous beat reaches its own framing by 25 % of the beat
const RAD = Math.PI / 180;
const LOW = 0.45; // lowSweep camera height above the floor (sets keep the floor at y = 0)

const lerp = (a, b, k) => a + (b - a) * k;
const lerp3 = (a, b, k) => a.map((v, i) => lerp(v, b[i], k));

// camera on a circle about `look`: `dist` out along `ang` (deg), `h` above it
function orbit(look, dist, h, ang) {
  const a = ang * RAD;
  return [look[0] + Math.sin(a) * dist, look[1] + h, look[2] + Math.cos(a) * dist];
}
const pose = (look, dist, h, ang, fov = FOV) => ({ pos: orbit(look, dist, h, ang), look: [...look], fov });
// sideways step (camera's right) for a pan at angle `ang`
const right = (ang, s) => [Math.cos(ang * RAD) * s, 0, -Math.sin(ang * RAD) * s];
const add = (a, b) => a.map((v, i) => v + b[i]);

export const CAM_MOVES = {
  static: (b) => pose(b.target, b.dist, b.height, b.angle),
  push: (b, e) => pose(b.target, b.dist * (1 - 0.25 * e), b.height, b.angle),
  pull: (b, e) => pose(b.target, b.dist * (1 + 0.3 * e), b.height, b.angle),
  panL: (b, e) => { const s = right(b.angle, -0.3 * b.dist * e); return { pos: add(orbit(b.target, b.dist, b.height, b.angle), s), look: add(b.target, s), fov: FOV }; },
  panR: (b, e) => { const s = right(b.angle, 0.3 * b.dist * e); return { pos: add(orbit(b.target, b.dist, b.height, b.angle), s), look: add(b.target, s), fov: FOV }; },
  orbitL: (b, e) => pose(b.target, b.dist, b.height, b.angle - 35 * e),
  orbitR: (b, e) => pose(b.target, b.dist, b.height, b.angle + 35 * e),
  rise: (b, e) => pose(b.target, b.dist, b.height + 0.45 * b.dist * e, b.angle),
  drop: (b, e) => pose(b.target, b.dist, b.height + 0.45 * b.dist * (1 - e), b.angle),
  // tilt up a tall object: the camera stays, its aim climbs from well below the target up to it
  tiltUp: (b, e) => ({ pos: orbit(b.target, b.dist, b.height, b.angle), look: [b.target[0], b.target[1] - 0.35 * b.dist * (1 - e), b.target[2]], fov: FOV }),
  // low along the floor, sliding sideways round the subject while closing in
  lowSweep: (b, e) => pose(b.target, b.dist * (1.1 - 0.2 * e), LOW - b.target[1], b.angle - 25 + 35 * e),
  // rise and pull out to a wide shot
  flyOver: (b, e) => pose(b.target, b.dist * (1 + 0.6 * e), b.height + 0.8 * b.dist * e, b.angle + 15 * e),
  // trail the followed prop at the story's offset, a little behind it, looking at it
  follow: (b, e, env) => {
    const f = (env && env.follow) || b.target;
    return { pos: orbit(lerp3(b.target, f, 0.8), b.dist, b.height, b.angle), look: [...f], fov: FOV };
  },
  // a reaction close-up: eye level, a quick small push
  closeUp: (b, e) => pose(b.target, b.dist * (1 - 0.15 * easeOut(e / 0.6)), b.height * 0.3, b.angle),
};

function base(cam) {
  const move = cam.move || "static";
  if (!CAM_MOVES[move]) throw new Error(`unknown camera move: ${move}`);
  return {
    move, target: cam.target || [0, 2, 0], dist: cam.dist ?? 9, height: cam.height ?? 1.2, angle: cam.angle || 0,
  };
}

const own = (cam, p, env) => { const b = base(cam); return CAM_MOVES[b.move](b, easeIO(p), env); };

export const framing = (cam, env) => own(cam, 0, env);

// blend a -> b keeping the camera on an arc about the aim point (shortest way round), not a straight cut through it
function mix(a, b, k) {
  const look = lerp3(a.look, b.look, k);
  const off = (p) => { const d = p.pos.map((v, i) => v - p.look[i]); return { r: Math.hypot(d[0], d[2]), yaw: Math.atan2(d[0], d[2]), y: d[1] }; };
  const oa = off(a), ob = off(b);
  let dy = ob.yaw - oa.yaw;
  dy = Math.atan2(Math.sin(dy), Math.cos(dy));
  const r = lerp(oa.r, ob.r, k), yaw = oa.yaw + dy * k, y = lerp(oa.y, ob.y, k);
  return { pos: [look[0] + Math.sin(yaw) * r, look[1] + y, look[2] + Math.cos(yaw) * r], look, fov: lerp(a.fov, b.fov, k) };
}

export function camPose(cam, prev, p, env) {
  const target = own(cam, p, env);
  if (cam.cut || !prev) return target;
  const w = easeIO(p / BLEND);
  if (w <= 0) return { pos: [...prev.pos], look: [...prev.look], fov: prev.fov };
  if (w >= 1) return target;
  return mix(prev, target, w);
}

// t: seconds since the iris window opened (it straddles the beat boundary, which sits at dur / 2)
export function irisMask(t, dur = 0.45) {
  if (t <= 0 || t >= dur) return 1;
  return easeIO(Math.abs((2 * t) / dur - 1));
}

// Names this registry adds to studio/catalog.json.
export function catalog() {
  return { cam_moves: Object.keys(CAM_MOVES) };
}
