// Cast registry under plain node: looks, costumes, Char.frame state, motions, catalog export.
const test = require("node:test");
const assert = require("node:assert");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const STUDIO = path.join(__dirname, "..");
const cast = () => import(pathToFileURL(path.join(STUDIO, "engine", "cast.js")).href);

const POSES = ["idle", "point", "wave", "armsUp", "shrug", "think", "hold", "cross", "facepalm", "present", "scared", "run",
  "fall", "cheer", "carry", "drink", "toast", "throw_wind", "throw", "duck", "cower", "grab"];
const EXPRS = ["neutral", "happy", "excited", "smug", "sly", "shocked", "scared", "sad", "worried", "angry", "pain"];
const MOTIONS = ["bob", "hop", "shake", "flinch", "run_across", "fall_over", "spin"];
const ENTERS = ["left", "right", "drop", "pop"];
const KEYS = ["costume", "shirt", "stripes", "pants", "hat", "hatColor", "bandana", "coat", "apron", "crown", "helmet",
  "glasses", "mustache", "beard", "badge", "prop"];
const COSTUMES = ["sailor", "pirate", "officer", "worker", "scientist", "suit", "king", "knight", "farmer", "chef", "doctor",
  "plain"];

test("registry names match the plan", async () => {
  const C = await cast();
  assert.deepStrictEqual(Object.keys(C.POSES), POSES);
  assert.deepStrictEqual(C.EXPRS, EXPRS);
  assert.deepStrictEqual(Object.keys(C.MOTIONS), MOTIONS);
  assert.deepStrictEqual(Object.keys(C.ENTERS), ENTERS);
  assert.deepStrictEqual(C.COSTUME_KEYS, KEYS);
  assert.deepStrictEqual(Object.keys(C.COSTUMES), COSTUMES);
});

test("every costume expands to costume keys only", async () => {
  const C = await cast();
  for (const [name, look] of Object.entries(C.COSTUMES)) {
    for (const k of Object.keys(look)) assert.ok(C.COSTUME_KEYS.includes(k), `${name}.${k}`);
    const full = C.resolveLook({ costume: name });
    for (const k of Object.keys(full)) assert.ok(C.COSTUME_KEYS.includes(k), `${name} -> ${k}`);
    assert.strictEqual(full.costume, name);
  }
});

test("looks: gus is the fixed signature, dicts merge over their costume, bad looks throw", async () => {
  const C = await cast();
  assert.deepStrictEqual(new C.Char("x", "gus").look, C.GUS_LOOK);
  const l = C.resolveLook({ costume: "sailor", shirt: "#ff0000" });
  assert.strictEqual(l.shirt, "#ff0000");
  assert.strictEqual(l.stripes, C.COSTUMES.sailor.stripes);
  assert.throws(() => C.resolveLook({ cape: "#fff" }), /unknown look key: cape/);
  assert.throws(() => C.resolveLook({ costume: "ninja" }), /unknown costume: ninja/);
  assert.throws(() => C.resolveLook("bob"), /unknown look: bob/);
  assert.throws(() => C.resolveLook({ hat: "sombrero" }), /unknown hat: sombrero/);
  assert.throws(() => C.resolveLook({ prop: "banana" }), /unknown prop: banana/);
});

test("talk mouth follows the envelope in thirds; silent chars keep it shut", async () => {
  const C = await cast();
  const c = new C.Char("x", "gus");
  const spec = { id: "x", pos: [0, 0, 0], pose: "idle", expr: "neutral", talk: true };
  assert.strictEqual(c.frame(spec, 1, 0.9).mouth, 1);
  assert.strictEqual(c.frame(spec, 1, 0.1).mouth, 0);
  assert.strictEqual(c.frame(spec, 1, 0.4).mouth, 1 / 3);
  assert.strictEqual(c.frame({ ...spec, talk: false }, 1, 0.9).mouth, 0);
});

test("unknown pose, expr, facing, motion or enter throws", async () => {
  const C = await cast();
  const c = new C.Char("x", { costume: "plain" });
  const ok = { id: "x", pos: [0, 0, 0] };
  assert.throws(() => c.frame({ ...ok, pose: "dab" }, 0, 0), /unknown pose: dab/);
  assert.throws(() => c.frame({ ...ok, expr: "meh" }, 0, 0), /unknown expr: meh/);
  assert.throws(() => c.frame({ ...ok, facing: "up" }, 0, 0), /unknown facing: up/);
  assert.throws(() => c.frame({ ...ok, motion: "moonwalk" }, 0, 0), /unknown motion: moonwalk/);
  assert.throws(() => c.frame({ ...ok, enter: "fly" }, 0, 0), /unknown enter: fly/);
});

