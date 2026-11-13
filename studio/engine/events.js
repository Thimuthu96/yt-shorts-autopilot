// Shot events (story format v2): visible actions anchored to spoken words. Pure registry module: nothing touches the
// DOM at import time (catalog.js and tests import it under node).
//   EVENT_TYPES[do] = {scope, validate(ev), apply(ctx, ev, dt), spawn?(ev, t)}
//     scope: a SCOPES name. A scoped event acts on ctx[SCOPES[scope].view].get(ev.who); "scene" acts on the frame.
//     validate throws a plain message (eventTimes adds "beat N: ");
//     apply changes this frame's ctx; dt = t - eventTime >= 0, so an effect is a function of dt alone;
//     spawn (fx, sign) makes the object at setup time, hidden until its event time: {kind: "fx"|"sign", obj, born}
//   SCOPES[name] = {view, listed(shot) -> [ids]}   the things events act on; a new scope is one more entry
//   eventTimes(shot, tlBeat) -> [{event, t}]   t = the at_word-th word's start (timeline seconds) + delay, by time
//   shotEvents(story, timeline) -> [[{event, t}] per shot]   (every event checked; the engine calls it in setup)
//   shotRoster(story) -> [{scope: Set(ids listed in that shot)} per shot]
//   applyEvents(state, shotIndex, t) -> ctx = {t, shake: [right, up], <view>: Map(id -> spec at t) per scope}
//     state = {story, timeline, <view>: Map(id -> base spec) per scope (a missing view is empty),
//              events?: shotEvents(...), roster?: shotRoster(...)}; never mutates state.
//   shakeAt(amount, dt) -> [right, up] camera offset in world units, 0 outside 0..SHAKE_DUR
//   ctx.fx: [{key, shot, type, at, born, scale, rotY?}] effects the actions make (see actions.js); ctx.key / ctx.shot
//     name the event being applied ("<shot>.<index in its sorted list>")
//   stageAt(story, timeline, k) -> {chars, props} base specs on stage in shot k (props carry id + spawnT)
//   followPosAt(state, k, id, t) -> the prop's position at t with its events (the camera's follow target)
// Action events (fire, launch, impact, fly_off, act) live in actions.js and are merged in below.
// Stateless per t: a thing's spec at t is the spec of the latest shot that lists it, plus every event of that shot
// and the later ones up to the current shot with eventTime <= t, applied in time order. A scoped event is spent once
// a later shot lists its `who` again (a new base spec) or once its `who` has left the stage; scene events never are.
// Nothing accumulates across frames, so seeking to t gives exactly the frame that stepping to t gives.
import { EXPRS, POSES, MOTIONS } from "./cast.js";
import { FX, makeFx } from "./fx.js";
import { SIGN_STYLES, spawnSign } from "./signs.js";
import { propPosAt } from "./world.js";
import { ACTION_TYPES, ACTION_FIELDS, pushAct, refresh } from "./actions.js";

export const SHAKE_DUR = 0.4; // seconds for a camera shake to die out

const need = (ev, key) => { if (ev[key] == null || ev[key] === "") throw new Error(`needs ${key}`); };
const oneOf = (ev, key, names, what) => { need(ev, key); if (!names.includes(ev[key])) throw new Error(`unknown ${what}: ${ev[key]}`); };

// the ids a shot lists (props without an id get the engine's `${type}${n}`)
export const SCOPES = {
  char: { view: "chars", listed: (shot) => (shot.chars || []).map((c) => c.id) },
  prop: { view: "props", listed: (shot) => (shot.props || []).map((p, n) => p.id || `${p.type}${n}`) },
};

