"""Trading lessons: curriculum + glossary formats, detector registry, validator, episode picker,
and the example / scene-plan schema the lesson pipeline builds on.

    lessons/curriculum.yaml   episodes in teaching order (list order IS the queue order)
    lessons/glossary.yaml     every concept defined once; narration and detectors both follow it

Curriculum entry fields:
    id             stable slug; what history's `episode` field stores
    track          0-6
    title          episode title
    key_points     non-empty list of approved points (narration never adds concepts)
    concepts       glossary keys the key points use
    prerequisites  ids of earlier episodes
    visual         visual type (VISUAL_TYPES)
    detector       registered detector name (DETECTORS) that finds the real examples

Glossary: `terms: {key: {term, definition}}`.

Example (what a detector returns, up to 2 per episode; [] = no clean example):
    {detector, glossary, asset, timeframe, date, candles: [{t, o, h, l, c}],
     region: {start, end, low, high}, primitives: [...], facts: {...}}   times ISO-8601
Times are read by to_datetime / timestamp / day (naive values and dates as UTC), shared with the
detectors and lesson_slides.
An `mtf` example adds a lower-timeframe panel checked by the same rules (problems prefixed "lower: "):
    lower: {timeframe, candles, region, primitives}

The picker is pure: history and the hold check are passed in, holds are never stored.
"""
import re
from dataclasses import dataclass, field
from datetime import date as _date, datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT / "lessons" / "curriculum.yaml"
GLOSSARY = ROOT / "lessons" / "glossary.yaml"

VISUAL_TYPES = {"chart", "mtf"}  # mtf = higher-timeframe chart + a lower-timeframe panel

# drawing primitives an example may use → required fields (`label` on level/zone is optional)
PRIMITIVES = {
    "swing": ("t", "price", "kind"),
    "level": ("price",),
    "trendline": ("t1", "p1", "t2", "p2"),
    "zone": ("t1", "t2", "low", "high"),
    "label": ("t", "price", "text"),
}
SWING_KINDS = {"HH", "HL", "LH", "LL", "high", "low"}
TIME_FIELDS = {"t", "t1", "t2"}
TEXT_FIELDS = {"kind", "label", "text"}

ENTRY_FIELDS = ("id", "track", "title", "key_points", "concepts", "prerequisites", "visual", "detector")
EXAMPLE_FIELDS = ("detector", "glossary", "asset", "timeframe", "date", "candles", "region", "primitives", "facts")
LOWER_FIELDS = ("timeframe", "candles", "region", "primitives")  # the optional `lower` panel (mtf)
SLUG = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


# ─── detector registry ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Detector:
    """`find(...)` returns up to 2 examples in the example schema, or [] when there is no clean one.
    `glossary` is the glossary key it implements (a tuple if one detector covers several, e.g. BOS/CHoCH)."""
    name: str
    glossary: str | tuple[str, ...]
    find: Callable[..., list[dict]]

    def glossary_keys(self) -> tuple[str, ...]:
        return (self.glossary,) if isinstance(self.glossary, str) else tuple(self.glossary)


DETECTORS: dict[str, Detector] = {}  # name -> detector; filled by the detector modules


def register(detector: Detector, registry: dict | None = None) -> Detector:
    registry = DETECTORS if registry is None else registry
    if detector.name in registry and registry[detector.name] is not detector:
        raise ValueError(f"detector '{detector.name}' is already registered")
    registry[detector.name] = detector
    return detector


# ─── files ─────────────────────────────────────────────────────────────────

def load_curriculum(path: Path = CURRICULUM) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    episodes = data.get("episodes") if isinstance(data, dict) else None
    if not isinstance(episodes, list):
        raise ValueError(f"{path}: needs a top-level `episodes:` list")
    return episodes


