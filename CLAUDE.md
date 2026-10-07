# CLAUDE.md — CryptoFX Daily (YouTube Shorts autopilot)

Context for Claude Code. Read this before changing anything.

## What this is

A fully automated faceless YouTube Shorts channel, **CryptoFX Daily**
(@CryptoFXDaily202), posting short crypto & forex market briefs with no manual work.
Runs free on **GitHub Actions** (repo `Thimuthu96/yt-shorts-autopilot`, branch `main`).

Owner goals: hands-off, near-zero cost, eventually monetized (YouTube Partner Program).
Owner is a developer (Flutter/Dart background), timezone Asia/Colombo (UTC+5:30).

## The pipeline (one run = one edition)

```
sources.gather()      prices + news + economic calendar         (free, no keys)
  → thumbnail.choose()  pick 1 of 4 thumbnail templates from the data
  → script.make_script()  Gemini writes the script (grounded in data) + fact-check pass
  → thumbnail.render()  thumbnail.jpg (1080x1920), also used as scene 1 of the video
  → voice.synthesize()  edge-tts narration per scene + word timings
  → slides.render_slides()  one PNG graphic per scene (charts, board, news card, calendar…)
  → render.build_video()  ffmpeg: segments + animations + word-highlight captions + audio mix
  → youtube.upload()    YouTube Data API v3 upload with SEO metadata (+ try set thumbnail)
  → history.json        logs the upload (dedupe + "don't repeat headlines")
```

Entry point: `main.py`. Orchestration is in `make_brief()`; `main()` handles edition
choice, weekend rule and the once-per-edition-per-day guard.

## Editions (up to 3 a day)

| key | label | cron (UTC) | Sri Lanka |
|---|---|---|---|
| `asia` | Asia Open | `30 0 * * *` | 06:00 |
| `london` | London Open | `40 5 * * *` | 11:10 |
| `newyork` | New York Open | `30 12 * * *` | 18:00 |

- Defined in `config.yaml → sessions` (label, short, focus text). `main.py` has
  `DEFAULT_SESSIONS` as a fallback if config lacks them.
- The workflow maps the firing cron string → session in the `SESSION:` env line.
  **If you change a cron time, change the matching string in `SESSION:` too.**
- Weekends: scheduled runs only make editions in `weekend_sessions` (default `[london]`).
- Each edition runs once per UTC day unless `--force`. Old history entries without a
  `session` field count as `london`.
- Each edition keeps only news published since the previous upload (if ≥6 fresh stories).

Manual runs: Actions → Shorts autopilot → Run workflow → `session` (auto/asia/london/newyork)
+ `force` checkbox. `auto` = by current UTC hour (<5 asia, <12 london, else newyork).

## Files

```
main.py                  orchestration, CLI: --session, --force, --no-upload, --scheduled
config.yaml              all settings (channel, llm, market, sessions, voice, video, upload)
get_token.py             one-time OAuth login on the owner's PC → prints YT_* secrets
autopilot/sources.py     news RSS, ForexFactory calendar, Coinbase crypto, Frankfurter FX
autopilot/script.py      Gemini prompt, fact-check, validate, fix_visuals (scene types)
autopilot/llm.py         Gemini REST client with model fallback + verbose logging
autopilot/thumbnail.py   4 thumbnail templates (Pillow) + choose() + clean_hook()
autopilot/slides.py      per-scene graphics (Pillow + matplotlib)
autopilot/render.py      ffmpeg segments, chart draw-in, push-in, ASS captions, mix
autopilot/voice.py       edge-tts per scene, WordBoundary timings
autopilot/youtube.py     metadata (SEO, sources, disclaimer), upload, set_thumbnail
autopilot/history.py     data/history.json helpers (per-session dedupe, last upload time)
autopilot/media.py       ffmpeg/ffprobe helpers
assets/fonts/            Anton + Space Grotesk (SIL OFL) for thumbnails
tests/test_offline.py    full offline render test with sample data + mocked LLM
data/history.json        upload log, committed back by the workflow (don't hand-edit casually)
.github/workflows/autopilot.yml   3 crons + workflow_dispatch inputs
```

## Data sources (all free, no API keys)

- **News:** RSS feeds in `sources.DEFAULT_FEEDS` — CoinDesk, Cointelegraph, Federal Reserve,
  and Google News search feeds (forex, dollar, central banks, crypto, macro). This is the
  same feed set the World Monitor finance dashboard (github.com/koala73/worldmonitor) uses;
  its own API needs a paid Pro key, so we read the feeds directly.
