// Usage:
//   node studio/render.js <story.json> --timeline <timeline.json> --out <dir> [--stills t1,t2] [--scale 0.5]
// Writes <dir>/video.mp4 (silent), or <dir>/still_<t>.jpg per requested time.
// Exit code 1 and "render failed at frame N: <reason>" on stderr when a frame cannot be rendered.
const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const STUDIO = __dirname;
const REPO = path.resolve(STUDIO, "..");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".ttf": "font/ttf", ".woff2": "font/woff2", ".json": "application/json" };
const W = 1080, H = 1920;

function arg(name) {
  const i = process.argv.indexOf("--" + name);
  return i > 0 ? process.argv[i + 1] : null;
}

// Static server: /node_modules/* from the repo root, everything else from studio/.
function serve() {
  return new Promise((res) => {
    const srv = http.createServer((req, rsp) => {
      const url = decodeURIComponent(req.url.split("?")[0]);
      const base = url.startsWith("/node_modules/") ? REPO : STUDIO;
      const p = path.join(base, url);
      if (!p.startsWith(base) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { rsp.writeHead(404); return rsp.end(); }
      rsp.writeHead(200, { "Content-Type": TYPES[path.extname(p)] || "application/octet-stream" });
      fs.createReadStream(p).pipe(rsp);
    });
    srv.listen(0, "127.0.0.1", () => res(srv));
  });
}

async function main() {
  const storyPath = process.argv[2];
  const tlPath = arg("timeline"), out = arg("out");
  if (!storyPath || !tlPath || !out) throw new Error("usage: render.js <story.json> --timeline <timeline.json> --out <dir> [--stills t1,t2] [--scale 0.5]");
  const scale = parseFloat(arg("scale") || "1");
  const stills = arg("stills");
  const story = JSON.parse(fs.readFileSync(storyPath, "utf8"));
  const tl = JSON.parse(fs.readFileSync(tlPath, "utf8"));
  fs.mkdirSync(out, { recursive: true });

  const srv = await serve();
  const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  let frame = 0;
  try {
    const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: scale });
    page.on("console", (m) => {
      if ((m.type() === "error" || m.type() === "warning") && !m.text().includes("GL Driver Message")) console.error("[page]", m.text());
    });
    page.on("pageerror", (e) => console.error("[pageerror]", e.message));
    await page.goto(`http://127.0.0.1:${srv.address().port}/engine/index.html?aa=1&scale=${scale}`);
    await page.waitForFunction(() => window.ENGINE_READY === true, null, { timeout: 30000 });
    await page.evaluate(([s, t]) => window.setup(s, t), [story, tl]);
    const CLIP = { x: 0, y: 0, width: W, height: H };
    const at = (t) => page.evaluate((x) => window.renderAt(x), t);

    if (stills) {
      // renderAt is stateful (beat changes), so walk forward through time at a coarse step
      let cur = 0;
      for (const T of stills.split(",").map(Number).sort((a, b) => a - b)) {
        for (; cur < T; cur += 5 / tl.fps) { frame = Math.round(cur * tl.fps); await at(cur); }
        frame = Math.round(T * tl.fps); await at(T); cur = T;
        await page.screenshot({ clip: CLIP, path: path.join(out, `still_${T.toFixed(1)}.jpg`), type: "jpeg", quality: 90, timeout: 180000 });
        console.log("still", T);
      }
      return;
    }

    const fps = tl.fps, n = Math.ceil(tl.duration * fps);
    const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-",
      "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-g", "60", "-pix_fmt", "yuv420p", path.join(out, "video.mp4")], { stdio: ["pipe", "inherit", "inherit"] });
    const closed = new Promise((r) => ff.on("close", r));
    ff.stdin.on("error", () => {});
    const t0 = Date.now();
    try {
      for (frame = 0; frame < n; frame++) {
        await at(frame / fps);
        const buf = await page.screenshot({ clip: CLIP, type: "jpeg", quality: 92, timeout: 180000 });
        if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
        if (frame % 150 === 0) console.log(`${story.slug}: frame ${frame}/${n}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
      }
    } catch (e) { ff.kill(); throw e; }
    ff.stdin.end();
    if ((await closed) !== 0) throw new Error("ffmpeg failed");
    console.log(`${story.slug}: rendered ${n} frames in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  } catch (e) {
    console.error(`render failed at frame ${frame}: ${(e && e.message) || e}`);
    process.exitCode = 1;
  } finally {
    await browser.close();
    srv.close();
  }
}

main().catch((e) => { console.error(`render failed at frame 0: ${e.message}`); process.exit(1); });