// this frame's spec of the character an event acts on (ctx.chars holds per-frame copies)
function who(ctx, ev) {
  const spec = ctx.chars.get(ev.who);
  if (!spec) throw new Error(`no character ${ev.who} on stage`);
  return spec;
}
const charEvent = (key, names) => ({
  scope: "char",
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
  // a pose joins the character's acts (actions.js), so it ends the current act and past moments still know it
  pose: {
    scope: "char",
    validate: (ev) => { need(ev, "who"); oneOf(ev, "pose", Object.keys(POSES), "pose"); },
    apply: (ctx, ev, dt) => { const s = who(ctx, ev); pushAct(s, ctx.t - dt, () => ({ pose: ev.pose, off: null })); refresh(s, ctx.t); },
  },
  // the motion runs from its event time, not the shot's start
  motion: {
    scope: "char",
    validate: (ev) => { need(ev, "who"); oneOf(ev, "motion", Object.keys(MOTIONS), "motion"); },
    apply: (ctx, ev, dt) => { const s = who(ctx, ev); s.motion = ev.motion; s.motionStart = ctx.t - dt; },
  },
  fx: {
    scope: "scene",
    validate: (ev) => oneOf(ev, "type", Object.keys(FX), "fx"),
    apply: noop,
    spawn: (ev, t) => ({ kind: "fx", obj: makeFx(ev.type, ev.at || [0, 0, 0], null, ev.scale || 1), born: t }),
  },
  sign: {
    scope: "scene",
    validate: (ev) => { need(ev, "text"); if (ev.style && !SIGN_STYLES[ev.style]) throw new Error(`unknown sign style: ${ev.style}`); },
    apply: noop,
    spawn: (ev, t) => {
      const obj = spawnSign({ text: ev.text, pos: ev.pos, style: ev.style, rot: ev.rot }, t);
      return { kind: "sign", obj, born: t };
    },
  },
  // a sound cue for the Python mixer (it reads the story); nothing to draw
  sfx_mark: { scope: "scene", validate: (ev) => need(ev, "sfx"), apply: noop },
  shake: {
    scope: "scene",
    validate: (ev) => { if (ev.amount != null && !(typeof ev.amount === "number" && ev.amount > 0)) throw new Error("amount must be a positive number"); },
    apply: (ctx, ev, dt) => {
      const [x, y] = shakeAt(ev.amount ?? 0.3, dt);
      ctx.shake[0] += x; ctx.shake[1] += y;
    },
  },
  ...ACTION_TYPES, // fire, launch, impact, fly_off, act
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

export const shotRoster = (story) => story.beats.map((shot) =>
  Object.fromEntries(Object.entries(SCOPES).map(([name, sc]) => [name, new Set(sc.listed(shot))])));

export function applyEvents(state, shotIndex, t) {
  const all = state.events || shotEvents(state.story, state.timeline);
  const roster = state.roster || shotRoster(state.story);
  const ctx = { t, shake: [0, 0], fx: [] };
  for (const { view } of Object.values(SCOPES)) {
    ctx[view] = new Map();
    (state[view] || new Map()).forEach((spec, id) => ctx[view].set(id, { ...spec }));
  }
  for (let k = 0; k <= shotIndex; k++) {
    for (const [n, { event, t: at }] of all[k].entries()) {
      if (at > t) break;
      const type = EVENT_TYPES[event.do], sc = SCOPES[type.scope];
      // a spent event from an earlier shot is skipped; in the current shot a missing `who` is an error (apply throws)
      if (sc && k < shotIndex) {
        if (!ctx[sc.view].has(event.who)) continue;
        let relisted = false;
        for (let j = k + 1; j <= shotIndex && !relisted; j++) relisted = roster[j][type.scope].has(event.who);
        if (relisted) continue;
      }
      ctx.shot = k; ctx.key = `${k}.${n}`; // fx made by this event are keyed by it
      ctx.past = k < shotIndex; // an earlier shot's action skips things that have left the stage since
      try { type.apply(ctx, event, t - at); } catch (e) { throw new Error(`beat ${k}: ${event.do}: ${e.message}`); }
    }
  }
  delete ctx.shot; delete ctx.key; delete ctx.past;
  return ctx;
}

// The base specs on stage in shot k, from the story alone (the engine's keep / remove rules): {chars, props}.
// A prop spec carries its id and spawnT (the start of the shot that listed it); a kept character without `pos`
// keeps its last one.
export function stageAt(story, timeline, k) {
  const chars = new Map(), props = new Map();
  for (let j = 0; j <= k; j++) {
    const b = story.beats[j], start = timeline.beats[j].start;
    if (!b.keep) { chars.clear(); props.clear(); }
    (b.remove || []).forEach((id) => { chars.delete(id); props.delete(id); });
    (b.props || []).forEach((p, n) => { const id = p.id || `${p.type}${n}`; props.set(id, { ...p, id, spawnT: start }); });
    (b.chars || []).forEach((c) => {
      const prev = chars.get(c.id);
      chars.set(c.id, { ...c, pos: c.pos || (prev && prev.pos) || [0, 0, 0] });
    });
  }
  return { chars, props };
}

// Where prop `id` is at t in shot k, events included (launched, held, flying): the camera's follow target.
// state = {story, timeline, events?, roster?, stages?: [stageAt per shot]}
export function followPosAt(state, k, id, t) {
  const stage = (state.stages && state.stages[k]) || stageAt(state.story, state.timeline, k);
  const spec = applyEvents({ ...state, ...stage }, k, t).props.get(id);
  if (!spec) throw new Error(`camera follow: no prop ${id} in beat ${k}`);
  return propPosAt(spec, spec.spawnT, t);
}

// Each event's own fields for the catalog (every event also has at_word, do and an optional delay):
// need = required, opt = optional. The action events' fields come from actions.js.
const FIELDS = {
  expr: { need: ["who", "expr"] }, pose: { need: ["who", "pose"] }, motion: { need: ["who", "motion"] },
  fx: { need: ["type"], opt: ["at", "scale"] }, sign: { need: ["text"], opt: ["style", "pos", "rot"] },
  sfx_mark: { need: ["sfx"] }, shake: { opt: ["amount"] },
  ...ACTION_FIELDS,
};

// Names this registry adds to studio/catalog.json.
export function catalog() {
  return { events: Object.keys(EVENT_TYPES), event_fields: FIELDS };
}
