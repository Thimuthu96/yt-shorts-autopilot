# CLAUDE.md — CryptoFX Daily (YouTube Shorts autopilot)

Context for Claude Code. Read this before changing anything.

## What this is

A fully automated faceless crypto-education channel, **CryptoFX Daily** (@CryptoFXDaily202), on the
**crypto-only weekly slate** (crypto pivot, epic 5; weekly-slate.md): two standalone Shorts a day (YouTube
Short + **Facebook Reel**), Crypto Basics (Wed) and a trading lesson (Thu) as YouTube 16:9 + Facebook 9:16
videos, triggered "why crypto moved" videos and a Saturday recap (YouTube only), evergreen top-ups for the
weekly floor, plus **3 Facebook-only crypto news image posts a day**. The market briefs (asia / london /
newyork) and the gold outlook are retired.
Runs free on **GitHub Actions** (repo `Thimuthu96/yt-shorts-autopilot`, branch `main`).

Owner goals: hands-off, near-zero cost, eventually monetized (YouTube Partner Program).
Owner is a developer (Flutter/Dart background), timezone Asia/Colombo (UTC+5:30).

## The pipeline (one run = one edition)

```
shared by every video format:
  → script.validate-style rules: rules.narration_problems()  no first person, targets, 10x, buy/sell calls,
                        dates/clock times/UTC → draft retried; failures stop the edition (exit 1)
  → main.narrate() → voice.synthesize()  edge-tts narration per scene + word timings; A/B voice
                        (main.ab_voice, logged as "voice"), pauses after key numbers (voice.paced), over-limit → faster
  → render.build_video()  ffmpeg: segments + animations + word-highlight captions + audio mix
  → publish per platform, one failure never blocks the other; Facebook follows the content (main.CONTENT_PLATFORMS):
       Shorts → main.publish(): youtube.upload() + facebook.publish_reel(); Basics / lessons → YouTube 16:9 +
       facebook.publish_video() 9:16; triggered / recap → YouTube only; news posts → facebook.publish_photo()
  → history.json        logs the ids (dedupe, once-per-slot guard, the slate budget)
  slate budget (autopilot/slate.py, config `slate`): ≤ 3 YouTube uploads per UTC day (timed Shorts skip at 3; Short B
                        yields to a triggered video published / due that day on Wed/Thu or on a day with a long video;
                        the trigger poll holds a would-be 4th trigger to 00:00 UTC next day: triggers.hold); 3-4 long
                        videos (basics, lesson, triggered, recap) per ISO week: main.floor_top_up runs the evergreen
                        top-up when a timed recap skips (Saturday) or at topup_sun (Sun 15:00) while the week has < 3;
                        a counting long upload that would be the 5th is refused ("Weekly cap", exit 0)
  news image post (kind: post, Facebook only):
  → news_post.pick_story()  48 h of news (all feeds incl. geopolitics + regulation) filtered to crypto
                            stories (is_crypto: crypto named in the headline or its lead, never only the
                            body; CAP-9), then topic weight + coverage + recency, skips stories earlier FB
                            posts used; no crypto story → RuntimeError, no post (exit 1)
  → news_post.write_post()  Gemini: kicker, 2-3 line headline, subline, caption, image prompt →
                            script.fact_check() → number check vs facts → deterministic fallback;
                            rules.narration_problems() on kicker/headline/subline/caption: a failing
                            Gemini post → fallback_post, a failing fallback → post stops (exit 1)
  → images.background()     Cloudflare FLUX.1 schnell → assets/backgrounds/<topic>/ → drawn
  → images.render_card()    post.jpg 1080x1350; news_post.caption() → caption_fb.txt
  → facebook.publish_photo()  POST /{page}/photos
  trading lesson (kind: lesson, make_lesson_edition() + publish_lesson()):
  → lessons.validate()      lessons/curriculum.yaml + glossary.yaml; problems → logged, exit 1
  → lessons.pick()          counting run, slot already recorded `episode: X` → X again (missing platforms
                            only, recorded examples preferred, can't be re-made → exit 1);
                            else first unpublished entry whose detector finds a clean example in
                            lesson_data.fetch_history() (held entries logged, never stored); none → "nothing
                            to publish in this slot", exit 0
  → make_lesson()           narration (lesson_script) → voice → 16:9 + 9:16 renders, thumbnail, chapters,
                            lesson_meta metadata (examples found by the hold check are passed through)
  → publish_lesson(pending) youtube.upload_lesson() 16:9 (public on upload, or private + publishAt with review_window_hours; playlists
                            only with lessons.playlists: true) · facebook.publish_video() 9:16
                            (/{page}/videos); one failure never blocks the other
  → history.json            kind: lesson, episode, track, examples (asset/timeframe/start/end), video_id,
                            fb_video_id
  Crypto Basics (kind: basics, make_basics() + publish_basics(); switch: basics.enabled, on since 5.7):
  → main.basics_topic()     basics/topics.yaml (list order = queue): basics.validate_topics (problems → logged,
                            exit 1) → basics.pick (first `approved: true` topic no uploaded kind: basics entry has
                            as its `topic`); none → "Basics: nothing to publish", exit 0 (ships 4 drafts, none
                            approved). tests/basics/sample_topic.yaml is the tests' tracer topic only
  → basics.scene_plan()     hook → one scene per point → recap; a point's diagram is validated (diagrams.validate,
                            problems → ValueError) and its parts' naming order goes into the scene's `covers`
  → basics.write_script()   Gemini narrates only the approved points (hook → one scene per point → recap), naming
                            each diagram part (its first `say` alias) in order, in the sentence where it comes up;
                            every scene narrated, basics.min/max_words (600-900 ≈ 4-6 min), rules.narration_problems,
                            the fixed `basics.subscribe_ask` (added by code at the end of point_1, the first payoff)
                            exactly once and nowhere else; 3 failures → exit 1. Then script.fact_check against
                            basics.facts(topic) (question, summary, approved points; the ask not sent) + every spoken
                            digit-number must be in those facts: reject / revised draft with problems / unknown
                            number → "Basics fact-check failed", exit 1 at once (no retry)
  → main.narrate()          A/B voice (main.ab_voice, pauses=True, logged as "voice")
  → basics.render_slides()  title / concept / recap slides with a CRYPTO BASICS chip, lesson_slides LANDSCAPE +
                            PORTRAIT; a point with a diagram = "KEY IDEA n OF m" + term + the drawn diagram
                            (diagrams.draw) with base + diff-crop layers (diagrams.step_layers) → reveal.time_steps
                            (each part fades in on the sentence naming it; unnamed → the sentence after its
                            predecessor's, logged "(fallback)", the edition continues) → render.build_video in both
                            shapes; a point without one = the text concept slide
  → packaging (packaging.md) basics.packaging_problems before narration (title = the question verbatim:
                            rules.title_problems, ≤ 100 chars; thumbnail text 1-3 words) → "Basics packaging", exit 1;
                            basics.render_thumbnail 1280x720 (the 1-3 words + the first point's diagram, notes dropped,
                            stacked in a tall column; doesn't fit → a drawn coin badge); basics.chapters (lesson_meta's
                            timing rule, Intro / terms / Recap); basics.metadata: summary → key ideas → chapters (≥ 3)
                            → disclosure once → ≤ 5 hashtags; Facebook: summary → key ideas → disclosure once → hashtags
  → publish_basics(pending) youtube.upload_lesson() 16:9 (no playlists, basics.review_window_hours) ·
                            facebook.publish_video() 9:16 (basics.fb_published); one failure never blocks the other
  → history.json            kind: basics, topic, title, video_id, fb_video_id, seconds, voice
  evergreen top-up (kind: evergreen, `--session evergreen --slot <session>`, CAP-6; the merged lesson --slot path):
                            make_evergreen → the next ready Basics episode (basics.stock, ready package only) into
                            today's slot, else make_lesson_edition under the slot's key (only with lessons.enabled);
                            once per slot/day (topup guard), recorded under the slot (trigger topup, evergreen: true);
                            timed runs skip while evergreen.enabled is false (on since 5.7); main.floor_top_up calls it
  evergreen stock: `--session basics --prepare <id|next>` narrates an approved, unpublished topic exactly as the
                            edition does and writes basics/ready/<id>.yaml (for a PR; never uploads); the edition uses
                            a picked topic's package as it is (basics.validate_ready re-checks it, no LLM call; invalid
                            → exit 1); `--session basics --stock` = ready, unpublished episodes
  → Shorts material         autopilot/material.py: built + validated before rendering (≥ 5 segments: overview + one
                            per point; problems → "Basics Shorts material", exit 1); after a publish written to
                            data/material/basics-<topic>.json (a later run merges a missed platform's id) + a copy
                            output/<stamp>/material.json, which the workflow's Save history step merges back after
                            its reset (`python -m autopilot.material add`) and commits with data/history.json
  trigger engine (CAP-4; switch: triggers.enabled, on since 5.7; autopilot/triggers.py, no LLM):
  → triggers.yml poll       every 30 min (13,43 * * * *, light install): `python -m autopilot.triggers check` = Coinbase
                            prices + crypto/regulation news + CoinGecko overview → evaluate: rule 1 BTC/ETH ±5% 24 h;
                            2 total cap ±4%; 3 top-50 coin ±15% only with a crypto headline naming it (coin gate);
                            4 focus.major_story (ETF decision / regulation / hack / upgrade, ≤ 6 h old) → record in
                            data/triggers.json (only the poll writes it): same cause pending → nothing; ≤ 2 per ISO week,
                            ≥ 48 h apart (published kind: triggered history by trigger_id + pending; simulated never
                            count), fired 03:00-11:00 UTC → due 12:00, not published within 3 h of due → dropped (logged)
                            → due + enabled → marked dispatched, commit, `gh workflow run autopilot.yml session=triggered
                            trigger=<id> scheduled=true`; disabled → logs only
  triggered video (kind: triggered, `--session triggered --trigger <id|fixture>`, YouTube 16:9 only):
  → triggered.py            packaging first (title "Why Bitcoin Just Dropped 7% (What Actually Happened)" from the data,
                            rules.title_problems; thumbnail "WHY -7%?" → "Triggered packaging", exit 1); scene plan move →
                            cause → coins (flow diagram cause → 1-3 coins, step reveal) → context → watch → recap;
                            420-600 words, subscribe ask after the cause, narration rules (3 attempts), fact_check +
                            number check (spoken number must round from fetched data) → stop; A/B voice; thumbnail
                            1280x720 (badge, arrow, %); description: cause, coins, headlines, Coinbase + "Data provided
                            by CoinGecko" once when used, disclosure once → publish_triggered (upload_lesson, review 2 h)
                            → history kind triggered + trigger_id (an already-published trigger is never re-made);
                            timed runs check triggers.enabled and the trigger's due time (not start_utc)
  Saturday recap (kind: recap, Sat 15:00, YouTube 16:9 only; switch: recap.enabled, on since 5.7; autopilot/recap.py):
                            skipped (logged) when a triggered video published this ISO week; else the 2-3 biggest 7-day
                            moves (Coinbase + CoinGecko top 50) and their headline causes, 560-750 words, ask after
                            move_1, fact-checked; title "This Week in Crypto: What Moved and Why", mini-board thumbnail
  market Shorts material    triggered / recap publishes write data/material/<kind>-<id>.json with a `market` section
                            (fetched numbers + source, data_source, credit, series, causes, ≥ 2 hooks; no segment minimum);
                            pulse material (kind pulse, autopilot/pulse.py, epic-shorts-reach 6.1, no LLM) is built from
                            the day's fetched data alone: Coinbase + crypto news + CoinGecko overview → lead = biggest
                            |24 h| of BTC / ETH / the first coin through rule 3's coin gate → its cause + headlines →
                            data/material/pulse-<date>-<slot>.json (no source video: youtube_id = a related long video or
                            null; `lead` + `headlines` added); |lead| < pulse.quiet_move_pct (1.5) with no story → none
                            ("quiet market"); shorts.pick_market serves only triggered / recap unless kinds=("pulse",)
  standalone Shorts (kind: short, short_a 13:00 / short_b 23:00 UTC + short_p (market pulse, untimed until 6.5), YT Short +
  FB Reel; switch: shorts.enabled, on since 5.7; autopilot/shorts.py + lesson_material.py; main.make_short → main.publish):
  → pulse-first (epic-shorts-reach 6.2; main.pulse_first = session `pulse: true` and (pulse.enabled or `gate: pulse`):
                            short_p always when it runs, short_a only once pulse.enabled is true (6.6); short_b never):
                            main.make_pulse → shorts.latest_long (newest counting basics / lesson / triggered / recap
                            upload whose publish time has passed = the related video, none → no link line) → pulse.make
                            (fetch + build + data/material/pulse-<date>-<slot>.json; a same date + slot file is merged)
                            → shorts.pick_pulse: a pulse Short (short_kind pulse) from that fresh material only (never an
                            earlier day's or slot's), through write_market (today's-data wording) / render_market_slides
                            (MARKET PULSE chip), title = the pulse hook ("Why did Ethereum just fall 5%?"); a quiet
                            market / no price data / fetch error / every hook used or too close → a concept Short (reason
                            logged), else the slot skips + low-stock warning (exit 0). The material copy goes to
                            output/<stamp>/material.json (Save history merges it). `gate: <section>` (any session): timed
                            runs log "<section>.enabled is false…" and exit 0 before any fetch; manual runs make + publish
  → shorts.pick             daily mix: a market Short when a triggered / recap material < 3 days old (not future) has an
                            unused hook candidate (≤ 2 per source, distinct candidates, hook text never re-used), else a
                            concept Short (shorts.pick_concept, E6-3; lesson material rebuilt from history's BTC / ETH
                            lessons + curriculum + glossary): round-robin over the Basics / Lesson materials (the one whose
                            last Short is oldest first, never-used first, ties by publish time; ≤ 2 Shorts per source in
                            7 days, relaxed only when no other source has an eligible segment, logged) + a hard 7-day
                            topic cooldown (shorts.topic: lowercase, "(…)" / "crypto" / "what is" / stop-words dropped,
                            plurals singular, swing high / low → "swing point"; a segment's term or first hook equal to,
                            containing or contained in a concept Short's topic of the last 7 days is refused, logged; an
                            entry without `topic` → its segment's term, else title, else hook; pulse / market Shorts never
                            block); pick_pulse's concept fallback uses the same rules; nothing eligible → slot skipped +
                            low-stock warning (also when < 7 eligible segments remain after this Short)
  → write_concept / write_market  Gemini: hook / explain / payoff, 70-105 words, narration rules, no subscribe ask in
                            the first sentence, numbers only from the material; originality guard (MinHash `fingerprint`
                            in history, ≥ 0.5 overlap → one rewrite → next segment); title = hook ≤ 60 chars + title rules
                            (one rewrite, else "Short packaging", exit 1); card 1-4 words
  → 9:16 slides             hook card = frame 0 / thumbnail (E6-4, never text alone): 1-4 card words over a visual:
                            market / pulse → the lead coin's drawn badge + %-move pill ("−7.2% · 24h") over its move
                            chart (no series → badge card); concept → the segment's diagram fully drawn (then without
                            notes), else an icon card (candles + coin badge + term pill; logged); concept: term →
                            diagram (step reveal) → payoff; market: move chart draw-in → cause → coins diagram →
                            numbers; text slides ≤ 14 words (shorts.text_pages: a longer text → pages of one scene's
                            slide, `pages`, sharing its time by word count in render.build_video); A/B voice `voice`
  → metadata                first line "▶ Full video: https://youtu.be/<source>" (pulse: "▶ Latest video: https://youtu.be/
                            <latest long>", no "From the full video" line), hook, payoff, data + CoinGecko credit
                            once (market / pulse), disclosure once, hashtags (#Shorts last); Reel caption = same without
                            #Shorts; after upload a "Studio task: set the related video" line (no API field)
  → history.json            kind short, short_kind (concept / market / pulse), material, segment (point_n / hook_n),
                            source_video, hook, topic (concept: the segment's normalized term; market / pulse: the
                            normalized hook), fingerprint
```

