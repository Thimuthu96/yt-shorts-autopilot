"""Lesson chapters and publishing metadata (no upload: entries 10/11 publish what this builds).

    chapters(plan, audio, examples, glossary=None)
        -> [{"start": s, "time": "m:ss", "title", "scenes": [ids]}]   from the scene timings
    build_lesson_metadata(entry, pkg, examples, chapters, cfg)
        -> {title, description, tags, category_id: "27", fb_title, fb_description}

Chapters follow the scenes: the first starts at 0:00, a scene starts a new chapter only when it is at
least MIN_CHAPTER seconds long and the current chapter already is (so a short scene merges into the
previous chapter and a short opening absorbs the next scene). With fewer than MIN_CHAPTERS the description
has no "Chapters:" block (YouTube would ignore it); the chapters are still returned. Names: hook "Intro", concept the entry's
first concept term, example_n "Example n: <asset> <timeframe>", misreads "Common misreads", recap "Recap".

Metadata text comes only from the entry (title, track, key points, concepts) and the examples' facts
(asset, timeframe, date, source); the narration is not used. Disclaimer always, the ICT non-affiliation
line on track 4. Facebook gets the same title and a short caption (summary, disclaimer, ≤ 5 hashtags,
no links).
"""
import re

from autopilot.lesson_slides import NON_AFFILIATION, TRACKS
from autopilot.lessons import example_label

MIN_CHAPTER = 10.0  # seconds; YouTube ignores chapters shorter than this
MIN_CHAPTERS = 3  # YouTube shows chapters only with at least 3 (first at 0:00, each ≥ 10 s)
CATEGORY_EDUCATION = "27"
ICT_TRACK = 4
DISCLAIMER = "This is education, not financial advice."
FIXED_NAMES = {"hook": "Intro", "misreads": "Common misreads", "recap": "Recap"}
ASSET_TAGS = {"BTC/USD": "#Bitcoin", "ETH/USD": "#Ethereum", "XAU/USD": "#Gold", "EUR/USD": "#EURUSD"}
ASSET_WORDS = {"BTC/USD": "bitcoin", "ETH/USD": "ethereum", "XAU/USD": "gold", "EUR/USD": "eurusd"}
TRACK_TAGS = {0: "#MarketStructure", 1: "#Trendlines", 2: "#Liquidity", 3: "#SmartMoneyConcepts",
              4: "#ICTConcepts", 5: "#MSNR", 6: "#PriceAction"}
MAX_HASHTAGS = 5


def _safe(text: str) -> str:
    return " ".join(re.sub(r"[<>]", "", str(text or "")).split())


def _human(key: str) -> str:
    return str(key).replace("_", " ").replace("-", " ").strip().capitalize()


def timestamp(seconds: float) -> str:
    s = int(max(seconds, 0))  # floor: the first chapter is always 0:00
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _scene_name(scene: dict, examples: list[dict], glossary: dict | None) -> str:
    sid = str(scene.get("id", ""))
    if sid in FIXED_NAMES:
        return FIXED_NAMES[sid]
    v = scene.get("visual") or {}
    if sid == "concept":
        keys = v.get("concepts") or []
        if keys:
            g = (glossary or {}).get(keys[0]) or {}
            return g.get("term") or _human(keys[0])
        return "The concept"
    m = re.fullmatch(r"example_(\d+)", sid)
    if m:
        n = int(m.group(1))
        ex = examples[n - 1] if 0 < n <= len(examples) else v.get("example") or {}
        return f"Example {n}: {ex.get('asset', '')} {ex.get('timeframe', '')}".strip()
    return _human(sid)


def chapters(plan: list[dict], audio: list[dict], examples: list[dict], glossary: dict | None = None) -> list[dict]:
    """Chapters from the scene timings (`audio[i]["duration"]` is scene i's length)."""
    if len(plan) != len(audio):
        raise ValueError(f"{len(plan)} scenes but {len(audio)} narration parts")
    out, t = [], 0.0
    for scene, a in zip(plan, audio):
        dur = float(a["duration"])
        if out and (dur < MIN_CHAPTER or t - out[-1]["start"] < MIN_CHAPTER):
            out[-1]["scenes"].append(scene["id"])  # too short: part of the previous chapter
        else:
            out.append({"start": round(t, 3), "time": timestamp(t),
                        "title": _scene_name(scene, examples, glossary), "scenes": [scene["id"]]})
        t += dur
    return out


def _track_name(entry: dict) -> str:
    return TRACKS.get(entry.get("track"), "Trading")


