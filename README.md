# Gus Explains: odd-fact cartoon Shorts on autopilot

Makes and publishes **two odd-fact cartoon Shorts a day** (YouTube Short + Facebook Reel) with no manual work,
running free on GitHub Actions. Each video is a 45–60 s cartoon: Gus and his round-headed cast act out a surprising,
true story in a code-built 3D world (a ship deck, a lighthouse coast, a castle yard, a lab…), with a moving camera,
actions on the words, one-word captions, music and sound effects. Every fact is researched with Google Search and
checked; the sources go in the description.

| Edition | Run starts (UTC) | Publishes (UTC) | Sri Lanka | New York | Where |
|---|---|---|---|---|---|
| Short A (`short_a`) | 16:25 daily | ~17:00 | ~22:30 | ~12 pm (1 pm in summer) | YouTube Short + Facebook Reel |
| Short B (`short_b`) | 22:25 daily | ~23:00 | ~04:30 | ~6 pm (7 pm in summer) | YouTube Short + Facebook Reel |

**How a video is made:** the next topic in `topics/backlog.yaml` (Gemini refills it) → Gemini researches it with
Google Search and writes a *story* (a shot list: what each shot says, its set, characters, props, actions on words,
camera) → a validator checks every name against the engine's catalog, a hook check and a fact-check run (bad drafts
are redrafted, then the topic is skipped) → edge-tts narrates it with word timings → a Three.js engine renders every
frame in headless Chromium → ffmpeg adds voice, music and sound effects (-14 LUFS) → upload to YouTube and Facebook
→ `data/history.json`.

**Timing:** GitHub's own schedule can start runs hours late or skip them, so a free outside timer (cron-job.org)
presses "Run workflow" through the GitHub API ~35 min before each slot (rendering takes ~20–30 min). GitHub's
schedule is a backup 17 min later; whichever runs first makes the video, the other sees it's up and stops. A timed
run that starts over 2 h late is skipped.

**The switch:** while `gus.enabled` is `false` in `config.yaml`, timed runs only log and stop. Manual runs work
anyway (tick **no_upload** to make a video without publishing it).

