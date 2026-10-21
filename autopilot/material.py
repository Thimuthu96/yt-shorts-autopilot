"""Shorts material: what a published long video leaves behind for the standalone Shorts (epic 4) cut days
later, in other runs. One JSON file per long video under data/material/ (committed by the workflow's
history-save step; output/ is discarded after 7 days).

Format (version 1), documented for epics 3 and 4:

    {
      "version": 1,
      "source": {"kind": "basics", "id": "<topic id>", "title": "<the long video's title>"},
      "youtube_id": "<YouTube video id>" | null,       the related-video link target
      "facebook_id": "<Facebook video id>" | null,
      "published_at": "<ISO time>",                    YouTube publishAt when scheduled, else the run's time
      "segments": [                                    at least MIN_SEGMENTS, ids unique
        {"id": "overview" | "point_<n>" | …,
         "kind": "overview" | "concept",
         "term": "<key term>",                         the concept's name (overview: the question)
         "narration": "<spoken text of that part>",    passes rules.narration_problems
         "diagram": {<autopilot/diagrams.py spec>} | null,
         "facts": ["<approved fact>", …],              the only facts a Short of it may state
         "hooks": ["<hook question ≤ 60 chars>", …]}   at least one; no title rule broken
      ],
      "market": {…}                                    market material only (below)
    }

Market material (source kind "triggered" | "recap", epic-volatility-videos entry 9; epic 4's market Short reads it):
segments may be empty (the 5-segment minimum applies to concept material only: Basics / Lesson) and a `market`
section is required:

    "market": {"numbers": {"<SYM>": {"name", "price", "change_24h", "change_7d", "source"}},   as fetched
               "total_cap_change_24h": <float> | null,
               "data_source": ["Coinbase", "CoinGecko"],      where those numbers came from
               "credit": "Data provided by CoinGecko" | "",   a Short using CoinGecko numbers adds it
               "series": {"<SYM>": [<price>, …]},             the chart series as fetched
               "cause_headline": "<the cause>" | null,        recap: the first move's cause
               "causes": {"<SYM>": "<headline>" | null},
               "hooks": ["<hook question ≤ 60 chars>", …]}    at least 2 distinct, no title / narration rule broken

Pulse material (source kind "pulse", epic-shorts-reach entry 6.1; autopilot/pulse.py builds it from the day's fetched
data alone, no long video): market material whose source is {"kind": "pulse", "id": "<YYYY-MM-DD>-<slot>", "title"};
`youtube_id` = the related long video when the builder was given one, else null (pulse is exempt from the platform-id
rule; `facebook_id` null), `published_at` = the build time, `segments` []. Its `market` section adds:

               "lead": "<SYM>",                                the coin the Short is about: in `numbers`, with a
                                                               `series` of at least 2 points
               "headlines": [{"title", "source", "published"}] the cause first, then other stories naming its coins

    VIDEO_MARKET_SOURCES = ("triggered", "recap")   what shorts.pick_market serves by default (the current mix)
    MARKET_SOURCES = VIDEO_MARKET_SOURCES + ("pulse",)

    build_triggered(trigger, meta, entry) / build_recap(recap, meta, entry)   market material of a published
                                         triggered / recap video (its fetched numbers, sources, series, causes and
                                         ≥ 2 hook candidates)
    build_pulse(pulse, now, slot, related)   pulse material from pulse.pick_lead's result (lead, coins, moves, cause,
                                         headlines, market, data_sources); `related` = the related long video id
    build_basics(topic, scenes, entry, cfg)  the material of one Basics episode: an overview segment (the
                                         question answered by the hook narration, the summary as its fact)
                                         + one concept segment per point (its narration without the
                                         subscribe ask, its diagram, its approved text as the fact)
    validate(m) -> [reason]              [] = usable
    path_for(m, root)                    data/material/<kind>-<id>.json (pulse: pulse-<YYYY-MM-DD>-<slot>.json)
    save(m, path) / load(path)           JSON (UTF-8, indented)
    merge(old, new)                      new's platform ids / publish time filled into old (idempotent)
    add(paths, root)                     merge each output copy into data/material/ (the workflow)

    python -m autopilot.material add output/*/material.json   # used by the workflow after its reset
"""
import json
import re
import sys
from pathlib import Path

