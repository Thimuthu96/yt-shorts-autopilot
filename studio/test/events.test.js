// Shot events under plain node: word-anchored times, stateless application (seek == step), shake decay, catalog.
const test = require("node:test");
const assert = require("node:assert");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const STUDIO = path.join(__dirname, "..");
const events = () => import(pathToFileURL(path.join(STUDIO, "engine", "events.js")).href);
const cast = () => import(pathToFileURL(path.join(STUDIO, "engine", "cast.js")).href);

const TYPES = ["expr", "pose", "motion", "fx", "sign", "sfx_mark", "shake"];

// shot 0: "hit by a cannonball," spoken 1.0-2.6 s; shot 1: "boom" at 3.0 s
const TL = {
  fps: 30, duration: 4,
  beats: [
    { i: 0, start: 1.0, end: 2.8, words: [{ w: "hit", s: 1.0, e: 1.3 }, { w: "by", s: 1.35, e: 1.5 }, { w: "a", s: 1.55, e: 1.6 },
      { w: "cannonball,", s: 1.7, e: 2.6 }] },
    { i: 1, start: 2.8, end: 4.0, words: [{ w: "boom", s: 3.0, e: 3.5 }] },
  ],
};
const shot0 = (evs) => ({ text: "hit by a cannonball,", chars: [{ id: "pirate", pos: [0, 0, 0], expr: "neutral" }], events: evs });
const story = (evs, evs1) => ({ beats: [shot0(evs), { text: "boom", keep: true, events: evs1 }] });

test("EVENT_TYPES lists the built-in event types", async () => {
  const E = await events();
  assert.deepStrictEqual(Object.keys(E.EVENT_TYPES), TYPES);
  for (const k of TYPES) {
    assert.strictEqual(typeof E.EVENT_TYPES[k].validate, "function", k);
    assert.strictEqual(typeof E.EVENT_TYPES[k].apply, "function", k);
  }
});

test("eventTimes maps at_word to that word's start, adds delay, sorts by time", async () => {
  const E = await events();
  const evs = [
    { at_word: 3, do: "shake", amount: 0.4 },
    { at_word: 1, do: "expr", who: "pirate", expr: "shocked" },
    { at_word: 0, do: "sfx_mark", sfx: "boom", delay: 0.25 },
  ];
  const got = E.eventTimes(shot0(evs), TL.beats[0]);
  assert.deepStrictEqual(got.map((x) => x.event.do), ["sfx_mark", "expr", "shake"]);
  assert.deepStrictEqual(got.map((x) => x.t), [1.25, 1.35, 1.7]);
  assert.strictEqual(got[1].event, evs[1]);
  assert.deepStrictEqual(E.eventTimes({ text: "x" }, TL.beats[0]), [], "a v1 beat has no events");
});

test("an at_word outside the shot's words throws with the beat number", async () => {
  const E = await events();
  assert.throws(() => E.eventTimes(shot0([{ at_word: 4, do: "shake" }]), TL.beats[0]), /beat 0: at_word 4 out of range/);
  assert.throws(() => E.eventTimes({ events: [{ at_word: -1, do: "shake" }] }, TL.beats[1]), /beat 1: at_word -1 out of range/);
  assert.throws(() => E.eventTimes({ events: [{ at_word: 0.5, do: "shake" }] }, TL.beats[1]), /beat 1: at_word 0.5 out of range/);
});

test("bad events throw with the beat number", async () => {
  const E = await events();
  const bad = (ev) => () => E.eventTimes({ events: [{ at_word: 0, ...ev }] }, TL.beats[1]);
  assert.throws(bad({ do: "dance" }), /beat 1: unknown event: dance/);
  assert.throws(bad({ do: "expr", who: "pirate", expr: "meh" }), /beat 1: expr: unknown expr: meh/);
  assert.throws(bad({ do: "expr", expr: "happy" }), /beat 1: expr: needs who/);
  assert.throws(bad({ do: "pose", who: "pirate", pose: "dab" }), /beat 1: pose: unknown pose: dab/);
  assert.throws(bad({ do: "motion", who: "pirate", motion: "moonwalk" }), /beat 1: motion: unknown motion: moonwalk/);
  assert.throws(bad({ do: "fx", type: "glitter" }), /beat 1: fx: unknown fx: glitter/);
  assert.throws(bad({ do: "sign" }), /beat 1: sign: needs text/);
  assert.throws(bad({ do: "sign", text: "HI", style: "neon" }), /beat 1: sign: unknown sign style: neon/);
  assert.throws(bad({ do: "sfx_mark" }), /beat 1: sfx_mark: needs sfx/);
  assert.throws(bad({ do: "shake", amount: -1 }), /beat 1: shake: amount must be a positive number/);
  assert.throws(bad({ do: "shake", delay: -0.1 }), /beat 1: delay must be a number >= 0/);
});

