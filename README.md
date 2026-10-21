# Shorts Autopilot: CryptoFX Daily (crypto-only slate)

Makes and publishes a **crypto-only weekly slate** with no manual work, running free on GitHub Actions:
three standalone **Shorts** a day (YouTube Short + Facebook Reel), a weekly **Crypto Basics** explainer and a
weekly **trading lesson** (YouTube 16:9 + Facebook 9:16 video), **"why crypto just moved"** videos after big
moves and a **Saturday recap** (YouTube only), plus **three crypto news image posts** a day on the Facebook
Page. Every edition runs 7 days a week (no forex weekend rule).

| Edition | UTC | Sri Lanka | What it is | Where |
|---|---|---|---|---|
| Short P (`short_p`) | 00:30 daily | 06:00 | market-pulse Short from the day's fetched data (timed runs skip while `pulse.enabled` is false) | YouTube Short + Facebook Reel |
| Morning News (`news_morning`) | 12:00 daily | 17:30 | news image post: one crypto story | Facebook |
| Short A (`short_a`) | 13:00 daily | 18:30 | standalone Short from a long video's material (a market-pulse Short first once `pulse.enabled` is true) | YouTube Short + Facebook Reel |
| Crypto Basics (`basics`) | 15:00 Wed | 20:30 | the next approved beginner explainer | YouTube 16:9 + Facebook 9:16 video |
| Trading Lesson (`lesson`) | 15:00 Thu | 20:30 | the next curriculum episode | YouTube 16:9 + Facebook 9:16 video |
| Weekly Recap (`recap`) | 15:00 Sat | 20:30 | the week's biggest moves and why; skipped in a week with a triggered video → evergreen top-up when the week is short | YouTube 16:9 |
| Sunday top-up (`topup_sun`) | 15:00 Sun | 20:30 | evergreen top-up (Basics first, then the next lesson) only when the week still has < 2 long videos | YouTube 16:9 + Facebook 9:16 video |
| Midday News (`news_midday`) | 16:00 daily | 21:30 | news image post | Facebook |
| Evening News (`news_evening`) | 21:00 daily | 02:30 | news image post | Facebook |
| Short B (`short_b`) | 23:00 daily | 04:30 | standalone Short | YouTube Short + Facebook Reel |
| Why Crypto Moved (`triggered`) | within ~3 h of a trigger | — | dispatched by the 30-minute trigger poll | YouTube 16:9 |

**Budget:** per UTC day on YouTube at most 3 Shorts and 1 planned long video (≤ 4 uploads; manual uploads count). A
timed Short skips when the day already has 3 Shorts; long videos never take a Short's slot. A triggered video is
never held for the budget: it publishes within ~3 h even on a day with a planned long video (Crypto Basics, the
Lesson, a recap or a top-up), and Basics / the Lesson still run (that day: 2 long videos, up to 5 uploads). 2-4 long videos per ISO week (a shortfall is
topped up Saturday 15:00, or Sunday 15:00 when Saturday already had the recap or a triggered video; a fifth is
refused).

**Release checklist (crypto slate, owner):** on a Monday you pick — (1) approve the Crypto Basics topics and fill
the evergreen stock to 4 ready episodes (`python main.py --session basics --prepare next`, `--stock`); (2) add the
`COINGECKO_API_KEY` secret; (3) delete the retired cron-job.org jobs (`asia`, `london`, `newyork`, `gold`; or
`python setup_cronjobs.py --delete-retired`); (4) push (together with the Thursday lesson-slot change); (5) run
`python setup_cronjobs.py` to move the news jobs and add the new ones; (6) check the first day's runs against the
table above. Details: CLAUDE.md "Release checklist".

**News image posts (Facebook):** each picks the most important crypto story of the last 48 h (crypto or crypto
regulation named in the headline or its lead), scored by topic, coverage and recency, never one an earlier post
used. Gemini writes a big 2–3 line headline and an SEO caption (fact-checked; numbers only from the data; source
named; no hype, no links, ≤5 hashtags, disclosure line). The 1080×1350 card sits on a story-matched AI background
(Cloudflare Workers AI, free tier; marked "AI illustration"), or an image from `assets/backgrounds/<topic>/`, or a
drawn background.

