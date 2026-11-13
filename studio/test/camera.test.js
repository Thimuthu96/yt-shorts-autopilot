// Camera registry under plain node: camPose continuity, moves, follow, iris, catalog export.
const test = require("node:test");
const assert = require("node:assert");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const STUDIO = path.join(__dirname, "..");
const camera = () => import(pathToFileURL(path.join(STUDIO, "engine", "camera.js")).href);
const world = () => import(pathToFileURL(path.join(STUDIO, "engine", "world.js")).href);

const MOVES = ["static", "push", "pull", "panL", "panR", "orbitL", "orbitR", "rise", "drop", "tiltUp", "lowSweep",
  "flyOver", "follow", "closeUp"];
const CAM = { target: [0, 2, 0], dist: 9, height: 1.2, angle: 0, move: "push", cut: false, follow: null };
const PREV = { pos: [6, 5, -3], look: [1, 1, 1], fov: 42, roll: 0 };
const sub = (a, b) => a.map((v, k) => v - b[k]);
const len = (v) => Math.hypot(...v);
const near = (a, b, eps = 1e-6) => assert.ok(len(sub(a, b)) < eps, `${JSON.stringify(a)} != ${JSON.stringify(b)}`);
const nearPose = (a, b) => { near(a.pos, b.pos); near(a.look, b.look); assert.ok(Math.abs(a.fov - b.fov) < 1e-9); assert.ok(Math.abs(a.roll - b.roll) < 1e-9); };

test("CAM_MOVES lists the plan's moves", async () => {
  const C = await camera();
  assert.deepStrictEqual(Object.keys(C.CAM_MOVES), MOVES);
});

test("a continuous camera starts exactly at the previous pose", async () => {
  const C = await camera();
  for (const move of MOVES) assert.deepStrictEqual(C.camPose({ ...CAM, move }, PREV, 0), PREV, move);
});

test("a cut starts on the beat's own framing", async () => {
  const C = await camera();
  const p = C.camPose({ ...CAM, cut: true }, PREV, 0);
  nearPose(p, C.framing({ ...CAM, cut: true }));
  near(p.pos, [0, 3.2, 9]);
  near(p.look, [0, 2, 0]);
  assert.strictEqual(p.fov, 42);
  // no previous pose (first beat) behaves like a cut
  nearPose(C.camPose(CAM, null, 0), p);
});

test("the blend into the beat's framing ends at 25 % of the beat", async () => {
  const C = await camera();
  for (const move of MOVES) {
    for (const p of [0.25, 0.5, 1]) nearPose(C.camPose({ ...CAM, move }, PREV, p), C.camPose({ ...CAM, move, cut: true }, PREV, p));
  }
  // halfway through the blend the camera is between the two poses
  const mid = C.camPose(CAM, PREV, 0.125);
  assert.ok(len(sub(mid.look, PREV.look)) > 0.1 && len(sub(mid.look, CAM.target)) > 0.1);
});

test("static is a slow push (about 3 %) toward the target", async () => {
  const C = await camera();
  const d = (p) => len(sub(C.camPose({ ...CAM, move: "static", cut: true }, null, p).pos, CAM.target));
  assert.ok(Math.abs(d(1) / d(0) - 0.97) < 0.01, `${d(1) / d(0)}`);
});

test("the camera keeps moving through a boundary between two continuous beats", async () => {
  const C = await camera();
  const A = { ...CAM, move: "push" }, durA = 2.5, durB = 3;
  const frame = 1 / 30;
  for (const move of ["orbitR", "static", "panL", "lowSweep", "push"]) {
    const B = { ...CAM, target: [1, 1.5, -1], dist: 7, angle: 20, move };
    const prev = C.handoff(A, durA, durB);
    nearPose(C.camPose(B, prev, 0), { pos: prev.pos, look: prev.look, fov: prev.fov, roll: prev.roll });
    const lastA = len(sub(C.camPose(A, null, 1).pos, C.camPose(A, null, 1 - frame / durA).pos));
    const firstB = len(sub(C.camPose(B, prev, frame / durB).pos, C.camPose(B, prev, 0).pos));
    assert.ok(lastA > 1e-3 && firstB > 1e-3, `${move}: ${lastA} ${firstB}`);
    assert.ok(firstB / lastA > 0.6 && firstB / lastA < 1.6, `${move}: last frame of A ${lastA}, first of B ${firstB}`);
  }
});

