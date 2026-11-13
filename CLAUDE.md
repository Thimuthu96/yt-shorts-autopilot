# CLAUDE.md — Gus Explains (YouTube Shorts + Facebook Reels autopilot)

Context for Claude Code. Read this before changing anything. Design: `docs/superpowers/specs/2026-11-12-gus-explains-design.md`
(§5 look, §11 improvement round); build plan: `docs/superpowers/plans/2026-11-12-gus-explains.md`.

## What this is

**Gus Explains**: a fully automatic, faceless odd-fact cartoon channel. Two Shorts a day (YouTube Short + Facebook
Reel), each 45–60 s, rendered from a code-built Three.js cartoon world (white round-head characters, toon-shaded
sets, a moving camera, actions on words) narrated by edge-tts. Same YouTube channel and Facebook Page as the retired
crypto channel (CryptoFX Daily); its history is archived in `data/archive/crypto-history.json`.
Runs free on **GitHub Actions** (repo `Thimuthu96/yt-shorts-autopilot`, branch `main`; made public for unlimited
Actions minutes).

Owner goals: hands-off, near-zero cost, eventually monetized (YouTube Partner Program). Owner is a developer
(Flutter/Dart background), timezone Asia/Colombo (UTC+5:30). Audience: US first.

## The pipeline (one run = one edition)

```
topics/backlog.yaml → topics.next_topic()   first queued topic whose category differs from the last video's, no two
                                            `levels` in a row, title not a near-copy (Jaccard ≥ 0.6) of a past title
→ writer.write()        Gemini (free tier): research with Google Search grounding (429 / error → ungrounded, logged
                        "grounding unavailable"); VERDICT MYTH → WriteFailed; sources = grounding + cited URLs that pass
                        check_url, < 2 → "not enough sources" → story JSON v2 draft → story.validate against
                        studio/catalog.json (≤ 2 redrafts with the problems) → hook check (rules + Gemini score,
                        1 redraft) → fact_check (1 redraft). WriteFailed → topic marked failed, next topic
                        (gus.max_topics = 3). Gemini unreachable (RuntimeError) stops the run without burning topics
→ timeline.build()      edge-tts per shot (Piper fallback) → voice.wav + timeline.json (word times, mouth envelope);
                        over video.max_seconds → once faster, still over → TooLong → topic failed
→ soundtrack.mix()      music from music/tracks.yaml (by mood, deterministic per slug; Facebook gets only facebook_ok
                        tracks, none → the Reel has no music) at music_db under the voice + synthesized SFX (shot sfx
                        and sfx_mark events) → mix_yt.wav / mix_fb.wav
→ studio.render()       node studio/render.js: headless Chromium (Playwright, SwiftShader) renders every frame of
                        studio/engine/ → video.mp4 (silent); a crash = RenderError naming the frame → exit 1, no upload
→ studio.mux()          H.264 yuv420p 1080x1920 30 fps -g 60, AAC 48 kHz stereo, two-pass loudnorm -14 LUFS
                        → short.mp4 (YouTube mix) + short_fb.mp4 (Facebook mix); thumbnail.jpg = frame 0
→ metadata.build()      title, description (hook line → summary → Sources by site name, no URLs → music attribution → disclosure once →
                        3-5 hashtags, #Shorts last), tags, category 27; reel_caption: no links, no #Shorts
→ main.publish()        youtube.upload + set_thumbnail (refusal ignored) · facebook.publish_reel; one platform's failure
                        never blocks the other (the run exits 1 if any failed)
→ output/<stamp>-<session>/  history_entry.json, backlog_changes.json, story.json → the workflow's Save step merges
                        them into data/history.json, topics/backlog.yaml and stories/published/<slug>.json
```

Backlog refill: after a publish, fewer than `gus.min_backlog` (10) queued topics → `writer.propose_topics` adds
`gus.refill_count` (15). A `--no-upload` run never writes the backlog (failed topics are marked in memory only).

## Editions (all times UTC, every day)

