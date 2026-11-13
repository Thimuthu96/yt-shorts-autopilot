"""Gemini story writer: research (Google Search grounding) → story JSON v2 → validate → hook check → fact-check.

    write(topic, cfg, catalog, log=print) -> dict      a valid story, or raises WriteFailed(reason)
    research(topic, cfg, log) -> (notes, sources, hashtags)
    draft(topic, notes, catalog, cfg, problems=None, previous=None) -> dict
    hook_problems(story) -> list[str]                  the deterministic hook rules (spec §11.1)
    hook_check(story, cfg, log) -> list[str]           rules + Gemini self-score (< HOOK_MIN_SCORE fails)
    fact_check(story, notes, cfg) -> {"ok": bool, "problems": [...]}
    check_url(url) -> str | None                       final URL when the page exists (bot walls count as existing)
    propose_topics(n, existing, cfg) -> list[dict]     {title_idea, category, format, angle} for the backlog refill

An invalid draft is redrafted up to twice with the validator's problems (still invalid → WriteFailed "invalid
story"); a weak hook once (hook rules still broken → WriteFailed "hook check failed"); a
failed fact-check once (still failing → WriteFailed "fact-check failed"). Sources and hashtags come from the
research, never from the draft. Gemini being unreachable (RuntimeError from llm) is not a WriteFailed: the
caller stops instead of burning topics.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from autopilot import llm, story as story_mod, topics

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "stories" / "sample" / "lighthouse.json"
GROUNDING = [{"google_search": {}}]
UA = {"User-Agent": "Mozilla/5.0 (compatible; source-check/1.0)"}
HOOK_MIN_SCORE = 7
HOOK_MAX_WORDS = 18
MAX_SOURCES = 5
SECOND_PERSON = re.compile(r"\b(?:you|your|you'd|you're|you'll|you've|yourself)\b", re.I)
# a concrete quantity: digits or a number word of two or more ("one", "half", "double" alone don't count)
NUMBER = re.compile(r"\d|\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
                    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
                    r"hundreds?|thousands?|millions?|billions?|trillions?)\b", re.I)
DEFAULT_TAGS = ("#didyouknow", "#explained", "#facts")
FILLER = ("subscribe", "follow for more", "thanks for watching", "like and share", "let me", "today we")
FILLER_RX = [(f, re.compile(r"\b" + re.escape(f) + r"\b", re.I)) for f in FILLER]
VALIDATE_REDRAFTS = 2


class WriteFailed(Exception):
    pass


def models(cfg: dict) -> list[str]:
    l = cfg.get("llm") or {}
    return [m for m in [l.get("model"), *(l.get("fallback_models") or [])] if m]


# ─── research ──────────────────────────────────────────────────────────────
RESEARCH = """### TASK: research
You are the researcher for "Gus Explains", a YouTube Shorts channel of short cartoon explainers about odd, TRUE facts.
Research this topic with Google Search and report only what reputable sources confirm.

TOPIC: {title}
ANGLE TO CHECK: {angle}

Return plain text in exactly this layout:
VERDICT: TRUE | PARTLY TRUE (say what to correct) | MYTH
FACTS:
- one short fact per line with the number / year / name / place it depends on, then " [n]" pointing to its sources
  (prefer encyclopedias, museums, universities, government and scientific sources, major newspapers)