from autopilot import diagrams, rules

VERSION = 1
MIN_SEGMENTS = 5  # owner, 2026-10-14: enough unused segments for ~10 evergreen Shorts a week
MAX_HOOK = 60  # characters (packaging.md: a Short's title is its hook question, ≤ 60)
KINDS = ("overview", "concept")
PULSE = "pulse"  # market material built from the day's fetched data alone (no source video)
VIDEO_MARKET_SOURCES = ("triggered", "recap")  # market material of a published long video
MARKET_SOURCES = VIDEO_MARKET_SOURCES + (PULSE,)  # market material: a `market` section, no segment minimum
MIN_HOOKS = 2  # market material: distinct hook candidates (epic 4 makes up to 2 Shorts from distinct ones)
MARKET_FIELDS = ("numbers", "data_source", "credit", "series", "cause_headline", "hooks")
FIELDS = ("version", "source", "youtube_id", "facebook_id", "published_at", "segments")
SEGMENT_FIELDS = ("id", "kind", "term", "narration", "diagram", "facts", "hooks")
FOLDER = Path("data") / "material"
PROPER = {"Bitcoin", "Ethereum", "Ether", "Lightning", "Satoshi", "Solana"}  # kept capitalised in hooks


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _hook_ok(h: str) -> bool:
    return bool(h) and len(h) <= MAX_HOOK and not rules.title_problems(h) and not rules.narration_problems(h)


WH = ("what", "how", "why", "who", "when", "where", "which")


def _stem(question: str) -> str:
    """The question without its "(…)" suffix and final "?" ("What Is a Bitcoin ETF? (Explained Simply)" →
    "What Is a Bitcoin ETF")."""
    return _clean(re.sub(r"\s*\(.*?\)\s*$", "", _clean(question))).rstrip("?").strip()


def hooks_for(term: str, question: str = "") -> list[str]:
    """Hook question candidates for a segment (epic 4 may rewrite them): the overview (no term) gets the episode
    question without its "(…)" suffix; a concept "What is / are <term>?" (a plain capitalised first word
    lower-cased; "are" for a plural or "x and y" term; none for a question-shaped term like "What miners do"),
    then the episode question as the last candidate. Only hooks within MAX_HOOK that break no title or
    narration rule are kept."""
    out = []
    t = _clean(term)
    if not t:
        if question:
            out.append(_stem(question) + "?")
    else:
        first = t.split()[0]
        if first[:1].isupper() and first[1:] == first[1:].lower() and first.strip("-") not in PROPER:
            t = t[0].lower() + t[1:]  # "Exchange-traded fund" → "exchange-traded fund"; Bitcoin / ETF kept
        if first.lower() not in WH:  # a question-shaped term ("What miners do") takes the episode's question
            last = t.split()[-1]
            plural = " and " in t or (last.endswith("s") and not last.endswith("ss") and last.islower())
            out.append(f"What {'are' if plural else 'is'} {t}?")
    if question:  # the episode's own question: always a candidate last, so no segment is left without one
        out.append(_stem(question) + "?")
    seen, keep = set(), []
    for h in out:
        if _hook_ok(h) and h.lower() not in seen:
            seen.add(h.lower())
            keep.append(h)
    return keep