test("blink is deterministic and brief", async () => {
  const C = await cast();
  const a = new C.Char("keeper", "gus"), b = new C.Char("keeper", "gus");
  const spec = { id: "keeper", pos: [0, 0, 0] };
  let blinks = 0;
  for (let f = 0; f < 300; f++) {
    const t = f / 30;
    const s = a.frame(spec, t, 0).blink;
    assert.strictEqual(s, b.frame(spec, t, 0).blink);
    blinks += s ? 1 : 0;
  }
  assert.ok(blinks > 0 && blinks < 30, `blink frames in 10 s: ${blinks}`);
});

test("enters and motions move the sprite", async () => {
  const C = await cast();
  const at = (spec, t) => { const c = new C.Char("x", "gus"); c.born = 0; return c.frame({ id: "x", pos: [1, 0, 0], ...spec }, t, 0); };
  assert.ok(at({ enter: "left" }, 0.05).x < 0, "enter left starts off to the left");
  assert.ok(at({ enter: "right" }, 0.05).x > 2, "enter right starts off to the right");
  assert.strictEqual(at({ enter: "left" }, 2).x, 1);
  assert.ok(at({ enter: "drop" }, 0.05).y > 2, "drop starts high");
  assert.ok(at({ enter: "pop" }, 0.02).scale < 0.5, "pop starts small");
  assert.strictEqual(at({ enter: "left" }, -0.1).visible, false);
  assert.ok(Math.abs(at({ motion: "fall_over" }, 2).tilt) > 1.4, "fall_over ends lying down");
  assert.ok(at({ motion: "run_across", facing: "right" }, 2).x > at({ motion: "run_across", facing: "right" }, 1).x);
  assert.ok(at({ motion: "run_across", facing: "left" }, 2).x < at({ motion: "run_across", facing: "left" }, 1).x);
  assert.strictEqual(at({ motion: "run_across" }, 1).pose, "run", "an idle runner uses the run pose");
  assert.ok(at({ motion: "hop" }, 0.2).y > 0.1);
  assert.notStrictEqual(at({ motion: "spin" }, 0.3).spin, 0);
  const kept = new C.Char("x", "gus"); kept.born = 0; kept.beatStart = 5;
  assert.ok(Math.abs(kept.frame({ id: "x", pos: [0, 0, 0], motion: "fall_over" }, 5.05, 0).tilt) < 0.2, "a kept char's motion restarts with the beat");
});

test("the sprite is drawn at its cache bucket's time, so seeking and stepping match", async () => {
  const C = await cast();
  const drawnAt = (look, spec, times) => {
    const c = new C.Char("x", look);
    const drawn = [];
    c.canvas = {}; // pretend there is a canvas; record what would be drawn
    c.draw = (st) => drawn.push(st.t);
    for (const t of times) c.frame({ id: "x", pos: [0, 0, 0], ...spec }, t, 0);
    return drawn[drawn.length - 1];
  };
  // wave redraws at 15 fps: 0.19 and 0.21 share bucket 3 (t = 0.2)
  const stepped = drawnAt({ costume: "plain" }, { pose: "wave" }, [0.19, 0.21]);
  const seeked = drawnAt({ costume: "plain" }, { pose: "wave" }, [0.21]);
  assert.strictEqual(stepped, seeked);
  assert.ok(Math.abs(seeked - 0.2) < 1e-9, `${seeked}`);
  // Gus's scarf redraws at 10 fps: 0.26 and 0.33 share bucket 3 (t = 0.3)
  assert.strictEqual(drawnAt("gus", {}, [0.26, 0.33]), drawnAt("gus", {}, [0.33]));
  // a still pose draws at t = 0
  assert.strictEqual(drawnAt({ costume: "plain" }, { pose: "point" }, [1.37]), 0);
});

test("a kept character without a new pos stays where it was", async () => {
  const C = await cast();
  const c = new C.Char("x", { costume: "plain" });
  c.keep({ id: "x", pos: [2, 0, 1] }, 0); // the beat that brings it in
  const spec = c.keep({ id: "x", pose: "point" }, 2); // a kept beat that omits pos
  assert.deepStrictEqual(spec.pos, [2, 0, 1]);
  const s = c.frame(spec, 2.4, 0);
  assert.ok(Math.abs(s.x - 2) < 1e-9 && s.z === 1, `at ${s.x}, ${s.z}`);
  assert.strictEqual(s.pose, "point");
  // the same pos again: no walk, so an idle pose stays idle
  const still = c.keep({ id: "x", pos: [2, 0, 1] }, 3);
  assert.strictEqual(c.frame(still, 3.2, 0).pose, "idle");
  // a new pos: walks there from the old one
  const moved = c.keep({ id: "x", pos: [-2, 0, 1] }, 4);
  const w = c.frame(moved, 4.4, 0);
  assert.ok(w.x < 2 && w.x > -2 && w.pose === "run", `walking: ${w.x} ${w.pose}`);
  assert.ok(Math.abs(c.frame(moved, 5, 0).x + 2) < 1e-9);
});

