// Action library under plain node: fire / launch / impact / fly_off and character acts, all stateless per t.
const test = require("node:test");
const assert = require("node:assert");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const STUDIO = path.join(__dirname, "..");
const mod = (name) => import(pathToFileURL(path.join(STUDIO, "engine", name)).href);
const load = async () => ({ E: await mod("events.js"), A: await mod("actions.js"), W: await mod("world.js"),
  C: await mod("cast.js"), Cam: await mod("camera.js") });

// shot 0: five words at 0.5 s steps; shot 1 (kept): one word at 4.2 s
const TL = {
  fps: 30, duration: 6,
  beats: [
    { i: 0, start: 0.5, end: 4.0, words: ["fire", "the", "big", "cannon", "now"].map((w, k) => ({ w, s: 0.5 + 0.5 * k, e: 0.9 + 0.5 * k })) },
    { i: 1, start: 4.0, end: 6.0, words: [{ w: "boom", s: 4.2, e: 4.6 }] },
  ],
};
const CANNON = { id: "cannon1", type: "cannon", pos: [0, 0, 0] };
const BALL = { id: "ball1", type: "cannonball", pos: [0, 0.8, 0], hidden: true };
const MUG = { id: "mug1", type: "mug", pos: [3, 0.9, 1] };
const shot = (events, extra = {}) => ({ text: "fire the big cannon now", props: [CANNON, BALL, MUG],
  chars: [{ id: "pirate", pos: [2, 0, 1], facing: "right" }, { id: "gus", pos: [-3, 0, 2], facing: "right" }], events, ...extra });
const one = (events, extra) => ({ beats: [shot(events, extra)] });
const near = (a, b, eps = 1e-6) => a.length === b.length && a.every((v, i) => Math.abs(v - b[i]) < eps);
const assertNear = (a, b, msg, eps = 1e-6) => assert.ok(near(a, b, eps), `${msg}: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`);

async function rig(story) {
  const L = await load();
  const state = { story, timeline: TL };
  const at = (t, k = 0) => L.E.applyEvents({ ...state, ...L.E.stageAt(story, TL, k) }, k, t);
  const propPos = (id, t, k = 0) => { const s = at(t, k).props.get(id); return L.W.propPosAt(s, s.spawnT, t); };
  return { ...L, state, at, propPos };
}

test("event types and acts are registered and in the catalog", async () => {
  const { E, A } = await load();
  for (const k of ["fire", "launch", "impact", "fly_off", "act"]) {
    assert.ok(E.EVENT_TYPES[k], k);
    assert.ok(E.EVENT_TYPES[k].scope === "scene" || E.SCOPES[E.EVENT_TYPES[k].scope], k);
  }
  const ACTS = ["hold", "drink", "toast", "throw", "duck", "cower", "grab", "run_to", "point_at", "look_at", "jump", "fall"];
  assert.deepStrictEqual(Object.keys(A.ACTS), ACTS);
  const r = spawnSync("node", [path.join(STUDIO, "catalog.js")], { encoding: "utf8" });
  assert.strictEqual(r.status, 0, r.stderr);
  const cat = JSON.parse(fs.readFileSync(path.join(STUDIO, "catalog.json"), "utf8"));
  assert.deepStrictEqual(cat.acts, ACTS);
  assert.deepStrictEqual(cat.surfaces, Object.keys(A.SURFACES));
  for (const k of ["fire", "launch", "impact", "fly_off", "act"]) assert.ok(cat.events.includes(k), k);
  assert.deepStrictEqual(Object.keys(cat.event_fields), cat.events, "every event documents its fields");
  assert.deepStrictEqual(Object.keys(cat.act_fields), ACTS, "every act documents its fields");
  assert.deepStrictEqual(cat.event_fields.launch, { need: ["who", "to"], opt: ["dur", "surface", "impact", "stay", "scale"] });
  for (const p of ["mug", "pistol"]) assert.ok(cat.props.includes(p), p);
  assert.ok(cat.fx.includes("gunsmoke"));
});

