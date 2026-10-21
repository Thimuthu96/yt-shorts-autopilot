"""Standalone Shorts (epic-standalone-shorts, kind: short): an original 30-40 second vertical piece with its own hook
and script, written from one segment of a long video's Shorts material (autopilot/material.py), or a market-pulse
Short from the day's fetched pulse material (autopilot/pulse.py; short_p, short_a once pulse.enabled). While
`shorts.enabled` is false, timed short_p / short_a / short_b runs log and skip; manual runs make and publish.

    load_materials(root, log)            every valid data/material/*.json (invalid files logged and skipped)
    key(m)                               "<source kind>-<source id>" (what a Short's history entry names)
    used_segments(history)               {(material key, segment id)} already used by published Shorts
    topic(text) / segment_topics(seg) / segment_topic(seg)   the E6-3 topic: normalized text (lowercase; "(…)",
                                         "crypto", "the", "a", "what is / are" and stop-words dropped; plurals singular;
                                         aliases: swing high / low → "swing point", trend line → "trendline"); a
                                         segment's candidates = its term + first hook, its recorded topic = the term's
    recent_topics(materials, history, now)   topics of the concept Shorts of the last COOLDOWN_DAYS (an entry without
                                         `topic`: its segment's term, else its title, else its hook; pulse / market
                                         Shorts never block a concept)
    pick_concept(materials, history, skip, now, log)   round-robin over the Basics / Lesson materials (the source whose
                                         last Short is oldest first, never-used first, ties by publish time): its first
                                         unused segment none of whose topics equals / contains / is contained in a
                                         recent topic (hard 7-day cooldown, refusals logged); a source with
                                         MAX_PER_SOURCE Shorts in 7 days is passed over unless no other source has an
                                         eligible segment (cap relaxed, logged); else None
    pick_market(materials, history, now, log, kinds)  (material, hook index) of a triggered / recap material (`kinds`;
                                         pulse only when passed) under
                                         MARKET_MAX_DAYS old with an unused hook candidate and fewer than
                                         MAX_PER_MARKET Shorts, else None (an old or used-up source is logged)
    pick(materials, history, now, log)   the daily mix (short_b; short_a until pulse.enabled): a market Short when
                                         one is due (about 4 a week from 2 market videos), else a concept Short
                                         (pick_concept: source rotation + topic cooldown), else None (slot skipped)
    latest_long(history, now)            the related video of a pulse Short: the newest counting basics / lesson /
                                         triggered / recap upload with a video id whose publish time (publish_at,
                                         else date) has passed → its id, else None (no link line)
    pick_pulse(fresh, materials, history, now, log, skip)   the pulse-first pick (epic-shorts-reach 6.2; short_p,
                                         short_a once pulse.enabled): ("pulse", fresh, hook index) from the material
                                         this run built only (never an earlier one), else ("concept", material,
                                         segment) (pick_concept), else None. Pulse Shorts reuse the market path:
                                         write_market (today's-data wording), render_market_slides, MARKET PULSE chip,
                                         "▶ Latest video" link line, no "From the full video" line
    stock(materials, history, now, also) eligible concept segments left (unused, no recent topic; segments sharing
                                         a topic count once; `also` = this Short's (material key, segment id, topic)
                                         counted as used); under LOW_STOCK → a low-stock warning
    write_market(cfg, m, idx, log)       the candidate is the hook; Gemini writes the scenes from the material's
                                         fetched numbers + causes only (triggered.unknown_numbers); 3 attempts
    render_market_slides(...)            hook card (frame 0: the card words over the lead coin's badge + %-move pill
                                         and its move chart) → the move chart draw-in (triggered.draw_move_chart), the
                                         cause → coins flow diagram with step reveal, the key numbers
    fingerprint(text) / similarity(a, b) the originality guard: a MinHash of the script's word 3-grams (stored
                                         in the Short's history entry); a script whose similarity to any earlier
                                         Short's reaches MAX_SIMILARITY is rewritten once, then TooClose (the run
                                         moves to another segment / hook); a hook an earlier Short used is rejected
    opening_problems(text)               a subscribe ask in the first sentence → [reason] (narration-rules.md)
    check_script(cfg, pkg, known)        deterministic problems: every scene narrated, word bounds, narration
                                         rules, no subscribe ask in the opening, spoken numbers in the facts
    write_concept(cfg, m, seg, log)      Gemini writes {hook, scenes: hook / explain / payoff}; 3 attempts
    render_slides(cfg, m, seg, pkg, wd)  9:16: the hook card (frame 0, `cover`) → the term, the segment's diagram
                                         with step reveal (diagrams.step_layers) or its fact, the payoff card
    hook_card(ctx, text, m, seg, log)    frame 0 (E6-4; = thumbnail.jpg = the Reel cover, its info kept on the cover
                                         slide as `frame0`): 1-CARD_WORDS card words (a longer hook is cut) on top of a
                                         visual, never text alone: market / pulse → the lead coin's drawn badge +
                                         %-move pill ("−7.2% · 24h", recap "· 7d") over its move chart (no ≥ 2-point
                                         series → the badge card); concept → the segment's diagram fully drawn (full
                                         spec, then without notes), else the icon card (candles, coin badge, term
                                         pill; logged). Layout-relative: PORTRAIT and LANDSCAPE
    text_pages(text) / text_scene(...)   text slides hold ≤ TEXT_WORDS (14) body words (text_slide raises on more);
                                         a longer text → ceil(n / 14) near-equal pages (breaks at a sentence / clause
                                         end within ±2 words), page 1 the scene's slide, the rest its `pages`, which
                                         share the scene's narration time by word count (render.build_video)
    title_problems(hook) / card_problems(card)   packaging.md Short row: the hook question is the title (≤ 60
                                         characters, rules.title_problems); the hook card (frame 0) carries 1-4 words
    package(cfg, pkg, ctx, log)          a hook breaking a title rule is rewritten once by Gemini, else
                                         RuntimeError ("Short packaging"); a bad card falls back to the term / hook
    source_link(m) / studio_task(...)    the related video: https://youtu.be/<source youtube_id> on the description's
                                         and Reel caption's first line (pulse: youtube_id = the latest long video);
                                         the Data API has no related-video field, so after an upload one line asks
                                         the owner to set it in Studio
    metadata(cfg, m, seg, pkg)           title = hook (no hashtag); description = link, hook, payoff, source, the
                                         disclosure line once, hashtags (#Shorts last); reel_caption(meta, cfg):
                                         the same metadata without #Shorts
"""
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from autopilot import diagrams, material, rules
from autopilot.basics import unknown_numbers as _concept_unknown
from autopilot.lesson_slides import BG, FG, MUTED, PORTRAIT, Layout, _flow, _font, _title_font
from autopilot.llm import generate_json
from autopilot.script import _models
from autopilot.slides import DOWN, PANEL, UP, _hex, _wrap
from autopilot.thumbnail import _fit as _fit_font

MAX_TITLE = 60  # packaging.md: a Short's title is its hook question, 60 characters or fewer
CARD_WORDS = 4  # the hook card (frame 0): 1-4 words
MIN_WORDS, MAX_WORDS = 70, 105  # cfg shorts.min_words / max_words: 30-40 s at +0%
SCENES = ("hook", "explain", "payoff")
CONCEPT_SOURCES = ("basics", "lesson")
MARKET_MAX_DAYS = 3  # a market Short goes up within 3 days of its source video
MAX_PER_MARKET = 2  # up to 2 market Shorts per source, each from a distinct hook candidate
LOW_STOCK = 7  # eligible concept segments: under half a week of evergreen Shorts → a low-stock warning
COOLDOWN_DAYS = 7  # E6-3: no concept topic repeats within 7 days (hard)
MAX_PER_SOURCE = 2  # E6-3: at most 2 Shorts per Basics / Lesson material in 7 days (relaxed only when nothing else)
CHIPS = {"basics": "CRYPTO BASICS", "lesson": "TRADING LESSON", "triggered": "WHY IT MOVED", "recap": "WEEKLY RECAP",
         "pulse": "MARKET PULSE"}