Entry point: `main.py`. Producing is in `make_short()` / `make_basics()` / `make_lesson_edition()` /
`make_triggered()` / `make_recap()` / `make_evergreen()` / `make_post()`; `main()` handles edition choice,
`--platforms`, timed vs manual rules, the slate budget and the once-per-edition-per-day-per-platform guard:
`pending = session platforms ∩ enabled − platforms published today for this session`.

## Editions (the crypto-only slate, all times UTC, 7 days a week)

| key | label | due (`start_utc`) | Sri Lanka | outside timer | backup cron (UTC) | platforms |
|---|---|---|---|---|---|---|
| `news_morning` | Morning News | 12:00 | 17:30 | cron-job.org, every day | `17 12 * * *` | FB post |
| `short_a` | Short A | 13:00 | 18:30 | cron-job.org, every day | `17 13 * * *` | YT Short + FB Reel |
| `basics` | Crypto Basics | 15:00 Wed | 20:30 | cron-job.org, Wed | `17 15 * * 3` | YT 16:9 + FB video 9:16 |
| `lesson` | Trading Lesson | 15:00 Thu | 20:30 | cron-job.org, Thu | `17 15 * * 4` | YT 16:9 + FB video 9:16 |
| `recap` | Weekly Recap (or the Saturday top-up) | 15:00 Sat | 20:30 | cron-job.org, Sat | `17 15 * * 6` | YT 16:9 |
| `topup_sun` | Sunday top-up (kind: floor) | 15:00 Sun | 20:30 | cron-job.org, Sun | `17 15 * * 0` | the episode's: YT 16:9 + FB 9:16 |
| `news_midday` | Midday News | 16:00 | 21:30 | cron-job.org, every day | `17 16 * * *` | FB post |
| `news_evening` | Evening News | 21:00 | 02:30 | cron-job.org, every day | `17 21 * * *` | FB post |
| `short_b` | Short B | 23:00 | 04:30 | cron-job.org, every day | `17 23 * * *` | YT Short + FB Reel |
| `short_p` | Short P (market pulse) | none yet (6.5 times it) | — | none yet | none | YT Short + FB Reel |
| `triggered` | Why Crypto Moved | trigger's due time | — | triggers.yml poll (30 min) dispatches it | none | YT 16:9 |
| `evergreen` | Evergreen top-up | — (`--slot`) | — | called by recap / topup_sun | none | the episode's |