test("bad action events throw with the beat number", async () => {
  const { E } = await load();
  const bad = (ev) => () => E.eventTimes({ events: [{ at_word: 0, ...ev }] }, TL.beats[1]);
  assert.throws(bad({ do: "fire" }), /beat 1: fire: needs who/);
  assert.throws(bad({ do: "fire", who: "cannon1", projectile: "ball1" }), /beat 1: fire: needs to/);
  assert.throws(bad({ do: "launch", who: "ball1", to: [1, 2] }), /beat 1: launch: to must be \[x, y, z\]/);
  assert.throws(bad({ do: "launch", who: "ball1", to: [1, 2, 3], surface: "jelly" }), /beat 1: launch: unknown surface: jelly/);
  assert.throws(bad({ do: "launch", who: "ball1", to: [1, 2, 3], impact: "glitter" }), /beat 1: launch: unknown impact: glitter/);
  assert.throws(bad({ do: "launch", who: "ball1", to: [1, 2, 3], dur: 0 }), /beat 1: launch: dur must be a number > 0/);
  assert.throws(bad({ do: "impact", surface: "wood" }), /beat 1: impact: needs at/);
  assert.throws(bad({ do: "fly_off", who: "mug1" }), /beat 1: fly_off: needs dir/);
  assert.throws(bad({ do: "act", who: "pirate", act: "dab" }), /beat 1: act: unknown act: dab/);
  assert.throws(bad({ do: "act", who: "pirate", act: "hold" }), /beat 1: act: hold needs prop/);
  assert.throws(bad({ do: "act", who: "pirate", act: "run_to" }), /beat 1: act: run_to: pos must be \[x, y, z\]/);
  assert.throws(bad({ do: "act", who: "pirate", act: "point_at" }), /beat 1: act: point_at needs id/);
  assert.throws(bad({ do: "act", who: "pirate", act: "throw", prop: "mug1" }), /beat 1: act: throw: to must be \[x, y, z\]/);
  assert.throws(bad({ do: "act", who: "pirate", act: "cower", expr: "meh" }), /beat 1: act: unknown expr: meh/);
  // a fire event aimed at a prop that cannot fire fails when it is applied
  const st = one([{ at_word: 0, do: "fire", who: "mug1" }]);
  assert.throws(() => E.applyEvents({ story: st, timeline: TL, ...E.stageAt(st, TL, 0) }, 0, 1), /beat 0: fire: mug1 \(mug\) cannot fire/);
});

test("launch: from its position at t0 to `to` on an arc whose apex is above both ends", async () => {
  const to = [10, 1.2, -4];
  const r = await rig(one([{ at_word: 1, do: "launch", who: "mug1", to, dur: 1.0 }]));
  assertNear(r.propPos("mug1", 0.9), MUG.pos, "before its word the prop stands still");
  assertNear(r.propPos("mug1", 1.0), MUG.pos, "at t0 the prop is at its start");
  assertNear(r.propPos("mug1", 2.0), to, "at arrival it is at `to`");
  let apex = -Infinity;
  for (let t = 1.0; t <= 2.0; t += 0.01) apex = Math.max(apex, r.propPos("mug1", t)[1]);
  assert.ok(apex > Math.max(MUG.pos[1], to[1]) + 0.5, `apex ${apex}`);
  // dur defaults by distance: longer flights take longer, and still land on `to`
  const far = await rig(one([{ at_word: 1, do: "launch", who: "mug1", to: [40, 0, -10] }]));
  const d = far.A.flightDur(MUG.pos, [40, 0, -10]);
  assert.ok(d > far.A.flightDur(MUG.pos, to) && d <= 2.5, `dur ${d}`);
  assertNear(far.propPos("mug1", 1.0 + d), [40, 0, -10], "default dur lands on `to`");
});

test("impact fx spawns at the arrival time, chosen by surface; nearby characters squash", async () => {
  const to = [2.5, 1, 1];
  const r = await rig(one([{ at_word: 1, do: "launch", who: "mug1", to, dur: 1.0, surface: "wood" },
    { at_word: 2, do: "launch", who: "ball1", to: [0, 0, -9], dur: 0.5, surface: "water" },
    { at_word: 3, do: "impact", at: [-3, 0, 6], impact: "explosion", scale: 0.5 }]));
  assert.deepStrictEqual(r.at(0.99).fx, [], "nothing before the launch");
  const fx = r.at(1.2).fx;
  assert.strictEqual(fx.length, 1);
  assert.strictEqual(fx[0].type, "splinters");
  assert.ok(Math.abs(fx[0].born - 2.0) < 1e-9, `born ${fx[0].born}`);
  assertNear(fx[0].at, to, "at the landing point");
  const all = r.at(3.0).fx.map((f) => [f.type, +f.born.toFixed(6)]);
  assert.deepStrictEqual(all, [["splinters", 2], ["splash", 2], ["explosion", 2]]);
  assert.strictEqual(new Set(r.at(3.0).fx.map((f) => f.key)).size, 3, "every fx has its own key");
  // squash & stretch: the pirate (0.5 from the landing point) squashes; Gus (5.5 away, 4 from the explosion) does not
  const sq = (id, t) => r.at(t).chars.get(id).squash;
  assert.strictEqual(sq("pirate", 1.99), undefined);
  assert.ok(sq("pirate", 2.08).sy < 0.92, `pirate sy ${sq("pirate", 2.08).sy}`);
  assert.strictEqual(sq("gus", 2.08), undefined, "too far from both impacts");
  const late = sq("pirate", 3.0);
  assert.ok(!late || (Math.abs(late.sy - 1) < 1e-9 && Math.abs(late.sx - 1) < 1e-9), "the squash ends");
  // an impact event at word 3 (t = 2.0) 0.5 from Gus
  const r2 = await rig(one([{ at_word: 3, do: "impact", at: [-3, 0, 2.5], surface: "stone" }]));
  assert.strictEqual(r2.at(2.1).fx[0].type, "debris");
  assert.ok(r2.at(2.08).chars.get("gus").squash.sy < 0.92);
});