DISCLAIMER = "Education only · Not financial advice"
SUBSCRIBE_OPEN = re.compile(r"\bsubscri[bp]\w*|\bhit the (?:bell|like)\b|\blike and (?:share|follow)\b|"
                            r"\bfollow (?:us|the channel|for more)\b|\bturn on (?:the )?notifications?\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
DIAGRAM_GAP = 44
MAX_SIMILARITY = 0.5  # cfg shorts.max_similarity: share of equal MinHash slots (≈ word 3-gram Jaccard overlap)
FP_SLOTS = 32


class TooClose(RuntimeError):
    """A script stayed too close to an earlier Short's after one rewrite: try another segment / hook."""


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _log(msg):
    print(msg)


# ─── material ──────────────────────────────────────────────────────────────

def key(m: dict) -> str:
    return f"{m['source']['kind']}-{m['source']['id']}"


def load_materials(root: Path, log=_log) -> list[dict]:
    out = []
    for p in sorted((Path(root) / material.FOLDER).glob("*.json")):
        try:
            m = material.load(p)
            problems = material.validate(m)
        except Exception as e:
            problems = [str(e)]
        if problems:
            log(f"Shorts: material {p.name} skipped: {'; '.join(problems)}")
            continue
        out.append(m)
    return out


def _published(m: dict) -> str:
    return str(m.get("published_at") or "")


def _shorts(history) -> list[dict]:
    return [v for v in history.uploaded() if v.get("kind") == "short"]


def used_segments(history) -> set[tuple[str, str]]:
    return {(v.get("material"), v.get("segment")) for v in _shorts(history) if v.get("material")}


def used_hooks(history) -> set[str]:
    return {_clean(v.get("hook")).lower() for v in _shorts(history) if v.get("hook")}


def fingerprints(history) -> list[list[str]]:
    return [v["fingerprint"] for v in _shorts(history) if v.get("fingerprint")]


def _shingles(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {" ".join(words[i:i + 3]) for i in range(max(1, len(words) - 2))} if words else set()


def fingerprint(text: str) -> list[str]:
    """MinHash (FP_SLOTS slots, 8 hex digits each) of the text's word 3-grams; similar texts share slots."""
    sh = _shingles(text) or {""}
    return [min(hashlib.blake2b(f"{k}:{g}".encode(), digest_size=4).hexdigest() for g in sh)
            for k in range(FP_SLOTS)]


def similarity(a: list[str], b: list[str]) -> float:
    n = min(len(a or []), len(b or []))
    return sum(x == y for x, y in zip(a[:n], b[:n])) / n if n else 0.0


def script_text(pkg: dict) -> str:
    return " ".join(s.get("text") or "" for s in pkg["scenes"])


def _limit(cfg: dict) -> float:
    return float((cfg.get("shorts") or {}).get("max_similarity", MAX_SIMILARITY))


# ─── concept rotation + topic cooldown (epic-shorts-reach E6-3) ─────────────

TOPIC_STOP = frozenset((
    "a an the what is are was were be been being how do does did why when where which who whom of in on at to for "
    "from by with and or vs versus as into about it its this that these those you your can should could would will "
    "just really actually crypto").split())
KEEP_S = frozenset("news series species bias gas plus always perhaps canvas atlas basics analytics economics".split())
TOPIC_ALIASES = ((re.compile(r"\bswing (?:high|low)(?: (?:swing )?(?:high|low))*\b"), "swing point"),
                 (re.compile(r"\btrend line\b"), "trendline"))


def _singular(w: str) -> str:
    if len(w) <= 3 or w in KEEP_S or w.isdigit():
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "xes", "zes", "ches", "shes")):  # losses → loss, taxes → tax, addresses → address
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _collapse(words: list[str]) -> list[str]:
    """Drop immediately repeated runs of 1-3 words ("swing point swing point" → "swing point")."""
    changed = True
    while changed:
        changed = False
        for n in (1, 2, 3):
            for i in range(len(words) - 2 * n + 1):
                if words[i:i + n] == words[i + n:i + 2 * n]:
                    words = words[:i + n] + words[i + 2 * n:]
                    changed = True
                    break
            if changed:
                break
    return words


def topic(text) -> str:
    """The normalized topic of a term / hook / title: lowercase, "(…)" dropped, words [a-z0-9]+ without stop-words
    (incl. crypto, what, is, are, how, do), plurals singular, aliases, repeats collapsed. "" when nothing is left."""
    t = re.sub(r"\([^)]*\)", " ", str(text or "").lower())
    t = re.sub(r"['’]s\b|['’]", "", t)  # Bitcoin's → bitcoin, What's → what
    words = [_singular(w) for w in re.findall(r"[a-z0-9]+", t) if w not in TOPIC_STOP]
    joined = " ".join(words)
    for pat, rep in TOPIC_ALIASES:
        joined = pat.sub(rep, joined)
    return " ".join(_collapse(joined.split()))


def segment_topics(seg: dict) -> list[str]:
    """A segment's candidate topics: its normalized term and its first hook (empty ones dropped, no duplicates)."""
    out = []
    for t in (topic(seg.get("term")), topic((seg.get("hooks") or [""])[0])):
        if t and t not in out:
            out.append(t)
    return out


def segment_topic(seg: dict) -> str:
    """The topic a concept Short records: the normalized term, else its first hook's."""
    return topic(seg.get("term")) or topic((seg.get("hooks") or [""])[0])


def overlaps(a: str, b: str) -> bool:
    """Equal, or one contains the other as whole words; an empty topic never overlaps."""
    return bool(a and b) and (f" {a} " in f" {b} " or f" {b} " in f" {a} ")


def _entry_at(v: dict) -> datetime | None:
    return _when(v.get("date") or "") or _when(v.get("brief_date") or "")


def _concept_shorts(history) -> list[dict]:
    return [v for v in _shorts(history) if (v.get("short_kind") or "concept") == "concept"]


def recent_topics(materials: list[dict], history, now: datetime) -> list[str]:
    """Topics of the concept Shorts of the last COOLDOWN_DAYS before `now` (age: `date`, else `brief_date`). An entry
    without `topic` gets its segment's term (material key + segment id in the loaded material), else its title, else
    its hook. Pulse / market Shorts are left out: they never block a concept."""
    segs = {(key(m), s["id"]): s for m in materials for s in m.get("segments") or []}
    since, out = now - timedelta(days=COOLDOWN_DAYS), []
    for v in _concept_shorts(history):
        at = _entry_at(v)
        if at is None or at <= since:
            continue
        seg = segs.get((v.get("material"), v.get("segment")))
        t = (topic(v.get("topic")) or (topic(seg.get("term")) if seg else "") or topic(v.get("title"))
             or topic(v.get("hook")))
        if t and t not in out:
            out.append(t)
    return out


def _clash(cands: list[str], recent: list[str]) -> tuple[str, str] | None:
    for c in cands:
        for r in recent:
            if overlaps(c, r):
                return c, r
    return None


def _concept_materials(materials: list[dict]) -> list[dict]:
    return [m for m in materials if m["source"]["kind"] in CONCEPT_SOURCES]