test("push closes in on the target from p=0.3 to p=1", async () => {
  const C = await camera();
  let last = Infinity;
  for (let p = 0.3; p <= 1.0001; p += 0.1) {
    const d = len(sub(C.camPose(CAM, PREV, p).pos, CAM.target));
    assert.ok(d < last, `p=${p.toFixed(1)}: ${d} >= ${last}`);
    last = d;
  }
  const pull = (p) => len(sub(C.camPose({ ...CAM, move: "pull" }, PREV, p).pos, CAM.target));
  assert.ok(pull(1) > pull(0.3));
});

test("every move gives a finite pose that changes over the beat; static drifts slowly", async () => {
  const C = await camera();
  for (const move of MOVES) {
    const cam = { ...CAM, move, cut: true, follow: move === "follow" ? "ball" : null };
    const a = C.camPose(cam, null, 0.3, { follow: [0, 2, 0] }), b = C.camPose(cam, null, 1, { follow: [0, 2, 0] });
    for (const v of [...a.pos, ...a.look, ...b.pos, ...b.look, a.fov]) assert.ok(Number.isFinite(v), move);
    const moved = len(sub(a.pos, b.pos)) + len(sub(a.look, b.look));
    if (move === "follow") assert.ok(moved < 1e-9, move); // the prop moves, not the camera on its own
    else if (move === "static") assert.ok(moved > 0.05 && moved < 0.4, `static drift ${moved}`);
    else assert.ok(moved > 0.2, `${move} barely moves (${moved})`);
  }
});

test("lowSweep keeps the camera near the floor; flyOver and rise end high", async () => {
  const C = await camera();
  const at = (move, p) => C.camPose({ ...CAM, move, cut: true }, null, p);
  for (const p of [0, 0.5, 1]) assert.ok(at("lowSweep", p).pos[1] < 0.8);
  assert.ok(at("flyOver", 1).pos[1] > at("flyOver", 0).pos[1] + 4);
  assert.ok(at("rise", 1).pos[1] > at("rise", 0).pos[1] + 2);
  assert.ok(at("drop", 1).pos[1] < at("drop", 0).pos[1] - 2);
  assert.ok(at("tiltUp", 1).look[1] > at("tiltUp", 0).look[1] + 2);
});

test("follow looks at the followed prop and keeps up with it", async () => {
  const C = await camera();
  const cam = { ...CAM, move: "follow", follow: "ball", cut: true };
  const a = C.camPose(cam, null, 0.5, { follow: [0, 2, 0] });
  const b = C.camPose(cam, null, 0.5, { follow: [10, 4, -2] });
  near(b.look, [10, 4, -2]);
  assert.ok(b.pos[0] - a.pos[0] > 5, "camera travels with the prop");
  // without a followed position it frames the target
  near(C.camPose(cam, null, 0.5).look, CAM.target);
});

test("framing: visible half-width at the target is about 0.22 x dist", async () => {
  const C = await camera();
  const p = C.framing({ ...CAM, height: 0 });
  const half = Math.tan(((p.fov / 2) * Math.PI) / 180) * (9 / 16) * len(sub(p.pos, p.look));
  assert.ok(Math.abs(half - 0.22 * CAM.dist) < 0.05 * CAM.dist * 0.22, `${half}`);
});

test("irisMask closes then opens", async () => {
  const C = await camera();
  assert.strictEqual(C.irisMask(0), 1);
  assert.ok(C.irisMask(0.225) < 0.02);
  assert.ok(Math.abs(C.irisMask(0.45) - 1) < 1e-9);
  assert.ok(C.irisMask(0.1) < 1 && C.irisMask(0.1) > C.irisMask(0.2));
  assert.ok(Math.abs(C.irisMask(0.5, 1) - 0) < 0.02);
  assert.strictEqual(C.irisMask(-1), 1);
  assert.strictEqual(C.irisMask(9), 1);
});

test("unknown move throws", async () => {
  const C = await camera();
  assert.throws(() => C.camPose({ ...CAM, move: "zoomy" }, PREV, 0.5), /unknown camera move/);
  assert.throws(() => C.framing({ ...CAM, move: "zoomy" }), /unknown camera move/);
});

test("propPosAt follows a flying prop the way its tick does", async () => {
  const W = await world();
  const spec = { id: "ball", type: "cannonball", pos: [-4, 1, 0], to: [6, 1, 0], anim: "fly", dur: 1.2, delay: 0.5 };
  const root = W.spawnProp(spec, 2);
  for (const t of [2.2, 2.5, 2.9, 3.3, 5]) {
    root.userData.tick(t);
    near(W.propPosAt(spec, 2, t), [root.position.x, root.position.y, root.position.z]);
  }
  near(W.propPosAt(spec, 2, 1), [-4, 1, 0]); // not born yet: its spawn position
});