test("fire: muzzle blast (flash, fireball, smoke) at the muzzle, recoil back to rest by 0.25 s, the projectile launches", async () => {
  const to = [12, 1, -6];
  const r = await rig(one([{ at_word: 1, do: "fire", who: "cannon1", projectile: "ball1", to, dur: 1.2, surface: "water" }]));
  const muzzle = r.W.muzzleAt(CANNON);
  assert.ok(muzzle[0] > 1 && muzzle[1] > 0.8, `muzzle ${muzzle}`);
  assertNear(r.propPos("cannon1", 0.99), [0, 0, 0], "at rest before");
  assertNear(r.propPos("cannon1", 1.0), [0, 0, 0], "recoil starts from rest");
  assert.ok(r.propPos("cannon1", 1.06)[0] < -0.2, `recoil ${r.propPos("cannon1", 1.06)}`);
  for (const t of [1.25, 1.3, 2.0]) assertNear(r.propPos("cannon1", t), [0, 0, 0], `back at rest at ${t}`);
  const fx = r.at(1.0).fx;
  assert.deepStrictEqual(fx.map((f) => f.type), ["gunsmoke", "splash"]);
  assertNear(fx[0].at, muzzle, "the blast is at the muzzle");
  assert.strictEqual(fx[0].born, 1.0);
  assert.ok(Math.abs(fx[0].rotY) < 1e-9, "turned along the barrel (+x)");
  assert.ok(Math.abs(fx[1].born - 2.2) < 1e-9 && near(fx[1].at, to), "the ball's splash waits for its landing");
  // the hidden ball appears at the muzzle on the word and lands on `to`
  assertNear(r.propPos("ball1", 1.0), muzzle, "launched from the muzzle");
  assertNear(r.propPos("ball1", 2.2), to, "lands on to");
  const ball = r.W.spawnProp(BALL, 0.5);
  const tick = (t) => { ball.userData.tick(t, r.at(t).props.get("ball1")); return ball.visible; };
  assert.strictEqual(tick(0.9), false, "hidden until fired");
  assert.strictEqual(tick(1.5), true, "visible in flight");
  assert.strictEqual(tick(2.3), false, "gone once it has splashed down");
  // recoil is pure: the base spec is never changed
  assert.deepStrictEqual(CANNON, { id: "cannon1", type: "cannon", pos: [0, 0, 0] });
});

test("run_to: runs from where the character stands and ends at pos", async () => {
  const r = await rig(one([{ at_word: 1, do: "act", who: "pirate", act: "run_to", pos: [6, 0, -1] }]));
  const c = new r.C.Char("pirate", { costume: "pirate" });
  c.born = 0.5; c.keep(shot([]).chars[0], 0.5);
  const st = (t) => c.frame(r.at(t).chars.get("pirate"), t, 0);
  assertNear([st(0.99).x, st(0.99).z], [2, 1], "stands before its word");
  const mid = st(1.3);
  assert.ok(mid.x > 2.2 && mid.x < 6, `mid ${mid.x}`);
  assert.strictEqual(mid.pose, "run");
  assert.strictEqual(mid.facing, "right");
  const end = st(3.9);
  assertNear([end.x, end.z], [6, -1], "ends at pos");
  assert.strictEqual(end.pose, "idle");
  // running left faces left
  const back = await rig(one([{ at_word: 0, do: "act", who: "pirate", act: "run_to", pos: [-4, 0, 1] }]));
  assert.strictEqual(back.at(0.8).chars.get("pirate").facing, "left");
});