def stock(materials: list[dict], history, now: datetime | None = None, also: tuple | None = None) -> int:
    """Eligible segments of the Basics / Lesson material (unused, no topic overlapping a concept Short of the last
    COOLDOWN_DAYS; segments sharing a topic count once): what evergreen concept Shorts can still be made from.
    Counted greedily in pick order (materials by publish time, concept segments before the overview): a counted
    segment's topic joins the recent topics. `also` = (material key, segment id, topic) of the Short being made,
    counted as already used."""
    now = now or datetime.now(timezone.utc)
    used, recent = used_segments(history), recent_topics(materials, history, now)
    if also:
        used.add((also[0], also[1]))
        if len(also) > 2 and also[2]:
            recent.append(also[2])
    n = 0
    for m in sorted(_concept_materials(materials), key=_published):
        for s in sorted(m["segments"], key=lambda s: s.get("kind") != "concept"):
            if (key(m), s["id"]) in used or _clash(segment_topics(s), recent):
                continue
            n += 1
            recent.append(segment_topic(s))
    return n


def _first_eligible(m: dict, used: set, recent: list[str], log) -> dict | None:
    """The material's first unused segment (concept segments before the overview) with no recent topic; each
    topic refusal is logged."""
    for s in sorted(m["segments"], key=lambda s: s.get("kind") != "concept"):
        if (key(m), s["id"]) in used:
            continue
        hit = _clash(segment_topics(s), recent)
        if hit:
            log(f'Shorts: {key(m)} · {s["id"]} refused: topic "{hit[0]}" overlaps "{hit[1]}", a concept Short of the '
                f"last {COOLDOWN_DAYS} days")
            continue
        return s
    return None


def pick_concept(materials: list[dict], history, skip: set | None = None, now: datetime | None = None,
                 log=_log) -> tuple[dict, dict] | None:
    """Round-robin over the Basics / Lesson materials: the source whose last Short is oldest first (never-used
    sources first; ties by the material's publish time, oldest first), its first eligible segment (unused, not in
    `skip`, no topic overlapping a concept Short of the last COOLDOWN_DAYS). A source with MAX_PER_SOURCE Shorts in
    the last COOLDOWN_DAYS is passed over (logged) unless no other source has an eligible segment (cap relaxed,
    logged). None when nothing is eligible."""
    now = now or datetime.now(timezone.utc)
    used = used_segments(history) | set(skip or ())
    recent = recent_topics(materials, history, now)
    since = now - timedelta(days=COOLDOWN_DAYS)
    last, count = {}, {}
    for v in _shorts(history):
        k, at = v.get("material"), _entry_at(v)
        if not k or at is None:
            continue
        if k not in last or at > last[k]:
            last[k] = at
        if at > since:
            count[k] = count.get(k, 0) + 1
    floor = datetime.min.replace(tzinfo=timezone.utc)
    order = sorted(_concept_materials(materials),
                   key=lambda m: (key(m) in last, last.get(key(m), floor), _published(m)))
    capped = None
    for m in order:
        s = _first_eligible(m, used, recent, log)
        if s is None:
            continue
        n = count.get(key(m), 0)
        if n >= MAX_PER_SOURCE:
            log(f"Shorts: {key(m)} already has {n} Shorts in the last {COOLDOWN_DAYS} days (cap {MAX_PER_SOURCE}); "
                "trying another source")
            capped = capped or (m, s)
            continue
        return m, s
    if capped:
        log(f"Shorts: no other source has an eligible segment; the per-source cap is relaxed for {key(capped[0])}")
    return capped


