// Camera registry: one continuously moving camera (spec §5 "Camera", §11 camera v2), the iris and whip transitions.
// Pure apart from placeCamera (which poses a three.js camera); nothing touches the DOM.
//   CAM_MOVES[move](base, e, env) -> {pos, look, fov}   the shot's own pose at progress e (0..1)
//   FRAMES[frame](subject, other, k) -> {target, dist, height, angle}   a framing preset (k = lens factor, below)
//   framing(cam, env)             -> the shot's own pose at p = 0 (a cut lands here; `dist` is the story's dist)
//   camPose(cam, prev, p, env)    -> {pos:[x,y,z], look:[x,y,z], fov, roll}; p = 0..1 through the shot
//   handoff(cam, durA, durB, envAt) -> shot A's last pose + its velocity, the `prev` of the shot after it
//   placeCamera(camera, pose, {shake, whip}) poses a three.js camera: lookAt, shake, whip turn, then roll
//   irisMask(t, dur)              -> visible radius 0..1 (1 = whole frame) across an iris boundary
//   whipAt(dt, kind)              -> {yaw, pitch, blur, dir} across a whip boundary (dt = t - boundary)
//   cutsAt(transition)            -> true when a shot entered by this transition starts on its own framing
// The camera never stops at a shot boundary: moves run at a steady speed through the shot, and a continuous shot
// starts on the previous shot's last pose, carrying on at its velocity while it eases into its own move.
// Story cam, either explicit (v1): {target:[x,y,z], dist, height, angle (deg, orbit about the target), move, cut,
// follow (prop id), fov?, roll?}
// or a preset (v2): {frame, subject (char / prop id), look_at? (id; two_shot and ots need it, pov aims at it), angle?
// (deg, turns the preset about its target), move, cut, follow, fov?, roll?} - explicit target/dist/height are ignored.
// roll: dutch tilt, degrees the camera turns about its view axis (+ = anticlockwise, so the horizon runs downhill to
// the right; - = clockwise, uphill to the right). fov: an explicit fov always wins; otherwise a v2 shot (a
// `frame` preset, or a story with "version": 2, which the engine passes in as cam.version) gets the wide lens, 60,
// and a v1 shot keeps 42. Presets are sized for fov 60 and move closer with a wider lens (dist x tan 30 / tan(fov/2)).
// env.follow: the followed prop's position at this moment (the engine resolves cam.follow to it).
// env.subject / env.other: the things cam.subject / cam.look_at name, at this moment (the engine resolves them):
// {pos: [x,y,z] where it stands, height, size? (a prop: its largest extent), head: y of its head (a prop: of its
// upper part), facing}.
// Framing rule: on a 9:16 frame the half-width visible at the target is tan(fov/2) x 9/16 x dist:
// about 0.22 x dist at fov 42, 0.325 x dist at fov 60 (catalog frame_half_width, for v2 stories).
import { easeIO, easeOut } from "./core.js";

const FOV = 42, FOV2 = 60; // v1 / v2 default lens
const BLEND = 0.25; // a continuous beat reaches its own framing by 25 % of the beat
const RAD = Math.PI / 180, DEG = 180 / Math.PI;
const HALF2 = Math.tan((FOV2 / 2) * RAD) * (9 / 16); // half-width / dist at fov 60 on 9:16 (0.325)
const LOW = 0.45; // lowSweep camera height above the floor (sets keep the floor at y = 0)

const lerp = (a, b, k) => a + (b - a) * k;
const lerp3 = (a, b, k) => a.map((v, i) => lerp(v, b[i], k));

// camera on a circle about `look`: `dist` out along `ang` (deg), `h` above it
function orbit(look, dist, h, ang) {
  const a = ang * RAD;
  return [look[0] + Math.sin(a) * dist, look[1] + h, look[2] + Math.cos(a) * dist];
}
const pose = (look, dist, h, ang, fov) => ({ pos: orbit(look, dist, h, ang), look: [...look], fov });
// sideways step (camera's right) for a pan at angle `ang`
const right = (ang, s) => [Math.cos(ang * RAD) * s, 0, -Math.sin(ang * RAD) * s];
const add = (a, b) => a.map((v, i) => v + b[i]);

