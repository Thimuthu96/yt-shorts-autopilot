// World registry under plain node: catalog export, set/prop builders, moods, anims.
const test = require("node:test");
const assert = require("node:assert");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const STUDIO = path.join(__dirname, "..");
const world = () => import(pathToFileURL(path.join(STUDIO, "engine", "world.js")).href);

const SET_NAMES = ["ship_deck", "open_sea", "harbour", "coast", "furnace_room", "town_street", "room", "office", "lab",
  "field", "castle_yard", "cutaway"];
const MOOD_NAMES = ["day", "interior_glow", "sunset", "night", "steel"];
const PROP_NAMES = ["cannon", "cannonball", "barrel", "crate", "rope_coil", "lantern", "ship", "lighthouse", "sign_post",
  "table", "chair", "bed", "door", "bell", "coffin", "jar", "coin", "lever", "gear", "train_car", "rail", "flag", "torch",
  "tongs", "furnace", "pillar_rock", "palm", "cloud"];
const ANIM_NAMES = ["spin", "float", "drop", "wobble", "fly", "sink"];

test("node studio/catalog.js writes every set, mood, prop and anim", () => {
  const r = spawnSync("node", [path.join(STUDIO, "catalog.js")], { encoding: "utf8" });
  assert.strictEqual(r.status, 0, r.stderr);
  assert.strictEqual(r.stderr, "");
  const cat = JSON.parse(fs.readFileSync(path.join(STUDIO, "catalog.json"), "utf8"));
  for (const s of SET_NAMES) assert.ok(cat.sets.includes(s), `set ${s}`);
  assert.deepStrictEqual([...cat.moods].sort(), [...MOOD_NAMES].sort());
  for (const p of PROP_NAMES) assert.ok(cat.props.includes(p), `prop ${p}`);
  assert.deepStrictEqual([...cat.anims].sort(), [...ANIM_NAMES].sort());
  assert.deepStrictEqual(cat.sfx, ["whoosh", "boom", "splash", "impact", "pop", "ding", "crackle", "creak"]);
  for (const k of ["poses", "exprs", "motions", "enters", "fx", "cam_moves", "sign_styles", "transitions", "looks",
    "costume_keys", "costumes", "frame_half_width"]) assert.ok(k in cat, `key ${k}`);
});

test("buildSet rejects an unknown set", async () => {
  const W = await world();
  assert.throws(() => W.buildSet({ type: "nope" }), /unknown set: nope/);
  assert.throws(() => W.buildSet({ type: "field", mood: "gloomy" }), /unknown mood: gloomy/);
});

test("every set builds in every mood, with its fog", async () => {
  const W = await world();
  for (const type of SET_NAMES) for (const mood of MOOD_NAMES) {
    const g = W.buildSet({ type, mood });
    assert.ok(g.isGroup && g.children.length > 3, `${type}/${mood}`);
    assert.ok(g.userData.fog && g.userData.fog.isFog, `${type}/${mood} fog`);
  }
});

test("moods carry sky, sun, ambient, fog and tint", async () => {
  const W = await world();
  assert.deepStrictEqual(Object.keys(W.MOODS).sort(), [...MOOD_NAMES].sort());
  for (const [name, m] of Object.entries(W.MOODS))
    for (const k of ["skyTop", "skyBottom", "sun", "ambient", "fog", "tint"]) assert.ok(m[k], `${name}.${k}`);
});

test("every prop spawns, takes a face and animates; unknown props fail", async () => {
  const W = await world();
  for (const type of PROP_NAMES) {
    const o = W.spawnProp({ id: type, type, pos: [1, 0, -2], rot: [0, 90, 0], scale: 1.5, face: "scared" }, 0);
    o.userData.tick(1);
    assert.ok(o.visible, type);
    assert.deepStrictEqual(o.position.toArray(), [1, 0, -2]);
  }
  assert.throws(() => W.spawnProp({ type: "nope" }, 0), /unknown prop: nope/);
  assert.throws(() => W.spawnProp({ type: "barrel", anim: "dance" }, 0), /unknown anim: dance/);
  assert.throws(() => W.spawnProp({ type: "barrel", face: "meh" }, 0), /unknown expr: meh/);
});

test("a delayed prop stays hidden until it is born; anims move it", async () => {
  const W = await world();
  const o = W.spawnProp({ type: "crate", pos: [0, 0, 0], delay: 0.5 }, 2);
  o.userData.tick(2.2);
  assert.strictEqual(o.visible, false);
  o.userData.tick(3);
  assert.strictEqual(o.visible, true);
  for (const anim of ANIM_NAMES) {
    const p = W.spawnProp({ type: "cannonball", pos: [0, 1, 0], anim }, 0);
    p.userData.tick(0.4);
    const a = p.position.toArray().concat(p.rotation.toArray().slice(0, 3));
    p.userData.tick(0.9);
    const b = p.position.toArray().concat(p.rotation.toArray().slice(0, 3));
    assert.notDeepStrictEqual(a, b, anim);
  }
});

test("a prop with no delay is there in full when its beat opens; a delayed one pops in", async () => {
  const W = await world();
  const now = W.spawnProp({ type: "crate", pos: [0, 0, 0], scale: 1.2 }, 5);
  now.userData.tick(5);
  assert.strictEqual(now.visible, true);
  assert.ok(Math.abs(now.scale.x - 1.2) < 1e-9, `scale at the cut: ${now.scale.x}`);
  const late = W.spawnProp({ type: "crate", pos: [0, 0, 0], delay: 0.5 }, 5);
  late.userData.tick(5.55);
  assert.ok(late.scale.x < 0.9, `a delayed prop starts small: ${late.scale.x}`);
  late.userData.tick(6);
  assert.ok(Math.abs(late.scale.x - 1) < 1e-9);
});
