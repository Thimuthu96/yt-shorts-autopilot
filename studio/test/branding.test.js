const test = require("node:test");
const assert = require("node:assert");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const pngSize = (f) => { const b = fs.readFileSync(f); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; };

test("branding renders the avatar at 800x800 and the cover at 1640x624", () => {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), "gus-brand-"));
  const r = spawnSync("node", [path.join(__dirname, "..", "branding.js"), "--out", out, "--only", "avatar,cover"], { encoding: "utf8", timeout: 120000 });
  assert.strictEqual(r.status, 0, r.stderr + r.stdout);
  assert.deepStrictEqual(pngSize(path.join(out, "youtube_avatar.png")), { w: 800, h: 800 });
  assert.deepStrictEqual(pngSize(path.join(out, "facebook_cover.png")), { w: 1640, h: 624 });
  assert.ok(!fs.existsSync(path.join(out, "youtube_banner.png")));
});