test("node studio/catalog.js exports the camera moves and look style values", async () => {
  const r = spawnSync("node", [path.join(STUDIO, "catalog.js")], { encoding: "utf8" });
  assert.strictEqual(r.status, 0, r.stderr);
  const cat = JSON.parse(fs.readFileSync(path.join(STUDIO, "catalog.json"), "utf8"));
  assert.deepStrictEqual(cat.cam_moves, MOVES);
  assert.deepStrictEqual(cat.cam_frames, FRAMES);
  assert.deepStrictEqual(cat.transitions, ["iris", "cut", "whipL", "whipR", "whipU"]);
  assert.strictEqual(cat.frame_half_width, 0.325);
  assert.deepStrictEqual(cat.hats, ["cap", "tricorn", "captain", "bowler", "top", "hardhat", "chef", "straw", "beret", "sailor", "beanie"]);
  assert.deepStrictEqual(cat.glasses, ["round", "square", "goggles"]);
  assert.deepStrictEqual(cat.held_props, ["wrench", "flask", "clipboard", "sword", "pitchfork", "ladle", "scepter", "spyglass", "book", "hammer"]);
});

// ---------- camera v2: framing presets, wide lens, roll, whip pans ----------
const THREE = () => import("three");
const FRAMES = ["close", "medium", "two_shot", "ots", "low_hero", "wide", "pov"];
// a 1.8-tall character standing at [0.5, 0, 0.3] (head centre 1.4), another at [2.1, 0, -0.5] facing it
const SUBJ = { pos: [0.5, 0, 0.3], height: 1.8, head: 1.4, facing: "right" };
const OTHER = { pos: [2.1, 0, -0.5], height: 1.8, head: 1.4, facing: "left" };
const ENV = { subject: SUBJ, other: OTHER };
const headOf = (s) => [s.pos[0], s.head, s.pos[2]];

// the pose on a real 9:16 three.js camera (placeCamera is what the engine uses); returns the camera
async function placed(pose, opts) {
  const T = await THREE(), C = await camera();
  const cam = new T.PerspectiveCamera(42, 9 / 16, 0.1, 1000);
  C.placeCamera(cam, pose, opts);
  cam.updateMatrixWorld();
  return cam;
}
async function ndc(cam, p) {
  const T = await THREE();
  const v = new T.Vector3(...p).project(cam);
  return [v.x, v.y, v.z];
}

test("FRAMES lists the presets", async () => {
  const C = await camera();
  assert.deepStrictEqual(Object.keys(C.FRAMES), FRAMES);
});

test("each preset puts the framed head inside the centre third of the frame", async () => {
  const C = await camera();
  for (const frame of FRAMES) {
    for (const move of ["static", "push"]) {
      const cam = { frame, subject: "a", look_at: "b", move, cut: true };
      const pose = C.camPose(cam, null, 0, ENV);
      const c = await placed(pose);
      // ots and pov frame the one being looked at; the others frame the subject
      const framed = frame === "ots" || frame === "pov" ? OTHER : SUBJ;
      const [x, y, z] = await ndc(c, headOf(framed));
      assert.ok(Math.abs(x) <= 1 / 3 && Math.abs(y) <= 1 / 3 && z < 1, `${frame}/${move}: head at ${x.toFixed(2)}, ${y.toFixed(2)}`);
    }
  }
});

