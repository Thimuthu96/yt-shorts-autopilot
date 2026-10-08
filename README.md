# Shorts Autopilot: Daily Market Brief

Makes and publishes **crypto & forex market briefs** and a **daily gold outlook** as YouTube
Shorts **and Facebook Reels** (one render, both platforms), four a day, plus **three news image
posts** a day on the Facebook Page, with no manual work, running free on GitHub Actions.

| Edition | UTC | Sri Lanka | What it is | Where |
|---|---|---|---|---|
| Asia Open | 00:30 | 06:00 | market brief: one lead story since the New York close | YouTube + Facebook Reel |
| Morning News | 03:00 | 08:30 | news image post: one market-moving story | Facebook |
| London Open | 05:40 | 11:10 | market brief: one lead story from the Asian session | YouTube + Facebook Reel |
| Gold Outlook | 06:15 | 11:45 | XAU/USD: bias for the next 1h / 4h / day, liquidity, key levels (Mon–Fri) | YouTube + Facebook Reel |
| Midday News | 09:30 | 15:00 | news image post | Facebook |
| New York Open | 12:30 | 18:00 | market brief: one lead story since London | YouTube + Facebook Reel |
| Evening News | 16:30 | 22:00 | news image post | Facebook |

**News image posts (Facebook):** each picks the most important story of the last 48 h that moves
crypto or forex (rate decisions, central-bank speeches and statements, war and geopolitics,
tariffs, regulation, macro data…), scored by topic, how many outlets cover it and how recent it
is, and never one an earlier post used. Gemini writes a big 2–3 line headline and an SEO caption
(fact-checked; numbers only from the data; source named; no hype, no links, ≤5 hashtags,
disclaimer). The 1080×1350 card sits on a story-matched AI background (Cloudflare Workers AI,
free tier; marked "AI illustration"), or an image from `assets/backgrounds/<topic>/`, or a drawn
background. Three posts every day, weekends included: if every fresh story was used, the best
unused one from the last 48 h is posted instead.

**One story per brief:** each market brief picks the day's lead story (scored from headlines,
price moves and upcoming events), researches how it spreads (e.g. a Bitcoin story → Ether and
Solana; a Fed story → EUR/USD, gold, USD/JPY), and charts only those assets, instead of reading
out every market. Each brief only uses news since the previous one.

**Gold outlook:** published after the Asian session has set its range and before London opens,
when gold is most liquid. Levels and bias come from fixed rules on hourly prices (EMA trend,
market structure, previous-day / Asian / weekly highs and lows, equal highs/lows, sweeps, ATR
ranges, dollar and real-yield tilt), and each video first says whether the last outlook played out.

At weekends (forex and gold closed) only the London edition and the three news posts run
(`weekend_sessions`).

