"""Gus Explains story validator (format v1 beats and v2 shots).

    load_catalog(path)              studio/catalog.json
    validate(story, catalog)        every problem as a short string naming the shot and field; [] = valid
    words(story)                    caption words in the whole story
    spoken(beat)                    what the voice says: `say` or `text`
    gus_narration_problems(text)    rules.narration_problems without the crypto-only rules (dates, clock
                                    times, UTC, price targets, 10x, buy/sell calls); bare years are fine
"""
import json
import re
from pathlib import Path

from autopilot import rules

ROOT = Path(__file__).resolve().parent.parent
FORMATS = ("explainer", "levels")
CRYPTO_ONLY = ("date/time", "price target", "10x", "buy/sell call")
HALF_V1 = 0.22  # frame half-width / dist for v1 stories (fov 42); v2 reads the catalog (fov 60)
HOOK_MAX_WORDS = 10
MAX_CUTS = 2


def log(*a):
    print(*a, flush=True)


def load_catalog(path=None) -> dict:
    return json.loads(Path(path or ROOT / "studio/catalog.json").read_text())


def spoken(beat: dict) -> str:
    return beat.get("say") or beat["text"]


def words(story: dict) -> int:
    return sum(len(b.get("text", "").split()) for b in story.get("beats", []))


def gus_narration_problems(text: str) -> list[str]:
    return [p for p in rules.narration_problems(text) if not p.startswith(tuple(f"{r}:" for r in CRYPTO_ONLY))]


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _vec(x, n) -> bool:
    return isinstance(x, (list, tuple)) and len(x) == n and all(_num(v) for v in x)


def _in(p, field, value, allowed, label) -> None:
    if value not in allowed:
        p.append(f"{label}: unknown {field} {value!r}")


def _look(p, cid, look, cat) -> None:
    label = f"cast {cid}"
    if look == "gus":
        return
    if not isinstance(look, dict):
        p.append(f"{label}: look must be 'gus' or an object")
        return
    for k, v in look.items():
        if k not in cat["costume_keys"]:
            p.append(f"{label}: unknown look key {k!r}")
        elif k == "costume" and v not in cat["costumes"]:
            p.append(f"{label}: unknown costume {v!r}")
        elif k == "hat" and v not in cat["hats"]:
            p.append(f"{label}: unknown hat {v!r}")
        elif k == "glasses" and v not in cat["glasses"]:
            p.append(f"{label}: unknown glasses {v!r}")
        elif k == "prop" and v not in cat["held_props"]:
            p.append(f"{label}: unknown held prop {v!r}")


def _fx(p, label, fx, cat) -> None:
    _in(p, "fx", fx.get("type"), cat["fx"], label)
    if "scale" in fx and not _num(fx["scale"]):
        p.append(f"{label}: fx scale must be a number")
    if "period" in fx:
        if fx.get("type") != "beam":
            p.append(f"{label}: fx period only on beam")
        elif not _num(fx["period"]) or fx["period"] <= 0:
            p.append(f"{label}: fx period must be > 0")


def _event(p, label, ev, nwords, ids, cat) -> None:
    do = ev.get("do")
    if do not in cat["events"]:
        p.append(f"{label}: unknown event {do!r}")
        return
    aw = ev.get("at_word")
    if not isinstance(aw, int) or isinstance(aw, bool) or not 0 <= aw < nwords:
        p.append(f"{label}: at_word {aw!r} out of range (0-{nwords - 1})")
    spec = cat["event_fields"].get(do, {})
    for k in spec.get("need", []):
        if k not in ev:
            p.append(f"{label}: {do} needs {k!r}")
    if "who" in ev and ev["who"] not in ids:
        p.append(f"{label}: unknown id {ev['who']!r}")
    if do == "expr":
        _in(p, "expr", ev.get("expr"), cat["exprs"], label)
    elif do == "pose":
        _in(p, "pose", ev.get("pose"), cat["poses"], label)
    elif do == "motion":
        _in(p, "motion", ev.get("motion"), cat["motions"], label)
    elif do == "fx":
        _fx(p, label, {**ev, "type": ev.get("type")}, cat)
    elif do == "sign" and "style" in ev:
        _in(p, "sign style", ev["style"], cat["sign_styles"], label)
    elif do == "sfx_mark":
        _in(p, "sfx", ev.get("sfx"), cat["sfx"], label)
    elif do == "act":
        act = ev.get("act")
        _in(p, "act", act, cat["acts"], label)
        for k in cat["act_fields"].get(act, {}).get("need", []):
            if k not in ev:
                p.append(f"{label}: act {act} needs {k!r}")
        if "id" in ev and ev["id"] not in ids:
            p.append(f"{label}: unknown id {ev['id']!r}")
        if "expr" in ev:
            _in(p, "expr", ev["expr"], cat["exprs"], label)