test("presets: two_shot shows both heads, ots has the subject near the lens, pov looks from the subject's eye", async () => {
  const C = await camera();
  const at = (frame, extra = {}) => C.camPose({ frame, subject: "a", look_at: "b", cut: true, ...extra }, null, 0, ENV);
  let c = await placed(at("two_shot"));
  for (const s of [SUBJ, OTHER]) { const [x, y] = await ndc(c, headOf(s)); assert.ok(Math.abs(x) < 0.9 && Math.abs(y) < 0.9, `two_shot ${x} ${y}`); }
  const ots = at("ots");
  // ots: the camera is behind the subject, which stands between it and the other
  const toS = len(sub(ots.pos, headOf(SUBJ))), toO = len(sub(ots.pos, headOf(OTHER)));
  assert.ok(toS < toO && toO > len(sub(headOf(SUBJ), headOf(OTHER))) + 0.5 * toS, `ots: ${toS} ${toO}`);
  // ... with its head at the frame's side edge (partly in frame, near the lens), not over the other's face
  c = await placed(ots);
  const [sx] = await ndc(c, headOf(SUBJ));
  assert.ok(Math.abs(sx) > 0.7 && Math.abs(sx) < 1.3, `ots subject head at x ${sx}`);
  const pov = at("pov");
  assert.ok(len(sub(pov.pos, headOf(SUBJ))) < 0.6, "pov: camera at the subject's eye");
  // pov without look_at looks along the subject's facing (right = +x)
  const free = C.camPose({ frame: "pov", subject: "a", cut: true }, null, 0, { subject: SUBJ });
  const dir = sub(free.look, free.pos);
  assert.ok(dir[0] > 0.9 * len(dir), `pov facing right: ${dir}`);
  // the close shot is closer than medium, medium closer than wide
  const d = (frame) => len(sub(at(frame).pos, at(frame).look));
  assert.ok(d("close") < d("medium") && d("medium") < d("wide"));
});

test("low_hero puts the camera about 0.4 high, below the subject's head, looking up", async () => {
  const C = await camera();
  for (const p of [0, 0.5, 1]) {
    const pose = C.camPose({ frame: "low_hero", subject: "a", move: "static", cut: true }, null, p, ENV);
    assert.ok(pose.pos[1] < SUBJ.head, `camera y ${pose.pos[1]}`);
    assert.ok(Math.abs(pose.pos[1] - 0.4) < 0.15, `camera y ${pose.pos[1]}`);
    assert.ok(pose.look[1] > pose.pos[1] + 0.3, "looks up");
  }
});

test("presets need their subject; two_shot and ots need look_at; unknown frames throw", async () => {
  const C = await camera();
  assert.throws(() => C.camPose({ frame: "close", subject: "a", cut: true }, null, 0, {}), /camera frame close: no subject/);
  for (const frame of ["two_shot", "ots"]) {
    assert.throws(() => C.camPose({ frame, subject: "a", cut: true }, null, 0, { subject: SUBJ }), new RegExp(`camera frame ${frame}: needs look_at`));
  }
  assert.throws(() => C.camPose({ frame: "dolly", subject: "a", cut: true }, null, 0, ENV), /unknown camera frame: dolly/);
});

test("fov: 60 for v2 shots (a frame preset or a version 2 story), 42 for v1, an explicit fov wins", async () => {
  const C = await camera();
  assert.strictEqual(C.camPose({ frame: "close", subject: "a", cut: true }, null, 0.5, ENV).fov, 60);
  assert.strictEqual(C.camPose({ ...CAM, cut: true, version: 2 }, null, 0.5).fov, 60);
  assert.strictEqual(C.camPose({ ...CAM, cut: true }, null, 0.5).fov, 42);
  assert.strictEqual(C.camPose({ ...CAM, cut: true, version: 2, fov: 75 }, null, 0.5).fov, 75);
  assert.strictEqual(C.camPose({ frame: "wide", subject: "a", cut: true, fov: 50 }, null, 0.5, ENV).fov, 50);
});

test("framing at fov 60: visible half-width at the target is about 0.325 x dist", async () => {
  const C = await camera();
  const p = C.framing({ ...CAM, height: 0, version: 2 });
  const half = Math.tan(((p.fov / 2) * Math.PI) / 180) * (9 / 16) * len(sub(p.pos, p.look));
  assert.ok(Math.abs(half - 0.325 * CAM.dist) < 0.01 * CAM.dist, `${half}`);
  // a wider lens brings a preset closer, so the subject keeps its size in frame
  const close = (fov) => { const q = C.camPose({ frame: "close", subject: "a", cut: true, fov }, null, 0, ENV); return len(sub(q.pos, q.look)); };
  assert.ok(close(75) < close(60) && close(60) < close(45));
});

