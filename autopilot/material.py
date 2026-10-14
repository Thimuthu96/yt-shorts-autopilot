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
      ]
    }

    build_basics(topic, scenes, entry, cfg)  the material of one Basics episode: an overview segment (the
                                         question answered by the hook narration, the summary as its fact)
                                         + one concept segment per point (its narration without the
                                         subscribe ask, its diagram, its approved text as the fact)
    validate(m) -> [reason]              [] = usable
    path_for(m, root)                    data/material/<kind>-<id>.json
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
    if "youtube_id" in m and "facebook_id" in m and not (m.get("youtube_id") or m.get("facebook_id")):
        out.append("no platform id (youtube_id or facebook_id)")
    if "published_at" in m and not _clean(m.get("published_at")):
        out.append("empty published_at")
    segs = m.get("segments")
    if "segments" in m and not isinstance(segs, list):
        out.append("segments must be a list")
        segs = []
    segs = segs or []
    if len(segs) < MIN_SEGMENTS:
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
