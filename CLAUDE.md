# CLAUDE.md — CryptoFX Daily (YouTube Shorts autopilot)

Context for Claude Code. Read this before changing anything.

## What this is

A fully automated faceless YouTube Shorts channel, **CryptoFX Daily**
(@CryptoFXDaily202), posting short crypto & forex market briefs (one lead story each) and a
daily gold (XAU/USD) outlook, with no manual work. The same videos also go to the
**CryptoFX Daily Facebook Page as Reels**, plus **3 Facebook-only news image posts a day**.
Runs free on **GitHub Actions** (repo `Thimuthu96/yt-shorts-autopilot`, branch `main`).

Owner goals: hands-off, near-zero cost, eventually monetized (YouTube Partner Program).
Owner is a developer (Flutter/Dart background), timezone Asia/Colombo (UTC+5:30).

## The pipeline (one run = one edition)

```
sources.gather(kind)  prices + gold + news + calendar + macro    (free, no keys)
  market brief:
  → focus.pick()        lead story + the 1-3 assets it moves (scores: headlines, move, events)
  → thumbnail.choose()  pick 1 of 4 templates, staying on the focus assets
  → script.make_script()  research() analyst note → write() one-story script → fact_check()
  gold outlook:
  → gold.analyze()      rule-based levels, liquidity, 1H/4H/daily bias, scenarios, last call review
  → thumbnail.choose_gold()  "BEARISH / BELOW $4,142" card
  → script.make_gold_script()  fixed scene plan, Gemini only narrates it + fact_check()
  both:
  → thumbnail.render()  thumbnail.jpg (1080x1920), also used as scene 1 of the video
  → voice.synthesize()  edge-tts narration per scene + word timings
  → slides.render_slides()  one PNG graphic per scene (charts, board, news card, calendar…)
  → render.build_video()  ffmpeg: segments + animations + word-highlight captions + audio mix
  → publish(pending)    per platform, one failure never blocks the other:
       youtube.upload()   YouTube Data API v3 upload with SEO metadata (+ try set thumbnail)
       facebook.publish_reel()  Graph API Reel (start → rupload → finish once → poll) + reel_caption()
  → history.json        logs the ids (dedupe + "don't repeat headlines")
  news image post (kind: post, Facebook only):
  → news_post.pick_story()  48 h of news (all feeds incl. geopolitics + regulation), topic weight +
                            coverage + recency, skips stories earlier FB posts used, never empty
  → news_post.write_post()  Gemini: kicker, 2-3 line headline, subline, caption, image prompt →
                            script.fact_check() → number check vs facts → deterministic fallback
  → images.background()     Cloudflare FLUX.1 schnell → assets/backgrounds/<topic>/ → drawn
  → images.render_card()    post.jpg 1080x1350; news_post.caption() → caption_fb.txt
  → facebook.publish_photo()  POST /{page}/photos
```

Entry point: `main.py`. Producing is in `make_brief()` / `make_post()`, publishing in
`publish()`; `main()` handles edition choice, `--platforms`, timed vs manual rules, the weekend
rule and the once-per-edition-per-day-per-platform guard:
`pending = session platforms ∩ enabled − platforms published today for this session`.

## Editions (3 market briefs + 1 gold outlook + 3 FB news posts a day; weekends: London + news)

| key | label | due (`start_utc`) | Sri Lanka | outside timer | backup cron (UTC) | platforms |
|---|---|---|---|---|---|---|
| `asia` | Asia Open | 00:30 | 06:00 | cron-job.org 06:00 Asia/Colombo | `47 0 * * *` | YT + FB Reel |
| `news_morning` | Morning News | 03:00 | 08:30 | cron-job.org 08:30 Asia/Colombo | `17 3 * * *` | FB post |
| `london` | London Open | 05:40 | 11:10 | cron-job.org 11:10 Asia/Colombo | `57 5 * * *` | YT + FB Reel |
| `gold` | Gold Outlook | 06:15 | 11:45 | cron-job.org 11:45 Asia/Colombo, Mon–Fri | `32 6 * * 1-5` | YT + FB Reel |
| `news_midday` | Midday News | 09:30 | 15:00 | cron-job.org 15:00 Asia/Colombo | `47 9 * * *` | FB post |
| `newyork` | New York Open | 12:30 | 18:00 | cron-job.org 18:00 Asia/Colombo | `47 12 * * *` | YT + FB Reel |
| `news_evening` | Evening News | 16:30 | 22:00 | cron-job.org 22:00 Asia/Colombo | `47 16 * * *` | FB post |