export const CAM_MOVES = {
  static: (b, e) => pose(b.target, b.dist * (1 - 0.03 * e), b.height, b.angle, b.fov), // a slow drift in, never frozen
  push: (b, e) => pose(b.target, b.dist * (1 - 0.25 * e), b.height, b.angle, b.fov),
  pull: (b, e) => pose(b.target, b.dist * (1 + 0.3 * e), b.height, b.angle, b.fov),
  panL: (b, e) => { const s = right(b.angle, -0.3 * b.dist * e); return { pos: add(orbit(b.target, b.dist, b.height, b.angle), s), look: add(b.target, s), fov: b.fov }; },
  panR: (b, e) => { const s = right(b.angle, 0.3 * b.dist * e); return { pos: add(orbit(b.target, b.dist, b.height, b.angle), s), look: add(b.target, s), fov: b.fov }; },
  orbitL: (b, e) => pose(b.target, b.dist, b.height, b.angle - 35 * e, b.fov),
  orbitR: (b, e) => pose(b.target, b.dist, b.height, b.angle + 35 * e, b.fov),
  rise: (b, e) => pose(b.target, b.dist, b.height + 0.45 * b.dist * e, b.angle, b.fov),
  drop: (b, e) => pose(b.target, b.dist, b.height + 0.45 * b.dist * (1 - e), b.angle, b.fov),
  // tilt up a tall object: the camera stays, its aim climbs from well below the target up to it
  tiltUp: (b, e) => ({ pos: orbit(b.target, b.dist, b.height, b.angle), look: [b.target[0], b.target[1] - 0.35 * b.dist * (1 - e), b.target[2]], fov: b.fov }),
  // low along the floor, sliding sideways round the subject while closing in
  lowSweep: (b, e) => pose(b.target, b.dist * (1.1 - 0.2 * e), LOW - b.target[1], b.angle - 25 + 35 * e, b.fov),
  // rise and pull out to a wide shot
  flyOver: (b, e) => pose(b.target, b.dist * (1 + 0.6 * e), b.height + 0.8 * b.dist * e, b.angle + 15 * e, b.fov),
  // trail the followed prop at the story's offset, a little behind it, looking at it
  follow: (b, e, env) => {
    const f = (env && env.follow) || b.target;
    return { pos: orbit(lerp3(b.target, f, 0.8), b.dist, b.height, b.angle), look: [...f], fov: b.fov };
  },
  // a reaction close-up: eye level, a quick small push
  closeUp: (b, e) => pose(b.target, b.dist * (1 - 0.12 * easeOut(e / 0.6) - 0.05 * e), b.height * 0.3, b.angle, b.fov),
};

// ---------- framing presets (v2) ----------
// Each turns the subject (and look_at's `other`) into {target, dist, height, angle}. Distances scale with the subject's
// size (s.size, else its height: a wide prop is framed by its width), heights with its height, so a preset frames a
// tall lighthouse or a long cannon the way it frames a character. k = tan 30 / tan(fov / 2): 1 at fov 60, < 1 for a
// wider lens (closer camera, same subject size, stronger perspective).
const flat = (v) => { const l = Math.hypot(v[0], v[2]) || 1; return [v[0] / l, 0, v[2] / l]; };
// the horizontal direction across the line a -> b, on the +z side (the side sets are built to be seen from)
function across(a, b) {
  const d = flat([b.pos[0] - a.pos[0], 0, b.pos[2] - a.pos[2]]);
  const n = [-d[2], 0, d[0]];
  return n[2] > 0 || (n[2] === 0 && n[0] >= 0) ? n : [-n[0], 0, -n[2]];
}
// a camera at `pos` aiming at `look`, as the orbit fields
function aim(pos, look) {
  const dx = pos[0] - look[0], dz = pos[2] - look[2];
  return { target: [...look], dist: Math.hypot(dx, dz), height: pos[1] - look[1], angle: Math.atan2(dx, dz) * DEG };
}
const FACING_DIR = { right: [1, 0, 0], left: [-1, 0, 0], front: [0, 0, 1] };
const at = (s, y) => [s.pos[0], y, s.pos[2]];
const size = (s) => s.size ?? s.height;