- **Economic calendar:** ForexFactory's official export
  `https://nfs.faireconomy.media/ff_calendar_thisweek.json` (fields: title, country, date,
  impact, forecast, previous — **no actual results**). Fetch once per run; never scrape
  forexfactory.com (ToS).
- **Crypto:** Coinbase Exchange public candles `api.exchange.coinbase.com/products/{BTC-USD}/candles`,
  hourly, 7 days (BTC, ETH, SOL, XRP). Returns newest-first; we sort. CoinGecko free plan was
  avoided (non-commercial terms).
- **Forex:** Frankfurter v2 `api.frankfurter.dev/v2/rates?base=USD&quotes=...` — daily
  central-bank reference rates (not live). EUR/USD etc. = 1/(USD→EUR). Script must say
  "yesterday's close / latest daily fix", never "right now".
- If **no** price data loads, the run stops (no guessing). Failed individual sources are skipped.

## LLM (Gemini, free tier)

- Key: `GEMINI_API_KEY` (Google AI Studio). Model `gemini-3.8-flash`, fallbacks in
  `config.yaml → llm.fallback_models`.
- `llm.generate_json()`: 404 → skip model for the run; 500/503 → one retry then next model;
  429 → wait/retry (daily-quota 429 → next model); 2-min read timeout; logs every call as
  `gemini: …`. If all fail, waits 60s and tries the list once more.
- History: `gemini-2.5-flash` returned 404 for this (new) key — 2.5 models are access-limited.
  Pro models are not on the free tier. Don't enable billing on the AI Studio project
  (it ends the free tier).
- `script.write()` prompt rules: only numbers from the data; "why" only if a headline says so;
  no predictions/targets/buy-sell; not-financial-advice line; scene 1 must state the thumbnail
  fact; returns `thumbnail_hook`. `fact_check()` re-checks against data. `fix_visuals()`
  forces scene 1 = `title` (the thumbnail) and degrades bad visuals to `board`.
- Scene visual types: `title, price{asset}, fx{asset}, board, news{source,headline}, calendar, outro`.

## Thumbnails

Shorts custom thumbnails can't be set via API for this channel (YouTube only allows custom
Shorts thumbnails for YPP members, in Studio desktop). So **scene 1 of every video is the
thumbnail design** (first frame = exact design, no captions over it, slow push-in) and
`set_thumbnail()` is attempted and its refusal ignored. `thumbnail.jpg` is kept as an artifact.

Templates (`thumbnail.choose()` priority):
1. **move** — any coin |24h| ≥ 4% or FX pair |1d| ≥ 0.8% (score = move/threshold). Hero "−6.2%",
   real chart (48h crypto / 15d FX), hook default "WHAT HAPPENED?" / "WHAT'S DRIVING IT?"
2. **event** — High-impact event within 12h. Yellow bg, "{CPI|FED|NFP|ECB…} DAY", chip
   "USD · 12:30 GMT", hook "WATCH BEFORE 12:30".
3. **split** — BTC |24h| ≥ 1.5% and USD strength (avg vs tracked pairs) |≥ 0.3%| opposite signs.
4. **level** — BTC (step $5K) / ETH (step $500) within 0.15–2% below the next round number.
5. fallback → move on the biggest mover.