def build_basics(topic: dict, scenes: list[dict], entry: dict, cfg: dict) -> dict:
    """The material of one Basics episode from its topic, its final narration scenes (the subscribe ask is
    removed from the narration) and its history entry (ids, date, publish_at)."""
    from autopilot import basics
    ask = basics.subscribe_ask(cfg)
    said = {s["id"]: _clean(_clean(s.get("text")).replace(ask, " ")) for s in scenes}
    segments = [{"id": "overview", "kind": "overview", "term": _clean(topic["question"]),
                 "narration": said.get("hook", ""), "diagram": None,
                 "facts": [_clean(topic.get("summary"))],
                 "hooks": hooks_for("", topic["question"])}]
    for n, p in enumerate(topic.get("points") or [], 1):
        segments.append({"id": f"point_{n}", "kind": "concept", "term": _clean(p["term"]),
                         "narration": said.get(f"point_{n}", ""), "diagram": p.get("diagram"),
                         "facts": [_clean(p["text"])], "hooks": hooks_for(p["term"], topic["question"])})
    return {"version": VERSION,
            "source": {"kind": "basics", "id": topic["id"], "title": _clean(topic["question"])},
            "youtube_id": entry.get("video_id"), "facebook_id": entry.get("fb_video_id"),
            "published_at": entry.get("publish_at") or entry.get("date"),
            "segments": segments}


def _pct_words(v: float) -> str:
    a = abs(v)
    return f"{round(a)}" if a >= 1 else f"{a:.1f}"


def _market_hooks(cands: list[str]) -> list[str]:
    seen, out = set(), []
    for h in cands:
        h = _clean(h)
        if _hook_ok(h) and h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    return out


def _numbers(moves: dict) -> dict:
    return {s: {k: m.get(k) for k in ("name", "price", "change_24h", "change_7d", "source")} for s, m in moves.items()}


def _market_base(kind: str, id_: str, title: str, entry: dict, moves: dict, market: dict | None, sources: list,
                 causes: dict, cause: str | None, hooks: list[str]) -> dict:
    from autopilot.sources import CG_CREDIT
    return {"version": VERSION, "source": {"kind": kind, "id": id_, "title": _clean(title)},
            "youtube_id": entry.get("video_id"), "facebook_id": entry.get("fb_video_id"),
            "published_at": entry.get("publish_at") or entry.get("date"), "segments": [],
            "market": {"numbers": _numbers(moves),
                       "total_cap_change_24h": (market or {}).get("total_cap_change_24h"),
                       "data_source": list(sources), "credit": CG_CREDIT if "CoinGecko" in sources else "",
                       "series": {s: list(m.get("series") or []) for s, m in moves.items()},
                       "cause_headline": cause, "causes": causes, "hooks": _market_hooks(hooks)}}


def build_triggered(trigger: dict, meta: dict, entry: dict) -> dict:
    """The market material of a published triggered video."""
    moves = trigger.get("moves") or {}
    lead = moves.get(trigger.get("lead")) or {}
    move = lead.get("change_24h")
    if move is None:
        move = (trigger.get("market") or {}).get("total_cap_change_24h") or 0.0
    name = _clean(trigger.get("label")) or "Crypto"
    up = move >= 0
    hooks = [f"Why did {name} just {'jump' if up else 'drop'} {_pct_words(move)}%?",
             f"What really moved {name}?", f"Why is {name} {'up' if up else 'down'} {_pct_words(move)}%?",
             "Why did crypto just move?"]
    cause = (trigger.get("cause") or {}).get("title")
    return _market_base("triggered", trigger["id"], meta.get("title") or name, entry, moves, trigger.get("market"),
                        trigger.get("data_sources") or [], {s: cause for s in trigger.get("coins") or []}, cause, hooks)


def build_recap(recap: dict, meta: dict, entry: dict) -> dict:
    """The market material of a published Saturday recap."""
    moves = recap.get("moves") or {}
    hooks = ["What moved crypto this week?"]
    for s in recap.get("coins") or []:
        m = moves[s]
        up = m["change_7d"] >= 0
        hooks.append(f"Why did {_clean(m['name'])} {'rise' if up else 'fall'} {_pct_words(m['change_7d'])}% this week?")
    hooks.append("Which coins moved most this week?")
    causes = {s: (c or {}).get("title") for s, c in (recap.get("causes") or {}).items()}
    first = (recap.get("coins") or [None])[0]
    return _market_base("recap", recap["id"], meta.get("title") or "This Week in Crypto", entry, moves,
                        recap.get("market"), recap.get("data_sources") or [], causes, causes.get(first), hooks)