| key | due (`start_utc`) | publishes | Sri Lanka | New York (EST / EDT) | outside timer | backup cron | platforms |
|---|---|---|---|---|---|---|---|
| `short_a` | 16:25 | ~17:00 | ~22:30 | ~12 pm / 1 pm | cron-job.org "Gus Explains · short_a" | `42 16 * * *` | YT Short + FB Reel |
| `short_b` | 22:25 | ~23:00 | ~04:30 | ~6 pm / 7 pm | cron-job.org "Gus Explains · short_b" | `42 22 * * *` | YT Short + FB Reel |

- The run starts ~35 min early: research + render take ~20–30 min (estimate; the repo is public, so the standard
  4-vCPU ubuntu-latest runner; write the measured figure here after the first real run). The Actions log shows
  render.js's progress (`studio: <slug>: frame N/n  Xs` every 150 frames, `rendered N frames in Xs`); a render still
  running after `video.render_timeout_minutes` (45) is killed → RenderError → exit 1 (job timeout 90 min).
- **Gate:** `gus.enabled: false` → timed runs log `gus.enabled is false: …` and exit 0 before anything else; manual
  runs still make (and publish unless `--no-upload`). The owner flips it after the rebrand (README release checklist).
- **Primary timer = cron-job.org** POSTing `workflow_dispatch` `{"ref":"main","inputs":{"session":"short_a","scheduled":"true"}}`
  (fine-grained PAT, this repo only, Actions read/write). `python setup_cronjobs.py` creates / fixes the two jobs
  (`--dry-run` first; `--delete-retired` deletes every "CryptoFX · …" job; `--disable short_a,short_b` = paused).
  GitHub crons are a **backup 17 min later**. **To change a time: change `start_utc`, re-run setup_cronjobs.py, and
  change the cron line and the matching string in the workflow's `EDITION:` env and `concurrency.group`.**
- Both triggers pass `--scheduled`. Timed runs skip when they start > `max_late_minutes` (120) after `start_utc` or
  > 30 min before it, and make each edition once per UTC day per platform
  (`pending = session platforms ∩ enabled − platforms published today for this session`; `--force` overrides, CLI only).
  Concurrency group `timed-<edition>` queues the second trigger, which sees the first's history and stops. If the
  first published only one platform, the second re-renders the saved `stories/published/<slug>.json` for the other.
- **Manual runs** (Actions → Gus Explains autopilot → Run workflow): `session`, `platforms` (all / youtube / facebook),
  `as_edition` (fills today's slot), `story` (render a story file, no writer), `topic` (write about this topic; the
  backlog is untouched), `no_upload`. Own concurrency group `manual-<run id>`; logged `trigger: manual, counts: false`
  unless `as_edition`. Run names: "Timer · short_a", "Backup schedule · 42 16 * * *", "Manual · short_b".
  No topic lock: a manual run from the backlog (no `topic` / `story`) started while a timed run is working reads the
  same backlog and can pick the same queued topic (a topic is only marked `used` by the Save step after publishing),
  so both publish it. Accepted (owner-started, rare): don't start a backlog manual run 16:25–17:10 or 22:25–23:10
  UTC, or give it a `topic`. `topics apply` stays idempotent (the second `used` mark changes nothing).
- **History saving** is safe with parallel runs: the Save step (always) resets to `origin/main`, runs
  `python -m autopilot.history add`, `python -m autopilot.history stories`, `python -m autopilot.topics apply`, commits
  `data/history.json topics/backlog.yaml stories/published/` and retries the push 5×. Run artifacts are kept 7 days.
- Quotas: YouTube 2 uploads/day ≈ 3,200 of 10,000 units; Facebook 2 of 30 API Reels / Page / 24 h.

## Story format v2 (`stories/*.json`; validated by `autopilot/story.py` against `studio/catalog.json`)