**Manual runs:** Actions → **Gus Explains autopilot** → **Run workflow**: pick `session`; optional `platforms`
(all / youtube / facebook), `as_edition` (count it as today's edition, so the timed run skips), `story` (render a
story file such as `stories/sample/lighthouse.json` instead of writing one), `topic` (write about your own topic),
`no_upload`. Leave `scheduled` unticked (it's for the outside timer). The video, story, timeline and metadata are
kept 7 days under the run's **Artifacts**.

## Release checklist (owner, in this order)

1. Merge the pause branch and run `python setup_cronjobs.py --disable …` so nothing crypto publishes (Task 1). ✔
2. Make the repository public (Settings → General → Danger Zone → Change visibility) for unlimited Actions minutes,
   after reading the safety audit (Task 2).
3. Approve the sample look (Task 8). ✔ (sample v2, 2026-11-13)
4. Merge the Gus branch (`ft/gus-explains`) into `main` (`gus.enabled` is still `false`).
5. Add music: download tracks from YouTube Studio → Audio Library into `music/` and list them in `music/tracks.yaml`
   ([Music](#music)). Optional: with no tracks the videos are voice + sound effects.
6. Rebrand by hand with `branding/` (steps in `branding/README.md`): channel name, handle, picture, banner,
   description; Facebook Page name, username, picture, cover, About.
7. Optional: delete the old crypto content — `python scripts/delete_old_content.py` (dry run, writes
   `output/deletion-plan.json`), read the plan, then the same command with `--confirm` ([Old content](#deleting-the-old-crypto-content)).
8. `python setup_cronjobs.py --dry-run`, then `python setup_cronjobs.py` (creates the two Gus jobs), then
   `python setup_cronjobs.py --delete-retired` (deletes every "CryptoFX · …" job).
9. One manual run with `no_upload` (Actions → Run workflow → session `short_a`, tick `no_upload`; it uses the
   `GEMINI_API_KEY` secret): download the artifact and watch `short.mp4`, read `metadata.json` and the sources. Do this
   real `--no-upload` run with GEMINI_API_KEY and review it before setting `gus.enabled` true.
10. Set `gus.enabled: true` in `config.yaml`, `git pull`, commit, push.
11. Watch the first day's two runs (Actions → "Timer · short_a" ~16:25 UTC and "Timer · short_b" ~22:25 UTC): each
    should end with the YouTube and Facebook ids in the log and a "Log published edition" commit.

## Setup (once)

### 1. Tools (only to run things on your computer)

- **Node 22** (https://nodejs.org) — the cartoon engine. Then in this folder: `npm ci` and
  `npx playwright install chromium` (the headless browser the engine renders in).
- **Python 3.12** and `pip install -r requirements.txt` (`pytest` too for the tests).
- **ffmpeg** on PATH (`brew install ffmpeg` on Mac; `winget install ffmpeg` on Windows).

GitHub Actions installs all of this by itself (`.github/actions/setup/action.yml`, Chromium cached).

### 2. Gemini API key

`GEMINI_API_KEY`: https://aistudio.google.com/apikey → **Create API key**. Free tier: text + Google Search grounding.
**Never enable billing** on that AI Studio project (it ends the free tier).

### 3. YouTube upload access

1. Google Cloud console (project already set up for this channel) → **APIs & Services → Library** → **YouTube Data
   API v3** is enabled; the **OAuth consent screen** must be **In production** (in *Testing* the login expires every
   7 days).
2. **Credentials → OAuth client ID** (type **Desktop app**) → **Download JSON** → save it next to `get_token.py` as
   `client_secret.json` (git-ignored, never commit it).
3. On your computer: `pip install google-auth-oauthlib` then `python get_token.py`. Sign in with the channel's
   account; it prints `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.
   (`python get_token.py --manage-scopes` also asks for the `youtube` scope; only the deletion script needs it, and
   the daily uploads work with either token.)
4. **API audit:** un-audited API projects upload as **private**. Submit the YouTube API Services audit form
   (https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits) describing an internal tool that
   uploads to your own channel; until then, make the videos public in Studio by hand.

### 4. Facebook Page

Needs the Page admin's account. Free.

1. https://developers.facebook.com/apps → **Create app** → use case **Manage everything on your Page** → permissions
   `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` (Standard Access is enough for your own Page).
2. **Switch the app to Live mode** (App settings → Basic → privacy policy URL, then the toggle). Posts from an app
   in Development mode are hidden from the public.
3. **Never-expiring Page token:** Graph API Explorer → your app → **Get User Access Token** with the three
   permissions → make it long-lived:
   `https://graph.facebook.com/v26.0/oauth/access_token?grant_type=fb_exchange_token&client_id=<APP_ID>&client_secret=<APP_SECRET>&fb_exchange_token=<USER_TOKEN>`
   → `https://graph.facebook.com/v26.0/me/accounts?access_token=<LONG_LIVED_USER_TOKEN>` → your Page's `id` is
   **`FB_PAGE_ID`**, its `access_token` is **`FB_PAGE_TOKEN`**. Check it in the Access Token Debugger:
   **Expires: Never**. It stops working if you change your Facebook password or lose your Page role (a run then says
   "Facebook error 190 … regenerate FB_PAGE_TOKEN").

To pause Facebook, set `facebook.enabled: false` in `config.yaml`.

### 5. GitHub secrets

Settings → Secrets and variables → Actions → **New repository secret**: `GEMINI_API_KEY`, `YT_CLIENT_ID`,
`YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, `FB_PAGE_ID`, `FB_PAGE_TOKEN`. The crypto-era `COINGECKO_API_KEY`,
`CF_ACCOUNT_ID` and `CF_API_TOKEN` are no longer used and can be deleted.

### 6. Outside timer (cron-job.org)

**Shortcut:** `python setup_cronjobs.py` creates or fixes the two jobs ("Gus Explains · short_a" at 16:25 UTC and
"Gus Explains · short_b" at 22:25 UTC, every day) from `config.yaml`. It asks for a cron-job.org API key
(Settings → API) and the GitHub token below, with hidden input, and stores neither. `--dry-run` shows the plan without
any key; `--delete-retired` deletes every old "CryptoFX · …" job; `--disable short_a,short_b` makes them paused.

By hand:
1. **GitHub token:** your photo → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** →
   Generate. Repository access: **Only select repositories** → this repo. Permissions → Repository → **Actions: Read
   and write** (nothing else). Expiry: 1 year.
2. **cron-job.org** → Create cronjob: URL
   `https://api.github.com/repos/Thimuthu96/yt-shorts-autopilot/actions/workflows/autopilot.yml/dispatches`, schedule
   every day **16:25**, time zone **UTC**; Advanced → method **POST**, headers `Authorization: Bearer <token>`,
   `Accept: application/vnd.github+json`, `Content-Type: application/json`; body
   `{"ref":"main","inputs":{"session":"short_a","scheduled":"true"}}`. **Test run** → `204` = a "Timer · short_a"
   run appears in Actions (it stops at once while `gus.enabled` is false).
3. Copy it for **22:25 → `short_b`**. Delete every old CryptoFX job.

Keep the token only in cron-job.org. `401` = the token expired: make a new one and run `setup_cronjobs.py` again.
`422` = the workflow on `main` doesn't accept that input (an old CryptoFX job, or the latest code isn't pushed).

## Music

1. YouTube Studio → **Audio Library** → download tracks, preferring **No attribution required**.
2. Put each `.mp3` in `music/` and add an entry to `music/tracks.yaml`:
   ```yaml
   - file: "Track Name.mp3"
     title: "Track Name"
     artist: "Artist"
     attribution: null          # or the exact attribution text the library asks for (it goes in the description)
     facebook_ok: false         # true only if the licence also covers Facebook
     moods: [curious, tense]    # curious | tense | upbeat | epic
   ```
Each video picks a track matching its story's mood, the same one every time for that story, and mixes it 20 dB
under the voice. Facebook Reels only use `facebook_ok: true` tracks; with none, the Reel has voice + sound effects.

## Branding

`branding/` holds the channel art rendered by the engine (`node studio/branding.js`): YouTube profile picture
(800×800) and banner (2560×1440), Facebook profile (720×720) and cover (1640×624), and `channel_description.txt`.
How to apply them, click by click: `branding/README.md`.

## Deleting the old crypto content

Irreversible, and only when you decide to. `scripts/delete_old_content.py` (needs the `--manage-scopes` YouTube
token in `YT_REFRESH_TOKEN` and the Facebook secrets in your shell):
```bash
python scripts/delete_old_content.py                 # dry run: lists everything before today, writes output/deletion-plan.json
python scripts/delete_old_content.py --youtube       # only YouTube (or --facebook); --before YYYY-MM-DD to choose the date
python scripts/delete_old_content.py --confirm       # deletes exactly the planned items (same options as the dry run)
```
`--confirm` lists again first and refuses if anything new appeared ("plan out of date"); every id goes to
`output/deletion-log.json`; it stops at the first permission or quota error with what to fix. YouTube allows about
200 deletions a day (quota); run `--confirm` again the next day for the rest.

## Settings you'll likely change (`config.yaml`)

| Setting | What it does |
|---|---|
| `gus.enabled` | the switch for timed runs |
| `gus.min_backlog` / `refill_count` / `max_topics` | topic queue refill and topics tried per run |
| `voice.name` / `rate` / `fallback` | narrator (`edge-tts --list-voices`), speed, the Piper voice used when edge-tts is down |
| `video.music_db` | music level under the voice |
| `upload.review_window_hours` | `0` = public at once; e.g. `6` = private for 6 h so you can check it, then public |
| `facebook.enabled` | Facebook on / off |
| Posting times | change all of: `start_utc`, the cron-job.org job (`setup_cronjobs.py`), the backup `cron` line in `.github/workflows/autopilot.yml` and the matching string in its `EDITION:` line and `concurrency.group` |
| Topics | add your own to `topics/backlog.yaml` (status `queued`), or use the `topic` input of a manual run |

## Run it on your computer

```bash
export GEMINI_API_KEY=...                            # Windows PowerShell: $env:GEMINI_API_KEY="..."
python main.py --session short_a --no-upload         # one real video → output/<time>-short_a/short.mp4
python main.py --session short_a --topic "Why ship windows are round" --no-upload
python main.py --session short_a --story stories/sample/lighthouse.json --no-upload   # no Gemini needed
python -m pytest -q && npm test                      # all tests, no keys or network
```
A `--no-upload` run never changes `topics/backlog.yaml`. A full 1080×1920 render takes several minutes.

## Staying eligible for monetization

YouTube's **inauthentic content** policy demonetizes channels whose videos look mass-produced. What the system does:
every video is a different topic, script, set, cast and shot list (category rotation, no two "Levels of" in a row);
the visuals are our own animation, not reused clips; facts are fact-checked and sourced; two a day, no hype. What
helps from your side: watch a few uploads a week, delete weak ones, reply to comments.

## Known limits

- Custom Shorts thumbnails can't be set through the API for this channel; the first frame (the hook shot) is the
  thumbnail and the Reel cover.
- Characters act with poses, expressions, actions and lip-sync, not hand-keyed animation.
- edge-tts is Microsoft's free read-aloud service; when it refuses GitHub's runner the video is voiced by a free
  local Piper voice (the log says so).
- Gemini model names get retired; update `llm.model` / `fallback_models` if runs fail with 404. The free tier may use
  prompts to improve Google's products.
- A Reel still processing after 10 minutes is logged as published (so it's never posted twice); check the Page if a
  run says so.

## Files

See CLAUDE.md → "Files". In short: `main.py` (one run), `config.yaml`, `autopilot/` (Python pipeline), `studio/`
(the cartoon engine), `topics/backlog.yaml`, `music/`, `branding/`, `scripts/delete_old_content.py`,
`setup_cronjobs.py`, `get_token.py`, `data/history.json`, `.github/workflows/autopilot.yml`.