WAIT-REALLY: the one most surprising true detail, and a concrete stake or number a viewer can picture
DISPUTED:
- popular claims about this topic that are exaggerated, uncertain or false, and what the evidence says
SOURCES:
[1] Page title - full URL
[2] ...
HASHTAGS: 3 to 5 specific hashtags for the topic (no #Shorts)
List 3-6 sources you actually used. Never invent a URL."""


def check_url(url: str) -> str | None:
    """Follow redirects; the final URL if the page exists (401 / 403 / 429 bot walls count as existing)."""
    try:
        r = requests.get(url, headers=UA, timeout=15, allow_redirects=True, stream=True)
        final, code = r.url, r.status_code
        r.close()
        if code < 400 or code in (401, 403, 429):
            return final
    except requests.RequestException:
        pass
    return None


def _cited(text: str) -> list[tuple[str, str]]:
    """(url, title) pairs from the SOURCES block (any https URL in the text as a fallback)."""
    out = []
    for line in text.splitlines():
        m = re.search(r"(https?://[^\s)\]>\"']+)", line)
        if not m:
            continue
        url = m.group(1).rstrip(".,;")
        title = re.sub(r"^\s*(?:\[\d+\]|[-*\d.]+)\s*", "", line[:m.start()]).strip(" -–:|")
        out.append((url, title))
    return out


def _site(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    return re.sub(r"^(?:www|en|m)\.", "", host)


def _hashtags(text: str) -> list[str]:
    m = re.search(r"^HASHTAGS:(.*)$", text, re.M | re.I)
    return clean_hashtags(re.findall(r"#\w+", m.group(1)) if m else [])


def clean_hashtags(tags) -> list[str]:
    out, seen = [], set()
    for t in tags or []:
        t = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(t).lstrip("#"))
        if len(t) < 3 or t.lower() in ("#shorts", "#short") or t.lower() in seen or t[1].isdigit():
            continue
        seen.add(t.lower())
        out.append(t)
    return out[:5]


def research(topic, cfg: dict, log=print) -> tuple[str, list[dict], list[str]]:
    prompt = RESEARCH.format(title=topic.title_idea, angle=topic.angle or "(none given)")
    ms = models(cfg)
    try:
        text, grounding = llm.generate_text(prompt, ms, tools=GROUNDING, temperature=0.3, rounds=1)
        log(f"writer: research grounded ({len(grounding.get('groundingChunks') or [])} search results)")
    except RuntimeError as e:
        log(f"writer: grounding unavailable ({str(e)[:160]}); researching without Google Search")
        text, grounding = llm.generate_text(prompt, ms, temperature=0.3)
    if re.search(r"^VERDICT:\s*MYTH", text, re.M | re.I):
        raise WriteFailed("research: the topic is a myth")
    candidates = [((c.get("web") or {}).get("uri"), (c.get("web") or {}).get("title") or "")
                  for c in grounding.get("groundingChunks") or []]
    candidates += _cited(text)
    sources, seen = [], set()
    for url, title in candidates:
        if len(sources) >= MAX_SOURCES:
            break
        if not url or not url.startswith("http"):
            continue
        final = check_url(url)
        if not final or not final.startswith("https://"):
            log(f"writer: source dropped (not reachable over https): {url[:100]}")
            continue
        key = final.split("#")[0].rstrip("/")
        if key in seen or "vertexaisearch" in final or "google.com/search" in final:
            continue
        seen.add(key)
        sources.append({"url": final, "title": title or _site(final)})
    log(f"writer: {len(sources)} working source(s)")
    if len(sources) < 2:
        raise WriteFailed("not enough sources")
    return text, sources, _hashtags(text)


# ─── the draft ─────────────────────────────────────────────────────────────
DRAFT = """### TASK: draft_story
You write one YouTube Short for "Gus Explains": a fast cartoon explainer of an odd, TRUE fact (45-60 s). An unseen
narrator speaks; round-headed cartoon characters act it out in a bright toon-shaded 3D world rendered by code. You
output the complete story JSON (format v2): the narration split into SHOTS, and the staging of every shot.

TOPIC: {title}
CATEGORY: {category}
FORMAT: {fmt}
ANGLE: {angle}

RESEARCH NOTES (the only facts you may use; every number, name, year and claim must come from these notes, and
nothing the DISPUTED part calls false or uncertain may be stated as fact):
{notes}

## Script
1. HOOK (shots 0-1, at most {hook_max} words together): a second-person scenario with a twist or high stakes, or a
   surprising number. Pattern (structure only, never reuse it): "If your ship got hit by a cannonball, you'd actually
   be one of the lucky ones." Other shapes: "If you..., you'd actually...", "This X could Y", "One X once Y".
   Characters are already on screen and moving in shot 0.
2. SETUP: the situation or problem. 3. TURN(S): the surprising mechanism or story, escalating with concrete facts
   and numbers from the notes; a visible event every 3-6 spoken words. 4. PAYOFF: answers the hook; the last line
   ties back to the opening (so the video loops).
5. 130-170 words in total (count the words of every shot's text). Fast, plain, vivid spoken English.
6. No outro, no sign-off, no "subscribe" / "follow" / "thanks for watching", no question to the audience at the end.
   No first person ("I", "my", "me", "we") except inside a quote from a named source. No hype words ("guaranteed",
   "to the moon"), no predictions. Years are fine.
7. TITLE (<= 60 chars, curiosity without lying), one of: "Why X...", "How X...", "The X That Y", "This X Saved Y",
   "Levels of X", "What If...", "The Job/Law/Rule...". Never copy an existing video's title. No dates, no hashtags,
   no "/" fractions.
8. FORMAT "levels": 4-7 levels, each bigger or nastier than the last, each opening on its own set or lighting
   change; put "level": 1, 2, 3... on the shot that opens each level (ints from 1, strictly increasing).
9. summary: 1-3 sentences, <= 400 chars, the facts of the video for the description. music_mood: curious | tense |
   upbeat | epic.

## Shots
- {shots_min}-{shots_max} shots; each shot's text is 2-8 words (shot 0 up to 10) and is both the caption and the
  voice. Split sentences at natural phrase breaks; keep the punctuation in the text. Optional "say": the same words
  spelled for the voice (e.g. numbers), only when needed.
- Every shot has at least one event or a moving camera (move other than "static"). Put events ON the words they
  illustrate: "at_word" is the 0-based index into that shot's text.split(). A fire / impact / sign / expression lands
  on its word; add an "sfx_mark" event on big moments.
- "keep": true continues the previous shot's set, props and characters (add only what is new, "remove" ids that
  leave); "keep": false builds a fresh set: list every prop and character again. Shot 0 never has keep.
- Camera: prefer presets: {{"frame": preset, "subject": id}} (+ "look_at": id for two_shot and ots, and to aim
  pov). Wide lens is the default (fov 60). Use "roll" (-12..12 degrees) for tension, "angle" to turn the preset,
  and keep the camera moving (push, pull, orbitL/R, panL/R, rise, drop, lowSweep, follow + "follow": projectile id
  to ride a flying prop). Never ots with push or closeUp; never pov with pull, flyOver or lowSweep.
- Transitions (into a shot): null inside a set; "whipL" / "whipR" / "whipU" to change sets (the whip hides the
  change); "iris" for a big chapter turn; "cut" at most 2 times in the whole video.
- Characters fill 40-70 % of the frame: frame them close / medium / low_hero / two_shot. Captions sit at 58 % of
  the frame height, so keep faces in the upper half (presets do this; with explicit target/dist the characters must
  stay within x +- {half} * dist of the target).
- Names and numbers appear as in-world signs (props of the world, text exactly as it should read), not overlays.
- Every id used by an event ("who", "id", "prop", "projectile"), cam "subject" / "look_at" / "follow" must be a
  character or prop present in that shot (spawned in it or kept). Characters must be in "cast". Characters face
  "right", "left" or "front".
- Gus (look "gus") is the channel's curious guide; use him when a guide helps. Other cast members get a look built
  from the look keys (costume, hat, colours, props they hold).
- Space and scale (world units, y up, ground y = 0, the camera looks towards -z): a character is 2.34 tall (head top
  at y 2.34, face at about y 1.9); characters stand near z 0 to -3, 1.2-2 apart side by side. Prop sizes at scale 1
  (width x height): crate 0.9 x 0.9, barrel 0.9 x 1.1, cannon about 2.5 long x 1.3 high (muzzle towards +x), table
  2 x 1 (top at y 1), door 1.6 x 3, chair 0.7 x 1.4, lighthouse 2.6 wide x 7.6 tall, ship 10 long x 2.8 wide.
  Put props a character uses within 1-1.5 of it; set pieces (ship, lighthouse, pillar_rock) far back (z -15 to
  -35) with scale 0.8-1.2 unless the shot is about them.
- Framing: a preset frames its subject, so other characters in that shot must stand near it: close / pov show only
  the subject; medium / low_hero keep others within x +-1.2 of the subject; two_shot needs the look_at partner
  within about 3 of the subject; wide shows about x +-4 around it. With explicit cam {{target, dist, height, angle}}
  every character must stand within x +- {half} * dist of target x (dist 6 → +-1.95, dist 9 → +-2.9).
- Signs: place them above or beside their subject, never over a face: about y 2.8-3.5 above a character, or on a
  wall / post beside it, within the framed area; short text (1-4 words or a number) so it reads at phone size.
- Ids: every prop and character must be declared (in "props" / "chars" of this shot or a kept earlier shot, and
  characters in "cast") BEFORE an event, cam subject / look_at / follow or "remove" uses it; a "keep": false shot
  forgets everything before it.

## Vocabulary (use ONLY these names)
{vocab}

## Story JSON (top level)
{{"slug": "[a-z0-9-] <= 48 chars", "title": "...", "version": 2, "category": "{category_hint}", "format": "{fmt}",
 "music_mood": "...", "cast": {{"id": {{"look": "gus" | {{look keys}}}}}}, "beats": [ shots ], "summary": "...",
 "hashtags": ["#..." 3-5, never #Shorts], "sources": []}}
Each shot: {{"text", "say"?, "level"?, "set": {{"type", "mood"}}, "keep", "remove": [], "props": [{{"id", "type",
"pos": [x,y,z], "rot"?: [deg,deg,deg], "scale"?, "anim"?, "delay"?}}], "chars": [{{"id", "pos", "facing", "pose",
"expr", "talk", "enter"?, "motion"?}}], "signs": [{{"text", "pos", "style", "rot"?: [x,y,z], "delay"?}}],
"fx": [{{"type", "at": [x,y,z], "scale"?, "delay"?, "period"? (beam only)}}], "sfx": [{{"type", "at": seconds}}],
"events": [{{"at_word", "do", ...fields}}], "cam": {{...}}, "transition": null | name}}
(sources stay [] - they are filled from the research.)

## Example: one complete approved story
Use it ONLY as the pattern for structure, pace and staging density. Never reuse its topic, title, lines, signs or
exact staging.
{example}
{previous}{problems}
Return only the JSON object."""


def vocabulary(cat: dict) -> str:
    lines = []
    for k in ("sets", "moods", "props", "poses", "exprs", "motions", "enters", "anims", "fx", "sfx", "events", "acts",
              "surfaces", "cam_frames", "cam_moves", "transitions", "sign_styles", "looks", "costume_keys",
              "costumes", "hats", "glasses", "held_props"):
        if k in cat:
            lines.append(f"{k}: {', '.join(map(str, cat[k]))}")
    lines.append("event fields (need / opt): " + json.dumps(cat.get("event_fields", {}), separators=(",", ":")))
    lines.append("act fields (an \"act\" event: {\"do\": \"act\", \"who\": char, \"act\": name, ...}): "
                 + json.dumps(cat.get("act_fields", {}), separators=(",", ":")))
    lines.append("look keys: \"costume\" (costumes), \"hat\" (hats), \"glasses\" (glasses), \"prop\" (held_props, held in "
                 "the hand); \"shirt\", \"pants\", \"hatColor\", \"stripes\", \"coat\", \"apron\", \"bandana\" = \"#RRGGBB\"; "
                 "\"beard\", \"mustache\", \"badge\" = true or \"#RRGGBB\"; \"crown\", \"helmet\" = true")
    return "\n".join(lines)


def example_text() -> str:
    s = json.loads(EXAMPLE.read_text())
    head = {k: v for k, v in s.items() if k != "beats"}
    beats = ",\n".join(json.dumps(b, separators=(",", ":")) for b in s["beats"])
    return json.dumps(head, separators=(",", ":"))[:-1] + ',"beats":[\n' + beats + "\n]}"


def draft(topic, notes: str, catalog: dict, cfg: dict, problems: list[str] | None = None,
          previous: dict | None = None) -> dict:
    cat = topic.category if topic.category in topics.CATEGORIES else ""
    prev = ("\n\n## Your previous draft (fix the problems below, keep what works)\n"
            + json.dumps(previous, separators=(",", ":"))) if previous else ""
    probs = ("\n\n## Problems to fix (the draft is rejected until every one is gone)\n"
             + "\n".join(f"- {p}" for p in problems)) if problems else ""
    prompt = DRAFT.format(
        title=topic.title_idea, category=cat or f"choose one of {', '.join(topics.CATEGORIES)}",
        category_hint=cat or "one of the categories", fmt=topic.format or "explainer",
        angle=topic.angle or "(find the most surprising true angle in the notes)", notes=notes.strip(),
        hook_max=HOOK_MAX_WORDS, shots_min=25, shots_max=35, half=catalog.get("frame_half_width", 0.325),
        vocab=vocabulary(catalog), example=example_text(), previous=prev, problems=probs)
    out = llm.generate_json(prompt, models(cfg), temperature=0.8)
    if isinstance(out, dict) and set(out) == {"story"} and isinstance(out["story"], dict):
        out = out["story"]
    return out


def _finish(s, topic, sources: list[dict], tags: list[str]) -> dict:
    if not isinstance(s, dict):
        return s
    s["version"] = 2
    if topic.category in topics.CATEGORIES:
        s["category"] = topic.category
    if topic.format in topics.FORMATS:
        s["format"] = topic.format
    if not re.fullmatch(r"[a-z0-9-]{3,48}", str(s.get("slug", ""))):
        s["slug"] = topics.slugify(str(s.get("title") or topic.title_idea), 48)
    s["sources"] = [dict(x) for x in sources]
    s["hashtags"] = clean_hashtags(list(tags) + clean_hashtags(s.get("hashtags")) + list(DEFAULT_TAGS))
    return s


def _problems(s, catalog: dict) -> list[str]:
    if not isinstance(s, dict):
        return ["the story must be one JSON object"]
    p = story_mod.validate(s, catalog)
    text = " ".join(str(b.get("text", "")) for b in s.get("beats", []) if isinstance(b, dict))
    p += [f"narration: no {f!r}" for f, rx in FILLER_RX if rx.search(text)]
    return p


def _valid_draft(topic, notes, catalog, cfg, sources, tags, log, problems=None, previous=None) -> dict:
    s = _finish(draft(topic, notes, catalog, cfg, problems, previous), topic, sources, tags)
    for k in range(VALIDATE_REDRAFTS + 1):
        p = _problems(s, catalog)
        if not p:
            return s
        if k == VALIDATE_REDRAFTS:
            break
        log(f"writer: draft invalid ({len(p)} problem(s)): {'; '.join(p[:6])}; redraft {k + 1}/{VALIDATE_REDRAFTS}")
        s = _finish(draft(topic, notes, catalog, cfg, p, s if isinstance(s, dict) else None), topic, sources, tags)
    raise WriteFailed("invalid story: " + "; ".join(p[:8]))


# ─── checks ────────────────────────────────────────────────────────────────
def hook_problems(s: dict) -> list[str]:
    beats = s.get("beats", [])[:2]
    hook = " ".join(b.get("text", "") for b in beats)
    p = []
    n = len(hook.split())
    if n > HOOK_MAX_WORDS:
        p.append(f"hook rule: shots 0-1 have {n} words (max {HOOK_MAX_WORDS})")
    if not SECOND_PERSON.search(hook) and not NUMBER.search(hook):
        p.append("hook rule: shots 0-1 need a second-person scenario (you / your) or a concrete number or stake")
    return p


HOOK = """### TASK: hook_check
Score the opening of this YouTube Short from 1 to 10 as a scroll-stopping hook. A 10 is a second-person scenario
with a twist or high stakes, or a surprising concrete number, in at most 18 words, that makes a viewer think
"wait, really?" (pattern: "If your ship got hit by a cannonball, you'd actually be one of the lucky ones.").
Plain facts, slow setups, questions without stakes and clickbait the video doesn't pay off score low.

TITLE: {title}
OPENING (shots 0-1): {hook}
WHOLE NARRATION: {narration}

Return JSON: {{"score": 1-10, "problems": ["what makes it weak, one short line each"]}}"""


def hook_check(s: dict, cfg: dict, log=print) -> list[str]:
    p = hook_problems(s)
    beats = s.get("beats", [])
    res = llm.generate_json(HOOK.format(title=s.get("title", ""), hook=" ".join(b["text"] for b in beats[:2]),
                                        narration=" ".join(b["text"] for b in beats)), models(cfg), temperature=0.2)
    try:
        score = float(res.get("score", 0))
    except (TypeError, ValueError, AttributeError):
        score = 0
    log(f"writer: hook score {score:g}/10")
    if score < HOOK_MIN_SCORE:
        why = [str(x) for x in (res.get("problems") if isinstance(res, dict) else None) or []][:3]
        p.append(f"hook score {score:g}/10 (need {HOOK_MIN_SCORE}): " + ("; ".join(why) or "too weak"))
    return p


FACT = """### TASK: fact_check
You are a strict fact-checker. Check every claim in this YouTube Short (narration, title, summary and the in-world
sign texts) against the research notes. A claim fails when the notes don't support it, contradict it, or call it
disputed; a number fails when it differs from the notes; the title fails when the video doesn't pay it off or it
misleads. Ignore style.

TITLE: {title}
NARRATION: {narration}
SIGNS: {signs}
SUMMARY: {summary}

RESEARCH NOTES:
{notes}

Return JSON: {{"ok": true | false, "problems": ["the claim, and what the notes say instead"]}}"""


def _signs(s: dict) -> list[str]:
    out = []
    for b in s.get("beats", []):
        out += [g.get("text", "") for g in b.get("signs", [])]
        out += [e.get("text", "") for e in b.get("events", []) if e.get("do") == "sign"]
    return [x for x in out if x]


def fact_check(s: dict, notes: str, cfg: dict) -> dict:
    res = llm.generate_json(FACT.format(title=s.get("title", ""), narration=" ".join(b["text"] for b in s["beats"]),
                                        signs=" | ".join(_signs(s)) or "(none)", summary=s.get("summary", ""),
                                        notes=notes.strip()), models(cfg), temperature=0.1)
    if not isinstance(res, dict):
        return {"ok": False, "problems": ["fact-check returned no verdict"]}
    probs = [str(x) for x in res.get("problems") or []]
    return {"ok": bool(res.get("ok")) and not probs, "problems": probs}


# ─── the whole write ───────────────────────────────────────────────────────
def write(topic, cfg: dict, catalog: dict, log=print) -> dict:
    log(f"writer: topic {topic.id!r}: {topic.title_idea}")
    notes, sources, tags = research(topic, cfg, log)
    s = _valid_draft(topic, notes, catalog, cfg, sources, tags, log)
    hp = hook_check(s, cfg, log)
    if hp:
        log(f"writer: hook weak: {'; '.join(hp)}; redrafting once")
        s = _valid_draft(topic, notes, catalog, cfg, sources, tags, log, ["hook: " + x for x in hp], s)
        hp = hook_check(s, cfg, log)
        if any(x.startswith("hook rule") for x in hp):
            raise WriteFailed("hook check failed: " + "; ".join(hp))
        if hp:
            log(f"writer: hook still scores low, kept ({'; '.join(hp)})")
    fc = fact_check(s, notes, cfg)
    if not fc["ok"]:
        log(f"writer: fact-check failed: {'; '.join(fc['problems'][:5])}; redrafting once")
        s = _valid_draft(topic, notes, catalog, cfg, sources, tags, log,
                         ["fact-check: " + x for x in fc["problems"] or ["unsupported claims"]], s)
        fc = fact_check(s, notes, cfg)
        if not fc["ok"]:
            raise WriteFailed("fact-check failed: " + "; ".join(fc["problems"][:5]))
        hp = hook_check(s, cfg, log)  # the redraft may have changed the opening: score it again
        if any(x.startswith("hook rule") for x in hp):
            raise WriteFailed("hook check failed after the fact-check redraft: " + "; ".join(hp))
        if hp:
            log(f"writer: after the fact-check redraft the hook scores low, kept ({'; '.join(hp)})")
    log(f"writer: story {s['slug']!r} ({len(s['beats'])} shots, {story_mod.words(s)} words) passed every check")
    return s


# ─── backlog refill ────────────────────────────────────────────────────────
PROPOSE = """### TASK: propose_topics
Propose {n} new topics for "Gus Explains", YouTube Shorts that explain an odd, TRUE, checkable fact in 50 seconds
with cartoon characters.
Categories: {cats}. Formats: explainer, or levels (only for category levels: "Levels of X", 4-7 escalating levels).
Each topic needs a "wait, really?" angle with stakes a viewer can picture, written as the hook would open:
second person ("If you..., you'd actually..."), a twist, or a surprising number. Prefer topics that can be staged
in these sets: {sets}; with these props: {props}; and characters dressed as: {costumes}.
Spread the categories; never repeat or near-copy these existing titles, and never copy existing YouTube videos'
titles:
{existing}

Return JSON: {{"topics": [{{"title_idea": "<= 60 chars, Why X / How X / The X That Y / Levels of X / What If...",
"category": "...", "format": "explainer | levels", "angle": "one or two sentences with the true surprising
detail"}}]}}"""


def propose_topics(n: int, existing: list[str], cfg: dict) -> list[dict]:
    cat = story_mod.load_catalog()
    res = llm.generate_json(PROPOSE.format(n=n, cats=", ".join(topics.CATEGORIES), sets=", ".join(cat["sets"]),
                                           props=", ".join(cat["props"]), costumes=", ".join(cat["costumes"]),
                                           existing="\n".join(f"- {t}" for t in existing[-80:]) or "(none)"),
                            models(cfg), temperature=0.9)
    items = res.get("topics") if isinstance(res, dict) else res
    return [x for x in items or [] if isinstance(x, dict)]