```
{slug, title (≤ 60), category, format: explainer|levels, music_mood: curious|tense|upbeat|epic,
 cast: {id: {look: "gus" | {costume, hat, shirt, prop, …}}}, beats: [shot …], sources: [{url, title}] (≥ 2),
 summary (≤ 400), hashtags (3-5)}
shot = {text (2-8 words; the hook shot ≤ 10), say?, set: {type, mood}, keep, remove, props[], chars[], signs[], fx[],
        sfx[], events: [{at_word, do, who?, …, delay?}], cam: {frame + subject [+ look_at] | target/dist/height/angle,
        fov, roll, move, follow, cut}, transition: null|whipL|whipR|whipU|iris|cut, level? (levels: 4-7 levels)}
```
15–40 shots, 130–170 words, at most 2 cuts, every id and name known to the catalog. `at_word` = index into the
shot's `text.split()`; the event fires at that word's start in timeline.json (+ `delay`). Event types: expr, pose,
motion, fx, sign, sfx_mark, shake, fire, launch, impact, fly_off, act (hold, drink, toast, throw, duck, cower, grab,
run_to, point_at, look_at, jump, fall). Framing presets: close, medium, two_shot / ots (need `look_at`), low_hero,
wide, pov. Reference story: `stories/sample/lighthouse.json` (+ `lighthouse.timeline.json`).
After changing an engine registry run `node studio/catalog.js` and commit `studio/catalog.json`.

## Files

```
main.py                   orchestration + CLI: --session short_a|short_b, --platforms, --scheduled, --as-edition, --force,
                          --no-upload, --story PATH, --topic TEXT; make_short, publish, refill, save_backlog
config.yaml               channel, gus (gate, backlog sizes), llm, sessions, voice, video, facebook, upload
autopilot/topics.py       backlog queue, rotation, mark, add (refill), changes / apply (+ workflow CLI)
autopilot/writer.py       Gemini research → story → validate → hook check → fact-check; check_url; propose_topics
autopilot/llm.py          Gemini REST client: generate_json, generate_text (grounding), model fallback
autopilot/story.py        story validator (v1 beats + v2 shots), load_catalog, gus_narration_problems
autopilot/timeline.py     narration per shot → voice.wav + timeline.json; TooLong
autopilot/voice.py        edge-tts with word timings, retries, Piper fallback
autopilot/soundtrack.py   music manifest + pick, synthesized SFX, the mix
autopilot/studio.py       node render bridge, mux (-14 LUFS), frame-0 thumbnail, stills
autopilot/metadata.py     title, YouTube description, Reel caption, tags
autopilot/rules.py        shared narration rules + disclosure helpers (story.py drops the crypto-only rules)
autopilot/youtube.py      upload, set_thumbnail, delete_video; SCOPES (upload) / MANAGE_SCOPES (+ youtube)
autopilot/facebook.py     Graph API v26.0: publish_reel, delete_video, classified errors / retries
autopilot/history.py      data/history.json: guards, titles / slugs / stories, add + stories CLI
autopilot/media.py        ffmpeg / ffprobe helpers
studio/render.js          story + timeline → frames → video.mp4 (--stills t1,t2, --scale); exports its static server
studio/catalog.js         writes studio/catalog.json from the engine registries
studio/branding.js        channel art → branding/*.png through studio/engine/branding.html
studio/engine/            index.html + engine.js (shots, camera handoff, iris, whip blur), world.js (sets, moods, props),
                          cast.js (characters; Gus = GUS_LOOK), camera.js (moves, framing presets, whips), events.js
                          (word-anchored events), actions.js (fire / launch / acts), fx.js, signs.js, captions.js,
                          core.js (toon material, ink outline), branding.html (channel art scenes)
studio/fonts/             Fredoka (OFL): captions, signs, branding
studio/test/              node --test unit tests (npm test); studio/fixtures/ = small stories for them
stories/sample/           the hand-made sample (v2) and v1; stories/published/ = every published story (workflow)
topics/backlog.yaml       the topic queue (status queued | used | failed)
music/tracks.yaml         music manifest (owner fills; music/README.txt)
branding/                 avatar, banner, Facebook profile + cover, channel_description.txt, README.md (owner steps)
scripts/delete_old_content.py   owner-confirmed deletion of the crypto-era videos and posts (dry-run default)
setup_cronjobs.py         cron-job.org jobs from config.yaml sessions
get_token.py              one-time OAuth login → YT_* secrets (--manage-scopes adds the youtube scope)
data/history.json         publish log, committed by the workflow (don't hand-edit casually)
data/archive/crypto-history.json   the crypto channel's history (read by nothing)
.github/workflows/autopilot.yml    backup crons, workflow_dispatch inputs, Save step
.github/actions/setup/action.yml   Node 22 + npm ci + cached Playwright Chromium + Python 3.12 + ffmpeg
tests/                    pytest: story, timeline, soundtrack, studio, topics, writer, metadata, main, workflow,
                          delete_old; tests/test_offline.py renders a cut-down story with every service mocked
```

