// Captions, FX and in-world signs under plain node: captionWord timing, FX determinism, sign styles, catalog export.
const test = require("node:test");
const assert = require("node:assert");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const STUDIO = path.join(__dirname, "..");
const load = (name) => import(pathToFileURL(path.join(STUDIO, "engine", name)).href);

const FX_NAMES = ["smoke", "fire", "splinters", "sparks", "explosion", "splash", "steam", "glow", "flash", "debris",
  "bubbles", "question", "gunsmoke"];
const SIGN_STYLES = ["plank", "barrel_label", "banner", "chalk", "metal", "paper"];

// two beats; beat 0 has a pause between "lighthouse" and "blinks" and ends 0.4 s after its last word
const TL = {
  fps: 30, duration: 4,
  beats: [
    { i: 0, start: 0, end: 2, words: [{ w: "Every", s: 0.1, e: 0.4 }, { w: "lighthouse", s: 0.45, e: 0.9 },
      { w: "blinks", s: 1.2, e: 1.6 }] },
    { i: 1, start: 2, end: 4, words: [{ w: "in", s: 2.3, e: 2.5 }, { w: "code.", s: 2.5, e: 3.0 }] },
  ],
};

test("captionWord: the word being spoken", async () => {
  const { captionWord } = await load("captions.js");
  assert.strictEqual(captionWord(TL, 0.2), "Every");
  assert.strictEqual(captionWord(TL, 0.45), "lighthouse");
  assert.strictEqual(captionWord(TL, 2.7), "code.");
});

test("captionWord: a gap inside a beat keeps the previous word", async () => {
  const { captionWord } = await load("captions.js");
  assert.strictEqual(captionWord(TL, 1.0), "lighthouse");
  assert.strictEqual(captionWord(TL, 1.19), "lighthouse");
  assert.strictEqual(captionWord(TL, 1.8), "blinks"); // after the last word, before the beat ends
});

test("captionWord: before the first word and outside beats it is empty", async () => {
  const { captionWord } = await load("captions.js");
  assert.strictEqual(captionWord(TL, 0), "");
  assert.strictEqual(captionWord(TL, 0.05), "");
  assert.strictEqual(captionWord(TL, 2.1), ""); // next beat, its first word not started yet
  assert.strictEqual(captionWord(TL, 4.5), ""); // after the last beat
  assert.strictEqual(captionWord(TL, -1), "");
  assert.strictEqual(captionWord({ beats: [] }, 1), "");
});

test("captionText drops trailing commas and full stops only", async () => {
  const { captionText } = await load("captions.js");
  assert.strictEqual(captionText("code."), "code");
  assert.strictEqual(captionText("sea,"), "sea");
  assert.strictEqual(captionText("why?"), "why?");
  assert.strictEqual(captionText("1,000"), "1,000");
  assert.strictEqual(captionText(""), "");
});

const snapshot = (g) => g.userData.parts.map((s) => [...s.position.toArray(), ...s.scale.toArray(), s.visible,
  s.material.rotation, s.material.opacity]);

test("FX lists the plan's effects; every one builds and moves", async () => {
  const F = await load("fx.js");
  assert.deepStrictEqual(Object.keys(F.FX), FX_NAMES);
  for (const type of FX_NAMES) {
    const g = F.makeFx(type, [1, 0.5, -2]);
    assert.deepStrictEqual(g.position.toArray(), [1, 0.5, -2], type);
    F.updateFx(g, 0.3);
    const a = JSON.stringify(snapshot(g));
    assert.ok(g.userData.parts.some((s) => s.visible), `${type} shows something at 0.3 s`);
    F.updateFx(g, 0.6);
    assert.notStrictEqual(JSON.stringify(snapshot(g)), a, `${type} moves`);
    for (const s of g.userData.parts) for (const v of s.position.toArray().concat(s.scale.toArray()))
      assert.ok(Number.isFinite(v), `${type} finite`);
  }
  assert.throws(() => F.makeFx("rainbow", [0, 0, 0]), /unknown fx: rainbow/);
});

