# Shorts Autopilot

Makes and uploads one YouTube Short a day with no manual work, running free on GitHub Actions.

```
pick topic ─► write script ─► fact-check ─► voiceover ─► stock footage ─► render with captions ─► upload with SEO
 (Gemini)      (Gemini)        (Gemini)     (edge-tts)     (Pixabay)         (ffmpeg)              (YouTube API)
```

**Default niche:** everyday science — the surprising "why" behind ordinary things (why ice is
slippery, why onions make you cry). It's evergreen, has plenty of matching stock footage, avoids
medical/financial advice, and curiosity questions hold attention well in Shorts. Change it in
`config.yaml` → `channel.niche`.

**Running cost:** $0 on the free tiers of Gemini, Pixabay, edge-tts and GitHub Actions.

---

## Setup (about 30–40 minutes, once)

### 1. Get the two content API keys

| Secret name | Where |
|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey → **Create API key** |
| `PIXABAY_API_KEY` | Create a free account at https://pixabay.com, then open https://pixabay.com/api/docs/ — your key is shown under **Parameters → key** |

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
2. **Settings → Secrets and variables → Actions → New repository secret** — add all five:
   `GEMINI_API_KEY`, `PIXABAY_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.
3. **Actions** tab → enable workflows → **Shorts autopilot** → **Run workflow** to test now.
   After that it runs by itself every day at 12:55 Sri Lanka time.

Each run's video, script and metadata are kept for 7 days under the run's **Artifacts**,
and `data/history.json` logs every upload so topics and footage never repeat.
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
| `upload.videos_per_run` | Videos per day (keep at 1–2) |
| Posting time | `cron` line in `.github/workflows/autopilot.yml` (UTC) |
| Extra footage source | Add a `PEXELS_API_KEY` secret if you have one; it's used as a fallback |
| Background music | Drop royalty-free `.mp3` files into `music/` |

## Run it on your computer

Needs Python 3.10+ and ffmpeg.

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=... PIXABAY_API_KEY=...        # Windows: set GEMINI_API_KEY=...
python main.py --no-upload                          # makes output/<time>/short.mp4
python main.py --topic "Why do cats purr?" --no-upload
python tests/test_render.py                         # offline render check, no keys needed
```

---

## Staying eligible for monetization

YouTube's **inauthentic content** policy demonetizes channels whose videos look mass-produced
or templated. Faceless and AI-assisted channels are allowed; low-effort repetition isn't.

What the system already does to stay on the right side:
- Every script goes through a separate fact-check pass; videos with a false premise are thrown away.
- Hooks and endings rotate between styles, so videos don't all open the same way.
- Topics and footage are never reused (tracked in `data/history.json`).
- One video a day by default, not a flood.

What helps most from your side, even if it's 10 minutes a week:
- Watch a few uploads and delete weak ones (or use `review_window_hours`).
- Reply to comments, and pin a comment with an extra fact.
- Narrow the niche to something with a distinct point of view; a specific channel identity
  reads as more original than a generic one.

## Known limits

- Shorts thumbnails can't be set through the API; YouTube picks a frame.
- edge-tts uses Microsoft's free Edge read-aloud service; if it ever stops working, swap
  `autopilot/voice.py` for a paid TTS (the rest of the pipeline doesn't change).
- The Gemini model name may be retired over time; update `llm.model` if runs start failing with 404.
- The free Gemini tier may use your prompts to improve Google's products.

## Files

```
main.py                 orchestrates one run
config.yaml             all settings
get_token.py            one-time YouTube login
autopilot/content.py    topic, script, fact-check (Gemini)
autopilot/voice.py      narration + word timings (edge-tts)
autopilot/footage.py    stock clips (Pixabay, optional Pexels)
autopilot/render.py     ffmpeg assembly + highlighted captions
autopilot/youtube.py    SEO metadata + upload
data/history.json       what has been uploaded
.github/workflows/      daily schedule
```
