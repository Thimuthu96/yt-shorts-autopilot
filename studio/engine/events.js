// Shot events (story format v2): visible actions anchored to spoken words. Pure registry module: nothing touches the
// DOM at import time (catalog.js and tests import it under node).
//   EVENT_TYPES[do] = {validate(ev), apply(ctx, ev, dt), spawn?(ev, t)}
//     validate throws a plain message (eventTimes adds "beat N: ");
//     apply changes this frame's ctx; dt = t - eventTime >= 0, so an effect is a function of dt alone;
//     spawn (fx, sign) makes the object at setup time, hidden until its event time: {kind: "fx"|"sign", obj, born}
//   eventTimes(shot, tlBeat) -> [{event, t}]   t = the at_word-th word's start (timeline seconds) + delay, by time
//   shotEvents(story, timeline) -> [[{event, t}] per shot]   (every event checked; the engine calls it in setup)
//   applyEvents(state, shotIndex, t) -> {chars: Map(id -> spec at t), shake: [right, up]}
//     state = {story, timeline, chars: Map(id -> base spec), events?: shotEvents(...)}; never mutates state.
//   shakeAt(amount, dt) -> [right, up] camera offset in world units, 0 outside 0..SHAKE_DUR
// Stateless per t: a character's spec at t is the spec of the latest shot that lists it, plus every event of that
// shot and the later ones up to the current shot with eventTime <= t, applied in time order. Nothing accumulates
// across frames, so seeking to t gives exactly the frame that stepping to t gives.
import { EXPRS, POSES, MOTIONS } from "./cast.js";
import { FX, makeFx } from "./fx.js";
import { SIGN_STYLES, spawnSign } from "./signs.js";

export const SHAKE_DUR = 0.4; // seconds for a camera shake to die out

const need = (ev, key) => { if (ev[key] == null || ev[key] === "") throw new Error(`needs ${key}`); };
const oneOf = (ev, key, names, what) => { need(ev, key); if (!names.includes(ev[key])) throw new Error(`unknown ${what}: ${ev[key]}`); };

// this frame's spec of the character an event acts on (ctx.chars holds per-frame copies)
function who(ctx, ev) {
  const spec = ctx.chars.get(ev.who);
  if (!spec) throw new Error(`no character ${ev.who} on stage`);
  return spec;
}
const charEvent = (key, names) => ({
  validate: (ev) => { need(ev, "who"); oneOf(ev, key, names, key); },
  apply: (ctx, ev) => { who(ctx, ev)[key] = ev[key]; },
});
const noop = () => {};

export function shakeAt(amount, dt) {
  if (!(dt >= 0 && dt < SHAKE_DUR)) return [0, 0];
  const k = amount * Math.pow(1 - dt / SHAKE_DUR, 2), w = 2 * Math.PI * dt;
  return [k * 0.8 * Math.sin(w * 15 + 0.9), k * 0.6 * Math.sin(w * 19 + 2.1)];
}

export const EVENT_TYPES = {
  expr: charEvent("expr", EXPRS),
  pose: charEvent("pose", Object.keys(POSES)),
  // the motion runs from its event time, not the shot's start
  motion: {
    validate: (ev) => { need(ev, "who"); oneOf(ev, "motion", Object.keys(MOTIONS), "motion"); },
    apply: (ctx, ev, dt) => { const s = who(ctx, ev); s.motion = ev.motion; s.motionStart = ctx.t - dt; },
  },
  fx: {
    validate: (ev) => oneOf(ev, "type", Object.keys(FX), "fx"),
    apply: noop,
    spawn: (ev, t) => ({ kind: "fx", obj: makeFx(ev.type, ev.at || [0, 0, 0], null, ev.scale || 1), born: t }),
  },
  sign: {
    validate: (ev) => { need(ev, "text"); if (ev.style && !SIGN_STYLES[ev.style]) throw new Error(`unknown sign style: ${ev.style}`); },
    apply: noop,
    spawn: (ev, t) => {
      const obj = spawnSign({ text: ev.text, pos: ev.pos, style: ev.style, rot: ev.rot }, t);
      return { kind: "sign", obj, born: t };
    },
  },
  // a sound cue for the Python mixer (it reads the story); nothing to draw
  sfx_mark: { validate: (ev) => need(ev, "sfx"), apply: noop },
  shake: {
    validate: (ev) => { if (ev.amount != null && !(typeof ev.amount === "number" && ev.amount > 0)) throw new Error("amount must be a positive number"); },
    apply: (ctx, ev, dt) => {
      const [x, y] = shakeAt(ev.amount ?? 0.3, dt);
      ctx.shake[0] += x; ctx.shake[1] += y;
    },
  },
};

export function eventTimes(shot, tlBeat) {
  const n = tlBeat.i, words = tlBeat.words || [];
  return (shot.events || []).map((event) => {
    const fail = (msg) => { throw new Error(`beat ${n}: ${msg}`); };
    const type = EVENT_TYPES[event.do];
    if (!type) fail(`unknown event: ${event.do}`);
    const k = event.at_word;
    if (!Number.isInteger(k) || k < 0 || k >= words.length) fail(`at_word ${k} out of range`);
    const delay = event.delay ?? 0;
    if (!(typeof delay === "number" && delay >= 0)) fail("delay must be a number >= 0");
    try { type.validate(event); } catch (e) { fail(`${event.do}: ${e.message}`); }
    return { event, t: words[k].s + delay };
  }).sort((a, b) => a.t - b.t);
}

export const shotEvents = (story, timeline) => story.beats.map((shot, k) => eventTimes(shot, { i: k, ...timeline.beats[k] }));

const lists = (shot, id) => (shot.chars || []).some((c) => c.id === id);

export function applyEvents(state, shotIndex, t) {
  const { story } = state;
  const all = state.events || shotEvents(story, state.timeline);
  const ctx = { t, chars: new Map(), shake: [0, 0] };
  state.chars.forEach((spec, id) => ctx.chars.set(id, { ...spec }));
  for (let k = 0; k <= shotIndex; k++) {
    for (const { event, t: at } of all[k]) {
      if (at > t) break;
      // a character event is spent once a later shot lists the character again (a new base spec) or once the
      // character has left the stage; in the current shot a missing character is an error (apply throws)
      if (event.who != null) {
        const spent = story.beats.slice(k + 1, shotIndex + 1).some((b) => lists(b, event.who));
        const gone = k < shotIndex && !ctx.chars.has(event.who);
        if (spent || gone) continue;
      }
      try { EVENT_TYPES[event.do].apply(ctx, event, t - at); } catch (e) { throw new Error(`beat ${k}: ${event.do}: ${e.message}`); }
    }
  }
  return { chars: ctx.chars, shake: ctx.shake };
}

// Names this registry adds to studio/catalog.json.
export function catalog() {
  return { events: Object.keys(EVENT_TYPES) };
}
