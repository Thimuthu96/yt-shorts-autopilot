// Gus Explains engine: window.setup(story, timeline), then window.renderAt(t) per frame.
// Registries live in their own modules (world.js: sets, props, moods; cast.js: characters; camera.js: camera moves,
// iris; fx.js: effects; signs.js: in-world signs; captions.js: the one-word caption; events.js: word-anchored shot events).
import * as THREE from "three";
import { clamp01 } from "./core.js";
import { buildSet, spawnProp, propPosAt } from "./world.js";
import { Char } from "./cast.js";
import { camPose, handoff, irisMask } from "./camera.js";
import { makeFx, updateFx } from "./fx.js";
import { spawnSign } from "./signs.js";
import { captionWord, drawCaption } from "./captions.js";
import { EVENT_TYPES, shotEvents, applyEvents } from "./events.js";

const W = 1080, H = 1920;
const Q = Object.fromEntries(new URLSearchParams(location.search));
const RS = parseFloat(Q.scale || "1");

const canvas = document.getElementById("c");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: Q.aa !== "0", preserveDrawingBuffer: true, alpha: true });
renderer.setPixelRatio(1);
renderer.setSize(Math.round(W * RS), Math.round(H * RS), false);
canvas.style.width = W + "px";
canvas.style.height = H + "px";
renderer.shadowMap.enabled = true;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(42, W / H, 0.1, 1000);

// iris: #stage is clipped to a circle (black outside) with a white ring on its edge
const stage = document.getElementById("stage"), ring = document.getElementById("iris");
const IRIS = 0.45, HALF_DIAG = Math.hypot(W, H) / 2;

// captions: a 2D canvas over the 3D view, inside #stage so the iris clips it too
const capCanvas = document.getElementById("cap");
capCanvas.width = Math.round(W * RS); capCanvas.height = Math.round(H * RS);
const capCtx = capCanvas.getContext("2d");
capCtx.scale(RS, RS);
let capWord = null;

// ---------- beats ----------
// The set (with its mood's sky, lights and fog) is rebuilt when a beat's `set` changes; props are
// cleared each beat unless `keep`, when only the ids in `remove` go. Characters follow the same rule; a kept
// character given a new `pos` walks there, one without `pos` stays put. FX and signs have no ids: they are cleared
// each beat unless `keep`; an effect's local time runs from its beat's start + delay, so it is stateless per t.
// A beat's `events` (story v2) are timed to its words: fx / sign events are spawned with the beat, hidden until their
// event time; character and shake events are applied per frame from the base specs (events.js), never stored.
let STORY = null, TL = null, EVENTS = null, beatIdx = -1, setGroup = null, setKey = null;
const props = new Map();
const chars = new Map(); // id -> {c: Char, spec}
let fxs = [], signs = []; // fxs: {g, born}; signs: roots with userData.tick

function dispose(obj) {
  obj.traverse((k) => k.geometry && k.geometry.dispose());
}
function drop(id) {
  const o = props.get(id);
  if (o) { scene.remove(o); dispose(o); props.delete(id); }
}

// FX sprites share one geometry and cached textures: only their own materials go. A sign owns its geometry and its
// painted face (material + texture); its side material is a shared cached one.
function dropFx({ g }) {
  scene.remove(g);
  g.traverse((k) => k.isSprite && k.material.dispose());
}
function dropSign(o) {
  scene.remove(o);
  dispose(o);
  o.traverse((k) => k.isMesh && [].concat(k.material).forEach((m) => { if (m.map) { m.map.dispose(); m.dispose(); } }));
}

function applyFxAndSigns(b, start, events) {
  if (!b.keep) {
    fxs.forEach(dropFx);
    signs.forEach(dropSign);
    fxs = []; signs = [];
  }
  (b.fx || []).forEach((spec) => {
    const g = makeFx(spec.type, spec.at || [0, 0, 0], null, spec.scale || 1);
    scene.add(g);
    fxs.push({ g, born: start + (spec.delay || 0) });
  });
  (b.signs || []).forEach((spec) => {
    const o = spawnSign(spec, start);
    scene.add(o);
    signs.push(o);
  });
  events.forEach(({ event, t }) => {
    const made = EVENT_TYPES[event.do].spawn && EVENT_TYPES[event.do].spawn(event, t);
    if (!made) return;
    scene.add(made.obj);
    if (made.kind === "fx") fxs.push({ g: made.obj, born: made.born });
    else signs.push(made.obj);
  });
}

function dropChar(id) {
  const ch = chars.get(id);
  if (ch) { scene.remove(ch.c.group); ch.c.dispose(); chars.delete(id); }
}

function applyChars(b, start) {
  if (!b.keep) [...chars.keys()].forEach(dropChar);
  (b.remove || []).forEach(dropChar);
  (b.chars || []).forEach((spec) => {
    const prev = chars.get(spec.id);
    if (prev) { prev.spec = prev.c.keep(spec, start); return; }
    const entry = STORY.cast && STORY.cast[spec.id];
    if (!entry) throw new Error(`char ${spec.id} not in cast`);
    const c = new Char(spec.id, entry.look);
    c.born = start;
    scene.add(c.group);
    chars.set(spec.id, { c, spec: c.keep(spec, start) });
  });
  const mood = setGroup ? setGroup.userData.mood : "day";
  chars.forEach(({ c }) => c.setTint(mood));
}

