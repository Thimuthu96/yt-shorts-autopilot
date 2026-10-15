"""Shorts material from published trading lessons (epic-standalone-shorts entry 6): trading-lessons keeps its
package only in 7-day run artifacts and writes nothing for Shorts, so the material (autopilot/material.py format,
source kind "lesson") is rebuilt from what lasts: the lesson's curriculum entry, its glossary terms and the
history entry's recorded examples. Lesson code and outputs are only read, never changed.

    crypto_examples(entry) -> bool       every recorded example is BTC or ETH (crypto-only lessons; a gold or FX
                                         example, or none recorded → False: no Shorts from that lesson)
    build_lesson(episode, glossary, entry) -> material | None
                                         overview (the search title answered by the key points) + one segment per
                                         key point + one per glossary concept, narration = the approved text,
                                         facts = it (+ the recorded example's coin and timeframe); None when the
                                         examples aren't BTC / ETH
    from_history(history, curriculum, glossary, log) -> [material]
                                         the valid material of every published lesson (invalid ones logged)
"""
from autopilot import material

COINS = ("BTC", "ETH")


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _coin(asset) -> str:
    return _clean(asset).upper().replace("/", "-").split("-")[0]


def crypto_examples(entry: dict) -> bool:
    ex = entry.get("examples") or []
    return bool(ex) and all(_coin(e.get("asset")) in COINS for e in ex)


def _example_facts(entry: dict) -> list[str]:
    out = []
    for e in entry.get("examples") or []:
        name = {"BTC": "Bitcoin", "ETH": "Ethereum"}.get(_coin(e.get("asset")), _coin(e.get("asset")))
        tf = _clean(e.get("timeframe"))
        out.append(f"The lesson's example was a {name} chart" + (f" on the {tf} timeframe." if tf else "."))
    return list(dict.fromkeys(out))


def build_lesson(episode: dict, glossary: dict, entry: dict) -> dict | None:
    """The material of one published lesson (None when its recorded examples aren't all BTC / ETH)."""
    if not crypto_examples(entry):
        return None
    question = _clean(episode.get("search_title") or episode.get("title"))
    points = [_clean(p) for p in episode.get("key_points") or [] if _clean(p)]
    concepts = [(k, glossary[k]) for k in episode.get("concepts") or [] if k in glossary]
    extra = _example_facts(entry)
    segs = [{"id": "overview", "kind": "overview", "term": question, "narration": " ".join(points), "diagram": None,
             "facts": points + extra, "hooks": material.hooks_for("", question)}]
    for n, p in enumerate(points, 1):
        term = _clean(concepts[(n - 1) % len(concepts)][1]["term"]) if concepts else question
        segs.append({"id": f"point_{n}", "kind": "concept", "term": term, "narration": p, "diagram": None,
                     "facts": [p] + extra, "hooks": material.hooks_for(term, question)})
    for k, g in concepts:
        term, definition = _clean(g.get("term")), _clean(g.get("definition"))
        segs.append({"id": f"concept_{k}", "kind": "concept", "term": term, "narration": definition,
                     "diagram": None, "facts": [definition] + extra, "hooks": material.hooks_for(term, question)})
    return {"version": material.VERSION, "source": {"kind": "lesson", "id": episode["id"], "title": question},
            "youtube_id": entry.get("video_id"), "facebook_id": entry.get("fb_video_id"),
            "published_at": entry.get("publish_at") or entry.get("date"), "segments": segs}


def from_history(history, curriculum: list[dict], glossary: dict, log=print) -> list[dict]:
    """Material for every published lesson in history (latest entry per episode); a lesson whose examples aren't
    BTC / ETH, that left the curriculum or whose material doesn't validate is logged and skipped."""
    by_id = {e.get("id"): e for e in curriculum}
    latest = {}
    for v in history.uploaded():
        if v.get("kind") == "lesson" and v.get("episode"):
            latest[v["episode"]] = {**latest.get(v["episode"], {}), **{k: x for k, x in v.items() if x}}
    out = []
    for ep, entry in latest.items():
        episode = by_id.get(ep)
        if episode is None:
            log(f"Shorts: lesson {ep} is no longer in the curriculum; no material")
            continue
        m = build_lesson(episode, glossary, entry)
        if m is None:
            log(f"Shorts: lesson {ep}'s examples aren't BTC / ETH; no material")
            continue
        problems = material.validate(m)
        if problems:
            log(f"Shorts: lesson {ep} material skipped: {'; '.join(problems)}")
            continue
        out.append(m)
    return out