**Timing:** GitHub's own schedule can start runs hours late or skip them, so runs are started
on time by a free outside timer (cron-job.org) that presses "Run workflow" through the GitHub
API. GitHub's schedule stays as a backup 17 min later. Whichever runs first makes the video; the
other sees it's already up and stops. A timed run that starts over 3 h late is skipped rather
than posting the wrong edition. Setup: [Outside timer](#outside-timer-cron-joborg) below.

**Manual runs:** Actions → Shorts autopilot → **Run workflow** → pick the edition (`auto` picks
a market edition by the current time, or `gold`) → Run. A manual run **always** makes and
uploads a video, at any time, and never blocks the autopilot: that edition's timed run still
happens. Tick **Count it as today's edition** only if you want the timed run to skip.
Leave **Timed run** unticked (it's for the outside timer). Keep it to ~2 manual uploads a day:
YouTube's API allows about 6 uploads daily in total. **Platforms** (`all` / `youtube` /
`facebook`) limits where it goes, e.g. `facebook` to post a Reel that failed earlier; news
posts (`news_*` editions) only ever go to Facebook.

```
market data + news ─► lead story ─► research ─► script ─► fact-check ─► voiceover ─► graphics ─► render ─► upload
 (see below)          (scoring)     (Gemini)    (Gemini)  (Gemini vs data) (edge-tts)  (charts)    (ffmpeg)  (YouTube API)
gold prices + macro ─► rule-based outlook ─► narration ─► fact-check ─► … same as above
```

**Sources (all free, no keys):**
- **News:** public RSS feeds: CoinDesk, Cointelegraph, The Daily Hodl (full articles), the
  Federal Reserve (policy statements, speeches), and Google News searches for forex, central
  banks, crypto, economic data, gold and Fed rate odds. Paid press releases are filtered out.
- **Economic calendar:** ForexFactory's official weekly calendar export (high-impact events).
- **Crypto prices:** Coinbase public market data (BTC, ETH, SOL, XRP; 7-day hourly).
- **Forex rates:** Frankfurter, daily central-bank reference rates (EUR/USD, GBP/USD, USD/JPY…).
- **Gold:** PAXG (gold-backed token) hourly prices from Kraken/Coinbase, aligned to spot XAU/USD.
- **Macro:** US Treasury yields (10Y, 2Y, 10Y real) and US CPI from the BLS.
- **Fed rate odds:** taken from headlines that quote CME FedWatch (the FedWatch site, Myfxbook and
  forexfactory.com pages block automated access and forbid scraping).

Every scene is a graphic drawn from that data (price chart that draws itself in, market
board, headline card, calendar table), so there's no stock footage to mismatch. The script
may only use numbers from the data, and a second pass checks it against the data before
anything is recorded. Market briefs make no predictions; the gold outlook's bias comes only from
its fixed rules and is worded as conditional ("bearish while below $4,142"). No buy/sell calls;
every video carries a not-financial-advice note. News photos aren't used (copyright).

**Thumbnail / opening frame:** every video opens on a thumbnail design picked from the day's
data, so the first frame (what the feed shows, and what YouTube usually uses as the
thumbnail) is built to stop the scroll:

| Template | Used when | Example |
|---|---|---|
| Big Move | a coin moves 4%+ in 24h or an FX pair 0.8%+ | "−6.2%" + chart + WHAT HAPPENED? |
| Event Day | a high-impact event is due within 12 hours | "CPI DAY" on yellow + WATCH BEFORE 12:30 |
| Split | Bitcoin and the US dollar move opposite ways | green/red split + WHY THE SPLIT? |
| Key Level | BTC/ETH/gold is within 2% of a round number | "1.2% AWAY FROM $100K" + SO CLOSE. |
| Gold Outlook | the gold edition | "BEARISH" + "BELOW $4,142" + 1H/4H chips + KEY LEVELS TODAY |

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
   session `london` with platforms `facebook`.

To pause Facebook, set `facebook.enabled: false` in `config.yaml`.

---

## Settings you'll likely change (`config.yaml`)

| Setting | What it does |
|---|---|
| `channel.niche` / `audience` / `tone` | What the channel is about and how it sounds |
| `voice.name` | Narrator voice. List them: `edge-tts --list-voices` |
| `upload.review_window_hours` | `0` = public immediately. e.g. `6` = sits private for 6 h so you can watch and delete it first, then goes public on its own |
| `channel.display_name` | Brand line at the top of every graphic |
| `market.calendar_impacts` | `[High]` by default; `[High, Medium]` for more events |
| `video.accent` / `video.footer` | Brand colour and the footer line on every graphic |
| Posting times | change all of: the cron-job.org job, `start_utc` in `config.yaml`, and the backup `cron` line in `.github/workflows/autopilot.yml` plus the matching string in its `EDITION:` line and `concurrency.group` |
| Editions | `sessions` (focus text per edition, `platforms`) and `weekend_sessions` in `config.yaml` |
| Facebook | `facebook.enabled`, `facebook.max_hashtags`; news posts: `news_posts.topic_weights`, `fresh_hours`, `disclaimer` |
| News post backgrounds | `images.provider` (`cloudflare` or `none`), `images.steps`; your own images in `assets/backgrounds/<topic>/` |
| Coins / FX pairs | `CRYPTO` and `FX` lists at the top of `autopilot/sources.py` |
| News feeds | `DEFAULT_FEEDS` in `autopilot/sources.py` |
| Background music | Drop royalty-free `.mp3` files into `music/` |

## Run it on your computer

Needs Python 3.10+ and ffmpeg.

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...          # Windows PowerShell: $env:GEMINI_API_KEY="..."
python main.py --no-upload --session london   # makes output/<time>/short.mp4 (+ thumbnail, data)
python main.py --no-upload --session news_morning   # makes output/<time>/post.jpg + caption_fb.txt
python tests/test_offline.py        # graphics + render + mocked Facebook check, no keys needed
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
- edge-tts uses Microsoft's free Edge read-aloud service; if it ever stops working, swap
  `autopilot/voice.py` for a paid TTS (the rest of the pipeline doesn't change).
- The Gemini model name may be retired over time; update `llm.model` if runs start failing with 404.
- The free Gemini tier may use your prompts to improve Google's products.
- Facebook may refuse a custom Reel cover through the API; the Reel then uses its own frame.
- A Reel still processing after 10 minutes is logged as published (so it isn't posted twice);
  check the Page if a run says so.

## Files

```
main.py                 orchestrates one run
config.yaml             all settings
get_token.py            one-time YouTube login
autopilot/sources.py    news feeds, economic calendar, crypto, forex + gold prices, US yields, CPI
autopilot/focus.py      picks each brief's lead story and the assets it moves
autopilot/gold.py       the gold outlook: levels, liquidity, 1h/4h/daily bias, scenarios
autopilot/script.py     research note, grounded script + fact-check against the data (Gemini)
autopilot/slides.py     charts, impact board, headline, calendar + gold outlook graphics
autopilot/thumbnail.py  thumbnail templates + picking one from the data
assets/fonts/           Anton + Space Grotesk (SIL Open Font License)
autopilot/voice.py      narration + word timings (edge-tts)
autopilot/render.py     ffmpeg assembly, chart draw-in, highlighted captions
autopilot/seo.py        search-friendly titles, descriptions, hashtags, tags
autopilot/youtube.py    metadata + upload
autopilot/facebook.py   Facebook Page: Reels, photos, error handling, captions
autopilot/news_post.py  news posts: story pick, headline + caption (Gemini, fact-checked)
autopilot/images.py     news post backgrounds (Cloudflare AI / library / drawn) + the 1080×1350 card
data/history.json       what has been published (YouTube id, Facebook Reel / post id)
.github/workflows/      backup schedule, manual runs, history saving
```

## Outside timer (cron-job.org)

One-time setup, free, about 10 minutes.

1. **GitHub token:** your photo → Settings → Developer settings → Personal access tokens →
   **Fine-grained tokens** → Generate new token. Repository access: **Only select repositories**
   → `yt-shorts-autopilot`. Permissions → Repository → **Actions: Read and write** (nothing
   else). Expiry: 1 year. Copy the token.
2. **cron-job.org:** sign up → Create cronjob:
   - URL: `https://api.github.com/repos/Thimuthu96/yt-shorts-autopilot/actions/workflows/autopilot.yml/dispatches`
   - Schedule: custom, time zone **Asia/Colombo**, every day at **06:00**
   - Advanced → Request method **POST**, headers:
     `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
     `Content-Type: application/json`
   - Body: `{"ref":"main","inputs":{"session":"asia","scheduled":"true"}}`
   - Save, then **Test run**: `204` = it worked (a "Timer · asia" run appears in Actions).
3. Copy the job three times, changing only the time and the session:
   **11:10 → `london`**, **11:45 → `gold`** (set this one to **Monday–Friday**), **18:00 → `newyork`**.
4. Facebook news posts: copy it three more times, **every day**:
   **08:30 → `news_morning`**, **15:00 → `news_midday`**, **22:00 → `news_evening`**.

Keep the token only in cron-job.org (never in the repo or chat). If the jobs start failing
with `401`, the token has expired: make a new one and paste it into all seven jobs. A `422`
means the workflow on `main` doesn't have the `scheduled` input yet (push the latest code).