## Look, voice, video

- Look (spec §5, §11): white round heads with ink outline, dot eyes, stick limbs, costumes by role; Gus = teal
  jumper, mustard knit scarf, round glasses, question-mark curl (same in the branding). Bright toon sets with painted
  textures; moods `day | interior_glow | sunset | night | steel` (faces stay white: ≤ 10 % mood tint). Continuously
  moving camera, framing presets, dutch roll, whip pans with motion blur, `iris` for "next level", rare cuts. FX
  smoke, fire, splinters, sparks, explosion, splash, steam, glow, flash, debris, gunsmoke, beam. Names and numbers
  are in-world signs, never overlays.
- Captions: one word at a time, centred at 58 % of the height, white `#FFFFFF`, ink outline `#17142B` ≈ 10 px + soft
  shadow, ~70 px Fredoka Bold, no box, no highlight colour.
- Voice: edge-tts `en-US-AndrewMultilingualNeural` at `+8%`; each shot retried with waits; still failing → the whole
  video is voiced by Piper `en_US-ryan-high` (estimated word times).
- Thumbnail: custom Shorts thumbnails can't be set via the API for this channel, so frame 0 (the hook shot,
  mid-action) is the thumbnail; `set_thumbnail` is attempted and its refusal ignored; `thumbnail.jpg` is the Reel cover.
- Disclosure line, exactly once in every description / caption: `Narrated with a synthetic voice.`
  `containsSyntheticMedia: false` (code-animated cartoon, stock TTS voice; the reason is in config.yaml).
- No first-person filler, no outro, no spoken sign-off, no "subscribe" in the first sentence. Every claim true and
  sourced (≥ 2 working URLs in the description).

## Secrets (GitHub → Settings → Secrets and variables → Actions)

`GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, `FB_PAGE_ID`, `FB_PAGE_TOKEN`.
The cron-job.org PAT lives only in cron-job.org. Never commit `client_secret.json` (git-ignored). Crypto-era secrets
(`COINGECKO_API_KEY`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`) are unused and can be deleted.

## Running & testing

```bash
npm ci && npx playwright install chromium        # Node 22; ffmpeg on PATH
pip install -r requirements.txt pytest           # Python 3.12
python -m pytest -q                              # every Python test, incl. tests/test_offline.py (no keys / network)
npm test                                         # engine unit tests (node --test studio/test/)
node studio/render.js stories/sample/lighthouse.json --timeline stories/sample/lighthouse.timeline.json --out build/s --stills 1,5
GEMINI_API_KEY=... python main.py --session short_a --no-upload   # one real video → output/<stamp>-short_a/
```
Look at stills / the video after any visual change. A local `--no-upload` run never changes topics/backlog.yaml.

## Decisions & rejected approaches (don't re-propose without a new reason)

- **Niche history:** "Tiny Whys" stock-footage science Shorts (footage never matched the script) → CryptoFX Daily
  crypto news (finance risk, needs fresh data daily) → **Gus Explains** (owner, 2026-11-12), the odd-fact cartoon
  genre that gets millions of views per Short.