def build_pulse(pulse: dict, now, slot: str, related: str | None = None) -> dict:
    """Pulse material from pulse.pick_lead's result: the lead's fetched move, its cause and headlines, the coins'
    numbers + series as fetched; `related` = the related long video's YouTube id (else null)."""
    lead = pulse["lead"]
    moves = pulse.get("moves") or {}
    m = moves.get(lead) or {}
    name = _clean(m.get("name")) or lead
    move = m.get("change_24h") or 0.0
    up, pct = move >= 0, _pct_words(move)
    hooks = [f"Why did {name} just {'rise' if up else 'fall'} {pct}%?", f"Why is {name} {'up' if up else 'down'} {pct}%?",
             f"What really moved {name}?"]
    if pct == "0.0":  # a flat move: no "0.0%" hook (fewer than 2 hooks → the validator refuses the material)
        hooks = hooks[2:]
    cause = (pulse.get("cause") or {}).get("title")
    coins = [s for s in pulse.get("coins") or [] if s in moves] or [lead]
    entry = {"video_id": related or None, "fb_video_id": None,
             "date": now.isoformat(timespec="seconds")}
    out = _market_base(PULSE, f"{now:%Y-%m-%d}-{slot}", f"What moved {name}: {'up' if up else 'down'} {pct}% in 24 hours",
                       entry, moves, pulse.get("market"), pulse.get("data_sources") or [],
                       {s: cause if s == lead else None for s in coins}, cause, hooks)
    out["market"]["lead"] = lead
    out["market"]["headlines"] = [dict(h) for h in pulse.get("headlines") or []]
    return out


def _market_problems(mk) -> list[str]:
    if not isinstance(mk, dict):
        return ["market material needs a `market` section"]
    out = [f"market: missing field '{f}'" for f in MARKET_FIELDS if f not in mk]
    nums = mk.get("numbers")
    if not (isinstance(nums, dict) and nums):
        out.append("market: numbers must name at least one coin")
    else:
        for sym, n in nums.items():
            if not isinstance(n, dict) or not _clean(n.get("source")) or \
                    all(n.get(k) is None for k in ("change_24h", "change_7d")):
                out.append(f"market: {sym} needs a fetched move and its source")
    src = mk.get("data_source")
    if not (isinstance(src, list) and src and all(x in ("Coinbase", "CoinGecko") for x in src)):
        out.append("market: data_source must list Coinbase and/or CoinGecko")
    hooks = mk.get("hooks")
    if not isinstance(hooks, list) or len({_clean(h).lower() for h in hooks}) < MIN_HOOKS:
        out.append(f"market: needs at least {MIN_HOOKS} distinct hook candidates")
    else:
        out += [f"market: hook {h!r} is over {MAX_HOOK} characters or breaks a rule" for h in hooks if not _hook_ok(_clean(h))]
    return out


def _pulse_problems(mk: dict) -> list[str]:
    """A pulse material's lead: one of its numbers, with a chart series of at least 2 points."""
    lead = mk.get("lead")
    if not (isinstance(lead, str) and isinstance(mk.get("numbers"), dict) and lead in mk["numbers"]):
        return [f"pulse: lead {lead!r} must be one of the numbers"]
    if len(((mk.get("series") or {}).get(lead)) or []) < 2:
        return [f"pulse: lead {lead} needs a series of at least 2 points"]
    return []