test("FX are deterministic: same seed and time give identical particles, seeking equals stepping", async () => {
  const F = await load("fx.js");
  for (const type of FX_NAMES) {
    const a = F.makeFx(type, [0, 1, 0], 42), b = F.makeFx(type, [0, 1, 0], 42);
    F.updateFx(a, 0.9);
    // b steps through earlier frames first; its state at 0.9 must not depend on them
    for (let t = 0; t < 2.5; t += 1 / 30) F.updateFx(b, t);
    F.updateFx(b, 0.9);
    assert.deepStrictEqual(snapshot(b), snapshot(a), type);
  }
  // the default seed comes from the type and position, so a re-render is identical too
  const c = F.makeFx("explosion", [3, 0, 1]), d = F.makeFx("explosion", [3, 0, 1]);
  F.updateFx(c, 0.4); F.updateFx(d, 0.4);
  assert.deepStrictEqual(snapshot(c), snapshot(d));
  // a different seed scatters the particles differently
  const e = F.makeFx("splinters", [0, 1, 0], 1), f = F.makeFx("splinters", [0, 1, 0], 2);
  F.updateFx(e, 0.5); F.updateFx(f, 0.5);
  assert.notDeepStrictEqual(snapshot(e), snapshot(f));
});

test("FX before their start show nothing; bursts end; splinters land on the ground", async () => {
  const F = await load("fx.js");
  for (const type of FX_NAMES) {
    const g = F.makeFx(type, [0, 1, 0]);
    F.updateFx(g, -0.1);
    assert.ok(!g.visible, `${type} hidden before it starts`);
  }
  for (const type of ["explosion", "flash", "splash", "gunsmoke"]) {
    const g = F.makeFx(type, [0, 1, 0]);
    F.updateFx(g, 20);
    assert.ok(!g.userData.parts.some((s) => s.visible), `${type} is over`);
  }
  const g = F.makeFx("splinters", [0, 1.5, 0]);
  F.updateFx(g, 2.5);
  const ys = g.userData.parts.filter((s) => s.visible).map((s) => g.position.y + s.position.y * g.scale.y);
  assert.ok(ys.length > 5 && ys.every((y) => y >= 0 && y < 0.2), `landed: ${ys.map((y) => y.toFixed(2))}`);
});

test("signs: every style builds a readable plane; unknown style fails; spawnSign pops in after its delay", async () => {
  const S = await load("signs.js");
  assert.deepStrictEqual(Object.keys(S.SIGN_STYLES), SIGN_STYLES);
  for (const style of SIGN_STYLES) {
    const g = S.signPlane("HOT SHOT", style);
    const box = g.userData.size;
    assert.ok(box.w > box.h && box.h > 0.2, `${style} size ${JSON.stringify(box)}`);
  }
  // longer text is wider; a line break makes it taller
  const short = S.signPlane("ICE", "plank").userData.size, long = S.signPlane("CARCASS SHOT", "plank").userData.size;
  assert.ok(long.w > short.w);
  assert.ok(S.signPlane("KEEP FROM\nFLAME", "paper").userData.size.h > S.signPlane("KEEP", "paper").userData.size.h);
  assert.throws(() => S.signPlane("X", "neon"), /unknown sign style: neon/);
  assert.throws(() => S.signPlane("", "plank"), /empty sign text/);
  const o = S.spawnSign({ text: "1 FLASH / 5 SEC", pos: [1, 3, 0], style: "plank", delay: 0.8 }, 2);
  o.userData.tick(2.5);
  assert.strictEqual(o.visible, false);
  o.userData.tick(4);
  assert.ok(o.visible);
  assert.deepStrictEqual(o.position.toArray(), [1, 3, 0]);
  assert.ok(Math.abs(o.scale.x - 1) < 1e-9);
});

test("catalog.json lists fx and sign_styles", () => {
  const r = spawnSync("node", [path.join(STUDIO, "catalog.js")], { encoding: "utf8" });
  assert.strictEqual(r.status, 0, r.stderr);
  const cat = JSON.parse(fs.readFileSync(path.join(STUDIO, "catalog.json"), "utf8"));
  assert.deepStrictEqual(cat.fx, FX_NAMES);
  assert.deepStrictEqual(cat.sign_styles, SIGN_STYLES);
});