export const FRAMES = {
  // head and shoulders: the head about half the frame width, above centre, the camera a little below it
  close: (s, o, k) => ({ target: at(s, s.head - 0.2 * s.height), dist: 1.5 * size(s) * k, height: -0.08 * s.height, angle: 12 }),
  // waist up (the 9:16 frame shows the legs too): the head about a third of the width
  medium: (s, o, k) => ({ target: at(s, s.pos[1] + 0.6 * s.height), dist: 2.2 * size(s) * k, height: 0, angle: -15 }),
  // both, the subject nearer the centre: the aim sits 30 % of the way to the other, square on to the pair
  two_shot: (s, o, k) => {
    const sep = Math.hypot(o.pos[0] - s.pos[0], o.pos[2] - s.pos[2]), n = across(s, o);
    const target = lerp3(at(s, s.head), at(o, o.head), 0.3);
    target[1] -= 0.1 * s.height;
    const half = Math.max(1.1 * sep, 0.7 * sep + 0.3 * size(s), 0.55 * size(s)); // world half-width to show
    return { target, dist: (half / HALF2) * k, height: -0.05 * s.height, angle: Math.atan2(n[0], n[2]) * DEG };
  },
  // over the subject's shoulder toward the other's face: the camera sits on the line from the other's head through a
  // point beside the subject's head, OTS_BACK x size behind it, so the subject's head is OTS_ANGLE off the view line
  // (its centre at the frame's edge, half of it in frame, near the lens) whatever the distance between the two
  ots: (s, o) => {
    const n = across(s, o), back = OTS_BACK * size(s), w = back * Math.tan(OTS_ANGLE / DEG);
    const look = at(o, o.head - 0.05 * o.height), side = [s.pos[0] + n[0] * w, s.head, s.pos[2] + n[2] * w];
    const v = side.map((x, i) => x - look[i]), l = Math.hypot(...v);
    return aim(side.map((x, i) => x + (v[i] / l) * back), look);
  },
  // the hero shot: camera about 0.4 above the floor (for a 1.8 tall subject), looking up at the head
  low_hero: (s, o, k) => {
    const look = at(s, s.head - 0.05 * s.height);
    return { target: look, dist: 1.35 * size(s) * k, height: s.pos[1] + 0.22 * s.height - look[1], angle: -18 };
  },
  // the whole subject small in its set, from a little above
  wide: (s, o, k) => ({ target: at(s, s.pos[1] + 0.55 * s.height), dist: 4.2 * size(s) * k, height: 0.9 * s.height, angle: 20 }),
  // through the subject's eyes: just in front of its eye, along its facing, or at look_at's head
  pov: (s, o) => {
    const dir = FACING_DIR[s.facing] || FACING_DIR.right, eye = s.pos[1] + 0.8 * s.height;
    const look = o ? at(o, o.head) : [s.pos[0] + dir[0] * 6, eye, s.pos[2] + dir[2] * 6];
    const d = o ? flat([o.pos[0] - s.pos[0], 0, o.pos[2] - s.pos[2]]) : dir;
    return aim([s.pos[0] + d[0] * 0.25, eye, s.pos[2] + d[2] * 0.25], look);
  },
};
const OTS_BACK = 1.0, OTS_ANGLE = 17; // ots: camera distance behind the subject's head (x size), its head's angle
const NEEDS_OTHER = new Set(["two_shot", "ots"]);