test("hold, drink, throw: the held prop rides the hand, then the throw hands it to a launch", async () => {
  const to = [8, 0.3, -2];
  const r = await rig(one([{ at_word: 0, do: "act", who: "pirate", act: "hold", prop: "mug1" },
    { at_word: 1, do: "act", who: "pirate", act: "drink" },
    { at_word: 3, do: "act", who: "pirate", act: "throw", to, dur: 0.8 }]));
  const hand = (t) => r.A.heldPos(r.at(t).chars.get("pirate"), t);
  assertNear(r.propPos("mug1", 0.49), MUG.pos, "on its own before the hold");
  assertNear(r.propPos("mug1", 0.7), hand(0.7), "in the hand");
  assert.strictEqual(r.at(0.7).chars.get("pirate").holding, "mug1");
  assert.strictEqual(r.at(1.5).chars.get("pirate").pose, "drink");
  assertNear(r.propPos("mug1", 1.5), hand(1.5), "raised with the hand to drink");
  assert.ok(r.propPos("mug1", 1.5)[1] > r.propPos("mug1", 0.7)[1] + 0.3, "the drink lifts the mug");
  // throw at 2.0: wind-up (still held), release at 2.0 + RELEASE, lands on `to`
  const rel = 2.0 + r.A.RELEASE;
  assertNear(r.propPos("mug1", rel - 0.01), hand(rel - 0.01), "held during the wind-up");
  assertNear(r.propPos("mug1", rel), hand(rel), "leaves from the hand in the throw pose");
  assertNear(r.propPos("mug1", rel + 0.8), to, "lands on to");
  assert.strictEqual(r.at(rel + 0.1).chars.get("pirate").holding, undefined, "the hand is empty after the release");
  assert.strictEqual(r.at(rel + 0.05).chars.get("pirate").pose, "throw");
});

test("fly_off: a held prop tumbles away along dir and the hand lets go", async () => {
  const r = await rig(one([{ at_word: 0, do: "act", who: "pirate", act: "toast", prop: "mug1" },
    { at_word: 2, do: "fly_off", who: "mug1", dir: [-1, 0.5, 0] }]));
  const hand = r.A.heldPos(r.at(1.49).chars.get("pirate"), 1.49);
  assertNear(r.propPos("mug1", 1.49), hand, "toasted high in the hand");
  assert.ok(hand[1] > 1.3, `toast raises the mug: ${hand[1]}`);
  const p0 = r.propPos("mug1", 1.5), p1 = r.propPos("mug1", 1.9);
  assert.ok(Math.hypot(...p0.map((v, i) => v - hand[i])) < 0.1, "starts from the hand");
  assert.ok(p1[0] < p0[0] - 1, `flies along -x: ${p1}`);
  assert.strictEqual(r.at(1.6).chars.get("pirate").holding, undefined);
  const o = r.W.spawnProp(MUG, 0.5);
  o.userData.tick(1.6, r.at(1.6).props.get("mug1"));
  const spin = o.rotation.toArray().slice(0, 3);
  o.userData.tick(1.7, r.at(1.7).props.get("mug1"));
  assert.ok(!near(spin, o.rotation.toArray().slice(0, 3), 0.05), "tumbles");
  assert.ok(r.propPos("mug1", 3.9)[1] >= 0, "rests on the ground, not under it");
});