test("an expr event changes the expression exactly from its time on; seeking equals stepping", async () => {
  const E = await events(), C = await cast();
  const st = story([{ at_word: 1, do: "expr", who: "pirate", expr: "shocked" }]);
  const base = new Map([["pirate", st.beats[0].chars[0]]]);
  const state = { story: st, timeline: TL, chars: base };
  const exprAt = (c, shot, t) => c.frame(E.applyEvents(state, shot, t).chars.get("pirate"), t, 0).expr;
  const c = new C.Char("pirate", { costume: "pirate" });
  assert.strictEqual(exprAt(c, 0, 1.3499), "neutral");
  assert.strictEqual(exprAt(c, 0, 1.35), "shocked");
  assert.strictEqual(exprAt(c, 0, 2.0), "shocked");
  assert.strictEqual(exprAt(c, 1, 3.2), "shocked", "carries into a kept shot that does not list the character");
  assert.strictEqual(base.get("pirate").expr, "neutral", "the base spec is not changed");
  // a shot that lists the character again starts from its new spec
  const relisted = { ...st, beats: [st.beats[0], { text: "boom", keep: true, chars: [{ id: "pirate", expr: "happy" }] }] };
  const s2 = { story: relisted, timeline: TL, chars: new Map([["pirate", { id: "pirate", pos: [0, 0, 0], expr: "happy" }]]) };
  assert.strictEqual(E.applyEvents(s2, 1, 3.2).chars.get("pirate").expr, "happy");
  // seek vs step: one char walked frame by frame, another jumped straight to t
  const stepped = new C.Char("pirate", { costume: "pirate" }), seeked = new C.Char("pirate", { costume: "pirate" });
  let last;
  for (let f = 30; f <= 75; f++) last = stepped.frame(E.applyEvents(state, f / 30 < 2.8 ? 0 : 1, f / 30).chars.get("pirate"), f / 30, 0);
  const jump = seeked.frame(E.applyEvents(state, 0, 2.5).chars.get("pirate"), 2.5, 0);
  assert.deepStrictEqual(jump, last);
});

test("pose and motion events: a motion starts at its event time", async () => {
  const E = await events(), C = await cast();
  const st = story([{ at_word: 0, do: "pose", who: "pirate", pose: "scared" }, { at_word: 3, do: "motion", who: "pirate", motion: "fall_over" }]);
  const state = { story: st, timeline: TL, chars: new Map([["pirate", st.beats[0].chars[0]]]) };
  const at = (t) => E.applyEvents(state, 0, t).chars.get("pirate");
  assert.strictEqual(at(0.99).pose, undefined);
  assert.strictEqual(at(1.0).pose, "scared");
  assert.strictEqual(at(1.69).motion, undefined);
  assert.strictEqual(at(1.7).motion, "fall_over");
  const c = new C.Char("pirate", "gus"); c.born = 1.0; c.beatStart = 1.0;
  assert.ok(Math.abs(c.frame(at(1.75), 1.75, 0).tilt) < 0.2, "the fall starts at its word, not the shot start");
  assert.ok(Math.abs(c.frame(at(2.7), 2.7, 0).tilt) > 1.4);
});

test("an event naming a character not on stage throws", async () => {
  const E = await events();
  const st = story([{ at_word: 0, do: "expr", who: "ghost", expr: "happy" }]);
  const state = { story: st, timeline: TL, chars: new Map() };
  assert.throws(() => E.applyEvents(state, 0, 1.5), /beat 0: expr: no character ghost on stage/);
});

test("shake displacement starts at its word and decays to 0 by 0.4 s", async () => {
  const E = await events();
  const st = story([{ at_word: 3, do: "shake", amount: 0.4 }]);
  const state = { story: st, timeline: TL, chars: new Map([["pirate", st.beats[0].chars[0]]]) };
  const mag = (t, shot = 0) => Math.hypot(...E.applyEvents(state, shot, t).shake);
  assert.strictEqual(mag(1.69), 0);
  let peak = 0;
  for (let dt = 0; dt < 0.4; dt += 1 / 60) peak = Math.max(peak, mag(1.7 + dt));
  assert.ok(peak > 0.1 && peak <= 0.4 + 1e-9, `peak ${peak}`);
  for (let dt = 0.3; dt < 0.4; dt += 1 / 120) assert.ok(mag(1.7 + dt) < 0.4 * 0.07, `late shake ${mag(1.7 + dt)} at ${dt}`);
  assert.strictEqual(mag(2.1), 0);
  assert.strictEqual(mag(3.5, 1), 0);
  assert.deepStrictEqual(E.shakeAt(0.4, 0.4), [0, 0]);
  assert.deepStrictEqual(E.shakeAt(0.4, -0.01), [0, 0]);
  // a shake near a shot's end carries over the cut (event at 2.7, next shot from 2.8)
  const late = story([{ at_word: 3, do: "shake", amount: 0.4, delay: 1.0 }]);
  const s2 = { story: late, timeline: TL, chars: state.chars };
  assert.ok(Math.hypot(...E.applyEvents(s2, 1, 2.9).shake) > 0, "a shake carries into the next shot");
});

test("fx and sign events spawn at their event time", async () => {
  const E = await events();
  const fx = E.EVENT_TYPES.fx.spawn({ do: "fx", type: "splash", at: [1, 0, 0], scale: 0.5 }, 2.5);
  assert.strictEqual(fx.kind, "fx");
  assert.strictEqual(fx.born, 2.5);
  assert.strictEqual(fx.obj.userData.type, "splash");
  assert.deepStrictEqual(fx.obj.position.toArray(), [1, 0, 0]);
  const sign = E.EVENT_TYPES.sign.spawn({ do: "sign", text: "BOOM", pos: [0, 3, 0], style: "plank" }, 2.5);
  assert.strictEqual(sign.kind, "sign");
  assert.strictEqual(sign.obj.userData.born, 2.5);
  sign.obj.userData.tick(2.49);
  assert.strictEqual(sign.obj.visible, false);
  sign.obj.userData.tick(2.5);
  assert.strictEqual(sign.obj.visible, true);
});

test("node studio/catalog.js exports the event types", () => {
  const r = spawnSync("node", [path.join(STUDIO, "catalog.js")], { encoding: "utf8" });
  assert.strictEqual(r.status, 0, r.stderr);
  const cat = JSON.parse(fs.readFileSync(path.join(STUDIO, "catalog.json"), "utf8"));
  assert.deepStrictEqual(cat.events, TYPES);
});
