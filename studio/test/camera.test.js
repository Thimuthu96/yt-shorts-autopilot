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
const PREV = { pos: [6, 5, -3], look: [1, 1, 1], fov: 42 };
const sub = (a, b) => a.map((v, k) => v - b[k]);
const len = (v) => Math.hypot(...v);
const near = (a, b, eps = 1e-6) => assert.ok(len(sub(a, b)) < eps, `${JSON.stringify(a)} != ${JSON.stringify(b)}`);
const nearPose = (a, b) => { near(a.pos, b.pos); near(a.look, b.look); assert.ok(Math.abs(a.fov - b.fov) < 1e-9); };

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

test("every move gives a finite pose that changes over the beat (except static)", async () => {
  const C = await camera();
  for (const move of MOVES) {
    const cam = { ...CAM, move, cut: true, follow: move === "follow" ? "ball" : null };
    const a = C.camPose(cam, null, 0.3, { follow: [0, 2, 0] }), b = C.camPose(cam, null, 1, { follow: [0, 2, 0] });
    for (const v of [...a.pos, ...a.look, ...b.pos, ...b.look, a.fov]) assert.ok(Number.isFinite(v), move);
    const moved = len(sub(a.pos, b.pos)) + len(sub(a.look, b.look));
    if (move === "static" || move === "follow") assert.ok(moved < 1e-9, move);
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
  assert.deepStrictEqual(cat.hats, ["cap", "tricorn", "captain", "bowler", "top", "hardhat", "chef", "straw", "beret", "sailor", "beanie"]);
  assert.deepStrictEqual(cat.glasses, ["round", "square", "goggles"]);
  assert.deepStrictEqual(cat.held_props, ["wrench", "flask", "clipboard", "sword", "pitchfork", "ladle", "scepter", "spyglass", "book", "hammer"]);
});
