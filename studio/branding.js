// Channel art for Gus Explains, rendered by the engine (studio/engine/branding.html) in headless Chromium.
// Usage: node studio/branding.js [--out branding] [--only avatar,banner,...] [--safe DIR]
//   branding/youtube_avatar.png   800x800   Gus's face + shoulders (YouTube shows it as a circle, down to 98 px)
//   branding/youtube_banner.png   2560x1440 key art inside the centred 1546x423 safe area
//   branding/facebook_profile.png 720x720
//   branding/facebook_cover.png   1640x624  key art inside the centred 1200x462 mobile-safe area
// --safe DIR also writes <name>_safe.png copies with the safe area / crop circle drawn on (for checking, not committed).
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const { serve } = require("./render.js");

const REPO = path.resolve(__dirname, "..");
const ART = [
  { kind: "avatar", file: "youtube_avatar.png", safe: { circle: 400 } },
  { kind: "banner", file: "youtube_banner.png", safe: { rect: [1546, 423] } },
  { kind: "fb_profile", file: "facebook_profile.png", safe: { circle: 360 } },
  { kind: "cover", file: "facebook_cover.png", safe: { rect: [1200, 462] } },
];

function arg(name) {
  const i = process.argv.indexOf("--" + name);
  return i > 0 ? process.argv[i + 1] : null;
}

async function main() {
  const out = path.resolve(REPO, arg("out") || "branding");
  const only = arg("only") ? arg("only").split(",") : null;
  const safeDir = arg("safe") ? path.resolve(arg("safe")) : null;
  fs.mkdirSync(out, { recursive: true });
  if (safeDir) fs.mkdirSync(safeDir, { recursive: true });
  const srv = await serve();
  const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  try {
    const page = await browser.newPage({ viewport: { width: 2560, height: 1440 }, deviceScaleFactor: 1 });
    page.on("console", (m) => {
      if ((m.type() === "error" || m.type() === "warning") && !m.text().includes("GL Driver Message")) console.error("[page]", m.text());
    });
    page.on("pageerror", (e) => console.error("[pageerror]", e.message));
    await page.goto(`http://127.0.0.1:${srv.address().port}/engine/branding.html`);
    await page.waitForFunction(() => window.BRAND_READY === true, null, { timeout: 30000 });
    for (const a of ART) {
      if (only && !only.includes(a.kind)) continue;
      const { w, h } = await page.evaluate((k) => window.brand(k), a.kind);
      const clip = { x: 0, y: 0, width: w, height: h };
      const file = path.join(out, a.file);
      await page.screenshot({ clip, path: file, type: "png", timeout: 180000 });
      console.log(`branding: ${path.relative(REPO, file)} ${w}x${h}`);
      if (safeDir) {
        await page.evaluate(([s, W, H]) => {
          const ctx = document.getElementById("o").getContext("2d");
          ctx.save(); ctx.lineWidth = 4; ctx.strokeStyle = "#FF2D55"; ctx.setLineDash([18, 10]);
          if (s.rect) ctx.strokeRect((W - s.rect[0]) / 2, (H - s.rect[1]) / 2, s.rect[0], s.rect[1]);
          else { ctx.beginPath(); ctx.arc(W / 2, H / 2, s.circle, 0, Math.PI * 2); ctx.stroke(); }
          ctx.restore();
        }, [a.safe, w, h]);
        await page.screenshot({ clip, path: path.join(safeDir, a.file.replace(".png", "_safe.png")), type: "png" });
      }
    }
  } finally {
    await browser.close();
    srv.close();
  }
}

main().catch((e) => { console.error(`branding failed: ${(e && e.message) || e}`); process.exit(1); });
