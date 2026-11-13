// Pure helpers shared by the engine and its registries. No DOM access at import time.
import * as THREE from "three";

export const INK = "#17142b";
export const OUT = 0.035;

const gradTex = (() => {
  const d = new Uint8Array([120, 120, 120, 255, 200, 200, 200, 255, 255, 255, 255, 255]);
  const t = new THREE.DataTexture(d, 3, 1, THREE.RGBAFormat);
  t.minFilter = t.magFilter = THREE.NearestFilter;
  t.needsUpdate = true;
  return t;
})();

const matCache = new Map();
export function toonMat(color, opts = {}) {
  const key = color + JSON.stringify(opts);
  if (!opts.map && matCache.has(key)) return matCache.get(key);
  const m = new THREE.MeshToonMaterial({ color: new THREE.Color(color), gradientMap: gradTex, ...opts });
  if (!opts.map) matCache.set(key, m);
  return m;
}

const outlineMat = new THREE.MeshBasicMaterial({ color: INK, side: THREE.BackSide });

// Ink outline: a slightly larger back-face copy of the mesh. Returns a group holding both.
export function inked(mesh, width = OUT) {
  const geom = mesh.geometry;
  geom.computeBoundingBox();
  const size = geom.boundingBox.getSize(new THREE.Vector3());
  const c = geom.boundingBox.getCenter(new THREE.Vector3());
  const k = new THREE.Vector3(...["x", "y", "z"].map((a) => (size[a] > 1e-6 ? 1 + (2 * width) / size[a] : 1)));
  // the hull sits in the mesh's own frame, scaled about the box centre
  const hull = new THREE.Mesh(geom, outlineMat);
  hull.scale.copy(k);
  hull.position.set(c.x * (1 - k.x), c.y * (1 - k.y), c.z * (1 - k.z));
  const pivot = new THREE.Group();
  pivot.position.copy(mesh.position);
  pivot.quaternion.copy(mesh.quaternion);
  pivot.scale.copy(mesh.scale);
  pivot.add(hull);
  mesh.position.set(0, 0, 0); mesh.quaternion.identity(); mesh.scale.set(1, 1, 1);
  pivot.add(mesh);
  return pivot;
}

export function canvasTex(w, h, draw) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 1;
  return t;
}

export function hash(n) {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return s - Math.floor(s);
}

export const clamp01 = (v) => Math.max(0, Math.min(1, v));
export const easeIO = (v) => (v = clamp01(v), v < 0.5 ? 2 * v * v : 1 - Math.pow(-2 * v + 2, 2) / 2);
export const easeOut = (v) => 1 - Math.pow(1 - clamp01(v), 3);
