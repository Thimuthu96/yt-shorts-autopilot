# Gus Explains Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crypto autopilot with "Gus Explains": two fully automatic odd-fact cartoon Shorts a day
(YouTube Short + Facebook Reel), rendered from a code-built Three.js cartoon world in the style of the
reference video, plus generated channel branding and an owner-confirmed old-content deletion script.

**Architecture:** Gemini (free tier, Google Search grounding) turns a backlog topic into a *story JSON* of
beats. A Python validator checks it against a catalog exported by the engine. edge-tts voices each beat →
`voice.wav` + `timeline.json` (word times, mouth envelope). A headless-Chromium Three.js engine
(`studio/`, method from Odd Fortune Studio, new design) renders frames → ffmpeg muxes voice + music + SFX.
The existing `youtube.py` / `facebook.py` / `history.py` / workflow / cron-job.org plumbing publishes it.

**Tech Stack:** Python 3.12 (existing `autopilot/`), Node 22 + three@0.170 + playwright (Chromium,
SwiftShader on CPU), ffmpeg (libx264, loudnorm), edge-tts (Piper fallback), Gemini REST, GitHub Actions,
cron-job.org.

**Spec:** `docs/superpowers/specs/2026-11-12-gus-explains-design.md` (read it with this plan). Visual
reference: `/Users/thimuthup/Downloads/Levels of Pirate Cannonballs.mp4`. Method reference (read only, the
owner's own code, may be adapted): `/Users/thimuthup/Downloads/odd-fortune-studio` — `engine/engine.js`,
`render.js`, `tts.py`, `audio.py`, `scripts/generate_story.py`, `scripts/validate_story.py`, `branding.js`.

## Global Constraints

- Free only: no paid API, no billing on the AI Studio project. Gemini text + Google Search grounding only;
  if grounding returns 429/quota for the free key, research falls back to an ungrounded call and the run
  logs `grounding unavailable` (sources then come only from URLs Gemini cites that pass `check_url`).
- Output: 1080×1920, 30 fps, H.264 yuv420p, AAC stereo 48 kHz, `-g 60` (closed ~2 s GOP), loudness
  `loudnorm=I=-14:TP=-1.5:LRA=11`. Length 45–60 s; narration 130–170 words.
- Editions: `short_a` publishes ~17:00 UTC, `short_b` ~23:00 UTC, every day, YouTube Short + Facebook Reel.
- Captions: one word at a time, centred, at 58 % of frame height, white `#FFFFFF`, dark outline
  `#17142B` ≈ 10 px + soft shadow, ~70 px font, no box, no highlight colour. Font: a free OFL heavy
  rounded sans **other than Lilita One** (builder picks, e.g. "Baloo 2 ExtraBold" or "Fredoka Bold";
  vendored in `studio/fonts/` with its OFL licence).
- Visual language (spec §5): white round heads with ink outline, dot eyes, stick limbs, costumes; bright
  toon-shaded 3D sets; lighting moods `day | interior_glow | sunset | night | steel`; continuously moving
  camera, few cuts; `iris` circle transition; FX smoke/fire/splinters/sparks/explosion/splash/steam/
  glow/flash; names and numbers as in-world signs, not overlays. Nothing from Ricks Clips or Odd Fortune's
  design (cast, Lilita font, stamps, colours) is reused.
- Every claim true; sources (≥ 2 working URLs) in the description. No first-person filler, no outro, no
  spoken sign-off, no "subscribe" in the first sentence.
- Disclosure line, exactly once per description/caption: `Narrated with a synthetic voice.`
- Description hashtags 3–5, `#Shorts` last on YouTube, none of `#Shorts` on Facebook. Category `27`.
- Every new Python module logs with small explicit lines (`log(...)`); the Actions log is the only monitoring.
- Owner applies changes via git; history is committed by the workflow → always rebase on `origin/main`.
- Outward actions (cron-job.org changes, repo visibility, deletions, enabling the gate) are done **by the
  owner** or only after the owner confirms at that moment. Tasks below say which.

## Review Focus

1. **Gemini returns a story that names a set/prop/pose the engine doesn't have, or invalid JSON** → the
   validator rejects it with the exact unknown names, the writer retries once with the problems in the
   prompt, then moves to the next topic; never a crash mid-render. (Task 9 + Task 13 tests.)
2. **edge-tts is blocked on the runner** (seen Oct 2026) → Piper fallback voices the whole video and the
   timeline still has word times and a mouth envelope; render proceeds. (Task 10 test with a fake Piper.)
3. **Narration runs long (> 60 s)** → re-recorded once faster via the existing `narrate()` rule; still
   over → the story is rejected before rendering (`too long`), next topic. (Task 10 test.)
4. **`music/` empty or no track cleared for Facebook** → YouTube gets music if any, the Reel gets no music
   (logged); never a crash and never an un-cleared track on Facebook. (Task 11 tests.)
5. **Render slower than expected / Chromium crash** → render.js exits non-zero with the frame number; the
   run fails (exit 1) without uploading a partial video; the next timed run of that slot is not blocked.
   (Task 12 test with a failing fake node command.)

---

## File Structure

```
studio/                         Node: the cartoon engine (new)
  package.json                  (at repo root: three, playwright, font package if used)
  render.js                     story + timeline → frames → build/<slug>/video.mp4; --stills t1,t2
  catalog.js                    writes studio/catalog.json from the engine's registries (node studio/catalog.js)
  catalog.json                  generated, committed: sets, moods, props, poses, exprs, motions, fx, cams, …
  branding.js                   renders branding/*.png via engine/branding.html
  engine/index.html             loads engine.js, fonts, exposes window.setup / window.renderAt
  engine/core.js                renderer, toon material + ink outline helpers, canvas text, hash
  engine/world.js               SETS, PROPS, MOODS registries + buildSet(spec), spawnProp(spec)
  engine/cast.js                Char class, drawChar(look, state), POSES, EXPRS, MOTIONS, COSTUME_KEYS, GUS_LOOK
  engine/camera.js              CAM_MOVES, camPose(cam, prevPose, f) pure function, iris(t) mask
  engine/fx.js                  FX registry: makeFx(type, at), updateFx(g, lt)
  engine/signs.js               in-world sign planes (SIGN_STYLES)
  engine/captions.js            one-word caption DOM layer
  engine/engine.js              beat application (keep/remove), frame loop, window.setup/renderAt
  engine/branding.html          avatar / banner / FB cover scenes
  fonts/                        caption + sign font (OFL) + OFL.txt
  test/*.test.js                node --test unit tests (pure functions only)
autopilot/
  story.py                      NEW: story schema + validate(story, catalog) -> list[str]
  timeline.py                   NEW: narrate beats → voice.wav + timeline.json
  soundtrack.py                 NEW: music manifest, SFX synthesis, mix per platform
  studio.py                     NEW: run node render, mux, frame-0 thumbnail
  topics.py                     NEW: topics/backlog.yaml queue, rotation, refill
  writer.py                     NEW: research → story → validate → fact-check (Gemini)
  metadata.py                   NEW: title rules, YouTube description, Reel caption
  llm.py                        MODIFY: add generate_text(prompt, models, tools=None) -> (text, grounding)
  youtube.py, facebook.py, history.py, voice.py, media.py, rules.py   KEEP (trim crypto-only helpers)
  everything else in autopilot/ DELETE (Task 16)
main.py                         REWRITE: --session short_a|short_b, gate, make_short, publish
config.yaml                     REWRITE (Task 15)
topics/backlog.yaml             NEW: topic queue
music/tracks.yaml               NEW: track manifest (owner fills)
stories/sample/lighthouse.json  NEW: hand-written sample story (Task 8)
branding/                       NEW: generated PNGs + channel_description.txt
scripts/delete_old_content.py   NEW (Task 19)
data/archive/crypto-history.json  history before the switch (Task 16)
tests/test_offline.py           REWRITE: full offline pipeline with mocks
tests/test_story.py, test_timeline.py, test_soundtrack.py, test_studio.py, test_topics.py,
tests/test_writer.py, test_metadata.py, test_main.py, test_delete_old.py   NEW
.github/workflows/autopilot.yml REWRITE; .github/workflows/triggers.yml DELETE
setup_cronjobs.py               MODIFY: new sessions; --disable used in Task 1
CLAUDE.md, README.md            REWRITE (Task 20)
```

## Shared formats (every task uses these names)

**Story JSON** (`stories/*.json`, written by `writer.py`, read by engine and validator):

```json
{
  "slug": "why-lighthouses-flash",           // [a-z0-9-], ≤ 48 chars, unique in history
  "title": "Why Lighthouses Flash in Patterns", // ≤ 60 chars
  "category": "engineering",                 // one of topics.CATEGORIES
  "format": "explainer",                     // explainer | levels
  "music_mood": "curious",                   // curious | tense | upbeat | epic
  "cast": { "gus": {"look": "gus"}, "keeper": {"look": {"costume": "sailor", "hat": "cap", "shirt": "#2f6fd6", "stripes": "#ffffff"}} },
  "beats": [{
    "text": "Every lighthouse blinks in its own secret code.",   // caption + voice
    "say": "optional pronunciation override",
    "set": {"type": "coast", "mood": "night"},
    "keep": false, "remove": [],
    "props": [{"id": "lh", "type": "lighthouse", "pos": [0,0,-4], "rot": [0,0,0], "scale": 1, "anim": null, "face": null, "delay": 0}],
    "chars": [{"id": "keeper", "pos": [-1.5,0,1], "facing": "right", "pose": "point", "expr": "smug",
               "talk": true, "enter": null, "motion": null}],
    "signs": [{"text": "1 FLASH / 5 SEC", "pos": [1,3,0], "style": "plank", "delay": 0.8}],
    "fx": [{"type": "glow", "at": [0,6,-4], "delay": 0}],
    "sfx": [{"type": "whoosh", "at": 0.0}],
    "cam": {"target": [0,2,0], "dist": 9, "height": 1.2, "angle": 0, "move": "push", "cut": false, "follow": null},
    "transition": null                           // null | "iris" | "cut"  (into this beat)
  }],
  "sources": [{"url": "https://…", "title": "…"}],
  "summary": "1-3 sentences, ≤ 400 chars, used in the description",
  "hashtags": ["#lighthouse", "#history", "#engineering"]
}
```
A beat in a `format: "levels"` story also carries `"level": <int>` on the beat that introduces each level.
```json
```

**catalog.json** (generated by `node studio/catalog.js`, committed, read by `autopilot/story.py`):
`{"sets": [...], "moods": [...], "props": [...], "poses": [...], "exprs": [...], "motions": [...],
"enters": [...], "fx": [...], "cam_moves": [...], "sign_styles": [...], "transitions": ["iris","cut"],
"looks": ["gus"], "costume_keys": [...], "costumes": [...], "anims": [...], "sfx": [...], "frame_half_width": 0.22}`

**timeline.json** (written by `timeline.py`, read by engine — same shape as Odd Fortune's):
`{"fps": 30, "duration": 52.4, "beats": [{"i": 0, "start": 0.0, "end": 3.1, "words": [{"w": "Every", "s": 0.03, "e": 0.31}]}], "mouth": [0.0, 0.42, …]}`
(one `mouth` value 0..1 per frame).

---

### Task 1: Pause crypto publishing now (owner-run outward step)

**Files:**
- Modify: `.github/workflows/autopilot.yml` (remove every `schedule:` cron line, keep `workflow_dispatch`)
- Modify: `.github/workflows/triggers.yml` (remove its `schedule:`)
- Modify: `config.yaml` (`triggers.enabled: false`, `shorts.enabled: false`, `pulse.enabled: false`,
  `basics.enabled: false`, `recap.enabled: false`, `evergreen.enabled: false`, `lessons.enabled: false`,
  `news_posts` sessions: add a top-level `paused: true` that `main.py` honours, see step 2)
- Modify: `main.py` (`main()`: if `cfg.get("paused")` and `args.scheduled` → `log("Channel paused for the Gus Explains switch; timed runs skip.")`, return 0)
- Test: `tests/test_offline.py` keeps passing

This lands on `main` on its own small branch `chore/pause-crypto` **before** the rebuild branch.

- [ ] **Step 1:** Make the four edits above.
- [ ] **Step 2:** Run `python tests/test_offline.py` → passes; run `python main.py --session short_a --scheduled --no-upload` → last log line is the paused message, exit 0.
- [ ] **Step 3:** Commit `chore: pause crypto publishing for the Gus Explains switch`.
- [ ] **Step 4 (owner):** Ask the owner to merge, then to run
  `python setup_cronjobs.py --dry-run --disable short_a,short_b,short_p,news_morning,news_midday,news_evening,basics,lesson,recap,topup_sun`
  and, if the plan shows all ten jobs paused, the same without `--dry-run`. Do not run it yourself.

### Task 2: Public-repo safety audit (report only)

**Files:** none changed (unless a finding needs a `.gitignore` line).

- [ ] **Step 1:** Run `git log --all -p | grep -nEi "(refresh_token|client_secret|api[_-]?key|EAA[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|ghp_|github_pat_)" | head -50` and `git ls-files | grep -Ei "secret|token|\.env|credential"`.
- [ ] **Step 2:** Expected: no real secret values (names in docs are fine). Report findings to the owner in plain words. If a real secret is found: stop, tell the owner to rotate it; do not rewrite history without their go-ahead.
- [ ] **Step 3 (owner):** owner switches the repo to public in GitHub settings.

### Task 3: Studio harness — render a 1-beat story

**Files:**
- Create: `package.json` (root; deps `three@0.170.0`, `playwright@1.63.0`), `studio/render.js`,
  `studio/engine/index.html`, `studio/engine/core.js`, `studio/engine/engine.js`, `studio/fonts/` (+OFL.txt),
  `studio/test/harness.test.js`, `studio/fixtures/one-beat.json`, `studio/fixtures/one-beat.timeline.json`
- Modify: `.gitignore` (`node_modules/`, `build/`)

**Interfaces:**
- Produces: `node studio/render.js <story.json> --timeline <timeline.json> --out <dir> [--stills t1,t2] [--scale 0.5]`
  (`--scale` renders at a fraction of 1080×1920 for fast tests) →
  `<dir>/video.mp4` (silent) or `<dir>/still_<t>.jpg`. Exit code 1 + `render failed at frame N: …` on error.
- Produces (browser): `window.ENGINE_READY`, `window.setup(story, timeline)`, `window.renderAt(t)`.
- Produces (core.js): `toonMat(color, opts)`, `inked(mesh)` (ink outline via back-face hull, width `OUT=0.035`),
  `canvasTex(w,h,draw)`, `hash(n)`.

Adapt Odd Fortune's `render.js` server + frame pipe (it's the owner's code); add `--timeline`/`--out`
args and the error/exit behaviour; keep SwiftShader args (CPU runners). `-g 60` on the x264 encode.

- [ ] **Step 1:** Write `studio/test/harness.test.js` (`node --test`): spawns render.js on the fixture with `--stills 0.5` and asserts the jpg exists and is 1080×1920 (read JPEG SOF header); spawns it on a fixture with a broken `set.type` and asserts exit code 1 and stderr matches `/render failed at frame \d+/`.
- [ ] **Step 2:** Run `npm i && npx playwright install chromium && node --test studio/test/` → FAIL (no render.js).
- [ ] **Step 3:** Implement render.js, index.html, core.js, and an engine.js that draws a sky gradient + ground plane for any beat and throws `unknown set: <type>` for types not in a stub `SETS = {test: …}`.
- [ ] **Step 4:** Run `node --test studio/test/` → PASS.
- [ ] **Step 5:** Commit `feat(studio): headless render harness`.

### Task 4: World — sets, props, lighting moods, catalog export

**Files:**
- Create: `studio/engine/world.js`, `studio/catalog.js`, `studio/catalog.json` (generated), `studio/test/world.test.js`, `studio/fixtures/sets-tour.json`
- Modify: `studio/engine/engine.js` (use `buildSet`, `spawnProp`, moods)

**Interfaces:**
- Produces: `SETS` (object: name → builder), `PROPS`, `MOODS` (`day | interior_glow | sunset | night | steel`,
  each `{skyTop, skyBottom, sun, ambient, fog, tint}`), `ANIMS` (`spin | float | drop | wobble | fly | sink`),
  `buildSet({type, mood, ...opts}) -> THREE.Group` (throws `unknown set: X`), `spawnProp(spec, t) -> Object3D`
  (throws `unknown prop: X`), `propFace(obj, expr)` (puts a cartoon face on a prop).
- Produces: `node studio/catalog.js` writes `studio/catalog.json` (shape in "Shared formats"; poses/exprs/fx/cams
  filled as later tasks add them — catalog.js imports every registry).

Starting set list (covers the first backlog topics; more are added only when a topic needs them):
`ship_deck, open_sea, harbour, coast, furnace_room, town_street, room, office, lab, field, castle_yard,
cutaway` (cutaway = abstract interior of an object on a gradient). Starting props: `cannon, cannonball,
barrel, crate, rope_coil, lantern, ship, lighthouse, sign_post, table, chair, bed, door, bell, coffin,
jar, coin, lever, gear, train_car, rail, flag, torch, tongs, furnace, pillar_rock, palm, cloud`.
Style: chunky rounded geometry, toon shading (3–4 band gradient map), ink outline on characters and key
props only, saturated palette (wood `#B9783F/#8C5A2B`, sea `#1FA3C8`, sky `#7CC8F2`, jungle `#3E9B45`),
tall rock pillars with jungle tops as the recurring "Gus world" backdrop for outdoor sets.

- [ ] **Step 1:** Test `world.test.js`: `catalog.json` after `node studio/catalog.js` contains every set above and all five moods; `buildSet({type:"nope"})` throws `/unknown set: nope/` (import world.js under node with three's node build).
- [ ] **Step 2:** Run `node --test studio/test/world.test.js` → FAIL.
- [ ] **Step 3:** Implement world.js + catalog.js; `sets-tour.json` has one beat per set (rotating moods).
- [ ] **Step 4:** Run tests → PASS; render `--stills` for every beat of `sets-tour.json` and look at them (all sets read clearly in 9:16, no empty sky-only frames).
- [ ] **Step 5:** Commit `feat(studio): sets, props and lighting moods`.

### Task 5: Characters — the round-head cast and Gus

**Files:**
- Create: `studio/engine/cast.js`, `studio/test/cast.test.js`, `studio/fixtures/cast-sheet.json`
- Modify: `studio/engine/engine.js`, `studio/catalog.js`

**Interfaces:**
- Produces: `POSES` (`idle, point, wave, armsUp, shrug, think, hold, cross, facepalm, present, scared, run, fall, cheer`),
  `EXPRS` (`neutral, happy, excited, smug, sly, shocked, scared, sad, worried, angry, pain`; `scared` adds a sweat drop,
  `pain` = squint `>_<`), `MOTIONS` (`bob, hop, shake, flinch, run_across, fall_over, spin`), `ENTERS` (`left, right, drop, pop`),
  `COSTUME_KEYS` (`costume, shirt, stripes, pants, hat, hatColor, bandana, coat, apron, crown, helmet, glasses, mustache, beard, badge, prop`),
  `COSTUMES` (`sailor, pirate, officer, worker, scientist, suit, king, knight, farmer, chef, doctor, plain`),
  `GUS_LOOK` (fixed signature look), `class Char { constructor(id, look); frame(spec, t, mouth) }`,
  `drawChar(ctx, look, state)` (2D canvas sprite on a camera-facing plane).
- Design: big white round head (≈ 45 % of height) with ink outline `#17142B`, dot eyes with white highlight,
  line brows that carry the expression, simple mouth shapes (closed / open-small / open-wide from `mouth`
  envelope, thirds), stick limbs with rounded ends, small torso carrying the costume. Gus: our own signature
  (e.g. mustard scarf + round glasses + tuft of hair) — must not resemble Ricks Clips' bandana-stripe pirates
  as a lead character.

- [ ] **Step 1:** Test `cast.test.js`: every `COSTUMES` entry expands to only `COSTUME_KEYS`; `new Char("x", "gus").look` equals `GUS_LOOK`; `Char.frame` with `talk:true, mouth:0.9` returns state `mouth === 1` and with `mouth:0.1` returns `0`; unknown pose → throws `/unknown pose/`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement cast.js (Odd Fortune's canvas-sprite approach adapted to the new design), wire into engine (enter/motion/talk/blink).
- [ ] **Step 4:** Tests PASS; render `cast-sheet.json` stills (every expression, every pose, every costume, Gus) and check readability at phone size.
- [ ] **Step 5:** Commit `feat(studio): round-head cast and Gus`.

### Task 6: Camera and transitions

**Files:**
- Create: `studio/engine/camera.js`, `studio/test/camera.test.js`
- Modify: `studio/engine/engine.js`, `studio/catalog.js`

**Interfaces:**
- Produces: `CAM_MOVES` (`static, push, pull, panL, panR, orbitL, orbitR, rise, drop, tiltUp, lowSweep, flyOver, follow, closeUp`),
  `camPose(cam, prev, p) -> {pos:[x,y,z], look:[x,y,z], fov}` — pure; `p` = 0..1 progress through the beat
  (ease-in-out); when `cam.cut` is false the pose at `p=0` equals `prev` (continuous camera) and blends to the
  beat's framing within the first 25 % of the beat; `follow` tracks the prop id given in `cam.follow`.
  `irisMask(t, dur=0.45) -> radius 0..1` (closes then opens across a beat boundary with `transition:"iris"`).

- [ ] **Step 1:** Tests: `camPose({move:"push",…}, prev, 0)` deep-equals `prev` when `cut:false`; with `cut:true` the p=0 pose equals the beat's own framing; `push` reduces distance to target between p=0.3 and p=1; `irisMask(0)=1`, minimum ≈0 at mid, `irisMask(dur)=1`; unknown move throws `/unknown camera move/`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement + wire in (iris = circular clip of the canvas, black outside like the reference's white-ring zoom — builder may use a white ring edge). **Step 4:** PASS; stills across a 3-beat fixture show continuous framing. **Step 5:** Commit `feat(studio): continuous camera and iris transition`.

### Task 7: FX, in-world signs, captions

**Files:**
- Create: `studio/engine/fx.js`, `studio/engine/signs.js`, `studio/engine/captions.js`, `studio/test/captions.test.js`
- Modify: `studio/engine/engine.js`, `studio/catalog.js`

**Interfaces:**
- Produces: `FX` (`smoke, fire, splinters, sparks, explosion, splash, steam, glow, flash, debris, bubbles, question`),
  `makeFx(type, at) / updateFx(g, localT)` (deterministic: seeded by `hash`, so re-renders are identical),
  `SIGN_STYLES` (`plank, barrel_label, banner, chalk, metal, paper`), `signPlane(text, style)`,
  `captionWord(timeline, t) -> string | ""` (pure: the word whose `[s,e)` contains t; between words inside a
  beat keeps the previous word until the next starts; outside beats → "").
- Caption rendering exactly per Global Constraints.

- [ ] **Step 1:** Tests for `captionWord` (inside word, gap inside beat → previous word, after beat end → "", t before first word → ""); FX determinism: two `updateFx` runs with same seed/time give identical particle positions.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS; stills of each FX and sign style. **Step 5:** Commit `feat(studio): effects, signs and captions`.

### Task 8: Sample story end-to-end + OWNER CHECKPOINT

**Files:**
- Create: `stories/sample/lighthouse.json` (hand-written, ~8 beats, "Why Lighthouses Flash in Patterns", original
  topic, uses ≥ 4 sets, ≥ 3 moods, an iris, Gus in hook and payoff), `stories/sample/lighthouse.timeline.json`
  (hand-made word times, ~50 s, mouth = 0.5 constant while talking)

- [ ] **Step 1:** `node studio/render.js stories/sample/lighthouse.json --timeline stories/sample/lighthouse.timeline.json --out build/sample` → `build/sample/video.mp4`; note render time in the log.
- [ ] **Step 2:** Make a contact sheet: `ffmpeg -i build/sample/video.mp4 -vf "fps=1,scale=240:-1,tile=8x7" -frames:v 1 build/sample/contact.png`, plus the reference's sheet (same command on the reference mp4), side by side.
- [ ] **Step 3:** Commit `feat(studio): sample story`.
- [ ] **Step 4 (STOP):** Show the owner both contact sheets, three full-size frames and the silent mp4 path; ask whether the look is right. Do not start Task 9 until the owner approves; feed changes back into Tasks 4–7.

### Task 9: Story validator (Python)

**Files:**
- Create: `autopilot/story.py`, `tests/test_story.py`

**Interfaces:**
- Consumes: `studio/catalog.json`, `rules.narration_problems(text) -> list[str]`.
- Produces: `load_catalog(path=ROOT/"studio/catalog.json") -> dict`; `validate(story: dict, catalog: dict) -> list[str]`
  (empty = valid); `words(story) -> int`; `spoken(beat) -> str` (`say` or `text`).
- Rules (each problem a short string naming beat index and field): required top-level keys; slug regex
  `^[a-z0-9-]{3,48}$`; title ≤ 60 chars + `rules.title_problems`; `format` in explainer|levels (`levels` needs
  4–7 beats with a `level` int, strictly increasing from 1); `summary` 1–3 sentences, ≤ 400 chars;
  4–14 beats; total words 130–170; every set/mood/prop/pose/expr/motion/enter/fx/cam move/sign style/
  transition/sfx in catalog; every `chars[].id` in `cast`; cast looks: `"gus"` or dict with keys ⊆
  `costume_keys`; `keep:true` not on beat 0; `remove` ids exist in the previous beat; characters within
  ±(`frame_half_width` × dist) of the camera target in x (Odd Fortune's framing rule); first beat has a
  character on screen; ≥ 2 `sources` with `https` URLs; 3–5 hashtags starting with `#`, none `#Shorts`;
  `rules.narration_problems` on the joined spoken text; no beat text > 22 words.

- [ ] **Step 1:** Tests: `stories/sample/lighthouse.json` (with sources/hashtags added) validates clean; one test per rule with a minimal broken copy asserting the specific message (e.g. `beat 2: unknown pose 'dab'`, `too short: 112 words (130-170)`, `beat 0: no character on screen`, `need ≥ 2 sources`).
- [ ] **Step 2:** `python -m pytest tests/test_story.py -q` → FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: story validator`.

### Task 10: Narration timeline

**Files:**
- Create: `autopilot/timeline.py`, `tests/test_timeline.py`

**Interfaces:**
- Consumes: `voice.synthesize(scenes: list[{"text": str}], voice, rate, workdir, log, fallback, pauses=False) -> list[{"audio", "duration", "words": [(s,e,text)], "voice"}]`; `main.faster_rate` (move it into `timeline.py` as `faster_rate(rate, factor) -> str`).
- Produces: `build(story: dict, vcfg: dict, workdir: Path, max_seconds: float = 60, log=print) -> dict`
  → writes `workdir/voice.wav` (48 kHz mono) and `workdir/timeline.json`, returns the timeline dict plus
  key `"voice"` (who spoke). Beats joined with 0.12 s gap, 0.6 s tail; word times offset by beat start;
  caption words are `beat["text"].split()` (when edge-tts word count differs from text, map by index and
  stretch — the existing `voice.estimate_words` covers the Piper case). Mouth envelope per frame exactly as
  Odd Fortune `tts.py` (RMS per 1/30 s, /95th percentile, clip 0..1, [0.25,0.5,0.25] smoothing).
  Over `max_seconds` → re-record once at `faster_rate`; still over → `raise TooLong(seconds)`.

- [ ] **Step 1:** Tests with a fake `voice.synthesize` (monkeypatch) returning sine-wave wavs of known length: beat starts/ends add up with gaps; words inside each beat; `len(mouth) == ceil(duration*30)`; values in 0..1; a 70 s fake → one re-record call with a faster rate, then `TooLong`; a fake reporting `voice="en_US-ryan-high"` (Piper) → timeline still has words for every caption word.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: narration timeline with mouth envelope`.

### Task 11: Soundtrack — music manifest, SFX, mix

**Files:**
- Create: `autopilot/soundtrack.py`, `music/tracks.yaml` (empty list + commented example), `tests/test_soundtrack.py`
- Modify: `music/README.txt` (owner instructions: download from YouTube Studio → Audio Library, prefer
  "no attribution required", add an entry per file)

**Interfaces:**
- `music/tracks.yaml` entry: `{file: "Track Name.mp3", title: str, artist: str, attribution: str|null, facebook_ok: bool, moods: [curious|tense|upbeat|epic]}`
- Produces: `load_tracks(dir=ROOT/"music") -> list[dict]` (skips entries whose file is missing, logged);
  `pick_track(tracks, mood, platform: "youtube"|"facebook", seed: str) -> dict | None` (facebook → only
  `facebook_ok`; prefer matching mood; deterministic by seed); `SFX_TYPES` (`whoosh, boom, splash, impact, pop, ding, crackle, creak`) synthesized with numpy (adapt Odd Fortune `audio.py`);
  `mix(voice_wav: Path, timeline: dict, story: dict, track: dict|None, out: Path, music_db=-20) -> Path`
  (music looped/trimmed to duration, ducked under voice, SFX placed at `beat.start + sfx.at`, 48 kHz stereo).
  `attribution_line(track) -> str | ""`.

- [ ] **Step 1:** Tests: empty manifest → `pick_track` None for both platforms; track with `facebook_ok:false` → picked for youtube, None for facebook; `mix` with `track=None` writes a wav of the voice duration ±0.05 s; unknown sfx type in story → ValueError (validator catches earlier, this is a guard).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: soundtrack with per-platform music`.

### Task 12: Studio bridge — render, mux, thumbnail

**Files:**
- Create: `autopilot/studio.py`, `tests/test_studio.py`

**Interfaces:**
- Produces: `render(story: dict, timeline: dict, workdir: Path, log=print, node="node") -> Path` (writes
  `workdir/story.json`, `workdir/timeline.json`, runs `node studio/render.js … --out workdir`, returns
  `workdir/video.mp4`; non-zero exit → `RenderError` with the last 20 log lines);
  `mux(video: Path, audio: Path, out: Path) -> Path` (Global Constraints encode settings + loudnorm);
  `thumbnail(video: Path, out: Path) -> Path` (frame 0 as jpg); `stills(story, timeline, workdir, times) -> list[Path]`.

- [ ] **Step 1:** Tests: a fake `node` script that exits 1 printing `render failed at frame 42` → `RenderError` whose message contains `frame 42`; `mux` on a 2 s ffmpeg-generated test video + tone → output has 1 video (1080×1920, 30 fps) + 1 AAC stereo 48 kHz stream (ffprobe); `thumbnail` writes a 1080×1920 jpg.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: studio bridge`.

### Task 13: Gemini writer — research, story, fact-check

**Files:**
- Create: `autopilot/writer.py`, `tests/test_writer.py`
- Modify: `autopilot/llm.py` (add `generate_text(prompt, models, tools=None, temperature=0.7) -> tuple[str, dict]`, returning text and `groundingMetadata`; same retry/fallback rules as `generate_json`; `tools=[{"google_search": {}}]` for grounding; no JSON mime type when tools are set)

**Interfaces:**
- Consumes: `topics.Topic` (Task 14), `story.validate`, `story.load_catalog`, `llm.generate_json`, `llm.generate_text`.
- Produces: `write(topic: Topic, cfg: dict, catalog: dict, log=print) -> dict` (a valid story) or raises
  `WriteFailed(reason)`. Flow: (1) `research(topic)` grounded → notes + source URLs (from grounding chunks;
  each through `check_url(url) -> str|None`, adapted from Odd Fortune); < 2 working sources → WriteFailed
  ("not enough sources"); (2) `draft(topic, notes, catalog, problems=None)` → story JSON; the prompt carries
  the catalog lists, the story shape, the spec's hook/turn/payoff arc, title formats, `format: levels` rules,
  framing rule, NARRATION_RULES, 130–170 words, "never copy existing videos' titles"; (3) `validate`;
  problems → one redraft with problems listed; still invalid → WriteFailed("invalid story: …"); (4)
  `fact_check(story, notes)` → `{"ok": bool, "problems": [...]}`; not ok → one redraft with problems, re-check;
  still not ok → WriteFailed("fact-check failed"). Sources and hashtags set from research, not invented.
- Also: `propose_topics(n: int, existing: list[str], cfg) -> list[dict]` (`{title_idea, category, format, angle}`)
  for the backlog refill.

- [ ] **Step 1:** Tests with monkeypatched `llm` functions: happy path returns a story that validates; an invalid first draft triggers exactly one redraft whose prompt contains the problem text; two invalid drafts → `WriteFailed` with "invalid story"; fact-check fail twice → `WriteFailed("fact-check failed")`; only 1 working source → `WriteFailed("not enough sources")`; grounding 429 → ungrounded research logged `grounding unavailable`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: Gemini story writer with grounding and fact-check`.

### Task 14: Topic backlog with rotation

**Files:**
- Create: `autopilot/topics.py`, `topics/backlog.yaml` (seed ~30 original topics across categories,
  written by the builder with Gemini's help, none a Ricks Clips title), `tests/test_topics.py`

**Interfaces:**
- `topics/backlog.yaml`: list of `{id, title_idea, category, format: explainer|levels, angle, status: queued|used|failed, used_on: date|null, reason: str|null}`.
- Produces: `CATEGORIES = ("history","engineering","science","psychology","laws_jobs_customs","luck_games","what_if","levels")`;
  `@dataclass Topic(id, title_idea, category, format, angle)`; `load(path) -> list[dict]`;
  `next_topic(backlog, history_titles: list[str], recent: list[dict]) -> Topic | None` — first `queued` topic whose
  category differs from the last published video's category **and** whose `format: levels` isn't right after
  another `levels`, and whose normalized title isn't within similarity 0.6 (token Jaccard) of any history title;
  if none passes rotation, the first queued one that passes the similarity check (logged `rotation relaxed`);
  `mark(backlog, id, status, reason=None, date=None)`; `save(path, backlog)`;
  `needs_refill(backlog, minimum=10) -> bool`.

- [ ] **Step 1:** Tests: rotation skips same-category next; two levels in a row avoided; similar title (“Why Lighthouses Blink in Patterns” vs used “Why Lighthouses Flash in Patterns”) skipped; all blocked by rotation → first non-duplicate returned; empty → None; `needs_refill` true below 10 queued.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat: topic backlog with category rotation`.

### Task 15: Metadata, main.py rewrite, config, gate, offline test

**Files:**
- Create: `autopilot/metadata.py`, `tests/test_metadata.py`, `tests/test_main.py`
- Rewrite: `main.py`, `config.yaml`, `tests/test_offline.py`
- Modify: `autopilot/youtube.py` (`upload` keeps its signature; drop `build_metadata`'s crypto logic — `metadata.py` replaces it), `autopilot/facebook.py` (keep `publish_reel`, `delete_video`, errors; remove photo/post/`reel_caption` crypto builder), `autopilot/history.py` (drop `used_headlines`, `fb_post_headlines`; add `titles() -> list[str]`, `last_category() -> str|None`)

**Interfaces:**
- `metadata.build(story, track_yt: dict|None, cfg) -> {"title", "description", "tags", "category_id": "27"}`;
  description = hook line (beat 0 text) → 2–3 sentence summary (story `summary`) → `Sources:` bullet URLs →
  attribution line if any → `Narrated with a synthetic voice.` → hashtags + `#Shorts` last.
  `metadata.reel_caption(story, track_fb, cfg) -> str` (same minus `#Shorts`, < 2,200 chars, no links: sources
  listed as `Sources: <site name>, <site name>` from the URLs' domains).
- `config.yaml` sections: `channel` (name "Gus Explains", language en), `gus` (`enabled: false`,
  `min_backlog: 10`), `llm` (keep models), `sessions` (`short_a: {label: "Short A", start_utc: "16:25", publish_note: "~17:00 UTC"}`,
  `short_b: {label: "Short B", start_utc: "22:25", publish_note: "~23:00 UTC"}`), `max_late_minutes: 120`,
  `voice` (`name: en-US-AndrewMultilingualNeural` or builder's pick, `rate: "+8%"`, `fallback: en_US-ryan-high`),
  `video` (`max_seconds: 60`, `music_db: -20`), `facebook` (keep), `upload` (`category_id: "27"`,
  `privacy_status: public`, `review_window_hours: 0`, `contains_synthetic_media` — builder checks YouTube's
  current rule for code-animated cartoons with synthetic narration and sets it, comment why, `disclaimer:
  "Narrated with a synthetic voice."`).
- `main.py`: `main(argv) -> int` with `--session short_a|short_b` (required), `--platforms`, `--scheduled`,
  `--as-edition`, `--force`, `--no-upload`, `--story PATH` (skip writer, render a given story),
  `--topic "text"` (manual topic). Timed run order: unknown session → 1; `gus.enabled` false → log
  `gus.enabled is false: timed runs skip until the owner turns it on after the rebrand.`, 0; late (> max_late)
  / early (> 30 min before `start_utc`) → skip 0; `published_on(today, session, platform)` guard as today;
  then `make_short(cfg, history, session, date) -> made | None` = topic → writer (on `WriteFailed`: mark topic
  failed, try next topic, max 3 topics → exit 1) → timeline (TooLong → mark failed, next topic) → two mixes
  (`mix_yt.wav`, `mix_fb.wav`) → render once → mux twice (`short.mp4`, `short_fb.mp4`) → thumbnail → metadata;
  `publish(made, pending, cfg)` uploads `short.mp4` to YouTube and `short_fb.mp4` as the Reel, one failure never
  blocks the other; history entry `{date, session, kind: "short", slug, title, category, format, topic_id, voice,
  music_yt, music_fb, video_id, fb_reel_id, trigger, counts, seconds}` written to `output/<stamp>/history_entry.json`
  as now; topic marked used + backlog saved (committed by the workflow along with history). Backlog refill:
  after a publish, if `needs_refill` → `writer.propose_topics(15, …)` appended as queued (failure logged, not fatal).
- `tests/test_offline.py`: no network/keys — mocked `llm`, fake `voice.synthesize` (tone wavs), real engine render of
  a 3-beat story at `--scale 0.5` if Chromium is installed (skip render with a log line otherwise), real mux;
  asserts `output/test/short.mp4` exists with audio and `history_entry.json` has the fields above.

- [ ] **Step 1:** `test_metadata.py`: disclosure exactly once; `#Shorts` last in YouTube, absent in Reel; sources listed; attribution present only when track has one; title ≤ 60. `test_main.py` (monkeypatched make/publish): gate off + `--scheduled` → 0 and no make; gate off + manual `--no-upload` → makes; already published today → skip; YouTube failure still publishes Facebook and returns 1; WriteFailed on 3 topics → 1.
- [ ] **Step 2:** FAIL. **Step 3:** Implement metadata, main, config, trims. **Step 4:** `pytest -q && python tests/test_offline.py` → PASS. **Step 5:** Commit `feat: Gus Explains edition pipeline`.

### Task 16: Remove crypto code and archive history

**Files:**
- Delete: `autopilot/{sources,focus,slate,script,slides,render,thumbnail,seo,news_post,images,lessons,lesson_data,lesson_script,lesson_slides,lesson_meta,reveal,basics,material,diagrams,triggers,triggered,recap,pulse,shorts}.py`, `autopilot/detectors/`, `lessons/`, `basics/`, `tests/{test_lessons.py,lessons/,basics/,fixtures/}` (keep only fixtures the new tests use), `data/triggers.json`, `data/material/`, `assets/backgrounds/`, `.github/workflows/triggers.yml`
- Move: `data/history.json` → `data/archive/crypto-history.json`; new `data/history.json` = `{"videos": []}`
- Modify: `requirements.txt` (drop feedparser, matplotlib if unused; keep edge-tts, piper-tts, google libs, requests, pyyaml, pillow, numpy, soundfile)

- [ ] **Step 1:** `grep -rn "import" autopilot main.py tests | grep -E "sources|focus|slate|lessons|basics|triggers|pulse|shorts|material|diagrams|news_post|images|seo|thumbnail|slides|recap|triggered|reveal"` → no hits after deletion.
- [ ] **Step 2:** `pytest -q && python tests/test_offline.py` → PASS.
- [ ] **Step 3:** Commit `chore: remove crypto pipeline, archive its history`.

### Task 17: Workflow and timers

**Files:**
- Rewrite: `.github/workflows/autopilot.yml`
- Create: `.github/actions/setup/action.yml` (Node 22 + npm ci + `npx playwright install --with-deps chromium` + Python 3.12 + pip + ffmpeg; cache npm/pip/playwright)
- Modify: `setup_cronjobs.py` (sessions from new config; `--delete-retired` deletes every CryptoFX job not in config: names `CryptoFX · <key>`; new jobs named `Gus Explains · <key>`)

**Interfaces:**
- Workflow: `workflow_dispatch` inputs `session` (short_a|short_b), `platforms`, `as_edition`, `scheduled`,
  `story` (optional path), `topic` (optional text), `no_upload` (boolean, passes `--no-upload`); backup crons `42 16 * * *` (short_a) and `42 22 * * *`
  (short_b) mapped in `EDITION:` and `concurrency.group` exactly as today's pattern; `timeout-minutes: 90`;
  artifacts `output/<stamp>/` 7 days; Save history step merges `history_entry.json` and commits
  `data/history.json` + `topics/backlog.yaml` (backlog merge: take origin's file and re-apply this run's
  `mark`/refill — write `output/<stamp>/backlog_changes.json` and add `python -m autopilot.topics apply …`).

- [ ] **Step 1:** Add a test in `tests/test_topics.py` for `apply(backlog, changes) -> backlog` (idempotent: applying twice equals once).
- [ ] **Step 2:** FAIL → implement → PASS.
- [ ] **Step 3:** `python setup_cronjobs.py --dry-run` prints two Gus jobs (16:25, 22:25 UTC daily) and lists the CryptoFX jobs it would delete with `--delete-retired`. Do not run without `--dry-run`.
- [ ] **Step 4:** Commit `ci: Gus Explains workflow and timers`.
- [ ] **Step 5 (owner, after merge):** Actions → Run workflow → `short_a` with `no_upload` ticked. Expected: green run, artifact has `short.mp4`, `short_fb.mp4`, `thumbnail.jpg`; the log shows render minutes (must leave the 16:25 → ~17:00 margin; if over 30 min, tell the owner and move `start_utc` earlier).

### Task 18: Branding

**Files:**
- Create: `studio/branding.js`, `studio/engine/branding.html`, `branding/` outputs, `branding/channel_description.txt`, `branding/README.md` (owner steps)

**Interfaces:**
- `node studio/branding.js` → `branding/youtube_avatar.png` (800×800, Gus's face + shoulders, readable at 98 px),
  `branding/youtube_banner.png` (2560×1440; "GUS EXPLAINS" lettering + Gus + 2–3 cast members in the rock-pillar
  sea world, all text/key art inside the centred 1546×423 safe area), `branding/facebook_profile.png` (720×720),
  `branding/facebook_cover.png` (1640×624; key art inside the centred 1200×462 mobile-safe area).
- `channel_description.txt`: ≤ 1,000 chars, US English, what the channel is ("odd facts, explained with
  cartoons, two new Shorts every day"), no false claims.
- `branding/README.md`: exact click paths for YouTube Studio → Customization (name "Gus Explains", handle
  — owner checks `@GusExplains` availability, fallback suggestions `@GusExplainsIt`, `@GusExplainsShorts`),
  and Facebook Page settings (name, username, profile, cover, About). Note: YouTube allows 2 name changes per 14 days.

- [ ] **Step 1:** Render, then check each PNG's size with `python -c "from PIL import Image;…"` → exact dimensions. Overlay the safe areas on copies (`*_safe.png`, not committed) and check by eye that no text crosses them.
- [ ] **Step 2:** Commit `feat: Gus Explains branding`.
- [ ] **Step 3 (owner):** show the owner the four images; owner applies them by hand.

### Task 19: Old-content deletion script (runs only on owner confirmation)

**Files:**
- Create: `scripts/delete_old_content.py`, `tests/test_delete_old.py`

**Interfaces:**
- CLI: `python scripts/delete_old_content.py [--youtube] [--facebook] [--before YYYY-MM-DD] [--confirm]`.
  Default = dry-run: lists every item (platform, id, date, title) and the count, writes
  `output/deletion-plan.json`. `--confirm` deletes items from that plan only (re-lists first and refuses if the
  live list contains items not in the plan → "plan out of date, re-run without --confirm"), logs each id to
  `output/deletion-log.json`, stops on the first auth/permission error with a fix hint.
- YouTube: list uploads via `channels.list(mine=True)` → uploads playlist → `playlistItems.list` paging;
  delete via existing `youtube.delete_video(video_id)` (needs `LESSON_SCOPES` token: owner runs
  `python get_token.py --lesson-scopes` and updates `YT_REFRESH_TOKEN`; the script detects a 403
  insufficientPermissions and prints that hint). `--before` defaults to the Gus release date so Gus videos are never listed.
- Facebook: list `/{page}/videos`, `/{page}/video_reels`, `/{page}/posts` (paging); delete via
  `DELETE /{id}`; reuse `facebook.py` request/error helpers; permission errors print the needed permission.

- [ ] **Step 1:** Tests with fake API clients: dry-run never calls delete; `--confirm` deletes exactly the planned ids; a new live item not in plan → refuses; 403 on first delete → stops, exit 1, hint printed; items on/after `--before` never listed.
- [ ] **Step 2:** FAIL → implement → PASS.
- [ ] **Step 3:** Commit `feat: old content deletion script (dry-run by default)`.
- [ ] **Step 4 (owner):** The builder never runs `--confirm`. Hand the owner the dry-run command; the owner reviews the plan file and runs `--confirm` themselves if they still want it.

### Task 20: Docs and release checklist

**Files:**
- Rewrite: `CLAUDE.md` (Gus Explains: what it is, pipeline, editions table 16:25/22:25 timers → ~17:00/23:00
  publish, files, formats, decisions incl. rejected AI images / FLUX / paid Gemini images, copying rules,
  gotchas carried over: edge-tts 403, cron-job.org 401/422, git pull before push, Actions UI time zone),
  `README.md` (setup: Node + Chromium + Python + ffmpeg; music manifest; branding; release checklist)

Release checklist in README (owner, in order): 1) merge pause branch + run cron `--disable` (Task 1) ✔
2) repo public (Task 2) 3) approve sample look (Task 8) 4) merge Gus branch 5) add music + `tracks.yaml`
6) rebrand by hand with `branding/` 7) optional: deletion dry-run → confirm 8) `python setup_cronjobs.py
--dry-run` then for real, then `--delete-retired` 9) one manual `no_upload` run, check artifact 10) set
`gus.enabled: true`, push 11) watch the first day's two runs.

- [ ] **Step 1:** Write both docs; every file path they mention exists (`grep -o '`[a-z_/.]*\.\(py\|js\|yaml\|json\)`' CLAUDE.md | …` check by hand).
- [ ] **Step 2:** `pytest -q && node --test studio/test/ && python tests/test_offline.py` → all PASS.
- [ ] **Step 3:** Commit `docs: Gus Explains CLAUDE.md and README`.
