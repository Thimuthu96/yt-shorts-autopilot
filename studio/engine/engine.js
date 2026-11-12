// Gus Explains engine: window.setup(story, timeline), then window.renderAt(t) per frame.
// Registries (SETS now; characters, FX, camera, captions later) are plain objects keyed by type.
import * as THREE from "three";
import { toonMat, inked, clamp01 } from "./core.js";

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
const camera = new THREE.PerspectiveCamera(42, W / H, 0.1, 400);
scene.add(new THREE.HemisphereLight(0xffffff, 0xb9a98a, 1.5));
const sun = new THREE.DirectionalLight(0xfff3dc, 2.1);
sun.position.set(-8, 16, 10);
scene.add(sun);

// ---------- registries ----------
// A set builds its backdrop into `group` for a beat's `set` ({type, mood}).
function skyTex(top, bottom) {
  const c = document.createElement("canvas");
  c.width = 4; c.height = 256;
  const x = c.getContext("2d");
  const g = x.createLinearGradient(0, 0, 0, 256);
  g.addColorStop(0, top); g.addColorStop(1, bottom);
  x.fillStyle = g; x.fillRect(0, 0, 4, 256);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
const SETS = {
  test(group, set) {
    const night = set.mood === "night";
    scene.background = skyTex(night ? "#101a3a" : "#4aa8f0", night ? "#3a4a8a" : "#bfe6ff");
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(60, 60), toonMat("#6ccf73"));
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    group.add(ground);
    const block = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.2, 1.2), toonMat("#ffd84a"));
    block.position.y = 0.6;
    group.add(inked(block));
  },
};

// ---------- beats ----------
let STORY = null, TL = null, beatIdx = -1, setGroup = null;

function applyBeat(i) {
  const set = STORY.beats[i].set || {};
  const build = SETS[set.type];
  if (!build) throw new Error(`unknown set: ${set.type}`);
  if (setGroup) scene.remove(setGroup);
  setGroup = new THREE.Group();
  scene.add(setGroup);
  build(setGroup, set);
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
  const cam = b.cam || {};
  const f = clamp01((t - TL.beats[i].start) / Math.max(0.5, TL.beats[i].end - TL.beats[i].start));
  const target = new THREE.Vector3(...(cam.target || [0, 2, 0]));
  const dist = (cam.dist || 9) * (cam.move === "push" ? 1 - 0.08 * f : 1);
  camera.position.set(target.x, target.y + (cam.height || 1.2), target.z + dist);
  camera.lookAt(target);
  renderer.render(scene, camera);
  return true;
};

window.ENGINE_READY = true;