test("character acts pose the character from their word: duck, cower, grab, point_at, look_at, jump, fall", async () => {
  const r = await rig(one([{ at_word: 0, do: "act", who: "pirate", act: "cower" },
    { at_word: 0, do: "act", who: "gus", act: "point_at", id: "cannon1" },
    { at_word: 2, do: "act", who: "gus", act: "jump" },
    { at_word: 4, do: "act", who: "gus", act: "fall" }]));
  const c = new r.C.Char("pirate", { costume: "pirate" });
  const p = c.frame(r.at(1.0).chars.get("pirate"), 1.0, 0);
  assert.strictEqual(p.pose, "cower");
  assert.strictEqual(p.expr, "scared");
  assert.ok(p.sy < 0.95, `cower crouches: ${p.sy}`);
  const g = r.at(1.0).chars.get("gus");
  assert.strictEqual(g.pose, "point");
  assert.strictEqual(g.facing, "right", "toward the cannon");
  const gus = new r.C.Char("gus", "gus");
  const air = gus.frame(r.at(1.75).chars.get("gus"), 1.75, 0);
  assert.ok(air.y > 0.3, `jump lifts: ${air.y}`);
  assert.ok(Math.abs(gus.frame(r.at(2.45).chars.get("gus"), 2.45, 0).y) < 0.05, "and lands");
  assert.ok(Math.abs(gus.frame(r.at(3.6).chars.get("gus"), 3.6, 0).tilt) > 1.3, "fall lies down");
  const look = await rig(one([{ at_word: 0, do: "act", who: "pirate", act: "look_at", id: "gus" },
    { at_word: 1, do: "act", who: "pirate", act: "duck", expr: "worried" },
    { at_word: 2, do: "act", who: "gus", act: "grab", prop: "mug1" }]));
  assert.strictEqual(look.at(0.6).chars.get("pirate").facing, "left");
  assert.strictEqual(look.at(1.2).chars.get("pirate").pose, "duck");
  assert.strictEqual(look.at(1.2).chars.get("pirate").expr, "worried");
  assertNear(look.propPos("mug1", 1.55), MUG.pos, "a grab reaches first");
  assertNear(look.propPos("mug1", 2.0), look.A.heldPos(look.at(2.0).chars.get("gus"), 2.0), "then holds");
  // a pose event ends the act
  const end = await rig(one([{ at_word: 0, do: "act", who: "pirate", act: "cower" }, { at_word: 1, do: "pose", who: "pirate", pose: "idle" }]));
  assert.strictEqual(end.at(1.2).chars.get("pirate").act, undefined);
});

test("the follow camera's target is the projectile's position mid-flight, in its shot and a kept one", async () => {
  const to = [30, 1, -20];
  const st = { beats: [shot([{ at_word: 3, do: "fire", who: "cannon1", projectile: "ball1", to, dur: 2.5 }]),
    { text: "boom", keep: true, cam: { move: "follow", follow: "ball1", target: [0, 1, 0], dist: 4, height: 1, angle: -20 } }] };
  const r = await rig(st);
  const f = r.A.flight(r.W.muzzleAt(CANNON), to, 2.0, 2.5);
  for (const [t, k] of [[2.8, 0], [3.5, 0], [4.3, 1]]) {
    const pos = r.E.followPosAt(r.state, k, "ball1", t);
    assertNear(pos, r.propPos("ball1", t, k), `prop position at ${t}`);
    assertNear(pos, r.A.flightPos(f, t), `on the arc at ${t}`);
    const cam = r.Cam.camPose({ ...st.beats[1].cam, cut: true }, null, 0.5, { follow: pos });
    assertNear(cam.look, pos, `camera looks at the ball at ${t}`);
  }
  assert.throws(() => r.E.followPosAt(r.state, 1, "nope", 4.3), /camera follow: no prop nope in beat 1/);
});

test("seeking equals stepping for a five-event shot", async () => {
  const story = one([{ at_word: 0, do: "act", who: "pirate", act: "hold", prop: "mug1" },
    { at_word: 1, do: "fire", who: "cannon1", projectile: "ball1", to: [2.4, 1, 0.8], dur: 1.0, surface: "wood" },
    { at_word: 1, do: "act", who: "gus", act: "run_to", pos: [-1, 0, 3] },
    { at_word: 2, do: "act", who: "pirate", act: "cower" },
    { at_word: 3, do: "fly_off", who: "mug1", dir: [1, 0.6, 0.3] }]);
  const r = await rig(story);
  const make = () => ({
    chars: new Map(story.beats[0].chars.map((s) => { const c = new r.C.Char(s.id, s.id === "gus" ? "gus" : { costume: "pirate" }); c.born = 0.5; c.keep(s, 0.5); return [s.id, c]; })),
    props: new Map(story.beats[0].props.map((s) => [s.id, r.W.spawnProp(s, 0.5)])),
  });
  const show = (w, t) => {
    const now = r.at(t);
    const out = { fx: now.fx };
    w.chars.forEach((c, id) => { out[id] = c.frame(now.chars.get(id), t, 0); });
    w.props.forEach((o, id) => { o.userData.tick(t, now.props.get(id)); out[id] = [o.visible, ...o.position.toArray(), ...o.rotation.toArray().slice(0, 3), ...o.scale.toArray()]; });
    return out;
  };
  const stepped = make(), T = 2.9;
  let last;
  for (let f = 15; f <= Math.round(T * 30); f++) last = show(stepped, f / 30);
  const seeked = make();
  show(seeked, 3.8); // jump past T first, then back: still the same frame
  assert.deepStrictEqual(show(seeked, T), last);
});

