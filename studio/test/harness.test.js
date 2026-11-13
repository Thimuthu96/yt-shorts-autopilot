const test = require("node:test");
const assert = require("node:assert");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const RENDER = path.join(__dirname, "..", "render.js");
const FIX = path.join(__dirname, "..", "fixtures");

function jpegSize(file) {
  const b = fs.readFileSync(file);
  let i = 2;
  while (i < b.length) {
    if (b[i] !== 0xff) { i++; continue; }
    const m = b[i + 1];
    if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) return { h: b.readUInt16BE(i + 5), w: b.readUInt16BE(i + 7) };
    i += 2 + b.readUInt16BE(i + 2);
  }
  throw new Error("no SOF marker");
}
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "gus-harness-"));
const run = (story, out, extra = []) =>
  spawnSync("node", [RENDER, story, "--timeline", path.join(FIX, "one-beat.timeline.json"), "--out", out, ...extra], { encoding: "utf8", timeout: 120000 });

test("renders a still at 1080x1920", () => {
  const out = tmp();
  const r = run(path.join(FIX, "one-beat.json"), out, ["--stills", "0.5"]);
  assert.strictEqual(r.status, 0, r.stderr + r.stdout);
  const f = path.join(out, "still_0.5.jpg");
  assert.ok(fs.existsSync(f));
  assert.deepStrictEqual(jpegSize(f), { w: 1080, h: 1920 });
});

test("an unknown set type fails with exit 1 and a frame number", () => {
  const out = tmp();
  const story = JSON.parse(fs.readFileSync(path.join(FIX, "one-beat.json"), "utf8"));
  story.beats[0].set.type = "nope";
  const bad = path.join(out, "bad.json");
  fs.writeFileSync(bad, JSON.stringify(story));
  const r = run(bad, out, ["--stills", "0.5"]);
  assert.strictEqual(r.status, 1);
  assert.match(r.stderr, /render failed at frame \d+/);
  assert.match(r.stderr, /unknown set: nope/);
});

test("renders a silent mp4 at a reduced scale", () => {
  const out = tmp();
  const r = run(path.join(FIX, "one-beat.json"), out, ["--scale", "0.25"]);
  assert.strictEqual(r.status, 0, r.stderr + r.stdout);
  const v = path.join(out, "video.mp4");
  assert.ok(fs.statSync(v).size > 1000);
  const p = spawnSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_frames", "-of", "csv=p=0", v], { encoding: "utf8" });
  assert.strictEqual(p.stdout.trim().replace(/,$/, ""), "270,480,30");
});