**Timing:** GitHub's own schedule can start runs hours late or skip them, so runs are started
on time by a free outside timer (cron-job.org) that presses "Run workflow" through the GitHub
API. GitHub's schedule stays as a backup 17 min later. Whichever runs first makes the video; the
other sees it's already up and stops. A timed run that starts over 3 h late is skipped rather
than posting the wrong edition. Setup: [Outside timer](#outside-timer-cron-joborg) below.

**Manual runs:** Actions → Shorts autopilot → **Run workflow** → pick the edition → Run. A manual run
**always** makes and uploads, at any time, and never blocks the autopilot: that edition's timed run still
happens. Tick **Count it as today's edition** only if you want the timed run to skip. Leave **Timed run**
unticked (it's for the outside timer). YouTube's API allows about 6 uploads daily in total, and the slate uses
up to 4 (3 Shorts + 1 long video; 5 on a day with a planned long video and a triggered video). **Platforms** (`all` / `youtube` / `facebook`) limits where it goes; news posts only ever go to
Facebook, triggered and recap videos only to YouTube.


**Sources (all free, no keys):**
- **News:** public RSS feeds: CoinDesk, Cointelegraph, The Daily Hodl (full articles), the
  Federal Reserve (policy statements, speeches), and Google News searches for forex, central
  banks, crypto, economic data, gold and Fed rate odds. Paid press releases are filtered out.
- **Economic calendar:** ForexFactory's official weekly calendar export (high-impact events).
- **Crypto prices:** Coinbase public market data (BTC, ETH, SOL, XRP; 7-day hourly).
- **Forex rates:** Frankfurter, daily central-bank reference rates (EUR/USD, GBP/USD, USD/JPY…).
- **Macro:** US Treasury yields (10Y, 2Y, 10Y real) and US CPI from the BLS.
- **Fed rate odds:** taken from headlines that quote CME FedWatch (the FedWatch site, Myfxbook and
  forexfactory.com pages block automated access and forbid scraping).

Every scene is a graphic drawn from that data (price chart that draws itself in, market
board, headline card, calendar table), so there's no stock footage to mismatch. The script
may only use numbers from the data, and a second pass checks it against the data before
anything is recorded. No predictions and no buy/sell calls;
"Not financial advice" is in every slide's footer, and the YouTube description and Facebook
caption carry the disclosure line once ("Narrated with a synthetic voice. Researched from public market
data. Not financial advice.", `upload.disclaimer`); none of it is spoken and there's no outro card.
News photos aren't used (copyright).

**Built to be watched:** each Short is 30–40 seconds (`video.max_seconds: 42`; longer narration is
re-recorded faster), opens with a line that has a real number and a reason to keep watching, and
ends on a line that loops back to the opening fact instead of a sign-off.

**Thumbnail / opening frame:** every video opens on a thumbnail design picked from the day's
data, so the first frame (what the feed shows, and what YouTube usually uses as the
thumbnail) is built to stop the scroll. It starts moving straight away (a quick push-in), holds
about a second, then the chart of the asset it shows draws in (gold: the gold chart) and the captions start:

| Template | Used when | Example |
|---|---|---|
| Big Move | a coin moves 4%+ in 24h or an FX pair 0.8%+ | "−6.2%" + chart + WHAT HAPPENED? |
| Event Day | a high-impact event is due within 12 hours | "CPI DAY" on yellow + WATCH BEFORE 12:30 |
| Split | Bitcoin and the US dollar move opposite ways | green/red split + WHY THE SPLIT? |
| Key Level | BTC/ETH/gold is within 2% of a round number | "1.2% AWAY FROM $100K" + SO CLOSE. |

In market briefs the template is chosen only from the brief's lead-story assets.

The 2–4 word hook is written by the AI for that day and must be answered in the video; hype
words (moon, buy, sell, will, guaranteed…) are rejected and replaced by the template's
default hook. Each run also saves `thumbnail.jpg`; the system tries to set it as the custom
thumbnail, which YouTube currently allows for Shorts only on some channels (e.g. Partner
Program members, set in Studio on desktop). If refused, the opening frame does the job.

**Each platform on its own:** a video is rendered once and published to each platform
separately. If YouTube fails (e.g. the daily quota), the Facebook Reel still goes out, and the
reverse; the backup run re-makes the edition only for the platform that's still missing.
Facebook is skipped (with a log line) until its secrets are set.

**Running cost:** $0 on the free tiers of Gemini, edge-tts, Cloudflare Workers AI, the Facebook
Graph API and GitHub Actions.

---

## Setup (about 30–40 minutes, once)

### 1. Get a Gemini API key

`GEMINI_API_KEY`: https://aistudio.google.com/apikey → **Create API key**. (The market data
sources need no keys.)

### 2. Let the system upload to your channel

1. Create the YouTube channel first (any Google account).
2. Go to https://console.cloud.google.com → create a new project (e.g. "shorts-autopilot").
3. **APIs & Services → Library** → search **YouTube Data API v3** → **Enable**.
4. **APIs & Services → OAuth consent screen** (may be called *Google Auth Platform*):
   - User type: **External**. Fill in app name and your email.
   - Under **Audience / Test users**, add the Google account that owns the channel.
   - Then click **Publish app** so the status is **In production**.
     ⚠️ If you leave it in *Testing*, the login expires every 7 days and uploads stop.
     You don't need Google's app verification for your own channel; you'll just see an
     "unverified app" warning once when you log in — click *Advanced → Continue*.
5. **APIs & Services → Credentials → Create credentials → OAuth client ID** → type **Desktop app**
   → **Download JSON**. Rename the file to `client_secret.json` and put it in this folder.
6. On your computer (Python 3.10+):
   ```bash
   pip install google-auth-oauthlib
   python get_token.py
   ```
   Log in with the channel's account, pick the channel, allow access. It prints
   `YT_CLIENT_ID`, `YT_CLIENT_SECRET` and `YT_REFRESH_TOKEN`.

### 3. Put it on GitHub

1. Create a new **private** repository and upload everything in this folder
   (`client_secret.json` is git-ignored — never commit it).
2. **Settings → Secrets and variables → Actions → New repository secret** — add all four:
   `GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`
   (and the Facebook / Cloudflare ones from step 5 when you set those up).
3. **Actions** tab → enable workflows → **Shorts autopilot** → **Run workflow** to test now.
   After that it runs by itself every day at 05:40 UTC (11:10 Sri Lanka time), before the
   London session opens. If today's brief is already up, a second run does nothing.

Each run's video, script and metadata are kept for 7 days under the run's **Artifacts**,
and `data/history.json` logs every upload so the same story doesn't lead two days running.
GitHub emails you if a run fails.

### 4. Request the YouTube API audit (needed for public videos)

Google locks every video uploaded by a new, un-audited API project to **private**, even when
the code asks for public. The system works end to end before the audit — videos just land
as private in YouTube Studio, where you can make them public by hand.

To remove the lock, submit the **YouTube API Services – Audit and Quota Extension Form**
(linked from https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits).
Describe it honestly: an internal tool that uploads videos to your own channel only.
Approval usually takes days to a few weeks. After that, videos go public automatically.

### 5. Facebook Page (Reels + news posts)

Needs a Facebook Page you are an admin of. Everything here is free.

1. **Meta app:** https://developers.facebook.com/apps → **Create app** (from the Page admin's
   account) → Add use cases → filter **Content management** → **Manage everything on your Page**.
   (Don't pick "Other": Meta is retiring it. Linking a Business portfolio is optional.)
   Then Use cases → Manage everything on your Page → **Customize** and check the permissions below.
2. **Permissions:** `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`, each showing
   **Ready for testing** (Standard Access is enough for your own Page; no App Review needed).
   `publish_video` isn't needed: Reels publishing only asks for these three.
3. **Switch the app to Live mode** (App settings → Basic → privacy policy URL, e.g. your GitHub
   Pages policy, then the Development/Live toggle). ⚠️ Posts made by an app in Development mode
   are hidden from the public.
4. **Page token that never expires:**
   - Graph API Explorer (https://developers.facebook.com/tools/explorer) → your app → **Get User
     Access Token** with the three permissions above → copy it.
   - Make it long-lived (App ID / App Secret from App settings → Basic):
     `https://graph.facebook.com/v26.0/oauth/access_token?grant_type=fb_exchange_token&client_id=<APP_ID>&client_secret=<APP_SECRET>&fb_exchange_token=<USER_TOKEN>`
   - `https://graph.facebook.com/v26.0/me/accounts?access_token=<LONG_LIVED_USER_TOKEN>` → find your
     Page: its `id` is **`FB_PAGE_ID`**, its `access_token` is **`FB_PAGE_TOKEN`**.
   - Check it: paste it into https://developers.facebook.com/tools/debug/accesstoken →
     **Expires: Never** (`expires_at: 0`).
   - The token stops working if you change your Facebook password or lose your Page role; a run
     then fails with "Facebook error 190 … regenerate FB_PAGE_TOKEN": repeat this step.
     (Sturdier alternative: a Business Manager **System User** token with the same permissions.)
5. **Cloudflare (AI backgrounds, optional):** sign up at https://dash.cloudflare.com (free plan) →
   copy the **Account ID** (right side of the account home) = **`CF_ACCOUNT_ID`**; My Profile → API
   Tokens → Create Token → template **Workers AI** → **`CF_API_TOKEN`**. Free: 10,000 neurons a day
   (about 60 per image, 3 images a day). Without these the posts use `assets/backgrounds/<topic>/`
   images (topics: rates, central_bank, geopolitics, tariffs, regulation, macro, crypto, gold, fx,
   markets, or `general`; only images you own or that are licensed for reuse) or a drawn background.
6. Add **`FB_PAGE_ID`**, **`FB_PAGE_TOKEN`**, **`CF_ACCOUNT_ID`**, **`CF_API_TOKEN`** as repository
   secrets (Settings → Secrets and variables → Actions).
7. Add the three news-post jobs to cron-job.org (see [Outside timer](#outside-timer-cron-joborg)).
8. Test: Actions → Run workflow → session `news_morning` (a news post) and, for a Reel,
   session `short_a` with platforms `facebook`.

To pause Facebook, set `facebook.enabled: false` in `config.yaml`.

### 6. Trading lessons (off until you switch them on)

The `lesson` edition publishes the next episode of `lessons/curriculum.yaml` (list order is the
queue) at 15:00 UTC (20:30 Sri Lanka) every **Thursday**: a 16:9 video on
YouTube (Education, public on upload; set `lessons.review_window_hours` to keep it private that many
hours first; playlists by hand in Studio unless `lessons.playlists: true`) and the same
narration as a 9:16 video on the Facebook Page. Every chart is a real historical example a detector
found in the free price history; an episode with no clean example is **held** (logged, retried next
time) and the next one goes out instead. If every episode is published or held, the run logs
"nothing to publish in this slot" and stops. Each platform is published on its own: if one fails,
the backup run re-makes the same episode (same examples) and publishes only the missing one; if
that episode can't be re-made, the run fails so you see it.

**Top-up in another slot:** `python main.py --session lesson --slot recap` (Actions → Run workflow →
session `lesson`, `slot` = the edition whose slot it fills) publishes the next unpublished episode once
in today's slot of that edition (Saturday 15:00, or Sunday when Saturday is taken), for a week that is
short of long videos. It counts for that slot: a second call for the same slot and day publishes
nothing, and no episode is ever repeated.

Each episode opens on its first real example, already marked, under the lesson title (no title card),
so the payoff is on screen from the first frame; the recap ends on "Next: <episode>". In the example
scenes the marks (swings, BOS / CHoCH lines, zones, labels) appear one at a time as the narration names them. The YouTube and
Facebook title is the entry's `search_title` in `lessons/curriculum.yaml` ("What Is a Break of
Structure? (Crypto Chart Example)"; edit it there, the validator checks the shape); the series label
goes in both descriptions as "Track 0 · Structure #2: BOS vs CHoCH", with the disclosure line once.
Chapters go in the description automatically. **End screen (once, by hand):** the API can't set end
screens, so in YouTube Studio make an end-screen template (Video element → "Best for viewer" or the series playlist +
Subscribe) and apply it to each lesson; the recap's last ~20 s are where it shows.

To switch them on:
1. **YouTube:** nothing to change: lessons upload with the existing `YT_REFRESH_TOKEN` and you add
   them to playlists by hand in YouTube Studio (`lessons.playlists: false`). Only if you want automatic
   playlists: add the `youtube` and `yt-analytics.readonly` scopes to the OAuth consent screen, run
   `python get_token.py --lesson-scopes`, replace **`YT_REFRESH_TOKEN`**, set `lessons.playlists: true`.
   Custom thumbnails on long videos need a phone-verified channel (youtube.com/verify).
2. **Curriculum:** merge the approved `lessons/curriculum.yaml` and `lessons/glossary.yaml`;
   `python tests/test_lessons.py` must pass (a run with curriculum problems lists them and fails).
3. Set **`lessons.enabled: true`** in `config.yaml` and push.
4. **Outside timer:** add the `lesson` job to cron-job.org (15:00 UTC / 20:30 Asia/Colombo,
   Thursday only; body `{"ref":"main","inputs":{"session":"lesson","scheduled":"true"}}`),
   or run `python setup_cronjobs.py` (it uses the edition's `days`).
5. Test: Actions → Run workflow → session `lesson` (a manual run works any day, publishes the next
   episode and doesn't fill the timed slot).

While `lessons.enabled` is false, lesson runs log why and stop without fetching or posting
(`python main.py --session lesson --no-upload` still makes one locally).

---

## Settings you'll likely change (`config.yaml`)

| Setting | What it does |
|---|---|
| `channel.niche` / `audience` / `tone` | What the channel is about and how it sounds |
| `voice.name` | Narrator voice. List them: `edge-tts --list-voices` |
| `voice.alternate` | Second edge-tts voice for the 30-day A/B test: Shorts and long videos alternate `name` / `alternate` per edition, logged as `voice` in `data/history.json`. Remove the line to keep one voice |
| `voice.fallback` | Piper voice used when edge-tts is down (`en_US-ryan-high`); remove to fail instead |
| `upload.review_window_hours` | `0` = public immediately. e.g. `6` = sits private for 6 h so you can watch and delete it first, then goes public on its own |
| `channel.display_name` | Brand line at the top of every graphic |
| `market.calendar_impacts` | `[High]` by default; `[High, Medium]` for more events |
| `video.accent` / `video.footer` | Brand colour and the footer line on every graphic |
| Posting times | change all of: the cron-job.org job, `start_utc` in `config.yaml`, and the backup `cron` line in `.github/workflows/autopilot.yml` plus the matching string in its `EDITION:` line and `concurrency.group` |
| Editions | `sessions` (start_utc, `days`, `platforms`) and `slate` (`shorts_day_cap` 3, `long_day_cap` 1, `week_floor` 2, `week_cap` 4; an old `day_cap` is read as the Shorts cap) in `config.yaml` |
| Facebook | `facebook.enabled`, `facebook.max_hashtags`; news posts: `news_posts.topic_weights`, `fresh_hours`, `disclaimer` |
| Trading lessons | `lessons.enabled`, `review_window_hours`, `path_playlist`, `track_playlist`, `fb_published`, `max_seconds`; run days: `sessions.lesson.days` |
| News post backgrounds | `images.provider` (`cloudflare` or `none`), `images.steps`; your own images in `assets/backgrounds/<topic>/` |
| Coins / FX pairs | `CRYPTO` and `FX` lists at the top of `autopilot/sources.py` |
| News feeds | `DEFAULT_FEEDS` in `autopilot/sources.py` |
| Background music | Drop royalty-free `.mp3` files into `music/` |

## Run it on your computer

Needs Python 3.10+ and ffmpeg.

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...          # Windows PowerShell: $env:GEMINI_API_KEY="..."
python main.py --no-upload --session short_a  # makes output/<time>/short.mp4 (+ thumbnail, metadata)
python main.py --no-upload --session news_morning   # makes output/<time>/post.jpg + caption_fb.txt
python main.py --no-upload --session lesson   # next lesson: output/<time>/lesson_16x9.mp4 + lesson_9x16.mp4
python tests/test_offline.py        # graphics + render + mocked Facebook check, no keys needed
python tests/test_lessons.py        # curriculum, detectors, lesson data + narration checks
```

---

## Staying eligible for monetization

YouTube's **inauthentic content** policy demonetizes channels whose videos look mass-produced
or templated. Faceless and AI-assisted channels are allowed; low-effort repetition isn't.

What the system already does to stay on the right side:
- Each video is built from that day's data, so every upload says something new.
- Original graphics drawn from the data, not reused clips.
- A fact-check pass against the data; drafts that don't hold up are thrown away.
- One brief a day, not a flood.

Finance-specific care:
- No predictions, price targets or buy/sell calls (YouTube and viewers both punish "signals").
- Not-financial-advice note on screen, in the narration and in the description.
- News is paraphrased and credited in the description; nothing is read out verbatim.

What helps most from your side, even if it's 10 minutes a week:
- Watch a few uploads and delete weak ones (or use `review_window_hours`).
- Reply to comments, and pin a comment with something extra.

## Known limits

- Shorts thumbnails can't be set through the API; YouTube picks a frame.
- Forex rates are daily reference rates (not live quotes); the script says "yesterday's close".
- Free data sources can change or go down. A source that fails is skipped; if no price data
  at all is available, the run stops instead of guessing.
- edge-tts uses Microsoft's free Edge read-aloud service. When it refuses GitHub's runner (it did on
  12 Oct 2026, "403 Invalid response status"), each scene is retried for ~100 s, then that video is
  voiced by a free local Piper voice (`voice.fallback`, a different male US voice; downloaded on first
  use). The log says "Narration by Piper" when that happens.
- The Gemini model name may be retired over time; update `llm.model` if runs start failing with 404.
- The free Gemini tier may use your prompts to improve Google's products.
- Facebook may refuse a custom Reel cover through the API; the Reel then uses its own frame.
- A Reel or lesson video still processing after 10 minutes is logged as published (so it isn't
  posted twice); check the Page if a run says so.
- YouTube's ~6 uploads a day: the autopilot uses at most 4 (3 Shorts + 1 long video), 5 on a day with a
  planned long video and a triggered video, leaving 1-2 manual uploads a day (a manual Short counts toward the 3 Shorts).

## Files

```
main.py                 orchestrates one run
config.yaml             all settings
get_token.py            one-time YouTube login
autopilot/sources.py    news feeds, economic calendar, crypto, forex + gold prices, US yields, CPI
autopilot/focus.py      picks each brief's lead story and the assets it moves
autopilot/slate.py      the slate's budget: 3 Shorts + 1 long video a day, weekly floor/cap (triggered videos never held)
autopilot/shorts.py     standalone Shorts: picking (market / pulse, concept rotation + 7-day topic cooldown), script,
                        visual frame 0, slides, metadata
autopilot/pulse.py      market-pulse material from the day's fetched data (no LLM; a quiet market writes none)
autopilot/script.py     research note, grounded script + fact-check against the data (Gemini)
autopilot/slides.py     shared slide constants + the (retired) brief's charts, kept as the offline render fixture
autopilot/thumbnail.py  thumbnail templates + picking one from the data
assets/fonts/           Anton + Space Grotesk (SIL Open Font License)
autopilot/voice.py      narration + word timings (edge-tts)
autopilot/render.py     ffmpeg assembly, chart draw-in, highlighted captions
autopilot/seo.py        search-friendly titles, descriptions, hashtags, tags
autopilot/youtube.py    metadata + upload
autopilot/facebook.py   Facebook Page: Reels, photos, error handling, captions
autopilot/news_post.py  news posts: story pick, headline + caption (Gemini, fact-checked)
autopilot/images.py     news post backgrounds (Cloudflare AI / library / drawn) + the 1080×1350 card
autopilot/lessons.py    trading lessons: curriculum / glossary format, validator, episode picker, scene plan
autopilot/detectors/    find real historical examples per concept (structure, trendlines, liquidity, SMC, mtf)
autopilot/lesson_data.py   multi-timeframe price history for the detectors (BTC/ETH from Coinbase only)
autopilot/lesson_script.py lesson narration from the approved key points (Gemini, fact-checked)
autopilot/lesson_slides.py lesson graphics + thumbnail in 16:9 and 9:16
autopilot/lesson_meta.py   lesson chapters, titles, descriptions, hashtags
lessons/                curriculum.yaml (the episode queue) + glossary.yaml
setup_cronjobs.py       creates / fixes the cron-job.org timers from config.yaml
data/history.json       what has been published (YouTube id, Facebook Reel / post / video id, lesson episode)
.github/workflows/      backup schedule, manual runs, history saving
```

## Outside timer (cron-job.org)

One-time setup, free, about 10 minutes.

**Shortcut:** `python setup_cronjobs.py` creates or fixes the slate's ten jobs from `config.yaml` through
the cron-job.org API (jobs titled "CryptoFX · <edition>", times in UTC, basics / lesson / recap / topup_sun on
their `days`). `--delete-retired` also deletes the retired `asia`, `london`, `newyork` and `gold` jobs (or delete
them by hand). It asks for a cron-job.org API key (Settings → API) and the GitHub token from step 1, with hidden
input. Run it again after changing any `start_utc`; `--dry-run` shows the plan. The manual steps below do the same.

1. **GitHub token:** your photo → Settings → Developer settings → Personal access tokens →
   **Fine-grained tokens** → Generate new token. Repository access: **Only select repositories**
   → `yt-shorts-autopilot`. Permissions → Repository → **Actions: Read and write** (nothing
   else). Expiry: 1 year. Copy the token.
2. **cron-job.org:** sign up → Create cronjob:
   - URL: `https://api.github.com/repos/Thimuthu96/yt-shorts-autopilot/actions/workflows/autopilot.yml/dispatches`
   - Schedule: custom, time zone **UTC**, every day at **13:00**
   - Advanced → Request method **POST**, headers:
     `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
     `Content-Type: application/json`
   - Body: `{"ref":"main","inputs":{"session":"short_a","scheduled":"true"}}`
   - Save, then **Test run**: `204` = it worked (a "Timer · short_a" run appears in Actions).
3. Copy the job, changing only the time, days and session (UTC): **23:00 → `short_b`**, **12:00 →
   `news_morning`**, **16:00 → `news_midday`**, **21:00 → `news_evening`**, **00:30 → `short_p`** (every day; the
   owner adds it with the pulse release, 6.6); **15:00 → `basics`**
   (Wednesday), **`lesson`** (Thursday), **`recap`** (Saturday), **`topup_sun`** (Sunday).
4. Delete the retired jobs: `asia`, `london`, `newyork`, `gold`.

Keep the token only in cron-job.org (never in the repo or chat). If the jobs start failing
with `401`, the token has expired: make a new one and paste it into all ten jobs (nine before the pulse release adds short_p). A `422`
means the workflow on `main` doesn't have the `scheduled` input yet (push the latest code).