def validate(m) -> list[str]:
    """Every problem with one material file ([] = usable), one reason each."""
    if not isinstance(m, dict):
        return ["material must be a mapping"]
    out = [f"missing field '{f}'" for f in FIELDS if f not in m]
    if m.get("version") != VERSION:
        out.append(f"version must be {VERSION} (got {m.get('version')!r})")
    src = m.get("source")
    if not (isinstance(src, dict) and all(_clean(src.get(k)) for k in ("kind", "id", "title"))):
        out.append("source needs kind, id and title")
    pulse = isinstance(src, dict) and src.get("kind") == PULSE  # no source video: no platform id needed
    if not pulse and "youtube_id" in m and "facebook_id" in m and not (m.get("youtube_id") or m.get("facebook_id")):
        out.append("no platform id (youtube_id or facebook_id)")
    if "published_at" in m and not _clean(m.get("published_at")):
        out.append("empty published_at")
    segs = m.get("segments")
    if "segments" in m and not isinstance(segs, list):
        out.append("segments must be a list")
        segs = []
    segs = segs or []
    market = isinstance(src, dict) and src.get("kind") in MARKET_SOURCES
    if market:
        out += _market_problems(m.get("market"))
        if pulse and isinstance(m.get("market"), dict):
            out += _pulse_problems(m["market"])
    elif len(segs) < MIN_SEGMENTS:
        out.append(f"{len(segs)} segments (at least {MIN_SEGMENTS})")
    ids = set()
    for i, s in enumerate(segs, 1):
        where = f"segment {s.get('id') if isinstance(s, dict) and s.get('id') else i}"
        if not isinstance(s, dict):
            out.append(f"{where}: must be a mapping")
            continue
        out += [f"{where}: missing field '{f}'" for f in SEGMENT_FIELDS if f not in s]
        if s.get("id") in ids:
            out.append(f"{where}: duplicate id")
        ids.add(s.get("id"))
        if s.get("kind") not in KINDS:
            out.append(f"{where}: kind must be one of {', '.join(KINDS)}")
        if not _clean(s.get("term")):
            out.append(f"{where}: empty term")
        narration = _clean(s.get("narration"))
        if not narration:
            out.append(f"{where}: empty narration")
        else:
            out += [f"{where} narration: {r}" for r in rules.narration_problems(narration)]
        if s.get("diagram") is not None:
            out += [f"{where} diagram: {r}" for r in diagrams.validate(s["diagram"])]
        facts = s.get("facts")
        if not (isinstance(facts, list) and facts and all(_clean(f) for f in facts)):
            out.append(f"{where}: facts must be a non-empty list of texts")
        hooks = s.get("hooks")
        if not (isinstance(hooks, list) and hooks):
            out.append(f"{where}: needs at least one hook")
        else:
            out += [f"{where}: hook {h!r} is over {MAX_HOOK} characters or breaks a title rule"
                    for h in hooks if not _hook_ok(_clean(h))]
    return out


def path_for(m: dict, root: Path) -> Path:
    return Path(root) / FOLDER / f"{m['source']['kind']}-{m['source']['id']}.json"


def save(m: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def merge(old: dict | None, new: dict) -> dict:
    """`old` with the platform ids it lacks (and its publish time when it had none) taken from `new`;
    no `old` → `new`. Merging the same file twice changes nothing."""
    if not old:
        return new
    out = dict(old)
    for k in ("youtube_id", "facebook_id", "published_at"):
        if not out.get(k) and new.get(k):
            out[k] = new[k]
    return out


def write(m: dict, root: Path) -> Path:
    """Merge a valid `m` into its data/material/ file (created when missing; an unreadable existing file is
    replaced) → the path. An invalid `m` → ValueError, nothing written."""
    problems = validate(m)
    if problems:
        raise ValueError(f"invalid material: {'; '.join(problems)}")
    path = path_for(m, root)
    try:
        old = load(path) if path.exists() else None
    except ValueError:
        old = None
    return save(merge(old if isinstance(old, dict) else None, m), path)


def add(paths: list, root: Path) -> list[Path]:
    """Merge each run's output copy into data/material/ (skipping files that don't validate)."""
    out = []
    for p in paths:
        try:
            m = load(p)
            problems = validate(m)
            if problems:
                print(f"material: skipped {p}: {'; '.join(problems)}")
                continue
            out.append(write(m, root))
        except Exception as e:  # never let one file stop the history commit
            print(f"material: skipped {p}: {e}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "add":
        sys.exit("usage: python -m autopilot.material add <material.json>...")
    done = add(sys.argv[2:], Path(__file__).resolve().parents[1])
    print(f"material: {len(done)} file(s) merged into {FOLDER}")