Layout: top/bottom 150 px kept clear (grid crop). Brand strip y≈170, hero, visual, tilted hook box.
`clean_hook()`: ≤4 words, ≤22 chars, allowed chars only, banned words (MOON, BUY, SELL, WILL,
GUARANTEED, 100X, …) → otherwise the template's default hook.
Design reference canvases (claude.ai, owner's account): "CryptoFX Daily Thumbnail Templates"
and "CryptoFX Daily Channel Art" (logo = coin ring + 3 candlesticks; banner 2560×1440).

## Video design

- 1080×1920, 30 fps, ≤59 s. Dark ground `#0E0F12`, accent `#FFD400`, up `#22C55E`, down `#EF4444`.
- Slides keep y 1230–1480 free for burned-in captions (ASS, 3 words/line, current word yellow).
- Chart scenes draw in left→right (background-coloured box slides off via ffmpeg overlay).
  Other scenes: slow push-in (`scale=...:eval=frame`).
- Footer on every slide: "Not financial advice · Data: Coinbase, ECB/Frankfurter, ForexFactory".
- Voice: edge-tts `en-US-AndrewMultilingualNeural`, `+10%`; re-recorded faster if > max_seconds.
- Optional background music: any `.mp3` in `music/` (royalty-free only).

## Upload / YouTube

- OAuth secrets: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` (from `get_token.py`,
  scope `youtube.upload`). Google Cloud project "Everyday Science", OAuth app "Tiny Whys
  Uploader" (old name, harmless), **In production** (Testing mode would expire tokens in 7 days).
  Branding page uses a GitHub Pages home page + privacy policy (`<user>.github.io`).
- Un-audited API projects upload as **private**; the YouTube API Services audit form removes it.
  Check status in Studio if uploads aren't public.
- Category 25 (News & Politics). Description = summary, "Stories mentioned" (source: headline),
  data credits, disclaimer, hashtags (+#Shorts). Tags ≤ ~480 chars, deduped.
- `containsSyntheticMedia: false` (AI voice + data graphics don't require the label).

## Secrets (GitHub → Settings → Secrets and variables → Actions)

`GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.
(`PIXABAY_API_KEY` / `PEXELS_API_KEY` are legacy and unused.) Never commit `client_secret.json`
(git-ignored).

## Running & testing

```bash
pip install -r requirements.txt            # + ffmpeg on PATH
python tests/test_offline.py               # no keys/network: renders output/test/short.mp4 + contact.png
export GEMINI_API_KEY=...                  # PowerShell: $env:GEMINI_API_KEY="..."
python main.py --no-upload --session london   # real data, no upload → output/<stamp>/
```
Each run writes `output/<stamp>/{data.json, package.json, metadata.json, thumbnail.jpg, short.mp4}`;
the workflow keeps them 7 days as run artifacts. Look at the `contact.png` / frames after visual changes.

## Decisions & rejected approaches (don't re-propose without a new reason)

- **Niche history:** started as "Tiny Whys" everyday-science Shorts with stock footage; switched
  to crypto/forex news because stock footage kept mismatching the script.
- **Stock footage (Pexels/Pixabay):** Pexels stopped issuing API keys; Pixabay's small library
  gave irrelevant clips even with relevance filtering. Replaced by data-generated graphics.
- **AI-generated images (Cloudflare Workers AI FLUX):** built, then removed at the owner's request.
- **AI video APIs (Veo, Kling…):** no free tier (~$0.05+/s).
- **Reusing YouTube/TikTok clips:** rejected — copyright strikes, reused-content demonetization, ToS.
- **Monetization policy:** YouTube "inauthentic content" targets mass-produced templated videos;
  keep editions genuinely different (fresh news per edition), max ~3/day, no hype.

## Gotchas we hit

- `.github/` and `.gitignore` are hidden folders/files — drag-and-drop uploads skip them; use git.
- A config.yaml that didn't get committed broke editions ("Choose one of:" empty) → hence
  `DEFAULT_SESSIONS`. After unzipping updates, check `git status` lists every changed file.
- The workflow commits `data/history.json` after each upload → **always `git pull` before pushing.**
- GitHub account billing lock once blocked all jobs ("account is locked due to a billing issue").
- Scheduled runs can start 5–30+ min late; schedules pause after 60 days of repo inactivity.
- A cron expression in YAML must stay on one line inside `${{ }}`.
- Node 20 deprecation warning for actions/checkout@v4, setup-python@v5, upload-artifact@v4 —
  harmless for now; bump to Node 24 versions when convenient (verify versions exist first).

## Ideas / next steps (not done)

- Bump GitHub Actions versions (Node 24).
- Submit / confirm the YouTube API audit so uploads are public automatically.
- Analytics feedback loop (YouTube Analytics API) to compare editions and thumbnail templates.
- Optional gold (XAU/USD) and DXY data source; Medium-impact calendar events for quiet days.
- Weekly recap long-form video from the week's history.
- Comment pinning / community posts (manual for now).

## Conventions for changes

- Keep everything free-tier; no new paid APIs without asking the owner.
- Every number shown or spoken must come from fetched data. No predictions or buy/sell language.
- Run `python tests/test_offline.py` after any change to rendering, slides, thumbnail or script flow.
- Prefer small, explicit log lines (`log(...)`) — the Actions log is the only monitoring.
- Owner applies changes via git (Mac or Windows); give exact file paths when handing over changes.