LISTS = ("remove", "props", "chars", "signs", "fx", "sfx", "events")


def _shape(story) -> list[str]:
    """Wrong JSON shapes as problems (never an exception), so a writer can redraft."""
    if not isinstance(story, dict):
        return ["the story must be a JSON object"]
    p = []
    if not isinstance(story.get("cast", {}), dict) or any(not isinstance(c, dict) for c in story.get("cast", {}).values()):
        p.append("cast must be an object of {id: {look: ...}}")
    for k in ("sources", "hashtags"):
        if not isinstance(story.get(k, []), list):
            p.append(f"{k} must be a list")
    sources = story.get("sources", [])
    if isinstance(sources, list) and any(not isinstance(x, dict) for x in sources):  # checked as a list first
        p.append("sources must be objects {url, title}")
    for k in ("title", "summary", "slug"):
        if k in story and not isinstance(story[k], str):
            p.append(f"{k} must be a string")
    beats = story.get("beats", [])
    if not isinstance(beats, list):
        return p + ["beats must be a list of shots"]
    for i, b in enumerate(beats):
        if not isinstance(b, dict):
            p.append(f"beat {i}: must be an object")
            continue
        if not isinstance(b.get("text", ""), str) or ("say" in b and not isinstance(b["say"], str)):
            p.append(f"beat {i}: text / say must be strings")
        for k in ("set", "cam"):
            if b.get(k) is not None and not isinstance(b[k], dict):
                p.append(f"beat {i}: {k} must be an object")
        for k in LISTS:
            v = b.get(k, [])
            if v is None:
                continue
            if not isinstance(v, list):
                p.append(f"beat {i}: {k} must be a list")
            elif k == "remove":
                if any(not isinstance(x, str) for x in v):
                    p.append(f"beat {i}: remove must list ids")
            elif any(not isinstance(x, dict) for x in v):
                p.append(f"beat {i}: every item of {k} must be an object")
    return p


def validate(story: dict, catalog: dict) -> list[str]:
    """Every problem as a short string; never raises on a malformed story."""
    shape = _shape(story)
    if shape:
        return shape
    try:
        return _validate(story, catalog)
    except (TypeError, AttributeError, KeyError, ValueError, IndexError) as e:
        return [f"malformed story: {type(e).__name__}: {e}"]