function applyBeat(i) {
  const b = STORY.beats[i], start = TL.beats[i].start;
  const set = b.set || {};
  const key = JSON.stringify(set);
  if (key !== setKey) {
    const g = buildSet(set);
    if (setGroup) { scene.remove(setGroup); dispose(setGroup); }
    setGroup = g; setKey = key;
    scene.add(g);
    scene.fog = g.userData.fog;
  }
  if (!b.keep) [...props.keys()].forEach(drop);
  (b.remove || []).forEach(drop);
  (b.props || []).forEach((spec, k) => {
    const id = spec.id || `${spec.type}${k}`;
    drop(id);
    const o = spawnProp({ ...spec, id }, start);
    scene.add(o);
    props.set(id, o);
  });
  applyChars(b, start);
  applyFxAndSigns(b, start, EVENTS[i]);
}

// ---------- camera ----------
// Each beat continues from where the last one ended unless it cuts (cam.cut, transition "cut" or "iris", first beat).
const cutsInto = (k) => k === 0 || !!(STORY.beats[k].cam || {}).cut || ["cut", "iris"].includes(STORY.beats[k].transition);

// the followed prop's position at t: spawned in beat k or in the kept beats before it
function followPos(k, t) {
  const cam = STORY.beats[k].cam || {};
  if (cam.move !== "follow" || !cam.follow) return null;
  for (let j = k; j >= 0; j--) {
    const b = STORY.beats[j];
    const spec = (b.props || []).map((s, n) => ({ ...s, id: s.id || `${s.type}${n}` })).find((s) => s.id === cam.follow);
    if (spec) return propPosAt(spec, TL.beats[j].start, t);
    if (!b.keep || (b.remove || []).includes(cam.follow)) break;
  }
  throw new Error(`camera follow: no prop ${cam.follow} in beat ${k}`);
}

const dur = (k) => Math.max(1e-3, TL.beats[k].end - TL.beats[k].start);
const progress = (k, t) => clamp01((t - TL.beats[k].start) / dur(k));

function poseAt(k, t) {
  const cam = { ...(STORY.beats[k].cam || {}), cut: cutsInto(k) };
  // a beat's last pose (and speed) does not depend on the one before it, so the previous beat's end is one call
  const prev = cam.cut ? null : handoff(STORY.beats[k - 1].cam || {}, dur(k - 1), dur(k),
    (p) => ({ follow: followPos(k - 1, TL.beats[k - 1].start + p * dur(k - 1)) }));
  return camPose(cam, prev, progress(k, t), { follow: followPos(k, t) });
}

function irisAt(t) {
  for (let k = 1; k < STORY.beats.length; k++) {
    const edge = TL.beats[k].start;
    if (STORY.beats[k].transition === "iris" && Math.abs(t - edge) < IRIS / 2) return irisMask(t - edge + IRIS / 2, IRIS);
  }
  return 1;
}

function applyIris(r) {
  const open = r >= 1;
  const px = r * HALF_DIAG;
  stage.style.clipPath = open ? "none" : `circle(${px.toFixed(1)}px at 50% 50%)`;
  ring.style.display = open || px < 2 ? "none" : "block";
  ring.style.width = ring.style.height = `${(2 * px).toFixed(1)}px`;
}

window.setup = async (story, timeline) => {
  STORY = story; TL = timeline; beatIdx = -1; capWord = null;
  EVENTS = shotEvents(story, timeline); // checks every event up front (bad at_word -> "beat N: ...")
  await document.fonts.load("700 80px Fredoka");
  await document.fonts.ready;
  return true;
};

window.renderAt = (t) => {
  let i = TL.beats.findIndex((b, k) => t < (k + 1 < TL.beats.length ? TL.beats[k + 1].start : Infinity));
  if (i < 0) i = TL.beats.length - 1;
  if (i !== beatIdx) { beatIdx = i; applyBeat(i); }
  props.forEach((o) => o.userData.tick(t));
  fxs.forEach(({ g, born }) => updateFx(g, t - born));
  signs.forEach((o) => o.userData.tick(t));
  const base = new Map([...chars].map(([id, { spec }]) => [id, spec]));
  const now = applyEvents({ story: STORY, timeline: TL, chars: base, events: EVENTS }, i, t);
  const pose = poseAt(i, t);
  camera.position.set(...pose.pos);
  if (camera.fov !== pose.fov) { camera.fov = pose.fov; camera.updateProjectionMatrix(); }
  camera.lookAt(...pose.look);
  // shake: [right, up] in the camera's own axes, added on top of the move (position and aim together)
  const [sx, sy] = now.shake;
  if (sx || sy) {
    const off = new THREE.Vector3(sx, sy, 0).applyQuaternion(camera.quaternion);
    camera.position.add(off);
    camera.lookAt(new THREE.Vector3(...pose.look).add(off));
  }
  applyIris(irisAt(t));
  const word = captionWord(TL, t);
  if (word !== capWord) { capWord = word; drawCaption(capCtx, word, W, H); }
  const mouth = (TL.mouth || [])[Math.round(t * (TL.fps || 30))] || 0;
  chars.forEach(({ c }, id) => { c.frame(now.chars.get(id), t, mouth); c.faceCamera(camera); });
  renderer.render(scene, camera);
  return true;
};

window.ENGINE_READY = true;