def _post_title(entry: dict) -> str:
    """The part of "Structure #2: BOS vs CHoCH" after the series prefix (the whole title without one)."""
    pre, _, post = str(entry.get("title", "")).partition(":")
    return _safe(post if post.strip() else pre)


def seo_title(entry: dict) -> str:
    """"<entry title> Explained | <track name> Lesson", ≤ 100 chars (series prefix dropped if needed)."""
    tail = f" Explained | {_track_name(entry)} Lesson"
    for head in (_safe(entry.get("title", "")), _post_title(entry)):
        if len(head + tail) <= 100:
            return head + tail
    return (_post_title(entry)[:100 - len(" Explained")] + " Explained").strip()


def summary(entry: dict) -> str:
    """2-3 sentences: the approved key points (a lead sentence from the title when there's only one)."""
    points = []
    for kp in entry.get("key_points") or []:
        kp = _safe(kp)
        if kp:
            points.append(kp if kp[-1] in ".!?" else kp + ".")
    points = points[:3]
    if len(points) < 2:
        points.insert(0, f"{_post_title(entry)}: a {_track_name(entry).lower()} lesson with real historical charts.")
    return " ".join(points)


def hashtags(entry: dict, examples: list[dict]) -> list[str]:
    tags = [TRACK_TAGS.get(entry.get("track"), "#PriceAction"), "#TradingEducation", "#TechnicalAnalysis"]
    tags += [ASSET_TAGS[ex["asset"]] for ex in examples if ex.get("asset") in ASSET_TAGS]
    seen, out = set(), []
    for h in tags:
        if h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    return out[:MAX_HASHTAGS]


def _credits(examples: list[dict]) -> str:
    by_source: dict[str, list[str]] = {}
    for ex in examples:
        src = _safe((ex.get("facts") or {}).get("source") or "")
        if src:
            assets = by_source.setdefault(src, [])
            if ex.get("asset") and ex["asset"] not in assets:
                assets.append(ex["asset"])
    if not by_source:
        return ""
    return "Price data: " + "; ".join(f"{src} ({', '.join(a)})" if a else src for src, a in by_source.items()) + "."


def _tags(entry: dict, examples: list[dict]) -> list[str]:
    post = _post_title(entry).lower()
    track = _track_name(entry).lower()
    seeds = [post, f"{post} explained", f"{track} trading lesson"]
    seeds += [_human(k).lower() for k in entry.get("concepts") or []]
    seeds += ["trading lesson", "technical analysis", "price action", "trading education"]
    seeds += [f"{ASSET_WORDS[ex['asset']]} chart" for ex in examples if ex.get("asset") in ASSET_WORDS]
    tags, seen, total = [], set(), 0
    for t in seeds:
        t = _safe(t).replace(",", "")
        cost = len(t) + (2 if " " in t else 0) + 1  # YouTube counts quotes + separator
        if t and t.lower() not in seen and total + cost <= 480:
            seen.add(t.lower())
            tags.append(t)
            total += cost
    return tags


def build_lesson_metadata(entry: dict, pkg: dict, examples: list[dict], chapters: list[dict], cfg: dict,
                          log=print) -> dict:
    """YouTube + Facebook metadata for one lesson. `pkg` (the narration) is accepted for the caller's
    convenience but never quoted: the text comes from the entry and the examples' facts only."""
    title = seo_title(entry)
    about = summary(entry)
    tags = hashtags(entry, examples)
    disclaimer = _safe((cfg.get("upload") or {}).get("disclaimer")) or DISCLAIMER
    ict = entry.get("track") == ICT_TRACK
    parts = [about]
    if len(chapters) >= MIN_CHAPTERS:
        parts.append("Chapters:\n" + "\n".join(f"{c['time']} {_safe(c['title'])}" for c in chapters))
    elif chapters:
        log(f"No chapters in the description: only {len(chapters)} of at least {MIN_CHAPTER:.0f} s "
            f"(YouTube needs {MIN_CHAPTERS})")
    if examples:
        parts.append("Historical examples:\n" + "\n".join(
            f"• {example_label(ex)} · {ex.get('timeframe', '')}".rstrip(" ·") for ex in examples))
    credits = _credits(examples)
    if credits:
        parts.append(credits)
    parts.append("⚠️ " + disclaimer)
    if ict:
        parts.append(NON_AFFILIATION)
    parts.append(" ".join(tags))
    description = "\n\n".join(p for p in parts if p)[:4900]

    fb = [about, "⚠️ " + disclaimer] + ([NON_AFFILIATION] if ict else []) + [" ".join(tags)]
    return {"title": title, "description": description, "tags": _tags(entry, examples),
            "category_id": CATEGORY_EDUCATION, "fb_title": title, "fb_description": "\n\n".join(fb)}