- Retired by the slate (epic 5): `asia`, `london`, `newyork`, `gold` (+ `auto`, `weekend_sessions`, the forex
  weekend skip and the gold outlook code). `--session` is required (no edition / `auto` → exit 1).
- Defined in `config.yaml → sessions` (label, short, start_utc, `kind`, `days`, `platforms`, Shorts: `pulse`, `gate`).
  `main.py` has `DEFAULT_SESSIONS` (news posts + Shorts) as a fallback if config lacks them. The release (5.7) turns on
  `basics`, `triggers`, `recap`, `shorts` and `evergreen` (`*.enabled`); while one is false its timed runs skip.
- **Market-pulse Short (`short_p`, epic-shorts-reach 6.2):** `pulse: true` + `gate: pulse`, no `start_utc` until 6.5
  times it (so no timer job, backup cron or late window yet). While `pulse.enabled` is false (it ships false; 6.6
  flips it) timed short_p runs log and exit 0 and short_a keeps today's mix; a manual short_p run makes and publishes
  a pulse Short (or the concept fallback).
- **`days`** (any session): timed runs on other weekdays are skipped with a log line; manual runs
  work any day. `setup_cronjobs.py` turns `days` into cron-job.org `wdays` (`--delete-retired` deletes the retired jobs).
- **Crypto Basics is live (`basics.enabled: true`, 5.7):** the Wednesday timed run publishes the next approved
  topic of `basics/topics.yaml` (a ready package from the evergreen stock as it is; none approved → nothing to
  publish), public on YouTube (`basics.review_window_hours: 0`) and on Facebook (`basics.fb_published: true`).
  `basics.enabled: false` makes timed runs log "basics.enabled is false…" and exit 0 again.