def load_glossary(path: Path = GLOSSARY) -> dict[str, dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    terms = data.get("terms") if isinstance(data, dict) else None
    if not isinstance(terms, dict):
        raise ValueError(f"{path}: needs a top-level `terms:` mapping")
    return {k: (v if isinstance(v, dict) else {}) for k, v in terms.items()}


# ─── validator ─────────────────────────────────────────────────────────────

def _glossary_problem(key, glossary: dict) -> str | None:
    if key not in glossary:
        return f"glossary key '{key}' is missing"
    if not str(glossary[key].get("definition") or "").strip():
        return f"glossary key '{key}' has an empty definition"
    return None


def validate(curriculum: list[dict], glossary: dict, detectors: dict | None = None) -> list[str]:
    """Every problem as "<episode id>: <reason>"; [] means the curriculum is usable."""
    detectors = DETECTORS if detectors is None else detectors
    errors, seen = [], set()
    for i, e in enumerate(curriculum):
        if not isinstance(e, dict):
            errors.append(f"#{i + 1}: entry is not a mapping")
            continue
        eid = e.get("id") if isinstance(e.get("id"), str) and e.get("id") else f"#{i + 1}"
        err = lambda reason: errors.append(f"{eid}: {reason}")  # noqa: E731
        for f in ENTRY_FIELDS:
            if f not in e:
                err(f"missing field '{f}'")
        if "id" in e:
            if not isinstance(e["id"], str) or not SLUG.match(e["id"]):
                err(f"id {e['id']!r} is not a slug (lowercase letters, digits, - or _)")
            elif e["id"] in seen:
                err("duplicate id")
        if "track" in e and (type(e["track"]) is not int or not 0 <= e["track"] <= 6):
            err(f"track {e['track']!r} is not 0-6")
        if "title" in e and not (isinstance(e["title"], str) and e["title"].strip()):
            err("empty title")
        if "key_points" in e and not (isinstance(e["key_points"], list) and e["key_points"]
                                      and all(isinstance(p, str) and p.strip() for p in e["key_points"])):
            err("key_points must be a non-empty list of text")
        if "visual" in e and (not isinstance(e["visual"], str) or e["visual"] not in VISUAL_TYPES):
            err(f"unknown visual type '{e['visual']}'")
        keys = []
        if "concepts" in e:
            if isinstance(e["concepts"], list) and all(isinstance(k, str) for k in e["concepts"]):
                keys += e["concepts"]
            else:
                err("concepts must be a list of glossary keys")
        if "detector" in e:
            d = detectors.get(e["detector"]) if isinstance(e["detector"], str) else None
            if d is None:
                err(f"detector '{e['detector']}' is not registered")
            else:
                keys += [k for k in d.glossary_keys() if k not in keys]
        for k in keys:
            problem = _glossary_problem(k, glossary)
            if problem:
                err(problem)
        if "prerequisites" in e:
            if not isinstance(e["prerequisites"], list) or not all(isinstance(p, str) for p in e["prerequisites"]):
                err("prerequisites must be a list of episode ids")
            else:
                for p in e["prerequisites"]:
                    if p not in seen:
                        err(f"prerequisite '{p}' is not an earlier episode")
        if isinstance(e.get("id"), str):
            seen.add(e["id"])
    return errors


# ─── examples ──────────────────────────────────────────────────────────────

def to_datetime(v) -> datetime:
    """An example time (ISO-8601 text, datetime or date) as an aware datetime: naive values and dates read
    as UTC, an aware value keeps its own offset. ValueError / TypeError on anything else."""
    if isinstance(v, datetime):
        d = v
    elif isinstance(v, _date):
        d = datetime(v.year, v.month, v.day)
    elif isinstance(v, str):
        d = datetime.fromisoformat(v)
    else:
        raise TypeError(f"not a time: {v!r}")
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def timestamp(v) -> float:
    """POSIX seconds of an example time (naive = UTC)."""
    return to_datetime(v).timestamp()


def day(v) -> str:
    """The calendar date ("YYYY-MM-DD") of an example time, in the time's own offset."""
    return to_datetime(v).date().isoformat()


def _is_time(v) -> bool:
    try:
        to_datetime(v)
        return True
    except (TypeError, ValueError):
        return False


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _panel_problems(ex: dict) -> list[str]:
    """Candle, region and primitive problems of one chart panel (an example or its `lower` panel)."""
    errors = []
    candles = ex.get("candles")
    if "candles" in ex:
        if not isinstance(candles, list) or not candles:
            errors.append("candles must be a non-empty list")
        else:
            for i, c in enumerate(candles):
                if not isinstance(c, dict) or any(k not in c for k in "tohlc"):
                    errors.append(f"candle {i}: needs t, o, h, l, c")
                elif not _is_time(c["t"]) or not all(_num(c[k]) for k in "ohlc"):
                    errors.append(f"candle {i}: t must be ISO-8601 and o/h/l/c numbers")
                elif not c["l"] <= min(c["o"], c["c"]) <= max(c["o"], c["c"]) <= c["h"]:
                    errors.append(f"candle {i}: low/high don't contain open/close")
    r = ex.get("region")
    if "region" in ex:
        if not isinstance(r, dict) or any(k not in r for k in ("start", "end", "low", "high")):
            errors.append("region needs start, end, low, high")
        elif not (_is_time(r["start"]) and _is_time(r["end"]) and _num(r["low"]) and _num(r["high"])):
            errors.append("region start/end must be ISO-8601 and low/high numbers")
        elif to_datetime(r["start"]) > to_datetime(r["end"]) or r["low"] > r["high"]:
            errors.append("region start/end or low/high are reversed")
    if "primitives" in ex:
        if not isinstance(ex["primitives"], list):
            errors.append("primitives must be a list")
        else:
            for i, p in enumerate(ex["primitives"]):
                kind = p.get("type") if isinstance(p, dict) else None
                name = f"primitive {i} ({kind})"
                if not isinstance(kind, str) or kind not in PRIMITIVES:
                    errors.append(f"primitive {i}: unknown primitive type '{kind}'")
                    continue
                for f in PRIMITIVES[kind]:
                    if f not in p:
                        errors.append(f"{name}: missing field '{f}'")
                for f, v in p.items():
                    if f == "type":
                        continue
                    if f in TIME_FIELDS and not _is_time(v):
                        errors.append(f"{name}: {f} {v!r} is not ISO-8601")
                    elif f in TEXT_FIELDS and not isinstance(v, str):
                        errors.append(f"{name}: {f} must be text")
                    elif f not in TIME_FIELDS | TEXT_FIELDS and not _num(v):
                        errors.append(f"{name}: {f} must be a number")
                if kind == "swing" and isinstance(p.get("kind"), str) and p["kind"] not in SWING_KINDS:
                    errors.append(f"{name}: kind '{p['kind']}' is not one of {sorted(SWING_KINDS)}")
                if kind == "zone" and _num(p.get("low")) and _num(p.get("high")) and p["low"] > p["high"]:
                    errors.append(f"{name}: low is above high")
    return errors


def _lower_problems(lower) -> list[str]:
    """The `lower` panel of an mtf example: same rules as the example's own chart."""
    if not isinstance(lower, dict):
        return ["panel is not a mapping"]
    errors = [f"missing field '{f}'" for f in LOWER_FIELDS if f not in lower]
    if "timeframe" in lower and not (isinstance(lower["timeframe"], str) and lower["timeframe"].strip()):
        errors.append("timeframe must be text")
    return errors + _panel_problems(lower)


def validate_example(ex: dict) -> list[str]:
    """Problems with a detector's example; each primitive problem names the primitive, each problem of
    the optional `lower` panel (mtf) starts with "lower: "."""
    if not isinstance(ex, dict):
        return ["example is not a mapping"]
    errors = [f"missing field '{f}'" for f in EXAMPLE_FIELDS if f not in ex]
    if "date" in ex and not _is_time(ex["date"]):
        errors.append(f"date {ex['date']!r} is not ISO-8601")
    errors += _panel_problems(ex)
    if "facts" in ex and not isinstance(ex["facts"], dict):
        errors.append("facts must be a mapping")
    if "lower" in ex:
        errors += [f"lower: {e}" for e in _lower_problems(ex["lower"])]
    return errors


def example_label(ex: dict) -> str:
    return f"Historical example · {ex['asset']} · {ex['date']}"


# ─── picker ────────────────────────────────────────────────────────────────

@dataclass
class Pick:
    entry: dict | None  # None = nothing to publish in this slot (caller logs and skips)
    rerun: bool = False  # this slot already recorded an episode: make that one again
    held: list[tuple[str, str]] = field(default_factory=list)  # (episode id, reason), in queue order


def pick(curriculum: list[dict], history, date: str, session: str,
         hold: Callable[[dict], str | None] | None = None, slot_rerun: bool = True) -> Pick:
    """Next episode for (date, session). `history` is an autopilot.history.History.

    A re-run of a slot whose counting entry recorded `episode: X` gets X again, published or held
    (slot_rerun=False, for runs that don't fill the slot, e.g. manual ones, skips this rule).
    Otherwise the first entry in curriculum order that no uploaded entry (manual or timed) has
    published and that `hold(entry)` doesn't hold. Same inputs → same answer.
    """
    by_id = {e["id"]: e for e in curriculum if isinstance(e, dict) and "id" in e}
    uploaded = history.uploaded()
    for v in uploaded if slot_rerun else []:  # same slot rule as History.published_on
        if (v.get("brief_date") == date and v.get("session", "london") == session and v.get("counts", True)
                and v.get("episode")):
            return Pick(by_id.get(v["episode"]), rerun=True)  # None if the episode left the curriculum
    published = {v["episode"] for v in uploaded if v.get("episode")}
    held = []
    for e in curriculum:
        if e["id"] in published:
            continue
        reason = hold(e) if hold else None
        if reason:
            held.append((e["id"], reason))
            continue
        return Pick(e, held=held)
    return Pick(None, held=held)


# ─── scene plan ────────────────────────────────────────────────────────────

def scene_plan(entry: dict, examples: list[dict], next_entry: dict | None = None) -> list[dict]:
    """Fixed episode shape (like script.gold_plan): hook, concept, example_1, [example_2], misreads,
    recap. Each scene says what its narration covers; narration is written per scene id."""
    if not examples:
        raise ValueError(f"{entry['id']}: no example; the episode should have been held")
    concepts = ", ".join(entry.get("concepts", []))
    plan = [
        {"id": "hook", "visual": {"type": "title", "title": entry["title"], "track": entry["track"]},
         "covers": f"the hook: what the viewer will be able to spot after \"{entry['title']}\""},
        {"id": "concept", "visual": {"type": "concept", "concepts": list(entry.get("concepts", []))},
         "covers": f"the concept, stated from its glossary entries ({concepts}) and the approved key points"},
    ]
    for n, ex in enumerate(examples[:2], 1):
        plan.append({"id": f"example_{n}",
                     "visual": {"type": entry["visual"], "example": ex, "label": example_label(ex)},
                     "covers": f"real example {n}: {ex['asset']} {ex['timeframe']} on {ex['date']}, "
                               f"the '{ex['glossary']}' the detector found, using only its facts"})
    plan.append({"id": "misreads", "visual": {"type": "misreads"},
                 "covers": "common misreads, only within the approved key points"})
    nxt = next_entry["title"] if next_entry else None
    affiliation = entry["track"] == 4  # ICT track: not affiliated with the concept's author
    plan.append({"id": "recap",
                 "visual": {"type": "outro", "next": nxt, "disclaimer": True, "non_affiliation": affiliation},
                 "covers": "recap of the key points, "
                           + (f"next episode: \"{nxt}\", " if nxt else "")
                           + "then: this is education, not financial advice"
                           + ("; plus the non-affiliation line" if affiliation else "")})
    return plan