test("an action whose other prop or character has left the stage in a later shot is a no-op there", async () => {
  const later = (events, removed) => ({ beats: [shot(events), { text: "boom", keep: true, remove: removed }] });
  // fire + projectile, ball removed: the cannon's own event goes on (no crash), the ball is simply gone
  const fire = await rig(later([{ at_word: 1, do: "fire", who: "cannon1", projectile: "ball1", to: [9, 0, -9] }], ["ball1"]));
  assert.doesNotThrow(() => fire.at(4.3, 1));
  assert.strictEqual(fire.at(4.3, 1).props.has("ball1"), false);
  // hold then throw, mug removed
  const thr = await rig(later([{ at_word: 0, do: "act", who: "pirate", act: "hold", prop: "mug1" },
    { at_word: 2, do: "act", who: "pirate", act: "throw", to: [6, 0, 0] }], ["mug1"]));
  assert.doesNotThrow(() => thr.at(4.3, 1));
  assert.strictEqual(thr.at(4.3, 1).chars.get("pirate").pose, "idle", "the throw itself still plays");
  // grab, mug removed
  const grab = await rig(later([{ at_word: 0, do: "act", who: "pirate", act: "grab", prop: "mug1" }], ["mug1"]));
  assert.doesNotThrow(() => grab.at(4.3, 1));
  // point_at / look_at a character that has left: the act is skipped, the facing stays
  const look = await rig(later([{ at_word: 0, do: "act", who: "pirate", act: "look_at", id: "gus" },
    { at_word: 1, do: "act", who: "pirate", act: "point_at", id: "cannon1" }], ["gus", "cannon1"]));
  const p = look.at(4.3, 1).chars.get("pirate");
  assert.strictEqual(p.facing, "right");
  assert.notStrictEqual(p.pose, "point");
  // in the action's own shot a missing id is still a story error
  const bad = await rig(one([{ at_word: 0, do: "act", who: "pirate", act: "point_at", id: "ghost" }]));
  assert.throws(() => bad.at(1.0), /beat 0: act: no character or prop ghost on stage/);
  const noBall = await rig(one([{ at_word: 0, do: "fire", who: "cannon1", projectile: "nope", to: [1, 1, 1] }]));
  assert.throws(() => noBall.at(1.0), /beat 0: fire: no prop nope on stage/);
});

test("fire without a projectile rejects flight fields; act fields come from the acts", async () => {
  const { E, A } = await load();
  const bad = (ev) => () => E.eventTimes({ events: [{ at_word: 0, ...ev }] }, TL.beats[1]);
  assert.throws(bad({ do: "fire", who: "cannon1", to: [1, 2, 3] }), /beat 1: fire: to needs a projectile/);
  assert.throws(bad({ do: "fire", who: "cannon1", surface: "wood" }), /beat 1: fire: surface needs a projectile/);
  assert.throws(bad({ do: "fire", who: "cannon1", impact: "splash" }), /beat 1: fire: impact needs a projectile/);
  assert.doesNotThrow(bad({ do: "fire", who: "cannon1" }));
  assert.throws(bad({ do: "act", who: "pirate", act: "grab" }), /beat 1: act: grab needs prop/);
  const cat = A.catalog().act_fields;
  for (const [name, a] of Object.entries(A.ACTS)) {
    assert.deepStrictEqual(cat[name].need, a.need, name);
    assert.deepStrictEqual(cat[name].opt, a.opt, name);
  }
  assert.deepStrictEqual(cat.run_to, { need: ["pos"], opt: ["speed"] });
});

test("run_to shows the run pose over an act pose; the held prop rides the running hand", async () => {
  const r = await rig(one([{ at_word: 0, do: "act", who: "pirate", act: "hold", prop: "mug1" },
    { at_word: 1, do: "act", who: "pirate", act: "run_to", pos: [6, 0, 1] }]));
  const c = new r.C.Char("pirate", { costume: "pirate" });
  c.born = 0.5; c.keep(shot([]).chars[0], 0.5);
  assert.strictEqual(c.frame(r.at(1.3).chars.get("pirate"), 1.3, 0).pose, "run");
  assert.strictEqual(c.frame(r.at(3.9).chars.get("pirate"), 3.9, 0).pose, "carry", "back to the act pose once there");
  const s = r.at(1.3).chars.get("pirate");
  assertNear(r.propPos("mug1", 1.3), r.C.handAt({ ...s, pose: "run" }, 1.3), "in the running hand");
});