- **Lessons are off until `lessons.enabled: true`** (owner: after merging the curriculum; the existing
  `YT_REFRESH_TOKEN` works while `lessons.playlists: false`, the owner's choice — playlists by hand). While off, lesson runs log why and exit 0 without
  fetching or publishing; a manual `--no-upload` run still makes one. An episode whose detector finds
  no clean example is held (logged, never stored) and the next one goes out. Manual lesson runs
  (without `--as-edition`) always take the next unpublished episode (`counts: false`). A counting run
  (timed or `--as-edition`) on a slot that already recorded an episode re-makes that episode with its
  recorded examples (history keeps each example's asset, timeframe and region start/end) and publishes
  only the platforms it's missing (`--force`: all); if it can't be re-made, the run fails (exit 1).
- **Lesson top-up (`--slot`, crypto-pivot weekly floor):** `python main.py --session lesson --slot <session>`
  (Actions: session `lesson` + input `slot`) fills today's slot of another edition (e.g. the Saturday
  recap; Sunday 15:00 when Saturday is used, owner 2026-10-14) with the next unpublished episode. It is a
  counting run recorded under that slot (`session: <slot>`, `trigger: topup`, `counts: true`) through
  `make_lesson_edition(…, session_key=<slot>)`, so the once-per-slot guard and the recorded-episode
  re-run apply and no episode repeats. The lesson's `days`, weekend rule and late window don't apply;
  `lessons.enabled` does. A slot already holding another edition's counting upload → logged, exit 0.
  `--slot` with a non-lesson session, an unknown slot or a news-post slot → exit 1. In the workflow a
  `slot` run gets its own `topup-<slot>` concurrency group (a slot's backup cron can't cancel a waiting
  top-up) and its run name ends "· slot <slot>".
- **News posts every day, weekends included, crypto only (CAP-9):** only crypto or crypto-regulation
  stories (crypto, a coin, stablecoins, crypto ETFs, crypto exchanges or digital assets named in the
  title or summary; a bare "ETF" / "exchange" / "coin" or a body-only mention doesn't count). No fresh
  unused crypto story → the best crypto story of the last 48 h not used by an earlier FB post → any
  crypto story. Fails (exit 1, nothing posted) only on no news, no crypto story at all, or a post that
  breaks the narration rules even as `fallback_post`.
- **Triggers.** GitHub's schedule proved unreliable (Oct 2026: the 12:30 run started 6.5 h late,
  the next day's 00:30 run never started), so the **primary trigger is cron-job.org** POSTing
  `workflow_dispatch` with `{"ref":"main","inputs":{"session":"short_a","scheduled":"true"}}`
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
  `python -m autopilot.history add …` (idempotent by any of `video_id`, `fb_reel_id`, `fb_post_id`,
  `fb_video_id`)
  and retries the push 5×. A platform added by a later run is a second entry for the same edition.
- Timed runs are skipped if they start > `max_late_minutes` (180) after `start_utc`, or > 30 min
  before it — so a very late run never posts the wrong edition. Manual runs aren't checked.
- The workflow maps the firing backup cron string → edition in the `EDITION:` env line **and**
  in the job's `concurrency.group`. **To change a time, change the cron-job.org job, `start_utc`,
  the cron line and the matching string in both places.**
- Run names in Actions: "Timer · short_a", "Backup schedule · 17 13 * * *", "Manual · basics".
- Job `timeout-minutes: 90` (a lesson renders two videos and polls Facebook up to 10 min).
- Timed runs make each edition once per UTC day (`--force` overrides, CLI only). Old history
  entries without `session` count as `london`; without `counts` they count.

Manual runs: Actions → Shorts autopilot → Run workflow → `session` (short_a/short_b/short_p/news_*/basics/lesson/recap/
topup_sun/evergreen/triggered), `platforms` (all/youtube/facebook, limited to the edition's own), optional
`as_edition`, `slot` (top-ups), `trigger` (triggered).
**YouTube API quota:** ~6 uploads/day (1,600 of 10,000 units each, resets midnight Pacific); the slate uses ≤ 3.

## Release checklist (crypto slate, epic 5.7; owner, hitl)

The code ships switched on (`basics`, `triggers`, `recap`, `shorts`, `evergreen`, `lessons` enabled). Nothing goes
live until the owner pushes; do these in order, on a **Monday** (the owner picks the date):

1. Before the push: approve the Crypto Basics topics (`basics/topics.yaml`, `approved: true`, by PR) and fill the
   evergreen stock to **4 ready episodes** (`python main.py --session basics --prepare next`, PR each package;
   `--stock` reports the count).
2. Add the **`COINGECKO_API_KEY`** repository secret (CoinGecko Demo key; the trigger poll and recap need it).
3. Delete the retired cron-job.org jobs (`CryptoFX · asia`, `london`, `newyork`, `gold`) — by hand or with
   `python setup_cronjobs.py --delete-retired`.
4. Push this epic's commits together with trading-lessons epic-crypto-lessons entry 4 (the Thursday lesson slot).
5. Run `python setup_cronjobs.py` (check with `--dry-run` first): it moves the news jobs to 12:00 / 16:00 / 21:00
   and creates short_a, short_b, basics, recap and topup_sun (lesson stays Thursday 15:00).
6. First day: Shorts at 13:00 and 23:00, news posts at 12:00, 16:00 and 21:00, no legacy edition runs, cron-job.org
   lists only the slate's nine jobs, and the trigger poll's runs log their evaluation with triggers enabled.

## Files

```
main.py                  orchestration, CLI: --session, --platforms, --scheduled (timed), --as-edition, --force, --no-upload,
                         --slot (lesson top-up into another slot), --lesson-sample; lessons: make_lesson_edition, make_lesson, publish_lesson;
                         Crypto Basics: make_basics, publish_basics
config.yaml              all settings (channel, llm, market, sessions, lessons, voice, video, upload)
get_token.py             one-time OAuth login on the owner's PC → prints YT_* secrets (--lesson-scopes adds playlists)
setup_cronjobs.py        creates / fixes the cron-job.org jobs from config.yaml sessions (start_utc, days)
autopilot/sources.py     news RSS, ForexFactory calendar, Coinbase crypto, Frankfurter FX, gold, macro,
                         CoinGecko market overview (`python -m autopilot.sources overview`)
autopilot/focus.py       lead story + related assets (keywords, scoring, typical market links)
autopilot/slate.py       the slate budget: day_uploads, short_skip (3 a day, Short B yield), hold_reason (trigger hold),
                         long_videos (ISO-week floor / cap), next_day
autopilot/script.py      Gemini prompt, fact-check, validate, fix_visuals (scene types)
autopilot/rules.py       shared narration rules: narration_problems(text) + NARRATION_RULES prompt text; date/time patterns
                         + packaging checks title_problems(title) / thumbnail_text_problems(text) (CAP-8): logged
                         only by youtube.build_metadata on brief/gold titles; the new formats enforce them
                         + DISCLOSURE / disclosure(cfg, *sections) / without_disclosure(text, line): the description line, once
autopilot/llm.py         Gemini REST client with model fallback + verbose logging
autopilot/thumbnail.py   4 thumbnail templates (Pillow) + choose() + clean_hook()
autopilot/slides.py      per-scene graphics (Pillow + matplotlib)
autopilot/render.py      ffmpeg segments, chart draw-in, push-in, ASS captions, mix
autopilot/voice.py       edge-tts per scene, WordBoundary timings, paced() key-number pauses, Piper fallback
autopilot/youtube.py     metadata assembly, upload (+ clear quota error), set_thumbnail; upload_lesson (publishAt
                         review window; playlists + LESSON_SCOPES only when asked), delete_video
autopilot/facebook.py    Graph API v26.0: publish_reel, publish_photo, publish_video (lessons, chunked /videos),
                         classified errors/retries, reel_caption
autopilot/news_post.py   FB news posts: pick_story, write_post (Gemini + fact_check + fallback), caption
autopilot/images.py      news post background (Cloudflare FLUX → library → drawn) + render_card 1080x1350
autopilot/seo.py         keyword-first titles (fallback built from data), description blocks, hashtags, tag seeds
autopilot/history.py     data/history.json helpers (ID_KEYS / PLATFORM_IDS, per-platform published_on, last_voice, merge CLI)
autopilot/lessons.py     curriculum + glossary formats, validate, DETECTORS registry, pick (episode picker), scene_plan
autopilot/detectors/     example detectors (structure, mtf, trendlines, liquidity, smc); importing registers them
autopilot/lesson_data.py multi-timeframe candles for the detectors (Coinbase, Kraken PAXG + Swissquote, Frankfurter)
autopilot/lesson_script.py  lesson narration from approved key points (Gemini + checks + fact_check)
autopilot/lesson_slides.py  lesson slides + thumbnail, 16:9 (LANDSCAPE) and 9:16 (PORTRAIT), TRACKS names
autopilot/reveal.py      step reveal (generic): example-scene marks fade in one at a time as narration names them (lessons.reveal_steps → lesson_slides base + diff-crop layers → time_steps → render._segment; hook stays fully drawn)
autopilot/basics.py      Crypto Basics: sample_topic, load_topics / validate_topic / validate_topics (topic
                         list validator: fields, question + thumbnail packaging rules, narration rules, diagrams,
                         unique ids / questions) and pick (first approved, never-published topic; main.basics_topic),
                         scene_plan, write_script (Gemini + checks, 3 attempts; subscribe ask after point_1;
                         fact-check vs facts(topic), failure stops),
                         render_slides (16:9 / 9:16, CRYPTO BASICS chip, diagram scenes stepped), packaging_problems,
                         render_thumbnail (words + diagram or coin icon), chapters, metadata (YouTube + Facebook)
autopilot/material.py    Shorts material format (documented in its docstring; epics 3/4 write / read it): source,
                         youtube_id / facebook_id, published_at, segments [{id, kind overview|concept, term,
                         narration, diagram, facts, hooks ≤ 60 chars}] (≥ 5); market material (triggered / recap /
                         pulse: `market` section); build_basics, build_triggered / build_recap / build_pulse, validate,
                         save / load, merge, write, add (workflow CLI)
autopilot/diagrams.py    drawn concept diagrams (shared: Basics now, epics 3/4 later): spec flow / compare / timeline
                         + notes (boxes, arrows, drawn coin badges BTC/ETH brand colours else accent, timeline
                         segments; `say` = spoken aliases), validate, steps (reveal order = spec order),
                         naming_order, draw (auto-layout 16:9 / 9:16 in the content box, text ≥ min_text, can't
                         fit → ValueError), step_layers (base + reveal.diff_crops layers for reveal.time_steps)
autopilot/lesson_meta.py lesson chapters, SEO title, description, hashtags, tags (YouTube + Facebook)
lessons/                 curriculum.yaml (episode queue, list order) + glossary.yaml
basics/topics.yaml       Crypto Basics topic list (list order = queue): id, question (search question = title),
                         thumbnail (1-3 words), summary, points (≥ 4) [{term, text, diagram}], approved; ships 4 builder
                         DRAFTS (approved: false) until the owner approves via PR (crypto-basics entry 4)
autopilot/triggers.py    trigger engine: evaluate (rules 1-4, coin gate), limits + data/triggers.json state, load(id|fixture),
                         check (the 30-minute poll, `python -m autopilot.triggers check`); coin_gate (rule 3's gate, shared)
autopilot/pulse.py       market-pulse material from fetched data alone (no long video, no LLM): pick_lead, build (quiet
                         market / no price data / invalid → none + reason), make (fetch + material.write
                         data/material/pulse-<date>-<slot>.json; main.make_pulse calls it for the pulse Short, 6.2)
autopilot/shorts.py      standalone Shorts: load_materials, pick (daily mix) / pick_market / pick_concept (source rotation,
                         MAX_PER_SOURCE, COOLDOWN_DAYS topic guard: topic / segment_topics / recent_topics), stock
                         (eligible segments), pick_pulse +
                         latest_long (pulse-first), write_concept / write_market (+ originality guard, packaging),
                         render_slides / render_market_slides (hook_card = the visual frame 0, text_pages / text_scene
                         = ≤ 14-word text pages), metadata / reel_caption, studio_task
autopilot/triggered.py   triggered video: scene plan, narration + checks + fact-check, slides, draw_move_chart (16:9 + 9:16),
                         packaging (title_for, thumbnail_words, render_thumbnail, metadata)
autopilot/recap.py       Saturday recap: fetch, week_has_triggered, build (biggest 7-day moves), narration, slides, board
                         thumbnail, metadata
data/triggers.json       trigger state (written only by the trigger poll workflow)
.github/workflows/triggers.yml    30-minute trigger poll (light install, commits data/triggers.json, dispatches `triggered`)
autopilot/media.py       ffmpeg/ffprobe helpers
assets/fonts/            Anton + Space Grotesk (SIL OFL) for thumbnails
tests/test_offline.py    full offline render test with sample data + mocked LLM (incl. the lesson and basics editions)
tests/test_lessons.py    curriculum/glossary validator, detectors on fixture candles, lesson data, narration
tests/lessons/           sample curriculum + glossary + fixture candles
tests/basics/            sample_topic.yaml: the Crypto Basics tracer topic (+ a diagram per point);
                         sample_narration.yaml: its narration naming every diagram part in order
data/history.json        upload log, committed back by the workflow (don't hand-edit casually)
data/material/           Shorts material per published long video (<kind>-<id>.json) + pulse-<date>-<slot>.json (a pulse
                         Short's run leaves a copy in output/<stamp>/material.json), merged and committed by the
                         workflow's Save history step
assets/backgrounds/      optional own images per news topic (<topic>/*.jpg, or general/)
.github/workflows/autopilot.yml   9 backup crons + workflow_dispatch inputs (session, platforms, as_edition, scheduled, slot)
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
  hourly, 7 days (BTC, ETH, SOL, XRP). Returns newest-first; we sort.
- **Market overview (trigger engine):** `sources.fetch_market_overview()` reads CoinGecko's free
  **Demo** API (`api.coingecko.com/api/v3`, key in header `x-cg-demo-api-key` from secret
  `COINGECKO_API_KEY`): `/global` (total market cap + its 24 h change) and `/coins/markets` (top 50
  by market cap, `price_change_percentage=24h,7d`, `sparkline=true` = 7 days hourly). Owner
  decision 2026-10-13: Demo tier is used even though CoinGecko states commercial use only for paid
  plans — **upgrade to Basic before monetizing**. Every video/description using it credits
  `sources.CG_CREDIT` ("Data provided by CoinGecko"). Missing key, 429, bad key or bad body →
  `None` with a log line (15 s timeout, one retry on network error/429/5xx), never a crash. Demo
  limits: 30 calls/min, 10k/month; one overview = 2 calls. Not part of `gather()`; briefs keep
  Coinbase candles. Live check: `python -m autopilot.sources overview`.
- **Forex:** Frankfurter v2 `api.frankfurter.dev/v2/rates?base=USD&quotes=...` — daily
  central-bank reference rates (not live). EUR/USD etc. = 1/(USD→EUR). Script must say
  "yesterday's close / latest daily fix", never "right now".
- If **no** price data loads, the run stops (no guessing). Failed individual sources are skipped.
- **News posts** (`gather(kind="post")`) read every feed incl. the FB-only `geopolitics`
  (war/sanctions/tariffs/conflict + markets) and `regulation` (SEC/CFTC/stablecoin) Google News
  searches, 48 h window (`pick_story` then keeps only crypto-relevant items, CAP-9); prices only feed
  the caption's "Market check". Video editions read the
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
- `script.write()` rules: 80–100 words (`llm.min_words/max_words`, ~35 s), 5–6 scenes; arc hook →
  what happened → why (headline-backed only) → spread to 1–2 related assets → what to watch; macro
  context only when a headline makes it the cause; only numbers from the data; no predictions/targets/
  buy-sell; **no spoken disclaimer, no outro, no sign-off** — the last line loops back to the opening
  fact; first line is a tension opener with a real number (`HOOKS`, e.g. "Ethereum just lost 5.7%.
  Here's who's selling." — "who" only if a headline names them); scene 1 must state the thumbnail
  fact; returns `thumbnail_hook`. `validate()`: 4–7 scenes, last scene not sign-off-only.
  `fix_visuals(data, pkg, cover, log)` forces scene 1 = `{"type": "title", "follow": opening_chart()}`
  (the cover's asset — move/level card `asset`, gold card → gold chart — else the lead's chart, else
  board), swaps later charts of that asset or of non-focus assets for an unused focus asset, degrades
  bad visuals to `board`; a stray `outro` is dropped if it only signs off, else becomes the board;
  spoken disclaimer/goodbye phrases (`SIGN_OFF`, `GOODBYE`) are cut from the last line (rest of the
  sentence kept); an all-sign-off last scene is dropped if ≥ 4 scenes remain. Each change is logged.
- Scene visual types: `title, price{asset}, fx{asset}, gold, board, news{source,headline}, calendar`
  (no `outro` in Shorts since Oct 2026). The market-brief helpers (script.make_script, slides.render_slides,
  thumbnail.choose/render, seo, youtube.build_metadata) are no edition's path any more: they stay as the offline
  render fixture in tests/test_offline.py main() until a refactor sweep removes them (deferred-work).

## Thumbnails

Shorts custom thumbnails can't be set via API for this channel (YouTube only allows custom
Shorts thumbnails for YPP members, in Studio desktop). So **every video opens on the thumbnail
design** for ~1 s (`render.COVER_HOLD`; frame 0 = the exact design, then an eased push-in to 1.06
within 0.35 s and hold, no captions over it), then scene 1's `follow` slide takes over for the rest
of that scene: the chart of the asset the cover names (else the lead's; gold edition: the gold chart;
no chart → board) drawing in, with captions from that moment. `set_thumbnail()` is attempted and its refusal ignored; `thumbnail.jpg` is kept
as an artifact and is the Facebook Reel cover.

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

- 1080×1920, 30 fps, aim 30–40 s (`video.max_seconds: 42`; over it → re-recorded faster). Dark ground `#0E0F12`, accent `#FFD400`, up `#22C55E`, down `#EF4444`.
- Slides keep y 1230–1480 free for burned-in captions (ASS, 3 words/line, current word yellow).
- Chart scenes draw in left→right (background-coloured box slides off via ffmpeg overlay).
  Other scenes: slow push-in (`scale=...:eval=frame`).
- Footer on every slide: "Not financial advice · Data: Coinbase, ECB/Frankfurter, ForexFactory" (gold:
  `gold.footer`). With the description / Reel caption disclosure line this is the only disclaimer: no
  spoken one, no outro card.
- Disclosure line (narration-rules.md, CAP-7): "Narrated with a synthetic voice. Researched from public
  market data. Not financial advice." in `upload.disclaimer` / `news_posts.disclaimer` (`rules.DISCLOSURE`
  if unset). `youtube.build_metadata`, `facebook.reel_caption` and `news_post.caption` append it exactly
  once (`rules.disclosure`; a copy in the writer's text is removed by `rules.without_disclosure`).
- Voice: edge-tts `en-US-AndrewMultilingualNeural`, `+0%` (narration-rules.md, CAP-7); re-recorded faster if > max_seconds.
  `main.narrate()` voices briefs and gold with `pauses=True` (`voice.paced()`): a comma after a spoken price or
  percentage that runs into an allow-listed word ("…two point one percent, to…", gold's "forty-one forty-three,
  as…"; never "a five percent, drop", "$500 million, in…" or inside a range "2% to 3%") and after a naming verb
  before a scene's optional concept term (`scene["term"]`, for the new formats). edge-tts 7.2.8 XML-escapes the
  text, so no SSML (no `<break>` / emphasis). Captions show the script's words. Lessons: no pauses, same rate.
  A/B (narration-rules.md, first 30 days): with `voice.alternate` (`en-US-BrianMultilingualNeural`) set, briefs
  and gold alternate `name` / `alternate` per edition (`main.ab_voice` + `History.last_voice`: the other voice
  from that session's latest uploaded edge-tts entry; Piper entries take no turn) and log `"voice"` (the
  edge voice or Piper model that spoke) in the history entry for epic 5's comparison. Lessons: `name` only.
  Each scene retries edge-tts with waits 0/10/30/60 s (`voice.EDGE_WAITS`); if it still fails, the
  whole video is voiced by `voice.fallback` (Piper `en_US-ryan-high`, free, local, downloaded on first
  use ~120 MB; word timings estimated) and the rest of the run uses Piper. No `fallback` → the run fails.
- Optional background music: any `.mp3` in `music/` (royalty-free only).

## Upload / YouTube

- OAuth secrets: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` (from `get_token.py`).
  Daily Shorts (`youtube.upload()` / `set_thumbnail()`) and lessons with `lessons.playlists: false`
  (owner's choice, playlists managed by hand) request only `youtube.upload` (`SCOPES`), so the existing
  token serves both. Only `lessons.playlists: true` (and `delete_video()` / `test-lesson --playlists`)
  request `LESSON_SCOPES` = + `youtube` + `yt-analytics.readonly`, which needs `get_token.py --lesson-scopes`. Google Cloud project "Everyday Science", OAuth app "Tiny Whys
  Uploader" (old name, harmless), **In production** (Testing mode would expire tokens in 7 days).
  Branding page uses a GitHub Pages home page + privacy policy (`<user>.github.io`).
- Un-audited API projects upload as **private**; the YouTube API Services audit form removes it.
  Check status in Studio if uploads aren't public.
- Lessons: category 27 (Education), 16:9, private with `publishAt` = `lessons.review_window_hours` (24) later,
  custom thumbnail, added to "Track N · <name>" (`lessons.track_playlist`) and `lessons.path_playlist`
  playlists (created if missing). Facebook gets the 9:16 render via `publish_video` (`lessons.fb_published`).
- Category 25 (News & Politics). SEO (`seo.py`): the title must have the lead asset name / "Gold price"
  in its first 45 chars, else a data-built title ("XRP Price Today: Down 5.0% | London Open, Oct 8",
  "Gold Price Today: Bearish Below $4,142 | XAU/USD Outlook Oct 8"). Description = keyword-first
  summary → Key numbers / Key levels → Stories mentioned → What to watch → posting schedule →
  data credits → disclosure line → hashtags (lead asset, its market, related asset, …, #Shorts last;
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
  the disclosure line once; Reel captions are built from the YouTube metadata (`reel_caption`, < 2,200 chars).
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
- The finished post must also pass `rules.narration_problems` (`news_post.post_problems`): a failing
  Gemini post is replaced by `fallback_post` (which drops rule-breaking summary sentences); a failing
  fallback raises and the post edition stops. The picker prefers stories whose title passes the rules.
- History: `kind: post`, `fb_post_id`, `headlines: [story title]`, `topic`, `background`. These
  headlines don't feed the videos' "don't repeat" list (`used_headlines()` skips posts).

## Secrets (GitHub → Settings → Secrets and variables → Actions)

`GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`,
`FB_PAGE_ID`, `FB_PAGE_TOKEN`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `COINGECKO_API_KEY` (CoinGecko
Demo key for the market overview; optional — without it the overview is skipped with a log line).
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
  news image posts a day at 03:00 / 09:30 / 16:30 UTC, every day (crypto stories only since the crypto
  pivot, CAP-9: no crypto story → no post). Card style follows
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
- **Gold bias by LLM (retired gold outlook):** rejected — the bias/levels were deterministic rules in `gold.py` so they're
  repeatable and auditable; tomorrow's video reviews today's call honestly (`review`).
- **"All markets" briefs:** replaced Oct 2026 by one-story briefs (owner: videos mixed BTC, ETH,
  EUR, GBP regardless of the news). Lead needs headlines: a move with no headline counts 0.7×.
  Crypto-first (Oct 2026: big crypto drops were all six top videos, FX-led briefs didn't chart):
  `MOVE_SCALE` crypto 3% = 1.0. **Crypto-only since the crypto pivot (CAP-9):** `focus.pick()` scores only
  coins with crypto prices (BTC, ETH, SOL, XRP); FX pairs, gold and the `USD` theme never lead (the old
  `FX_LEAD_WEIGHT` / calendar-event bonus is gone). Session `focus` texts ask only for crypto.
- **Retention pass (owner, 2026-10-12):** viewers left almost at once (YT ~14 s average on 45–58 s
  videos, FB ~2.7 s), so briefs and the gold outlook are 30–40 s, open with motion (cover push-in →
  the cover asset's chart at ~1 s, captions on), have tension hooks and no outro card / spoken disclaimer (footer +
  description keep it). Lessons keep their own recap outro, but (same day) open on example 1's chart
  fully marked under the lesson title (`scene_plan` hook: `heading` + `still`, no title card, no draw-in)
  and the recap ends on "Next: <episode>" (slide and narration; disclaimer/ICT line before it). End
  screens can't be set via the API: a Studio template, by hand (README).

## Gotchas we hit

- edge-tts 403 "Invalid response status" (2026-10-12, 05:41–06:30 UTC): Microsoft refused GitHub's
  runners for a while (it worked from a home IP, same version 7.2.8 = latest) → retries with waits +
  the Piper fallback voice.
- `.github/` and `.gitignore` are hidden folders/files — drag-and-drop uploads skip them; use git.
- A config.yaml that didn't get committed broke editions ("Choose one of:" empty) → hence
  `DEFAULT_SESSIONS`. After unzipping updates, check `git status` lists every changed file.
- The workflow commits `data/history.json` after each upload → **always `git pull` before pushing.**
  (Its save step resets to `origin/main` and re-merges the run's entry, so parallel runs don't lose logs.)
- GitHub account billing lock once blocked all jobs ("account is locked due to a billing issue").
- GitHub scheduled runs can start hours late or never (hence the outside timer); schedules
  also pause after 60 days of repo inactivity. A green 1-min run = a skip; read its last log line.
- Run times in the Actions UI are in the browser's time zone (GMT+5:30), not UTC.
- cron-job.org `401` = PAT expired (1-year expiry) → new token into all nine jobs (setup_cronjobs.py re-patches them).
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
  make no predictions.
- Run `python tests/test_offline.py` after any change to rendering, slides, thumbnail or script flow.
- Prefer small, explicit log lines (`log(...)`) — the Actions log is the only monitoring.
- Owner applies changes via git (Mac or Windows); give exact file paths when handing over changes.