- Defined in `config.yaml → sessions` (label, short, start_utc, focus text, `kind: gold` for gold,
  `kind: post` + `platforms: [facebook]` for news posts; video editions default to
  `[youtube, facebook]`). `main.py` has `DEFAULT_SESSIONS` as a fallback if config lacks them.
- **News posts every day, weekends included, never skipped:** no fresh unused story → the best
  story of the last 48 h not used by an earlier FB post → any story (only "no news at all" fails).
- **Gold time (06:15 UTC):** the Asian session (00:00–06:00 GMT) has set its range, London opens
  next (07:00 GMT summer / 08:00 winter) and usually tests the Asian high/low first, and US data
  (12:30–14:00 GMT) is still ahead, so the levels are fresh and useful for the whole day.
- **Triggers.** GitHub's schedule proved unreliable (Oct 2026: the 12:30 run started 6.5 h late,
  the next day's 00:30 run never started), so the **primary trigger is cron-job.org** POSTing
  `workflow_dispatch` with `{"ref":"main","inputs":{"session":"asia","scheduled":"true"}}`
  (fine-grained PAT, this repo only, Actions read/write; setup in README "Outside timer").
  GitHub crons stay as a **backup 17 min later**, off the busy :00/:30 marks.
- Both triggers pass `--scheduled` ("timed run"). Job concurrency group `timed-<edition>` queues
  the second one; it checks out the history the first pushed and stops with "already published".
  If the first run published only one platform (e.g. FB failed), the second re-makes the edition
  (with history minus today's slot, so same lead / same gold review) and publishes only the missing one.
- **Manual runs** (Run workflow, no `scheduled`) always make and upload a video, any time, in
  their own concurrency group (`manual-<run id>`): they never wait for or cancel autopilot runs,
  and are logged with `trigger: manual, counts: false`, so the timed run of that edition still
  happens. Tick `as_edition` to make a manual run fill today's slot (timed run then skips).
- **History saving** is safe with parallel runs: `main.py` writes `output/<stamp>/history_entry.json`;
  the workflow resets to the latest `origin/main`, merges entries with
  `python -m autopilot.history add …` (idempotent by any of `video_id`, `fb_reel_id`, `fb_post_id`)
  and retries the push 5×. A platform added by a later run is a second entry for the same edition.
- Timed runs are skipped if they start > `max_late_minutes` (180) after `start_utc`, or > 30 min
  before it — so a very late run never posts the wrong edition. Manual runs aren't checked.
- The workflow maps the firing backup cron string → edition in the `EDITION:` env line **and**
  in the job's `concurrency.group`. **To change a time, change the cron-job.org job, `start_utc`,
  the cron line and the matching string in both places.**
- Run names in Actions: "Timer · asia", "Backup schedule · 47 0 * * *", "Manual · gold".
- Weekends: timed runs only make editions in `weekend_sessions` (`[london, news_morning,
  news_midday, news_evening]`; no gold).
- Timed runs make each edition once per UTC day (`--force` overrides, CLI only). Old history
  entries without `session` count as `london`; without `counts` they count.
- Market briefs keep only news since the previous *market* upload (if ≥6 fresh stories).

Manual runs: Actions → Shorts autopilot → Run workflow → `session` (auto/asia/london/newyork/gold/
news_morning/news_midday/news_evening), `platforms` (all/youtube/facebook, limited to the edition's
own), optional `as_edition`. `auto` = market edition by current UTC hour (<5 asia, <12 london, else newyork).
**YouTube API quota:** ~6 uploads/day (1,600 of 10,000 units each, resets midnight Pacific).
Autopilot uses 4 on weekdays, so about 2 manual uploads a day fit.

## Files

```
main.py                  orchestration, CLI: --session, --platforms, --scheduled (timed), --as-edition, --force, --no-upload
config.yaml              all settings (channel, llm, market, sessions, voice, video, upload)
get_token.py             one-time OAuth login on the owner's PC → prints YT_* secrets
autopilot/sources.py     news RSS, ForexFactory calendar, Coinbase crypto, Frankfurter FX, gold, macro
autopilot/focus.py       lead story + related assets (keywords, scoring, typical market links)
autopilot/gold.py        gold outlook: levels, liquidity, 1H/4H/daily bias, scenarios, review
autopilot/script.py      Gemini prompt, fact-check, validate, fix_visuals (scene types)
autopilot/llm.py         Gemini REST client with model fallback + verbose logging
autopilot/thumbnail.py   4 thumbnail templates (Pillow) + choose() + clean_hook()
autopilot/slides.py      per-scene graphics (Pillow + matplotlib)
autopilot/render.py      ffmpeg segments, chart draw-in, push-in, ASS captions, mix
autopilot/voice.py       edge-tts per scene, WordBoundary timings
autopilot/youtube.py     metadata assembly, upload (+ clear quota error), set_thumbnail
autopilot/facebook.py    Graph API v26.0: publish_reel, publish_photo, classified errors/retries, reel_caption
autopilot/news_post.py   FB news posts: pick_story, write_post (Gemini + fact_check + fallback), caption
autopilot/images.py      news post background (Cloudflare FLUX → library → drawn) + render_card 1080x1350
autopilot/seo.py         keyword-first titles (fallback built from data), description blocks, hashtags, tag seeds
autopilot/history.py     data/history.json helpers (per-platform published_on, fb_post_headlines, merge CLI)
autopilot/media.py       ffmpeg/ffprobe helpers
assets/fonts/            Anton + Space Grotesk (SIL OFL) for thumbnails
tests/test_offline.py    full offline render test with sample data + mocked LLM
data/history.json        upload log, committed back by the workflow (don't hand-edit casually)
assets/backgrounds/      optional own images per news topic (<topic>/*.jpg, or general/)
.github/workflows/autopilot.yml   7 backup crons + workflow_dispatch inputs (session, platforms, as_edition, scheduled)
```

## Data sources (all free, no API keys)

- **News:** RSS feeds in `sources.DEFAULT_FEEDS` — CoinDesk, Cointelegraph, The Daily Hodl (full
  article text in `body`), Federal Reserve (monetary press releases + speeches), Google News
  searches (crypto, forex, dollar, central banks, macro, gold, Fed rate odds). Paid press releases
  (Chainwire etc.) are dropped (`SPONSORED`). Started from the World Monitor finance feed set.
- **Fed rate odds:** CME FedWatch blocks bots (403) and forbids scraping, so `rate_expectations()`
  keeps headlines that quote odds ("hike odds drop to 18%"); the script must name the source.
- **Gold:** PAXG/USD hourly candles (token backed 1:1 by gold, 24/7) — Kraken OHLC (720 h), Coinbase
  as backup — shifted by the gap to Swissquote's public spot XAU/USD quote (typically ~$5, ~0.1%).
  Yahoo GC=F is futures (~$20 above spot) and stooq is behind a JS challenge: not used.
- **Macro:** US Treasury daily yield-curve CSVs (10Y, 2Y, 10Y real) and BLS CPI API v1 (no key,
  25 calls/day per IP; months BLS skipped are "-").
- **Blocked / not allowed:** forexfactory.com pages, Myfxbook, CME FedWatch (403 + ToS). Don't scrape.
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
- **News posts** (`gather(kind="post")`) read every feed incl. the FB-only `geopolitics`
  (war/sanctions/tariffs/conflict + markets) and `regulation` (SEC/CFTC/stablecoin) Google News
  searches, 48 h window; prices only feed the caption's "Market check". Video editions read the
  same feeds as before (`MARKET_FEEDS` / `GOLD_FEEDS`).

## LLM (Gemini, free tier)

- Key: `GEMINI_API_KEY` (Google AI Studio). Model `gemini-3.8-flash`, fallbacks in
  `config.yaml → llm.fallback_models`.
- `llm.generate_json()`: 404 → skip model for the run; 500/503 → one retry then next model;
  429 → wait/retry (daily-quota 429 → next model); 2-min read timeout; logs every call as
  `gemini: …`. If all fail, waits 60s and tries the list once more.
- History: `gemini-2.5-flash` returned 404 for this (new) key — 2.5 models are access-limited.
  Pro models are not on the free tier. Don't enable billing on the AI Studio project
  (it ends the free tier).
- Market brief = 3 calls: `research()` (analyst note: what happened, why only from headlines,
  impact on each focus asset with its number, macro context, what to watch), `write()` (one
  story, only the focus assets' data is in the prompt, story arc), `fact_check()` (full data).
  Typical market links (`focus.LINKS`) may be said as tendencies ("usually"), never as today's cause.
- `script.write()` rules: only numbers from the data; "why" only if a headline says so;
  no predictions/targets/buy-sell; not-financial-advice line; scene 1 must state the thumbnail
  fact; returns `thumbnail_hook`. `fix_visuals()` forces scene 1 = `title`, swaps charts of
  non-focus assets for an unused focus asset, degrades bad visuals to `board`.
- Scene visual types: `title, price{asset}, fx{asset}, gold, board, news{source,headline}, calendar, outro`;
  gold outlook adds `gold_chart, review, bias, liquidity, scenarios, drivers`.
- Gold outlook = 2 calls: `write_gold()` narrates the fixed `gold_plan()` scenes (by id) from
  `gold.analyze()` only; biases worded as conditional reads ("bearish while below…"); never buy/
  sell/long/short/entry/stop/target. `fact_check(…, GOLD_RULES)`.

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
With `data["focus"]`, all of the above only consider the focus assets / currencies (gold counts
as an asset: |24h| ≥ 1.5% scores 1, level step $100). **gold** template (gold outlook only):
daily bias word (BULLISH/BEARISH/RANGE), "BELOW $4,142", 1H/4H chips, 48h chart, "KEY LEVELS TODAY".

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
- Category 25 (News & Politics). SEO (`seo.py`): the title must have the lead asset name / "Gold price"
  in its first 45 chars, else a data-built title ("XRP Price Today: Down 5.0% | London Open, Oct 8",
  "Gold Price Today: Bearish Below $4,142 | XAU/USD Outlook Oct 8"). Description = keyword-first
  summary → Key numbers / Key levels → Stories mentioned → What to watch → posting schedule →
  data credits → disclaimer → hashtags (lead asset, its market, related asset, …, #Shorts last;
  the first 3 show above the title). Tags: keyword seeds first, then the writer's; ≤ ~480 chars.
- `containsSyntheticMedia: false` (AI voice + data graphics don't require the label).

## Facebook (Graph API v26.0)

- Secrets `FB_PAGE_ID`, `FB_PAGE_TOKEN` (never-expiring Page token: Meta Business app owned by the
  Page admin, `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` (no `publish_video`),
  **app in Live mode** or posts are hidden; setup in README "Facebook Page"). Missing secrets or
  `facebook.enabled: false` → skipped with a log line. Token dies on password change / lost role.
- Reel: `POST /{page}/video_reels upload_phase=start` → `POST rupload.facebook.com/video-upload/v26.0/{id}`
  (`Authorization: OAuth`, `offset: 0`, `file_size`) → `finish` (`video_state=PUBLISHED`, description)
  → poll `GET /{id}?fields=status` ≤ 10 min. **`finish` is sent once**; on an unclear answer the status
  is checked before it is ever re-sent. Cover via `/{id}/thumbnails` is best effort. 30 API Reels/Page/24 h.
- Photo: `POST /{page}/photos` (`source`, `caption`, `published=true`), ≤ 10 MB.
- Errors: 190 / 10 / 200–299 / 100 / 368 fail fast with a fix hint; 4/17/32/613/80001 (throttled)
  fail with a message; 1, 2, `is_transient`, HTTP 5xx retry 3× with backoff from 5 s.
- Captions: hook first (cut at ~280 chars), source named, no links, ≤ 5 hashtags (no #Shorts),
  disclaimer; Reel captions are built from the YouTube metadata (`reel_caption`, < 2,200 chars).
- Renders use a closed ~2 s GOP (`-g 2*fps`) and stereo AAC (`-ac 2`) for the Reels spec.

## News image posts (Facebook)

- Card (owner's reference style): full-bleed story-matched background, small kicker pill, huge
  2–3 line Anton headline with one line in the accent colour, short subline, brand + date chip,
  "Source: …", and "AI illustration" when the background is AI.
- Background: Cloudflare Workers AI `@cf/black-forest-labs/flux-1-schnell` (secrets `CF_ACCOUNT_ID`,
  `CF_API_TOKEN`; free 10k neurons/day ≈ 60 per image) → random `assets/backgrounds/<topic>/` →
  drawn branded background. Prompts are symbolic scenes: no text, logos, real people or realistic
  depiction of the actual event (style suffix in `images.STYLE`).
- Gemini output is used only if it passes `fact_check()` and a deterministic number check against
  the facts; card text also fails on `thumbnail.BANNED` words; caption sentences with banned words
  are dropped. Otherwise the post is built from the story's own title/summary (`fallback_post`).
- History: `kind: post`, `fb_post_id`, `headlines: [story title]`, `topic`, `background`. These
  headlines don't feed the videos' "don't repeat" list (`used_headlines()` skips posts).

## Secrets (GitHub → Settings → Secrets and variables → Actions)

`GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`,
`FB_PAGE_ID`, `FB_PAGE_TOKEN`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`.
The cron-job.org PAT lives only in cron-job.org (not a repo secret).
(`PIXABAY_API_KEY` / `PEXELS_API_KEY` are legacy and unused.) Never commit `client_secret.json`
(git-ignored).

## Running & testing

```bash
pip install -r requirements.txt            # + ffmpeg on PATH
python tests/test_offline.py               # no keys/network: renders output/test/short.mp4 + contact.png,
                                           # output/test_news/post.jpg + caption_fb.txt; Graph API mocked
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
- **AI-generated images (Cloudflare Workers AI FLUX):** built for videos, then removed at the
  owner's request. **Re-adopted Oct 2026 for the Facebook news-post backgrounds only** (owner's
  decision: AI per post, library and drawn fallbacks, "AI illustration" note on the card).
- **Facebook (owner, 2026-10-08):** the 4 video editions also go out as Reels (same render), plus 3
  news image posts a day at 03:00 / 09:30 / 16:30 UTC, every day, never skipped. Card style follows
  the owner's references; everything else goes in the caption with SEO hashtags.
- **Publisher photos / scraping for news posts:** not allowed (copyright, ToS); backgrounds are
  AI, own library or drawn.
- **AI video APIs (Veo, Kling…):** no free tier (~$0.05+/s).
- **Reusing YouTube/TikTok clips:** rejected — copyright strikes, reused-content demonetization, ToS.
- **Monetization policy:** YouTube "inauthentic content" targets mass-produced templated videos;
  keep editions genuinely different (fresh news per edition, one lead story, lead repeats get a
  score penalty), ~4/day, no hype.
- **News photos in videos:** rejected — publisher images (Reuters/Getty/AP) are copyrighted →
  Content ID claims and reused-content risk. News is shown as drawn headline cards instead.
- **Gold bias by LLM:** rejected — the bias/levels are deterministic rules in `gold.py` so they're
  repeatable and auditable; tomorrow's video reviews today's call honestly (`review`).
- **"All markets" briefs:** replaced Oct 2026 by one-story briefs (owner: videos mixed BTC, ETH,
  EUR, GBP regardless of the news). Lead needs headlines: a move with no headline counts 0.7×.

## Gotchas we hit

- `.github/` and `.gitignore` are hidden folders/files — drag-and-drop uploads skip them; use git.
- A config.yaml that didn't get committed broke editions ("Choose one of:" empty) → hence
  `DEFAULT_SESSIONS`. After unzipping updates, check `git status` lists every changed file.
- The workflow commits `data/history.json` after each upload → **always `git pull` before pushing.**
  (Its save step resets to `origin/main` and re-merges the run's entry, so parallel runs don't lose logs.)
- GitHub account billing lock once blocked all jobs ("account is locked due to a billing issue").
- GitHub scheduled runs can start hours late or never (hence the outside timer); schedules
  also pause after 60 days of repo inactivity. A green 1-min run = a skip; read its last log line.
- Run times in the Actions UI are in the browser's time zone (GMT+5:30), not UTC.
- cron-job.org `401` = PAT expired (1-year expiry) → new token into all seven jobs.
  `422` = `main`'s workflow lacks the `scheduled` input.
- A cron expression in YAML must stay on one line inside `${{ }}`.
- Node 20 deprecation warning for actions/checkout@v4, setup-python@v5, upload-artifact@v4 —
  harmless for now; bump to Node 24 versions when convenient (verify versions exist first).

## Ideas / next steps (not done)

- Bump GitHub Actions versions (Node 24).
- Submit / confirm the YouTube API audit so uploads are public automatically.
- Analytics feedback loop (YouTube Analytics API) to compare editions and thumbnail templates.
- Gold outlook accuracy tracking over weeks (history has `outlook` per day) → monthly hit-rate video.
- Medium-impact calendar events for quiet days; DXY (no free intraday source found yet).
- Weekly recap long-form video from the week's history.
- Comment pinning / community posts (manual for now).

## Conventions for changes

- Keep everything free-tier; no new paid APIs without asking the owner.
- Every number shown or spoken must come from fetched data. No buy/sell language. Market briefs
  make no predictions; the gold outlook's bias/scenarios come only from `gold.py` rules.
- Run `python tests/test_offline.py` after any change to rendering, slides, thumbnail or script flow.
- Prefer small, explicit log lines (`log(...)`) — the Actions log is the only monitoring.
- Owner applies changes via git (Mac or Windows); give exact file paths when handing over changes.