def _when(text: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def hook_id(idx: int) -> str:
    return f"hook_{idx}"


def pick_market(materials: list[dict], history, now: datetime, log=_log,
                skip: set | None = None, kinds: tuple = material.VIDEO_MARKET_SOURCES) -> tuple[dict, int] | None:
    """The oldest market material of a source kind in `kinds` (default: triggered / recap, the current mix; pulse
    material only when asked for, `kinds=("pulse",)`) still under MARKET_MAX_DAYS old with fewer than MAX_PER_MARKET
    Shorts and an unused hook candidate (by index, and its text unused by any Short) → (material, hook index); a
    source over the age limit or used up is logged."""
    used, hooks = used_segments(history) | set(skip or ()), used_hooks(history)
    count = {}
    for v in _shorts(history):
        count[v.get("material")] = count.get(v.get("material"), 0) + 1
    for m in sorted((m for m in materials if m["source"]["kind"] in kinds), key=_published):
        k, at = key(m), _when(m.get("published_at"))
        if at is not None and at > now:  # scheduled (publishAt) and not public yet
            continue
        if at is None or now - at >= timedelta(days=MARKET_MAX_DAYS):
            if at is not None and now - at < timedelta(days=MARKET_MAX_DAYS + 7):
                log(f"Shorts: {k} is {(now - at).days} days old (market Shorts only within {MARKET_MAX_DAYS} days); "
                    "refused")
            continue
        if count.get(k, 0) >= MAX_PER_MARKET:
            log(f"Shorts: {k} already has {MAX_PER_MARKET} market Shorts; refused")
            continue
        free = [i for i, h in enumerate(m["market"]["hooks"])
                if (k, hook_id(i)) not in used and _clean(h).lower() not in hooks]
        if free:
            return m, free[0]
    return None


def latest_long(history, now: datetime) -> str | None:
    """The related long video of a pulse Short: the newest counting basics / lesson / triggered / recap upload with
    a YouTube id whose publish time (publish_at when scheduled, else the run's date) has passed; None when none."""
    from autopilot.slate import LONG_KINDS
    best, best_at = None, None
    for v in history.uploaded():
        if v.get("kind") not in LONG_KINDS or not v.get("video_id") or not v.get("counts", True):
            continue
        at = _when(v.get("publish_at") or v.get("date") or "")
        if at is None or at > now:
            continue
        if best_at is None or at >= best_at:
            best, best_at = v["video_id"], at
    return best


def pick_pulse(fresh: dict | None, materials: list[dict], history, now: datetime, log=_log,
               skip: set | None = None):
    """The pulse-first pick: ("pulse", fresh, hook index) when the material this run built (`fresh`; never an
    earlier one) has an unused hook (pick_market with kinds=("pulse",)), else ("concept", material, segment)
    (pick_concept: source rotation + topic cooldown), else None (slot skipped)."""
    got = pick_market([fresh], history, now, log, skip, kinds=(material.PULSE,)) if fresh else None
    if got:
        return ("pulse", *got)
    got = pick_concept(materials, history, skip, now=now, log=log)
    return ("concept", *got) if got else None


def pick(materials: list[dict], history, now: datetime, log=_log, skip: set | None = None):
    """("market", material, hook index) when a market Short is due, else ("concept", material, segment)
    (pick_concept: source rotation + topic cooldown), else None. `skip`: (material key, segment / hook id) pairs
    this run already gave up on (TooClose)."""
    got = pick_market(materials, history, now, log, skip)
    if got:
        return ("market", *got)
    got = pick_concept(materials, history, skip, now=now, log=log)
    return ("concept", *got) if got else None


# ─── script ────────────────────────────────────────────────────────────────

def _bounds(cfg: dict) -> tuple[int, int]:
    sc = cfg.get("shorts") or {}
    return int(sc.get("min_words", MIN_WORDS)), int(sc.get("max_words", MAX_WORDS))


def first_sentence(text: str) -> str:
    parts = _SENTENCE.split(_clean(text), maxsplit=1)
    return parts[0] if parts else ""


def opening_problems(text: str) -> list[str]:
    """A Short never opens with a subscribe ask (narration-rules.md, Delivery): the first sentence is checked."""
    m = SUBSCRIBE_OPEN.search(first_sentence(text))
    return [f'subscribe ask in the opening: "{m.group(0)}"'] if m else []


def _words(scenes: list[dict]) -> int:
    return sum(len((s.get("text") or "").split()) for s in scenes)


def check_script(cfg: dict, pkg: dict, known: dict, unknown=_concept_unknown) -> list[str]:
    lo, hi = _bounds(cfg)
    scenes = pkg.get("scenes") or []
    texts = {s.get("id"): _clean(s.get("text")) for s in scenes}
    out = [f"scene '{k}': no narration" for k in SCENES if not texts.get(k)]
    n = _words(scenes)
    if not lo <= n <= hi:
        out.append(f"{n} words (target {lo}-{hi})")
    spoken = " ".join(texts.get(k, "") for k in SCENES)
    out += [f"narration rule: {r}" for r in rules.narration_problems(spoken)]
    out += opening_problems(spoken)
    bad = unknown(spoken, known)
    if bad:
        out.append("numbers not in the material: " + ", ".join(bad))
    return out


def _parse(answer) -> dict:
    a = answer if isinstance(answer, dict) else {}
    got = {s.get("id"): _clean(s.get("text")) for s in a.get("scenes") or [] if isinstance(s, dict)}
    return {"hook": _clean(a.get("hook")), "card": _clean(a.get("card")),
            "scenes": [{"id": k, "text": got.get(k, "")} for k in SCENES]}


def _concept_prompt(cfg: dict, m: dict, seg: dict, problems: list[str]) -> str:
    lo, hi = _bounds(cfg)
    ch = cfg.get("channel") or {}
    src = {"episode": m["source"]["title"], "term": seg["term"], "facts": seg["facts"],
           "episode_narration": seg["narration"], "hook_ideas": seg["hooks"]}
    redo = ("\nYour last draft was rejected: " + "; ".join(problems) + "\n") if problems else ""
    return f"""You write a NEW standalone YouTube Short ({lo}-{hi} words, 30-40 seconds) for
{ch.get('display_name', 'CryptoFX Daily')}, a crypto data desk. It explains ONE idea from a longer episode, with its
own hook and its own wording: never copy the episode narration's sentences.

SOURCE (the only facts you may state):
{json.dumps(src, ensure_ascii=False, indent=1)}

Write three scenes:
- "hook": one curiosity question or tension line about the idea (the first sentence is the hook).
- "explain": the idea in short, plain sentences; name each part of the picture as it comes up.
- "payoff": the one thing to remember, looping back to the hook.
Rules:
- Only the facts above. No other number, product, company, date or claim; no prices, predictions or advice.
- Never ask viewers to subscribe, like or follow, and above all never in the opening.
- No greetings, no "in this video", no sign-off.
- "hook" (the title): a question of 60 characters or fewer, no date, no hashtag, no hype words.
- "card": 1-4 words for the opening card (frame 0), e.g. "WHAT IS AN ETF?".
{rules.NARRATION_RULES}{redo}
Return JSON: {{"hook": "...", "card": "...", "scenes": [{{"id": "hook", "text": "..."}}, {{"id": "explain", "text": "..."}},
{{"id": "payoff", "text": "..."}}]}}"""


def title_problems(hook: str) -> list[str]:
    hook = _clean(hook)
    out = [] if hook else ["no hook"]
    if len(hook) > MAX_TITLE:
        out.append(f"title is {len(hook)} characters (at most {MAX_TITLE})")
    if hook and not hook.endswith("?"):
        out.append("title must be the hook question (ends with '?')")
    return out + [f"title {r}" for r in rules.title_problems(hook)]


def card_problems(card: str) -> list[str]:
    return rules.thumbnail_text_problems(_clean(card), max_words=CARD_WORDS) if _clean(card) else ["no card words"]


def _card_fallback(pkg: dict, term: str) -> str:
    for c in ((_clean(term).upper() + "?") if term else "", " ".join(_clean(pkg["hook"]).upper().split()[:CARD_WORDS])):
        if not card_problems(c):
            return c
    return "KEY IDEA"


def _rewrite_prompt(pkg: dict, problems: list[str], context: str) -> str:
    return f"""Rewrite the title of a YouTube Short. It is the Short's hook question, read before the video plays.
Current title: "{pkg['hook']}"
Problems: {'; '.join(problems)}
What the Short says: {context}
Rules: a question of {MAX_TITLE} characters or fewer, ending with "?"; no date, no session or time stamp, no hashtag,
no price target, no "10x", no "explode", no hype. Also give 1-{CARD_WORDS} words for the opening card.
Return JSON: {{"hook": "...", "card": "..."}}"""


def package(cfg: dict, pkg: dict, term: str, log=_log) -> dict:
    """The packaging rules on a written script (in place): a title breaking them is rewritten once (Gemini),
    then RuntimeError("Short packaging: …"); the card words fall back to the term or the hook's first words."""
    problems = title_problems(pkg["hook"])
    if problems:
        log(f"Short title rewrite ({pkg['hook']!r}): {'; '.join(problems)}")
        context = " ".join(s["text"] for s in pkg["scenes"])
        got = generate_json(_rewrite_prompt(pkg, problems, context), _models(cfg), temperature=0.5) or {}
        hook, card = _clean(got.get("hook")), _clean(got.get("card"))
        again = title_problems(hook)
        if again:
            raise RuntimeError(f"Short packaging: the title {hook or pkg['hook']!r} still breaks the rules after one "
                               f"rewrite ({'; '.join(again)})")
        pkg["hook"], pkg["card"] = hook, card or pkg.get("card")
    if card_problems(pkg.get("card") or ""):
        pkg["card"] = _card_fallback(pkg, term)
    log(f"Short title: {pkg['hook']} · card: {pkg['card']}")
    return pkg


def concept_facts(m: dict, seg: dict) -> dict:
    return {"term": seg["term"], "facts": seg["facts"], "narration": seg["narration"], "title": m["source"]["title"]}


def market_facts(m: dict) -> dict:
    mk = m["market"]
    return {"numbers": mk["numbers"], "total_cap_change_24h": mk.get("total_cap_change_24h"),
            "causes": mk.get("causes"), "cause_headline": mk.get("cause_headline"), "data_source": mk["data_source"]}


def _market_prompt(cfg: dict, m: dict, idx: int, problems: list[str]) -> str:
    lo, hi = _bounds(cfg)
    ch = cfg.get("channel") or {}
    hook = m["market"]["hooks"][idx]
    period = "this week" if m["source"]["kind"] == "recap" else "in the last 24 hours"
    redo = ("\nYour last draft was rejected: " + "; ".join(problems) + "\n") if problems else ""
    if m["source"]["kind"] == material.PULSE:  # no long video behind it: today's fetched data is the source
        source = ("It answers that hook in its own words from today's fetched market data below (a market pulse: no "
                  "long video behind it). If no headline is given, say no single story explains the move.")
    else:
        source = f"It answers that hook in its own words (the long video \"{m['source']['title']}\" is the source; never copy it)."
    return f"""You write a NEW standalone YouTube Short ({lo}-{hi} words, 30-40 seconds) for
{ch.get('display_name', 'CryptoFX Daily')}, a crypto data desk, about a market move {period}.
HOOK: {hook}
{source}

FETCHED DATA (the only facts and numbers you may state; change_24h / change_7d are percent):
{json.dumps(market_facts(m), ensure_ascii=False, indent=1)}

Write three scenes:
- "hook": opens with the hook (a tension line with the real move).
- "explain": why it moved, only from the headlines above; name the news first, then each coin as it comes up.
- "payoff": the one number to remember, looping back to the hook.
Rules:
- Every number must round from a value above. No predictions, targets, prices to come, advice or buy/sell words.
- Never ask viewers to subscribe, like or follow, and above all never in the opening.
- No greetings, no "in this video", no sign-off. "card": 1-4 words for the opening card, e.g. "WHY -7%?".
{rules.NARRATION_RULES}{redo}
Return JSON: {{"card": "...", "scenes": [{{"id": "hook", "text": "..."}}, {{"id": "explain", "text": "..."}},
{{"id": "payoff", "text": "..."}}]}}"""


def _original(cfg: dict, pkg: dict, earlier: list, hooks: set, rewritten: bool, log=_log) -> list[str]:
    """The originality guard on a passing draft: [] = original (its fingerprint set on pkg); a re-used hook is a
    problem; a script too close to an earlier Short's is one problem (the one rewrite), then TooClose."""
    if _clean(pkg["hook"]).lower() in hooks:
        return [f"hook {pkg['hook']!r} was used by an earlier Short; write a different one"]
    fp = fingerprint(script_text(pkg))
    close = max((similarity(fp, e) for e in earlier), default=0.0)
    if close >= _limit(cfg):
        if rewritten:
            raise TooClose(f"script still {close:.0%} like an earlier Short's after one rewrite")
        log(f"Short script too close to an earlier Short's ({close:.0%} overlap); rewriting once")
        return [f"the script is {close:.0%} like an earlier Short's; use different wording and a different angle"]
    pkg["fingerprint"] = fp
    return []


def _write(cfg: dict, what: str, prompt, known: dict, unknown, fix_hook, earlier: list, hooks: set, log) -> dict:
    """3 attempts at a draft passing check_script, plus one originality rewrite."""
    problems: list[str] = []
    attempt, failed, rewritten = 0, 0, False
    while failed < 3:
        attempt += 1
        log(f"Writing the Short script ({what}, attempt {attempt})...")
        pkg = _parse(generate_json(prompt(problems), _models(cfg), temperature=0.8))
        fix_hook(pkg)
        problems = check_script(cfg, pkg, known, unknown=unknown)
        if not problems:
            problems = _original(cfg, pkg, earlier, hooks, rewritten, log)
            if not problems:
                log(f"Short script: {_words(pkg['scenes'])} words · hook: {pkg['hook']}")
                return pkg
            if problems[0].startswith("the script is"):
                rewritten = True
                continue
        failed += 1
        log(f"Discarding Short draft: {'; '.join(problems)}")
    raise RuntimeError(f"Could not write a valid Short in 3 attempts: {'; '.join(problems)}")


def write_market(cfg: dict, m: dict, idx: int, log=_log, earlier: list | None = None,
                 hooks: set | None = None) -> dict:
    """{hook (= hook candidate idx), card, scenes, fingerprint} for a market Short; numbers only from the
    material; `earlier` = earlier Shorts' fingerprints, `hooks` = their hooks (originality guard)."""
    from autopilot.triggered import unknown_numbers

    def fix(pkg):
        pkg["hook"] = _clean(m["market"]["hooks"][idx])
    pkg = _write(cfg, f"{key(m)} · {hook_id(idx)}", lambda p: _market_prompt(cfg, m, idx, p), market_facts(m),
                 unknown_numbers, fix, earlier or [], set(), log)
    return package(cfg, pkg, "", log)


def write_concept(cfg: dict, m: dict, seg: dict, log=_log, earlier: list | None = None,
                  hooks: set | None = None) -> dict:
    """{hook, card, scenes, fingerprint} for a concept Short of `seg`; a draft with any check_script problem or a
    re-used hook is discarded (its problems are sent back), RuntimeError after 3; a script too close to an
    earlier Short's is rewritten once, then TooClose."""
    pkg = _write(cfg, f"{key(m)} · {seg['id']}", lambda p: _concept_prompt(cfg, m, seg, p), concept_facts(m, seg),
                 _concept_unknown, lambda pkg: None, earlier or [], hooks or set(), log)
    for s in pkg["scenes"]:
        if s["id"] == "explain":
            s["term"] = seg["term"]
    return package(cfg, pkg, seg["term"], log)


# ─── slides (9:16) ─────────────────────────────────────────────────────────

@dataclass
class _Ctx:
    cfg: dict
    layout: Layout
    accent: tuple
    brand: str
    chip: str
    footer: str


def _ctx(cfg: dict, m: dict, layout: Layout = PORTRAIT) -> _Ctx:
    footer = DISCLAIMER
    if m.get("market"):
        footer = f"Not financial advice · Data: {', '.join(m['market']['data_source'])}"
    return _Ctx(cfg, layout, _hex(cfg["video"].get("accent", "FFD400")),
                cfg["channel"].get("display_name", "CryptoFX Daily").upper(),
                CHIPS.get(m["source"]["kind"], "CRYPTO"), footer)


def _base(ctx: _Ctx):
    L = ctx.layout
    img = Image.new("RGB", (L.w, L.h), BG)
    d = ImageDraw.Draw(img)
    x0, x1 = L.content_box[0], L.content_box[2]
    d.text((x0, L.header_y), ctx.brand, font=_font(max(34, L.min_text), True), fill=ctx.accent)
    f = _font(L.min_text, True)
    cw, pad, ch = d.textlength(ctx.chip, font=f), round(L.min_text * 0.6), round(L.min_text * 1.5)
    d.rounded_rectangle([x1 - cw - 2 * pad, L.header_y, x1, L.header_y + ch], radius=ch // 2, fill=ctx.accent)
    d.text((x1 - cw - pad, L.header_y + ch / 2), ctx.chip, font=f, fill=BG, anchor="lm")
    d.line([(x0, L.rule_y), (x1, L.rule_y)], fill=PANEL, width=3)
    f = _font(L.min_text)
    lines = _wrap(d, ctx.footer, f, x1 - x0, L.footer_lines)
    lh = round(L.min_text * 1.3)
    y = L.footer_y - (len(lines) - 1) * lh
    for ln in lines:
        d.text(((L.w - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=MUTED)
        y += lh
    return img, d


def _fit(d, text: str, size: int, width: int) -> int:
    """The largest title size ≤ `size` at which the longest word of `text` fits `width` (words never break)."""
    longest = max(_clean(text).split() or [""], key=len)
    while size > 40 and d.textlength(longest, font=_title_font(size)) > width:
        size -= 6
    return size


# ─── frame 0 (epic-shorts-reach E6-4): the card words over a visual, never text alone ──────────

FRAME0_WORDS_SHARE = 0.36  # the card words take at most this share of the content box's height; the visual the rest
CANDLES = ((0.22, 0.46, 0.12, 0.54), (0.46, 0.34, 0.26, 0.56), (0.34, 0.64, 0.30, 0.72), (0.64, 0.52, 0.44, 0.70),
           (0.52, 0.86, 0.48, 0.96))  # the icon card's candles: (open, close, low, high) as shares of their height
COIN_WORDS = ((re.compile(r"\b(?:bitcoin|btc)\b", re.I), "BTC"), (re.compile(r"\b(?:ethereum|ether|eth)\b", re.I), "ETH"))
DIAGRAM_COIN = re.compile(r"'coin': '([A-Z]{2,5})'")


def card_words(text) -> str:
    """The frame-0 words: the card text's first CARD_WORDS words in upper case (a longer hook passed in is cut)."""
    return " ".join(_clean(text).upper().split()[:CARD_WORDS])


def _move(m: dict, sym: str) -> tuple[float | None, str]:
    """(the coin's move in %, "24h" / "7d"): a recap reads change_7d first, any other material change_24h first."""
    n = m["market"]["numbers"].get(sym) or {}
    order = ("change_7d", "change_24h") if m["source"]["kind"] == "recap" else ("change_24h", "change_7d")
    for k in order:
        if n.get(k) is not None:
            return n[k], "7d" if k == "change_7d" else "24h"
    return None, ""


def _ticker(sym) -> str:
    t = re.sub(r"[^A-Z]", "", str(sym).upper())[:5]
    return t or "?"


def _coin_badge(ctx: _Ctx, d, cx: int, cy: int, size: int, coin: str) -> None:
    """A drawn coin badge (diagrams._badge: BTC / ETH brand colours, else the accent) of diameter `size`."""
    L = ctx.layout
    f = _fit_font(coin, lambda s: _font(s, True), round(size * 0.72), max(L.min_text, round(size * 0.36)), L.min_text)
    diagrams._paint(d, diagrams._badge(cx, cy, size, coin, f, ctx.accent))


def _pill(ctx: _Ctx, d, text: str, h: int):
    """(width, draw(x, cy)) of a rounded pill of height `h` holding `text` in bold."""
    f = _font(max(ctx.layout.min_text, round(h * 0.46)), True)
    pad = round(h * 0.42)
    w = round(d.textlength(text, font=f)) + 2 * pad

    def draw(x: int, cy: int, fill, ink) -> None:
        d.rounded_rectangle([x, cy - h // 2, x + w, cy - h // 2 + h], radius=h // 2, fill=fill)
        d.text((x + pad, cy), text, font=f, fill=ink, anchor="lm")
    return w, draw


def _market_visual(ctx: _Ctx, img, d, box, m: dict, sym: str) -> dict:
    """The lead coin's row (badge + name + %-move pill, green / red) over its move chart; no ≥ 2-point series →
    the badge card (a panel with a large badge and the pill)."""
    from autopilot.triggered import draw_move_chart
    L = ctx.layout
    x0, y0, x1, y1 = box
    ch, period = _move(m, sym)
    name = _clean(m["market"]["numbers"][sym].get("name")) or sym
    label = f"{_pct(ch)} · {period}" if ch is not None else name
    fill, ink = ((UP if ch >= 0 else DOWN), FG) if ch is not None else (ctx.accent, BG)
    coin = _ticker(sym)
    series = [v for v in (m["market"].get("series") or {}).get(sym) or [] if v is not None]
    gap = round(L.min_text * 0.8)
    if len(series) >= 2:
        D = round(L.min_text * 3.4)
        cy = y0 + D // 2
        _coin_badge(ctx, d, x0 + D // 2, cy, D, coin)
        pw, pill = _pill(ctx, d, label, round(D * 0.72))
        x = x0 + D + gap
        nf = _font(max(L.min_text, round(D * 0.48)), True)
        nw = round(d.textlength(name, font=nf))
        if ch is not None and x + nw + gap + pw <= x1:
            d.text((x, cy), name, font=nf, fill=FG, anchor="lm")
            x += nw + gap
        pill(x, cy, fill, ink)
        draw_move_chart(img, (x0, y0 + D + gap, x1, y1), series, L, ctx.accent)
        return {"kind": "chart", "coin": coin, "pill": label}
    w, h = x1 - x0, y1 - y0
    pad = max(L.min_text, round(min(w, h) * 0.07))
    d.rounded_rectangle(box, radius=round(pad * 0.8), fill=PANEL)
    D = max(L.min_text * 2, min(round(h * 0.5), round(w * 0.4)))
    ph = max(round(L.min_text * 2.2), round(D * 0.34))
    pw, pill = _pill(ctx, d, label, ph)
    top = y0 + (h - (D + gap + ph)) // 2
    _coin_badge(ctx, d, x0 + w // 2, top + D // 2, D, coin)
    pill(x0 + (w - pw) // 2, top + D + gap + ph // 2, fill, ink)
    return {"kind": "badge", "coin": coin, "pill": label}


def icon_coin(seg: dict) -> str | None:
    """The icon card's coin: the first coin of the segment's diagram, else Bitcoin / Ethereum named in its term or
    facts (first mention wins), else None."""
    found = DIAGRAM_COIN.findall(repr(seg.get("diagram") or {}))
    if found:
        return found[0]
    text = " ".join([_clean(seg.get("term"))] + [_clean(f) for f in seg.get("facts") or []])
    hits = [(hit.start(), sym) for pat, sym in COIN_WORDS for hit in [pat.search(text)] if hit]
    return min(hits)[1] if hits else None


def _icon_card(ctx: _Ctx, d, box, term: str, coin: str | None) -> str:
    """A rounded panel: a drawn candlestick cluster (+ a coin badge when a coin is named) above the term
    (parentheticals dropped, ≤ 3 lines) in an accent pill. → the pill's text."""
    L = ctx.layout
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pad = max(L.min_text, round(min(w, h) * 0.07))
    d.rounded_rectangle(box, radius=round(pad * 0.8), fill=PANEL)
    label = _clean(re.sub(r"\([^)]*\)", " ", term)) or _clean(term) or "KEY IDEA"
    iw, pp = w - 2 * pad, round(L.min_text * 0.7)
    size = round(L.min_text * 2)
    while True:
        f = _font(size, True)
        lines = diagrams._wrap_all(d, label, f, iw - 2 * pp)
        if (lines is not None and len(lines) <= 3) or size <= L.min_text:
            break
        size -= 2
    if lines is None or len(lines) > 3:
        lines = _wrap(d, label, f, iw - 2 * pp, 3)
    lh = round(size * 1.22)
    ph = len(lines) * lh + 2 * pp
    pw = min(iw, max(round(d.textlength(ln, font=f)) for ln in lines) + 2 * pp)
    px0, py0 = x0 + (w - pw) // 2, y1 - pad - ph
    d.rounded_rectangle([px0, py0, px0 + pw, py0 + ph], radius=min(ph // 2, pp * 2), fill=ctx.accent)
    for i, ln in enumerate(lines):
        d.text((x0 + w // 2, py0 + pp + i * lh + lh // 2), ln, font=f, fill=BG, anchor="mm")
    top, bottom = y0 + pad, py0 - pad
    ah = bottom - top
    if ah < L.min_text * 2:
        return label
    D = min(ah, round(iw * 0.3)) if coin else 0
    cw = min(iw - (D + pad if coin else 0), round(ah * (1.3 if coin else 1.5)))
    gx = x0 + (w - (cw + (pad + D if coin else 0))) // 2
    slot = cw / len(CANDLES)
    body, wick = max(6, round(slot * 0.56)), max(3, round(slot * 0.08))
    for k, (o, c, lo, hi) in enumerate(CANDLES):
        cx = round(gx + slot * (k + 0.5))
        colour = UP if c > o else DOWN
        d.rectangle([cx - wick // 2, round(bottom - hi * ah), cx - wick // 2 + wick, round(bottom - lo * ah)], fill=colour)
        b0, b1 = sorted((round(bottom - o * ah), round(bottom - c * ah)))
        d.rectangle([cx - body // 2, b0, cx - body // 2 + body, max(b1, b0 + 4)], fill=colour)
    if coin:
        _coin_badge(ctx, d, round(gx + cw + pad + D / 2), top + ah // 2, D, coin)
    return label


def _concept_visual(ctx: _Ctx, img, d, box, seg: dict, words: str, log=_log) -> dict:
    """The segment's diagram fully drawn in `box` (the full spec, then without its notes), else the icon card
    (logged)."""
    term = _clean(seg.get("term")) or words
    spec = seg.get("diagram")
    if spec:
        tries = [spec] + ([{k: v for k, v in spec.items() if k != "notes"}] if isinstance(spec, dict)
                          and spec.get("notes") else [])
        why = ""
        for n, s in enumerate(tries):
            try:
                parts = diagrams.draw(img, box, s, ctx.layout, ctx.accent, who="Short frame 0")
            except ValueError as e:
                why = str(e)
                continue
            if n:
                log(f"Short frame 0 ({term}): the diagram fits only without its notes; notes dropped")
            return {"kind": "diagram", "parts": sorted(parts), "notes": bool(s.get("notes"))}
        log(f"Short frame 0 ({term}): the diagram doesn't fit ({why}); drawing the icon card")
    coin = icon_coin(seg)
    label = _icon_card(ctx, d, box, term, coin)
    return {"kind": "icon", "coin": coin, "term": label}


def hook_card(ctx: _Ctx, text: str, m: dict | None = None, seg: dict | None = None,
              log=_log) -> tuple[Image.Image, dict]:
    """Frame 0 (= thumbnail.jpg = the Reel cover; no captions over it): the card's 1-CARD_WORDS words (card_words)
    on top, then a visual: market / pulse material (`m` with a `market` section) → the lead coin's badge + %-move
    pill over its move chart (triggered.draw_move_chart; no ≥ 2-point series → the badge card); otherwise the
    segment's (`seg`) diagram fully drawn (diagrams.draw: full spec, then without notes), else the icon card
    (logged). → (image, {"words", "words_box", "visual": (x0, y0, x1, y1), "kind": chart / badge / diagram /
    icon, …})."""
    img, d = _base(ctx)
    L = ctx.layout
    x0, y0, x1, y1 = L.content_box
    words = card_words(text) or "KEY IDEA"
    cap = y0 + round((y1 - y0) * FRAME0_WORDS_SHARE)
    y = _flow(d, [{"text": words, "size": _fit(d, words, 170, x1 - x0), "title": True, "fill": FG, "keep": True}],
              (x0, y0, x1, cap), L, who="frame 0 words")
    bar, by = max(10, round(L.min_text * 0.4)), y + round(L.min_text * 1.1)
    d.rectangle([x0, by, x0 + round(L.min_text * 6), by + bar], fill=ctx.accent)
    box = (x0, by + bar + round(L.min_text * 0.9), x1, y1)
    info = {"words": words, "words_box": (x0, y0, x1, y), "visual": box}
    if m and m.get("market"):
        info.update(_market_visual(ctx, img, d, box, m, lead_coin(m)))
    else:
        info.update(_concept_visual(ctx, img, d, box, seg or {}, words, log))
    return img, info


def term_slide(ctx: _Ctx, term: str, sub: str = "") -> Image.Image:
    img, d = _base(ctx)
    x0, _, x1, _ = ctx.layout.content_box
    items = [{"text": term, "size": _fit(d, term, 130, x1 - x0), "title": True, "fill": FG, "gap": 30,
              "max_lines": 3}]
    if sub:
        items.append({"text": sub, "size": 56, "bold": True, "fill": ctx.accent, "max_lines": 3})
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", who="term slide")
    return img


def diagram_slide(ctx: _Ctx, term: str, spec: dict, show=None) -> Image.Image:
    img, d = _base(ctx)
    L = ctx.layout
    x0, y0, x1, y1 = L.content_box
    y = _flow(d, [{"text": term, "size": _fit(d, term, 88, x1 - x0), "title": True, "fill": FG, "max_lines": 2}],
              L.content_box, L,
              who="Short diagram heading")
    diagrams.draw(img, (x0, y + DIAGRAM_GAP, x1, y1), spec, L, ctx.accent, show=show, who="Short diagram")
    return img


TEXT_WORDS = 14  # E6-4: a text slide holds at most 14 body words; text_pages splits a longer text
_SENT_END = re.compile(r"[.!?…][\"'”’)]*$")
_CLAUSE_END = re.compile(r"[,;:—–][\"'”’)]*$|^[—–-]+$")


def _counted(tok: str) -> bool:
    return any(c.isalnum() for c in tok)


def text_words(text) -> int:
    """Body words of a text slide: whitespace tokens with a letter or digit ("·" / "—" don't count)."""
    return sum(_counted(t) for t in str(text or "").split())


def text_pages(text) -> list[str]:
    """The text in pages of ≤ TEXT_WORDS words: ceil(n / TEXT_WORDS) near-equal pages, each break moved to a
    sentence end (else a clause end) within ±2 words when both pages beside it stay ≤ TEXT_WORDS. Every token is
    kept, in order (" ".join(pages) == the cleaned text); a word-less token stays with the page before it."""
    toks = _clean(text).split()
    idx = [i for i, t in enumerate(toks) if _counted(t)]  # token index of each counted word
    n = len(idx)
    if n <= TEXT_WORDS:
        return [" ".join(toks)]
    k = -(-n // TEXT_WORDS)
    bounds = [0]
    for i in range(1, k):
        ideal = round(i * n / k)
        nxt = round((i + 1) * n / k) if i + 1 < k else n
        ok = [c for c in (ideal, ideal - 1, ideal + 1, ideal - 2, ideal + 2)
              if bounds[-1] < c < n and c - bounds[-1] <= TEXT_WORDS and nxt - c <= TEXT_WORDS]
        bounds.append(next((c for pat in (_SENT_END, _CLAUSE_END) for c in ok if pat.search(toks[idx[c] - 1])),
                           ideal))
    cuts = [0] + [idx[b] for b in bounds[1:]] + [len(toks)]
    return [" ".join(toks[a:b]) for a, b in zip(cuts, cuts[1:])]


def text_slide(ctx: _Ctx, heading: str, text: str) -> Image.Image:
    """A heading + ≤ TEXT_WORDS body words (more → ValueError: text_pages / text_scene split a longer text)."""
    n = text_words(text)
    if n > TEXT_WORDS:
        raise ValueError(f"Short text slide: {n} words (at most {TEXT_WORDS}; text_scene pages a longer text)")
    img, d = _base(ctx)
    _flow(d, [{"text": heading, "size": 48, "bold": True, "fill": ctx.accent, "gap": 34, "max_lines": 1},
              {"text": text, "size": 64, "bold": True, "fill": FG, "keep": True}],
          ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.2, who="Short text slide")
    return img


def text_scene(ctx: _Ctx, heading: str, text: str, path: Path, sid: str) -> dict:
    """One scene's text slide(s): page 1 (text_pages) is the slide at `path`; later pages (<stem>_p2.png, …) ride on
    it as `pages` [{image, reveal, words}] and share the scene's narration time in proportion to their `words`
    (render.build_video), so slides and scenes stay one to one."""
    path = Path(path)
    slide = None
    for k, page in enumerate(text_pages(text)):
        p = path if k == 0 else path.with_name(f"{path.stem}_p{k + 1}{path.suffix}")
        text_slide(ctx, heading, page).save(p)
        part = {"image": p, "reveal": None, "words": text_words(page)}
        if slide is None:
            slide = dict(part, id=sid)
        else:
            slide.setdefault("pages", []).append(part)
    return slide


def _cover(ctx: _Ctx, card_text: str, follow_img: Image.Image, workdir: Path, m: dict | None = None,
           seg: dict | None = None, log=_log) -> tuple[dict, Path]:
    """The cover slide: frame 0 (hook_card) saved as thumbnail.jpg, its info as `frame0`, then the follow slide."""
    card = workdir / "thumbnail.jpg"
    img, info = hook_card(ctx, card_text, m=m, seg=seg, log=log)
    img.save(card, quality=92)
    follow = workdir / "short_01_follow.png"
    follow_img.save(follow)
    return {"image": card, "cover": True, "follow": {"image": follow, "reveal": None}, "reveal": None,
            "id": "hook", "frame0": info}, card


def render_slides(cfg: dict, m: dict, seg: dict, pkg: dict, workdir: Path, log=_log) -> tuple[list[dict], Path]:
    """The concept Short's slides (one per scene; a long text scene carries its later pages as `pages`) → (slides,
    hook card path = the thumbnail / Reel cover: the card words over the segment's diagram or the icon card)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(cfg, m)
    cover, card = _cover(ctx, pkg.get("card") or pkg["hook"], term_slide(ctx, seg["term"]), workdir, seg=seg,
                         log=log)
    out = [cover]
    path = workdir / "short_02.png"
    if seg.get("diagram"):
        spec = seg["diagram"]
        diagram_slide(ctx, seg["term"], spec).save(path)
        slide = {"image": path, "reveal": None, "id": "explain"}
        slide["base"], slide["steps"] = diagrams.step_layers(
            lambda show: diagram_slide(ctx, seg["term"], spec, show=show), diagrams.steps(spec), workdir, "short_02")
    else:
        slide = text_scene(ctx, seg["term"].upper(), seg["facts"][0], path, "explain")
    out.append(slide)
    out.append(text_scene(ctx, "REMEMBER", seg["facts"][0], workdir / "short_03.png", "payoff"))
    return out, card


def _pct(v: float) -> str:
    return f"{'+' if v >= 0 else '−'}{abs(v):.1f}%"


def _change(m: dict, sym: str):
    """The coin's move in % (recap: change_7d first, else change_24h first; see _move)."""
    return _move(m, sym)[0]


def lead_coin(m: dict) -> str:
    """The coin whose move leads: a pulse material's own `lead` (the coin its hook is about) when it has a chart
    series, else the biggest move among coins with a chart series (else any coin)."""
    nums, series = m["market"]["numbers"], m["market"].get("series") or {}
    lead = m["market"].get("lead")
    if lead in nums and len(series.get(lead) or []) >= 2:
        return lead
    with_series = [s for s in nums if len(series.get(s) or []) >= 2] or list(nums)
    return max(with_series, key=lambda s: abs(_change(m, s) or 0))


def market_diagram(m: dict) -> dict:
    """The cause → coins flow diagram (as triggered.diagram, from the material's numbers)."""
    from autopilot.triggered import ALIASES
    nums = m["market"]["numbers"]
    coins = sorted(nums, key=lambda s: -abs(_change(m, s) or 0))[:3]
    nodes = [{"label": "The news", "say": ["headline", "news"]}]
    for i, sym in enumerate(coins):
        name, ch = _clean(nums[sym].get("name")) or sym, _change(m, sym)
        node = {"label": f"{name} {_pct(ch)}" if ch is not None else name, "arrow": "moved" if i == 0 else "and",
                "say": [name] + ALIASES.get(sym, [])}
        if re.fullmatch(r"[A-Z]{2,5}", sym):
            node["coin"] = sym
        nodes.append(node)
    return {"type": "flow", "nodes": nodes}


def chart_slide(ctx: _Ctx, m: dict, sym: str) -> tuple[Image.Image, tuple]:
    """The lead coin's move (heading + drawn chart) → (image, the chart's draw-in box (x, y, w, h))."""
    from autopilot.triggered import draw_move_chart
    img, d = _base(ctx)
    L = ctx.layout
    x0, y0, x1, y1 = L.content_box
    n = m["market"]["numbers"][sym]
    ch = _change(m, sym)
    period = "7 days" if m["source"]["kind"] == "recap" else "24 hours"
    y = _flow(d, [{"text": f"{_clean(n.get('name')) or sym} {_pct(ch)}" if ch is not None else sym, "size": 110,
                   "title": True, "fill": FG, "gap": 18, "max_lines": 2},
                  {"text": f"over {period}", "size": 48, "bold": True, "fill": ctx.accent, "gap": 30, "max_lines": 1}],
              L.content_box, L, who="market chart heading")
    draw_move_chart(img, (x0, y, x1, y1), m["market"]["series"][sym], L, ctx.accent)
    return img, (x0, y, x1 - x0, y1 - y)


def render_market_slides(cfg: dict, m: dict, pkg: dict, workdir: Path, log=_log) -> tuple[list[dict], Path]:
    """The market Short's slides → (slides, hook card path = the card words over the lead coin's badge, %-move pill
    and move chart)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(cfg, m)
    sym = lead_coin(m)
    has_chart = len((m["market"].get("series") or {}).get(sym) or []) >= 2
    follow, box = chart_slide(ctx, m, sym) if has_chart else (term_slide(ctx, pkg["hook"]), None)
    cover, card = _cover(ctx, pkg.get("card") or pkg["hook"], follow, workdir, m=m, log=log)
    cover["follow"]["reveal"] = box  # the move draws in left to right
    spec = market_diagram(m)
    path = workdir / "short_02.png"
    diagram_slide(ctx, "Why it moved", spec).save(path)
    slide = {"image": path, "reveal": None, "id": "explain"}
    slide["base"], slide["steps"] = diagrams.step_layers(
        lambda show: diagram_slide(ctx, "Why it moved", spec, show=show), diagrams.steps(spec), workdir, "short_02")
    nums = m["market"]["numbers"]
    lines = [f"{_clean(nums[s].get('name')) or s}: {_pct(_change(m, s))}" for s in list(nums)[:4]
             if _change(m, s) is not None]
    return [cover, slide, text_scene(ctx, "THE NUMBERS", " · ".join(lines), workdir / "short_03.png", "payoff")], card


# ─── packaging ─────────────────────────────────────────────────────────────

def hashtags(m: dict, seg: dict | None = None) -> list[str]:
    kind = m["source"]["kind"]
    tags = ["#Crypto", {"basics": "#CryptoBasics", "lesson": "#Trading"}.get(kind, "#CryptoNews")]
    names = " ".join(_clean(n.get("name")) for n in (m.get("market") or {}).get("numbers", {}).values())
    text = " ".join([m["source"]["title"], (seg or {}).get("term", ""), names]).lower()
    for word, tag in (("bitcoin", "#Bitcoin"), ("ethereum", "#Ethereum"), ("ether", "#Ethereum")):
        if word in text and tag not in tags:
            tags.append(tag)
    return tags[:4] + ["#Shorts"]


def source_link(m: dict) -> str:
    return f"https://youtu.be/{m['youtube_id']}" if m.get("youtube_id") else ""


def studio_task(short_id: str | None, m: dict) -> str:
    """The owner's one-line Studio task (YouTube Data API v3 has no related-video field), '' when not needed."""
    link = source_link(m)
    if not (short_id and link):
        return ""
    return (f"Studio task: set the related video of https://youtube.com/shorts/{short_id} to {link} "
            "(YouTube Studio → Content → the Short → Related video; the API can't set it)")


HASHTAG = re.compile(r"(?<![\w&])#\w+")


def _no_tags(text: str) -> str:
    return _clean(HASHTAG.sub("", text or ""))


def metadata(cfg: dict, m: dict, seg: dict | None, pkg: dict, extra: list[str] | None = None) -> dict:
    """YouTube metadata: title = the hook question (packaging rules already checked; any hashtag removed);
    description = link → hook → payoff → `extra` lines → data + credit (market) → source (not for pulse) → the
    disclosure line once → hashtags (#Shorts last). Pulse: "▶ Latest video: <latest long video>" as the link."""
    line = rules.disclosure(cfg, "shorts")
    payoff = " ".join(s["text"] for s in pkg["scenes"] if s["id"] == pkg["scenes"][-1]["id"])
    body = rules.without_disclosure(_no_tags(payoff), line)
    tags = hashtags(m, seg)
    link = source_link(m)
    mk = m.get("market") or {}
    credits = [f"Data: {', '.join(mk['data_source'])}", mk.get("credit") or ""] if mk else []
    pulse = m["source"]["kind"] == material.PULSE  # no source video: the link is the latest long video
    parts = [(f"▶ Latest video: {link}" if pulse else f"▶ Full video: {link}") if link else "", _no_tags(pkg["hook"]),
             body, *(extra or []), *credits, "" if pulse else f"From the full video: {m['source']['title']}",
             "⚠️ " + line, " ".join(tags)]
    return {"title": _no_tags(pkg["hook"])[:MAX_TITLE], "description": "\n\n".join(p for p in parts if p),
            "tags": [t.lstrip("#") for t in tags if t != "#Shorts"] + ([seg["term"]] if seg else []),
            "hashtags": tags}


def reel_caption(meta: dict, cfg: dict) -> str:
    """The Facebook Reel caption from the same metadata: no #Shorts, the disclosure line once, < 2,200 chars."""
    parts = [p for p in meta["description"].split("\n\n") if p]
    tags = " ".join(t for t in meta.get("hashtags", []) if t.lower() != "#shorts")
    body = "\n\n".join(parts[:-1] if parts and parts[-1].startswith("#") else parts)
    return (body[:2190 - len(tags) - 2].rstrip() + "\n\n" + tags).strip()


def now_iso(now: datetime) -> str:
    return now.isoformat(timespec="seconds")