test("roll: camPose carries it, placeCamera tilts about the view axis after the shake", async () => {
  const C = await camera();
  const T = await THREE();
  const pose = C.camPose({ frame: "medium", subject: "a", roll: -8, cut: true }, null, 0.5, ENV);
  assert.strictEqual(pose.roll, -8);
  assert.strictEqual(C.camPose({ ...CAM, cut: true }, null, 0.5).roll, 0);
  // a continuous shot eases the roll from the previous shot's
  const mid = C.camPose({ ...CAM, roll: 10 }, { ...PREV, roll: -10 }, 0.125);
  assert.ok(mid.roll > -10 && mid.roll < 10);
  const level = await placed({ ...pose, roll: 0 }), tilted = await placed(pose);
  const fwd = (c) => new T.Vector3(0, 0, -1).applyQuaternion(c.quaternion);
  const up = (c) => new T.Vector3(0, 1, 0).applyQuaternion(c.quaternion);
  assert.ok(fwd(level).distanceTo(fwd(tilted)) < 1e-9, "same view direction");
  const ang = Math.acos(Math.min(1, up(level).dot(up(tilted)))) * 180 / Math.PI;
  assert.ok(Math.abs(ang - 8) < 1e-6, `rolled ${ang}`);
  // -8 = the camera turns clockwise: its up vector leans to its right (the horizon runs uphill to the right)
  const right = new T.Vector3(1, 0, 0).applyQuaternion(level.quaternion);
  assert.ok(up(tilted).dot(right) > 0.1);
  // the shake moves the camera along the unrolled axes
  const a = await placed({ ...pose, roll: 0 }, { shake: [0.3, 0.1] }), b = await placed(pose, { shake: [0.3, 0.1] });
  assert.ok(a.position.distanceTo(b.position) < 1e-9);
  // roll 0 and no shake / whip gives exactly lookAt's orientation (v1 frames unchanged)
  const ref = new T.PerspectiveCamera(42, 9 / 16, 0.1, 1000);
  ref.position.set(...CAM_POS); ref.lookAt(...CAM.target);
  const v1 = await placed({ pos: CAM_POS, look: CAM.target, fov: 42, roll: 0 });
  assert.deepStrictEqual(v1.quaternion.toArray(), ref.quaternion.toArray());
});
const CAM_POS = [0, 3.2, 9];

test("whip: blur peaks at the boundary and is 0 outside +-0.12 s; the turn keeps one direction", async () => {
  const C = await camera();
  for (const kind of ["whipL", "whipR", "whipU"]) {
    assert.strictEqual(C.whipAt(0, kind).blur, 1);
    for (const dt of [-0.12, 0.12, -0.5, 0.3, -Infinity]) {
      const w = C.whipAt(dt, kind);
      assert.strictEqual(w.blur, 0, `${kind} ${dt}`);
      assert.strictEqual(w.yaw, 0); assert.strictEqual(w.pitch, 0);
    }
    for (const dt of [0.03, 0.06, 0.09]) {
      assert.ok(C.whipAt(-dt, kind).blur > C.whipAt(-dt - 0.01, kind).blur, `${kind} rises to the boundary`);
      assert.ok(C.whipAt(dt, kind).blur > C.whipAt(dt + 0.01, kind).blur, `${kind} falls after it`);
    }
    // the turn's angle increases (or decreases) the whole way through: one fast move, no turning back
    const axis = kind === "whipU" ? "pitch" : "yaw";
    const sign = kind === "whipR" ? -1 : 1; // left = +yaw (turn about +y), up = +pitch
    let last = -Infinity;
    for (let dt = -0.115; dt < 0.12; dt += 0.01) {
      const v = sign * C.whipAt(dt, kind)[axis];
      // the angle jumps from +max to -max at the boundary (the new shot comes in from the other side); within each half it grows
      if (Math.abs(dt) > 0.006) {
        if (dt > 0 && last > 0) last = -Infinity;
        assert.ok(v > last, `${kind} ${dt.toFixed(3)}: ${v} <= ${last}`);
        last = v;
      }
    }
    assert.ok(sign * C.whipAt(-0.001, kind)[axis] > 0.5 && sign * C.whipAt(0.001, kind)[axis] < -0.5, `${kind} big turn at the boundary`);
    // the boundary frame belongs to the new shot (the engine switches beats at t = start), so it takes the incoming turn
    assert.ok(Math.abs(C.whipAt(0, kind)[axis] - C.whipAt(1e-9, kind)[axis]) < 1e-6, `${kind} at the boundary`);
    // blur direction: along the screen axis of the turn
    const dir = C.whipAt(0, kind).dir;
    assert.deepStrictEqual(dir, kind === "whipU" ? [0, 1] : [1, 0]);
  }
  assert.strictEqual(C.whipAt(0, null).blur, 0);
});

