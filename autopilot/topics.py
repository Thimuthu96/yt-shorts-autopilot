"""Topic backlog: topics/backlog.yaml, a queue of video ideas with category rotation.

    CATEGORIES                                   the topic space (spec §4)
    Topic(id, title_idea, category, format, angle)
    load(path) -> list[dict]                     the backlog entries ([] when the file is missing)
    save(path, backlog)
    next_topic(backlog, history_titles, recent) -> Topic | None
                                                 first queued topic that differs in category from the last
                                                 published video, isn't a second `levels` in a row, and whose
                                                 title isn't a near-copy (token Jaccard >= 0.6) of a past title;
                                                 none passes rotation → the first non-duplicate (logged)
    mark(backlog, id, status, reason=None, date=None)   status queued | used | failed
    needs_refill(backlog, minimum=10) -> bool    fewer than `minimum` queued
    add(backlog, proposals, history_titles, log) -> int   append writer.propose_topics results as queued
    similar(a, b) -> float                       token Jaccard of two normalized titles
"""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

CATEGORIES = ("history", "engineering", "science", "psychology", "laws_jobs_customs", "luck_games", "what_if",
              "levels")
FORMATS = ("explainer", "levels")
STATUSES = ("queued", "used", "failed")
SIMILAR = 0.6


def log(*a):
    print(*a, flush=True)


@dataclass
class Topic:
    id: str
    title_idea: str
    category: str
    format: str
    angle: str


def load(path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return list(yaml.safe_load(p.read_text(encoding="utf-8")) or [])


def save(path, backlog: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    head = "# Gus Explains topic queue (autopilot/topics.py). The daily run takes the next queued topic;\n" \
           "# status: queued | used | failed. Refilled by Gemini when fewer than gus.min_backlog are queued.\n"
    p.write_text(head + yaml.safe_dump(backlog, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")


def _tokens(title: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", (title or "").lower().replace("'", "")):
        out.add(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def similar(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _duplicate(title: str, history_titles: list[str]) -> str | None:
    for h in history_titles:
        if similar(title, h) >= SIMILAR:
            return h
    return None


def _topic(e: dict) -> Topic:
    return Topic(str(e["id"]), str(e["title_idea"]), str(e.get("category", "")), str(e.get("format", "explainer")),
                 str(e.get("angle", "")))


def next_topic(backlog: list[dict], history_titles: list[str], recent: list[dict], log=log) -> Topic | None:
    last = recent[-1] if recent else {}
    last_cat, last_fmt = last.get("category"), last.get("format")
    fresh = []
    for e in backlog:
        if e.get("status", "queued") != "queued":
            continue
        dup = _duplicate(e.get("title_idea", ""), history_titles)
        if dup:
            log(f"topics: {e['id']} skipped, too close to the published title {dup!r}")
            continue
        fresh.append(e)
    for e in fresh:
        if last_cat and e.get("category") == last_cat:
            continue
        if last_fmt == "levels" and e.get("format") == "levels":
            continue
        return _topic(e)
    if fresh:
        log(f"topics: rotation relaxed, every queued topic follows a {last_cat} / {last_fmt} video")
        return _topic(fresh[0])
    return None


def mark(backlog: list[dict], id: str, status: str, reason: str | None = None, date: str | None = None) -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    for e in backlog:
        if str(e.get("id")) == str(id):
            e["status"], e["reason"] = status, reason
            e["used_on"] = date if status != "queued" else None
            return
    raise KeyError(f"no topic {id!r} in the backlog")


def needs_refill(backlog: list[dict], minimum: int = 10) -> bool:
    return sum(1 for e in backlog if e.get("status", "queued") == "queued") < minimum


def slugify(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower().replace("'", "")).strip("-")
    return s[:n].rstrip("-") or "topic"


def add(backlog: list[dict], proposals: list[dict], history_titles: list[str], log=log) -> int:
    """Append valid, non-duplicate proposals ({title_idea, category, format, angle}) as queued topics."""
    titles = list(history_titles) + [e.get("title_idea", "") for e in backlog]
    ids = {str(e.get("id")) for e in backlog}
    added = 0
    for p in proposals:
        t, cat, fmt, angle = (str(p.get(k) or "").strip() for k in ("title_idea", "category", "format", "angle"))
        if not t or cat not in CATEGORIES or fmt not in FORMATS or not angle:
            log(f"topics: proposal dropped (fields): {p}")
            continue
        if _duplicate(t, titles):
            log(f"topics: proposal dropped (too close to an earlier title): {t}")
            continue
        base = slugify(t)
        tid, k = base, 2
        while tid in ids:
            tid, k = f"{base}-{k}", k + 1
        ids.add(tid)
        titles.append(t)
        backlog.append({"id": tid, "title_idea": t, "category": cat, "format": fmt, "angle": angle,
                        "status": "queued", "used_on": None, "reason": None})
        added += 1
    log(f"topics: {added} new topic(s) queued")
    return added