- **AI images for the videos:** rejected. Gemini image models are not on the free tier (paid Gemini images: no
  billing, ever); Cloudflare FLUX can't keep characters consistent from shot to shot. Every visual is code.
- **AI video (Veo, Kling, …):** no free tier.
- **Stock footage, reused YouTube / TikTok clips, publisher photos:** copyright claims and reused-content
  demonetization.
- **Copying rules (anti-goals):** the reference's genre, pacing, camera language and look class may be matched; Ricks
  Clips' characters, exact stories / titles and audio may not, and neither may Odd Fortune Studio's design (Lilita One
  font, its cast, stamps, colours). Odd Fortune's *method* (Three.js world + canvas characters + headless Chromium +
  validated story JSON) is the owner's own code and is reused. Topics may overlap in subject, never in angle or
  script. Music: only YouTube Audio Library tracks the owner downloaded.
- **Improvement round (owner review 2026-11-13, spec §11):** sample v1's hook, pace and camera were too weak →
  second-person stakes hooks, shots of 0.6–2.5 s with events on words, an action library, camera v2 (presets, roll,
  whips), look v2 (bigger characters, warm day, moonlit night, white faces). The owner approved sample v2.
- **No human review:** the validator, hook check, fact-check and ≥ 2 sources stand in for it (owner accepted the risk).
- **Monetization policy:** YouTube's inauthentic-content rule targets templated mass production; keep each video's
  topic, sets, cast and shots different (category rotation, no two `levels` in a row), two a day, no hype.
- **Deleting old content** is a separate, owner-confirmed step (`scripts/delete_old_content.py`); the builder never
  runs `--confirm`. `--before` defaults to `gus.cutover` (2026-11-13, config.yaml), never today; every `video_id` /
  `fb_reel_id` in data/history.json (Gus uploads) is always excluded; `--max` (150) caps YouTube deletes per run
  (50 units each ≈ 7,500 units); a Facebook "does not exist" answer counts as already gone. Finish it before
  `gus.enabled` is turned on.

## Gotchas we hit (carried over)

- edge-tts 403 "Invalid response status" (2026-10-12): Microsoft refused GitHub's runners for a while → retries with
  waits + the Piper fallback voice.
- cron-job.org `401` = the PAT expired (1-year expiry) → a new token into both jobs (`setup_cronjobs.py` re-patches).
  `422` = the workflow on `main` lacks the `scheduled` input, or a job dispatches a session the workflow doesn't offer
  (an old CryptoFX job: delete those with `--delete-retired`).
- The workflow commits history after each run → **always `git pull` (rebase on origin/main) before pushing.**
- Run times in the Actions UI are in the browser's time zone (GMT+5:30), not UTC.
- GitHub scheduled runs can start hours late or never (hence the outside timer); schedules pause after 60 days of repo
  inactivity. A green 1-minute run = a skip: read its last log line.
- `.github/` and `.gitignore` are hidden: drag-and-drop uploads skip them; use git.
- A cron expression in YAML must stay on one line inside `${{ }}`.
- A GitHub billing lock once blocked all jobs ("account is locked due to a billing issue").
- The Facebook Page token dies on a password change or a lost Page role (error 190); the Meta app must be in Live
  mode or posts are hidden.
- Un-audited YouTube API projects upload as private: check Studio if uploads aren't public (README → API audit).

## Release checklist

The owner's ordered release steps are in README → "Release checklist". Nothing publishes on a timer until the owner
sets `gus.enabled: true`.

## Conventions for changes

- Keep everything free-tier; no new paid APIs without asking the owner. Never enable billing on the AI Studio project.
- Every fact true and sourced.
- Run `python -m pytest -q` and `npm test` after any change; look at stills after engine changes.
- Prefer small, explicit `log(...)` lines — the Actions log is the only monitoring.
- Outward actions (cron-job.org, repo visibility, deletions, the gate) are the owner's.
- Owner applies changes via git (Mac or Windows); give exact file paths when handing over changes.