test("placeCamera turns the view by the whip yaw / pitch", async () => {
  const T = await THREE();
  const pose = { pos: CAM_POS, look: CAM.target, fov: 60, roll: 0 };
  const fwd = (c) => new T.Vector3(0, 0, -1).applyQuaternion(c.quaternion);
  const base = fwd(await placed(pose));
  const l = fwd(await placed(pose, { whip: { yaw: 0.5, pitch: 0 } }));
  const u = fwd(await placed(pose, { whip: { yaw: 0, pitch: 0.5 } }));
  assert.ok(l.x < base.x - 0.3, "whipL turns the view left");
  assert.ok(u.y > base.y + 0.3, "whipU turns the view up");
});

test("whips count as cuts: the shot after a whip starts on its own framing", async () => {
  const C = await camera();
  assert.deepStrictEqual(C.TRANSITIONS, ["iris", "cut", "whipL", "whipR", "whipU"]);
  for (const tr of ["cut", "iris", "whipL", "whipR", "whipU"]) assert.ok(C.cutsAt(tr), tr);
  assert.ok(!C.cutsAt(null) && !C.cutsAt(undefined));
});

// ---------- fix round 1 ----------
test("whipU keeps the horizon in frame at the peak: incoming low_hero / close / wide shots", async () => {
  const C = await camera();
  const T = await THREE();
  for (const frame of ["low_hero", "close", "wide", "medium"]) {
    const incoming = C.camPose({ frame, subject: "a", cut: true }, null, 0, ENV);
    const max = C.whipLimit(incoming, "whipU");
    assert.ok(max <= (35 * Math.PI) / 180 + 1e-9, `${frame}: cap ${max}`);
    for (const dt of [0, 0.02, 0.05]) {
      const c = await placed(incoming, { whip: C.whipAt(dt, "whipU", max) });
      // the ray through the top-centre of the frame points above the horizon (the ground plane is not the whole frame)
      const top = new T.Vector3(0, 1, 0.5).unproject(c).sub(c.position).normalize();
      assert.ok(top.y > Math.sin((4 * Math.PI) / 180), `${frame} dt ${dt}: top ray y ${top.y.toFixed(3)}`);
    }
  }
  // the cap is used on both sides of the boundary, so the turn speed still matches and peaks there
  const w = (dt) => C.whipAt(dt, "whipU", 0.3).pitch;
  assert.ok(Math.abs(w(-1e-9) - 0.3) < 1e-6 && Math.abs(w(0) + 0.3) < 1e-6);
  // rate: the turn speed, peaking at 2 x max / 0.12 s at the boundary, 0 outside
  assert.ok(Math.abs(C.whipAt(0, "whipU", 0.3).rate - (2 * 0.3) / 0.12) < 1e-9);
  assert.strictEqual(C.whipAt(0.2, "whipU", 0.3).rate, 0);
  assert.ok(C.whipAt(0.06, "whipL").rate < C.whipAt(0.01, "whipL").rate);
  // whipL / whipR keep their yaw (60 deg); the limit only changes pitch
  assert.ok(Math.abs(C.whipLimit({ pos: [0, 0.4, 3], look: [0, 1.3, 0], fov: 60 }, "whipL") - Math.PI / 3) < 1e-9);
});

test("ots and pov ignore moves that would drive the camera through the subject", async () => {
  const C = await camera();
  for (const move of ["push", "closeUp"]) {
    const a = C.camPose({ frame: "ots", subject: "a", look_at: "b", move, cut: true }, null, 1, ENV);
    const b = C.camPose({ frame: "ots", subject: "a", look_at: "b", move: "static", cut: true }, null, 1, ENV);
    nearPose(a, b);
  }
  for (const move of ["pull", "flyOver", "lowSweep"]) {
    for (const p of [0, 0.5, 1]) {
      const q = C.camPose({ frame: "pov", subject: "a", look_at: "b", move, cut: true }, null, p, ENV);
      const ahead = sub(q.look, q.pos), back = sub(q.pos, headOf(SUBJ));
      // the camera stays in front of the subject's head, toward what it looks at
      assert.ok(back[0] * ahead[0] + back[2] * ahead[2] > 0, `pov ${move} p=${p}`);
    }
  }
  // the ots camera stays behind the subject through the whole shot for every other move
  for (const move of MOVES.filter((m) => m !== "follow")) {
    for (const p of [0, 1]) {
      const q = C.camPose({ frame: "ots", subject: "a", look_at: "b", move, cut: true }, null, p, ENV);
      assert.ok(len(sub(q.pos, headOf(OTHER))) > len(sub(headOf(SUBJ), headOf(OTHER))) + 0.3, `ots ${move} p=${p}`);
    }
  }
});
