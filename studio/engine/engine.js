// Gus Explains engine: window.setup(story, timeline), then window.renderAt(t) per frame.
// Registries live in their own modules (world.js: sets, props, moods); characters, FX, camera, captions later.
import * as THREE from "three";
import { clamp01 } from "./core.js";
import { buildSet, spawnProp } from "./world.js";

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

// ---------- beats ----------
// The set (with its mood's sky, lights and fog) is rebuilt when a beat's `set` changes; props are
// cleared each beat unless `keep`, when only the ids in `remove` go.
let STORY = null, TL = null, beatIdx = -1, setGroup = null, setKey = null;
const props = new Map();

function dispose(obj) {
  obj.traverse((k) => k.geometry && k.geometry.dispose());
}
function drop(id) {
  const o = props.get(id);
  if (o) { scene.remove(o); dispose(o); props.delete(id); }
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
}

window.setup = async (story, timeline) => {
  STORY = story; TL = timeline; beatIdx = -1;
  await document.fonts.load("700 80px Fredoka");
  await document.fonts.ready;
  return true;
};

window.renderAt = (t) => {
  let i = TL.beats.findIndex((b, k) => t < (k + 1 < TL.beats.length ? TL.beats[k + 1].start : Infinity));
  if (i < 0) i = TL.beats.length - 1;
  if (i !== beatIdx) { beatIdx = i; applyBeat(i); }
  const b = STORY.beats[i];
  props.forEach((o) => o.userData.tick(t));
  const cam = b.cam || {};
  const f = clamp01((t - TL.beats[i].start) / Math.max(0.5, TL.beats[i].end - TL.beats[i].start));
  const target = new THREE.Vector3(...(cam.target || [0, 2, 0]));
  const dist = (cam.dist || 9) * (cam.move === "push" ? 1 - 0.08 * f : 1);
  const ang = ((cam.angle || 0) * Math.PI) / 180;
  camera.position.set(target.x + Math.sin(ang) * dist, target.y + (cam.height ?? 1.2), target.z + Math.cos(ang) * dist);
  camera.lookAt(target);
  renderer.render(scene, camera);
  return true;
};

window.ENGINE_READY = true;