function preset(cam, env, fov) {
  const fr = FRAMES[cam.frame];
  if (!fr) throw new Error(`unknown camera frame: ${cam.frame}`);
  const s = env && env.subject, o = env && env.other;
  if (!s) throw new Error(`camera frame ${cam.frame}: no subject ${cam.subject}`);
  if (NEEDS_OTHER.has(cam.frame) && (!cam.look_at || !o)) throw new Error(`camera frame ${cam.frame}: needs look_at`);
  const k = Math.tan(FOV2 / 2 / DEG) / Math.tan(fov / 2 / DEG);
  const f = fr(s, cam.look_at ? o : null, k);
  return { ...f, angle: f.angle + (cam.angle || 0) };
}

const isV2 = (cam) => !!cam.frame || cam.version >= 2;

function base(cam, env) {
  const move = cam.move || "static";
  if (!CAM_MOVES[move]) throw new Error(`unknown camera move: ${move}`);
  const fov = cam.fov ?? (isV2(cam) ? FOV2 : FOV);
  if (cam.frame) return { move, fov, ...preset(cam, env, fov) };
  return {
    move, fov, target: cam.target || [0, 2, 0], dist: cam.dist ?? 9, height: cam.height ?? 1.2, angle: cam.angle || 0,
  };
}

// steady progress: a move keeps its speed up to the beat's end, so the next beat can carry it on
const own = (cam, p, env) => {
  const b = base(cam, env);
  return { ...CAM_MOVES[b.move](b, Math.max(0, Math.min(1, p)), env), roll: cam.roll || 0 };
};

export const framing = (cam, env) => own(cam, 0, env);

// blend a -> b keeping the camera on an arc about the aim point (shortest way round), not a straight cut through it
function mix(a, b, k) {
  const look = lerp3(a.look, b.look, k);
  const off = (p) => { const d = p.pos.map((v, i) => v - p.look[i]); return { r: Math.hypot(d[0], d[2]), yaw: Math.atan2(d[0], d[2]), y: d[1] }; };
  const oa = off(a), ob = off(b);
  let dy = ob.yaw - oa.yaw;
  dy = Math.atan2(Math.sin(dy), Math.cos(dy));
  const r = lerp(oa.r, ob.r, k), yaw = oa.yaw + dy * k, y = lerp(oa.y, ob.y, k);
  return { pos: [look[0] + Math.sin(yaw) * r, look[1] + y, look[2] + Math.cos(yaw) * r], look, fov: lerp(a.fov, b.fov, k), roll: lerp(a.roll, b.roll, k) };
}

// prev: the previous beat's last pose; prev.vel = {pos, look} its velocity per unit of this beat's progress
// (handoff makes it). Over the first 25 % the camera carries on along that velocity and eases into its own move.
export function camPose(cam, prev, p, env) {
  const target = own(cam, p, env);
  if (cam.cut || !prev) return target;
  const w = easeIO(p / BLEND);
  if (w <= 0) return { pos: [...prev.pos], look: [...prev.look], fov: prev.fov, roll: prev.roll || 0 };
  if (w >= 1) return target;
  const v = prev.vel || { pos: [0, 0, 0], look: [0, 0, 0] };
  const carried = { pos: prev.pos.map((x, i) => x + v.pos[i] * p), look: prev.look.map((x, i) => x + v.look[i] * p), fov: prev.fov, roll: prev.roll || 0 };
  return mix(carried, target, w);
}

// Beat A's last pose with its velocity, rescaled from A's progress to B's (durations in seconds).
// envAt(p) gives A's env at its progress p (the followed prop moves too).
const STEP = 0.02; // seconds
export function handoff(cam, durA, durB, envAt = () => undefined) {
  const a = { ...cam, cut: true }, h = Math.min(0.5, STEP / durA);
  const end = camPose(a, null, 1, envAt(1)), before = camPose(a, null, 1 - h, envAt(1 - h));
  const k = durB / (h * durA);
  const vel = (key) => end[key].map((x, i) => (x - before[key][i]) * k);
  return { ...end, vel: { pos: vel("pos"), look: vel("look") } };
}