test("node studio/catalog.js exports the cast names", () => {
  const r = spawnSync("node", [path.join(STUDIO, "catalog.js")], { encoding: "utf8" });
  assert.strictEqual(r.status, 0, r.stderr);
  const cat = JSON.parse(fs.readFileSync(path.join(STUDIO, "catalog.json"), "utf8"));
  assert.deepStrictEqual(cat.poses, POSES);
  assert.deepStrictEqual(cat.exprs, EXPRS);
  assert.deepStrictEqual(cat.motions, MOTIONS);
  assert.deepStrictEqual(cat.enters, ENTERS);
  assert.deepStrictEqual(cat.costume_keys, KEYS);
  assert.deepStrictEqual(cat.costumes, COSTUMES);
  assert.deepStrictEqual(cat.looks, ["gus"]);
});

test("characters are 30 % taller than v1 (1.8 -> 2.34) and the head sits at the same fraction", async () => {
  const C = await cast();
  assert.ok(Math.abs(C.CHAR_HEIGHT - 1.8 * 1.3) < 1e-9, `height ${C.CHAR_HEIGHT}`);
  assert.ok(C.HEAD_AT > 0.7 && C.HEAD_AT < 0.85);
});

test("faces stay white in every mood: the mood tints the sprite at most 10 % from white", async () => {
  const C = await cast();
  const { MOODS } = await import(pathToFileURL(path.join(STUDIO, "engine", "world.js")).href);
  for (const mood of Object.keys(MOODS)) {
    const hex = C.SPRITE_TINT[mood];
    assert.ok(hex, `tint for ${mood}`);
    const n = parseInt(hex.slice(1), 16), rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    for (const v of rgb) assert.ok((255 - v) / 255 <= 0.1, `${mood} ${hex} is within 10 % of white`);
  }
  assert.strictEqual(C.SPRITE_TINT.day, "#FFFFFF");
});

test("motion and enter distances scale with the character (tuned at 1.8 tall)", async () => {
  const C = await cast();
  const K = C.CHAR_SCALE;
  assert.ok(Math.abs(K - 1.3) < 1e-9);
  const dir = 1;
  assert.ok(Math.abs(C.MOTIONS.run_across(1, 0, dir).x - C.MOTIONS.run_across(0, 0, dir).x - 3.4 * K) < 1e-9, "run_across speed");
  assert.ok(Math.abs(C.MOTIONS.run_across(0, 0, dir).x + 4 * K) < 1e-9, "run_across start");
  const hop = Math.max(...Array.from({ length: 200 }, (_, i) => C.MOTIONS.hop(i / 200).y));
  assert.ok(Math.abs(hop - 0.38 * K) < 0.01, `hop peak ${hop}`);
  assert.ok(Math.abs(C.ENTERS.left(0).x + 6 * K) < 1e-9 && Math.abs(C.ENTERS.drop(0).y - 5 * K) < 1e-9);
});


test("the sprite has headroom above the design for Gus's curl; feet stay on y = 0", async () => {
  const C = await cast();
  const T = await import("three");
  assert.ok(C.SPRITE_PAD >= 45, "the curl's stroke reaches y ≈ -41 design units");
  const c = new C.Char("x", "gus");
  const box = new T.Box3().setFromBufferAttribute(c.plane.geometry.attributes.position);
  const h = box.max.y - box.min.y, w = box.max.x - box.min.x;
  assert.ok(Math.abs(h / w - (C.CH + C.SPRITE_PAD) / C.CW) < 1e-6, `${h / w}`);
  assert.ok(box.min.y < 0 && box.max.y > C.CHAR_HEIGHT + 0.1, "the plane reaches above the head");
  // Char.draw shifts the drawing down by SPRITE_PAD (a recording 2D context: any method is a no-op)
  const moves = [];
  c.ctx = new Proxy({ canvas: { width: C.CW, height: C.CH + C.SPRITE_PAD } }, {
    get: (o, k) => (k in o ? o[k] : k === "translate" ? (dx, dy) => moves.push([dx, dy]) : () => ({ addColorStop() {} })),
    set: () => true,
  });
  c.tex = {};
  c.draw({ pose: "idle", expr: "neutral", facing: "right", t: 0, mouth: 0 });
  assert.deepStrictEqual(moves[0], [0, C.SPRITE_PAD]);
});
