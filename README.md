# Shorts Autopilot: Daily Market Brief

Makes and uploads **crypto & forex market briefs** as YouTube Shorts, up to three a day, with
no manual work, running free on GitHub Actions.

| Edition | UTC | Sri Lanka | Focus |
|---|---|---|---|
| Asia Open | 00:30 | 06:00 | moves since the New York close, yen/AUD, the day ahead |
| London Open | 05:40 | 11:10 | the Asian session, euro/pound, the day's big events |
| New York Open | 12:30 | 18:00 | moves since London, the dollar, what's left on the calendar |

Each edition only uses news since the previous brief. At weekends (forex closed) only the
London edition runs (`weekend_sessions` in `config.yaml`). GitHub may start a run a few
minutes late.

**Manual runs:** Actions → Shorts autopilot → **Run workflow** → pick the edition (or `auto`,
which picks by the current time) and tick **force** to make one even if that edition is
already up today.

```
market data + news ─► script ─► fact-check ─► voiceover ─► data graphics ─► render + captions ─► upload with SEO
 (see below)          (Gemini)   (Gemini vs data) (edge-tts) (charts, boards)    (ffmpeg)            (YouTube API)
```

**Sources (all free, no keys):**
- **News:** public RSS feeds, the same set the [World Monitor](https://github.com/koala73/worldmonitor)
  finance dashboard uses: CoinDesk, Cointelegraph, the Federal Reserve, and Google News searches
  for forex, central banks, crypto and economic data.
- **Economic calendar:** ForexFactory's official weekly calendar export (high-impact events).
- **Crypto prices:** Coinbase public market data (BTC, ETH, SOL, XRP; 7-day hourly).
- **Forex rates:** Frankfurter, daily central-bank reference rates (EUR/USD, GBP/USD, USD/JPY…).

Every scene is a graphic drawn from that data (price chart that draws itself in, market
board, headline card, calendar table), so there's no stock footage to mismatch. The script
may only use numbers from the data, and a second pass checks it against the data before
anything is recorded. No predictions or buy/sell calls; every video carries a
not-financial-advice note.

**Thumbnail / opening frame:** every video opens on a thumbnail design picked from the day's
data, so the first frame (what the feed shows, and what YouTube usually uses as the
thumbnail) is built to stop the scroll:

| Template | Used when | Example |
|---|---|---|
| Big Move | a coin moves 4%+ in 24h or an FX pair 0.8%+ | "−6.2%" + chart + WHAT HAPPENED? |
| Event Day | a high-impact event is due within 12 hours | "CPI DAY" on yellow + WATCH BEFORE 12:30 |
| Split | Bitcoin and the US dollar move opposite ways | green/red split + WHY THE SPLIT? |
| Key Level | BTC/ETH is within 2% of a round number | "1.2% AWAY FROM $100K" + SO CLOSE. |

The 2–4 word hook is written by the AI for that day and must be answered in the video; hype
words (moon, buy, sell, will, guaranteed…) are rejected and replaced by the template's
default hook. Each run also saves `thumbnail.jpg`; the system tries to set it as the custom
thumbnail, which YouTube currently allows for Shorts only on some channels (e.g. Partner
Program members, set in Studio on desktop). If refused, the opening frame does the job.

**Running cost:** $0 on the free tiers of Gemini, edge-tts and GitHub Actions.

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
   `GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.
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
| Posting times | the three `cron` lines in `.github/workflows/autopilot.yml` (UTC); if you change one, change the matching time in the `SESSION:` line below it |
| Editions | `sessions` (focus text per edition) and `weekend_sessions` in `config.yaml` |
| Coins / FX pairs | `CRYPTO` and `FX` lists at the top of `autopilot/sources.py` |
| News feeds | `DEFAULT_FEEDS` in `autopilot/sources.py` |
| Background music | Drop royalty-free `.mp3` files into `music/` |

## Run it on your computer

Needs Python 3.10+ and ffmpeg.

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...          # Windows PowerShell: $env:GEMINI_API_KEY="..."
python main.py --no-upload --session london   # makes output/<time>/short.mp4 (+ thumbnail, data)
python tests/test_offline.py        # graphics + render check with sample data, no keys needed
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

## Files

```
main.py                 orchestrates one run
config.yaml             all settings
get_token.py            one-time YouTube login
autopilot/sources.py    news feeds, economic calendar, crypto + forex prices
autopilot/script.py     grounded script + fact-check against the data (Gemini)
autopilot/slides.py     charts, market board, headline + calendar graphics
autopilot/thumbnail.py  thumbnail templates + picking one from the data
assets/fonts/           Anton + Space Grotesk (SIL Open Font License)
autopilot/voice.py      narration + word timings (edge-tts)
autopilot/render.py     ffmpeg assembly, chart draw-in, highlighted captions
autopilot/youtube.py    SEO metadata + upload
data/history.json       what has been uploaded
.github/workflows/      daily schedule
```