// Poses a three.js camera: position, lens, lookAt; then the shake ([right, up] world units along the camera's own
// axes after lookAt, position and aim together), the whip turn (yaw about the camera's up, pitch about its right),
// and last the roll about the view axis. With no roll, shake or whip this is exactly the v1 lookAt.
export function placeCamera(camera, pose, { shake = [0, 0], whip = null } = {}) {
  camera.position.set(...pose.pos);
  if (camera.fov !== pose.fov) { camera.fov = pose.fov; camera.updateProjectionMatrix(); }
  camera.lookAt(...pose.look);
  const [sx, sy] = shake;
  if (sx || sy) {
    const off = rotate(camera.quaternion, [sx, sy, 0]); // sx along the camera's right, sy along its up
    camera.position.set(pose.pos[0] + off[0], pose.pos[1] + off[1], pose.pos[2] + off[2]);
    camera.lookAt(pose.look[0] + off[0], pose.look[1] + off[1], pose.look[2] + off[2]);
  }
  if (whip && whip.yaw) camera.rotateY(whip.yaw);
  if (whip && whip.pitch) camera.rotateX(whip.pitch);
  if (pose.roll) camera.rotateZ(pose.roll * RAD);
}
// v rotated by the unit quaternion q (three.js Vector3.applyQuaternion, without importing three)
function rotate(q, [vx, vy, vz]) {
  const { x: qx, y: qy, z: qz, w: qw } = q;
  const tx = 2 * (qy * vz - qz * vy), ty = 2 * (qz * vx - qx * vz), tz = 2 * (qx * vy - qy * vx);
  return [vx + qw * tx + qy * tz - qz * ty, vy + qw * ty + qz * tx - qx * tz, vz + qw * tz + qx * ty - qy * tx];
}

// t: seconds since the iris window opened (it straddles the shot boundary, which sits at dur / 2)
export function irisMask(t, dur = 0.45) {
  if (t <= 0 || t >= dur) return 1;
  return easeIO(Math.abs((2 * t) / dur - 1));
}

// ---------- whip pans ----------
// Over the last WHIP s of the old shot the camera turns ever faster in the whip's direction (0 -> +MAX, quadratic in
// time); the new shot comes in from the other side and settles (-MAX -> 0): the turn speed is the same on both sides
// of the boundary and peaks there, where the set changes. blur = turn speed / its peak (0..1); dir = the screen axis the
// image smears along. whipL turns left (+yaw), whipR right, whipU up (+pitch). Stateless: a function of dt alone.
export const WHIP = 0.12; // seconds each side of the boundary
const WHIP_MAX = { yaw: 60 / DEG, pitch: 50 / DEG };
const WHIPS = { whipL: ["yaw", 1], whipR: ["yaw", -1], whipU: ["pitch", 1] };
export function whipAt(dt, kind) {
  const w = WHIPS[kind], out = { yaw: 0, pitch: 0, blur: 0, dir: kind === "whipU" ? [0, 1] : [1, 0] };
  if (!w || !(Math.abs(dt) < WHIP)) return out;
  const [axis, sign] = w, u = dt / WHIP; // -1..1
  // t = boundary is the new shot's first frame (the engine switches shots there), so it takes the incoming side
  out[axis] = sign * WHIP_MAX[axis] * (u < 0 ? (1 + u) ** 2 : -((1 - u) ** 2));
  out.blur = 1 - Math.abs(u);
  return out;
}

export const TRANSITIONS = ["iris", "cut", ...Object.keys(WHIPS)];
// a cut, an iris (black at the boundary) or a whip (blurred at the boundary, usually into another set)
export const cutsAt = (transition) => TRANSITIONS.includes(transition);

// Names this registry adds to studio/catalog.json.
export function catalog() {
  return {
    cam_moves: Object.keys(CAM_MOVES), cam_frames: Object.keys(FRAMES), transitions: TRANSITIONS,
    frame_half_width: Math.round(HALF2 * 1000) / 1000, // the framing rule for v2 stories (fov 60)
  };
}