def _validate(story: dict, catalog: dict) -> list[str]:
    p: list[str] = []
    cat = catalog
    for k in ("slug", "title", "category", "format", "music_mood", "cast", "beats", "sources", "summary", "hashtags"):
        if k not in story:
            p.append(f"missing key {k!r}")
    if p:
        return p
    v2 = story.get("version") == 2
    half = cat["frame_half_width"] if v2 else HALF_V1
    beats = story["beats"]

    if not re.fullmatch(r"[a-z0-9-]{3,48}", str(story["slug"])):
        p.append(f"bad slug {story['slug']!r}")
    title = story["title"]
    if len(title) > 60:
        p.append(f"title too long: {len(title)} chars (max 60)")
    p += [f"title: {x}" for x in rules.title_problems(title)]
    if story["format"] not in FORMATS:
        p.append(f"unknown format {story['format']!r}")
    if story["music_mood"] not in ("curious", "tense", "upbeat", "epic"):
        p.append(f"unknown music_mood {story['music_mood']!r}")
    summ = story["summary"]
    if not 1 <= len(re.findall(r"[.!?](?:\s|$)", summ)) <= 3 or len(summ) > 400:
        p.append("summary must be 1-3 sentences and at most 400 chars")

    lo, hi = (15, 40) if v2 else (4, 14)
    if not lo <= len(beats) <= hi:
        p.append(f"{len(beats)} shots (need {lo}-{hi})")
    if story["format"] == "levels":
        lv = [b.get("level") for b in beats if "level" in b]
        if v2 and not 4 <= len(lv) <= 7:  # v2: shots carry `level` on the shot that opens each level
            p.append("levels story needs 4-7 levels")
        elif not v2 and not 4 <= len(beats) <= 7:
            p.append("levels story needs 4-7 beats")
        if not lv or any(not isinstance(x, int) for x in lv) or lv[0] != 1 or any(b <= a for a, b in zip(lv, lv[1:])):
            p.append("levels: `level` ints must start at 1 and strictly increase")

    cast = story["cast"]
    for cid, c in cast.items():
        _look(p, cid, c.get("look"), cat)

    n = words(story)
    if n < 130:
        p.append(f"too short: {n} words (130-170)")
    elif n > 170:
        p.append(f"too long: {n} words (130-170)")
    bad = gus_narration_problems(" ".join(spoken(b) for b in beats if "text" in b))
    p += [f"narration: {x}" for x in bad]

    known: set[str] = set()  # ids of props and characters alive in the current set
    prev_chars: set[str] = set()
    cuts = 0
    for i, b in enumerate(beats):
        L = f"beat {i}"
        text = b.get("text", "")
        nw = len(text.split())
        if not text:
            p.append(f"{L}: no text")
        if v2:
            if not 2 <= nw <= (HOOK_MAX_WORDS if i == 0 else 8):
                p.append(f"{L}: {nw} words (2-{HOOK_MAX_WORDS if i == 0 else 8})")
        elif nw > 22:
            p.append(f"{L}: text too long: {nw} words (max 22)")
        s = b.get("set") or {}
        _in(p, "set", s.get("type"), cat["sets"], L)
        _in(p, "mood", s.get("mood"), cat["moods"], L)
        if b.get("keep"):
            if i == 0:
                p.append(f"{L}: keep on the first beat")
            for r in (b.get("remove") or []):
                if r not in prev_chars and r not in known:
                    p.append(f"{L}: remove {r!r} not in the previous beat")
        else:
            known = set()
        for r in (b.get("remove") or []):
            known.discard(r)
        for pr in (b.get("props") or []):
            _in(p, "prop", pr.get("type"), cat["props"], L)
            if "anim" in pr and pr["anim"] is not None:
                _in(p, "anim", pr["anim"], cat["anims"], L)
            known.add(pr.get("id"))
        chars = (b.get("chars") or [])
        for c in chars:
            if c.get("id") not in cast:
                p.append(f"{L}: character {c.get('id')!r} not in cast")
            for k, cl in (("pose", "poses"), ("expr", "exprs"), ("motion", "motions"), ("enter", "enters")):
                if c.get(k) is not None:
                    _in(p, k, c[k], cat[cl], L)
            known.add(c.get("id"))
        if i == 0 and not chars:
            p.append(f"{L}: no character on screen")
        for sg in (b.get("signs") or []):
            if "style" in sg:
                _in(p, "sign style", sg["style"], cat["sign_styles"], L)
            if "rot" in sg and not _vec(sg["rot"], 3):
                p.append(f"{L}: sign rot must be [x, y, z] numbers")
        for fx in (b.get("fx") or []):
            _fx(p, L, fx, cat)
        for sf in (b.get("sfx") or []):
            _in(p, "sfx", sf.get("type"), cat["sfx"], L)
        ids = known | set(cast)
        for j, ev in enumerate((b.get("events") or [])):
            _event(p, f"{L} event {j}", ev, nw, ids, cat)

        cam = b.get("cam") or {}
        mv = cam.get("move", "static")
        _in(p, "cam move", mv, cat["cam_moves"], L)
        fr = cam.get("frame")
        if fr is not None:
            _in(p, "cam frame", fr, cat["cam_frames"], L)
            if cam.get("subject") is None:
                p.append(f"{L}: cam frame needs a subject")
        if fr in ("two_shot", "ots") and cam.get("look_at") is None:
            p.append(f"{L}: cam frame {fr} needs look_at")
        for key in ("subject", "follow", "look_at"):
            if cam.get(key) is not None and cam[key] not in ids:
                p.append(f"{L}: unknown cam {key} {cam[key]!r}")
        if fr == "ots" and mv in ("push", "closeUp"):
            p.append(f"{L}: ots frame can't {mv}")
        if fr == "pov" and mv in ("pull", "flyOver", "lowSweep"):
            p.append(f"{L}: pov frame can't {mv}")
        tr = b.get("transition")
        if tr is not None:
            _in(p, "transition", tr, cat["transitions"], L)
        if tr == "cut" or cam.get("cut"):
            cuts += 1
        if v2 and not b.get("events") and mv == "static":
            p.append(f"{L}: no events and a static camera")
        if "target" in cam and "dist" in cam and _vec(cam["target"], 3):
            lim = half * cam["dist"]
            for c in chars:
                pos = c.get("pos")
                if _vec(pos, 3) and abs(pos[0] - cam["target"][0]) > lim:
                    p.append(f"{L}: {c['id']} out of frame (x {pos[0]} vs target {cam['target'][0]}, limit ±{lim:.1f})")
        prev_chars = {c.get("id") for c in chars}
    if v2 and cuts > MAX_CUTS:
        p.append(f"too many cuts: {cuts} (max {MAX_CUTS})")

    src = story["sources"]
    if len([s for s in src if str(s.get("url", "")).startswith("https://")]) < 2:
        p.append("need ≥ 2 sources with https URLs")
    tags = story["hashtags"]
    if not 3 <= len(tags) <= 5 or any(not t.startswith("#") for t in tags) or any(t.lower() == "#shorts" for t in tags):
        p.append("need 3-5 hashtags starting with #, none #Shorts")
    return p
