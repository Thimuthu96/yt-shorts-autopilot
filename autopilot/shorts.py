"""Standalone Shorts (epic-standalone-shorts, kind: short): an original 30-40 second vertical piece with its own hook
and script, written from one segment of a long video's Shorts material (autopilot/material.py). Dark until
`shorts.enabled`: timed short_a / short_b runs log and skip; manual runs make and publish.

    load_materials(root, log)            every valid data/material/*.json (invalid files logged and skipped)
    key(m)                               "<source kind>-<source id>" (what a Short's history entry names)
    used_segments(history)               {(material key, segment id)} already used by published Shorts
    pick_concept(materials, history)     (material, segment) of the oldest Basics / Lesson material with an
                                         unused segment, else None
    opening_problems(text)               a subscribe ask in the first sentence → [reason] (narration-rules.md)
    check_script(cfg, pkg, known)        deterministic problems: every scene narrated, word bounds, narration
                                         rules, no subscribe ask in the opening, spoken numbers in the facts
    write_concept(cfg, m, seg, log)      Gemini writes {hook, scenes: hook / explain / payoff}; 3 attempts
    render_slides(cfg, m, seg, pkg, wd)  9:16: the hook card (frame 0, `cover`) → the term, the segment's diagram
                                         with step reveal (diagrams.step_layers) or its fact, the payoff card
    title_problems(hook) / card_problems(card)   packaging.md Short row: the hook question is the title (≤ 60
                                         characters, rules.title_problems); the hook card (frame 0) carries 1-4 words
    package(cfg, pkg, ctx, log)          a hook breaking a title rule is rewritten once by Gemini, else
                                         RuntimeError ("Short packaging"); a bad card falls back to the term / hook
    metadata(cfg, m, seg, pkg)           title = hook (no hashtag); description = hook, payoff, source, the
                                         disclosure line once, hashtags (#Shorts last); reel_caption(meta, cfg):
                                         the same metadata without #Shorts
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from autopilot import diagrams, material, rules
from autopilot.basics import unknown_numbers as _concept_unknown
from autopilot.lesson_slides import BG, FG, MUTED, PORTRAIT, Layout, _flow, _font, _title_font
from autopilot.llm import generate_json
from autopilot.script import _models
from autopilot.slides import PANEL, _hex, _wrap

MAX_TITLE = 60  # packaging.md: a Short's title is its hook question, 60 characters or fewer
CARD_WORDS = 4  # the hook card (frame 0): 1-4 words
MIN_WORDS, MAX_WORDS = 70, 105  # cfg shorts.min_words / max_words: 30-40 s at +0%
SCENES = ("hook", "explain", "payoff")
CONCEPT_SOURCES = ("basics", "lesson")
CHIPS = {"basics": "CRYPTO BASICS", "lesson": "TRADING LESSON", "triggered": "WHY IT MOVED", "recap": "WEEKLY RECAP"}
DISCLAIMER = "Education only · Not financial advice"
SUBSCRIBE_OPEN = re.compile(r"\bsubscri[bp]\w*|\bhit the (?:bell|like)\b|\blike and (?:share|follow)\b|"
                            r"\bfollow (?:us|the channel|for more)\b|\bturn on (?:the )?notifications?\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
DIAGRAM_GAP = 44


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


def pick_concept(materials: list[dict], history) -> tuple[dict, dict] | None:
    """The oldest Basics / Lesson material's first unused segment (concept segments before the overview)."""
    used = used_segments(history)
    for m in sorted((m for m in materials if m["source"]["kind"] in CONCEPT_SOURCES), key=_published):
        segs = sorted(m["segments"], key=lambda s: s.get("kind") != "concept")
        for s in segs:
            if (key(m), s["id"]) not in used:
                return m, s
    return None


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
    for c in (_clean(term).upper() + "?", " ".join(_clean(pkg["hook"]).upper().split()[:CARD_WORDS])):
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


def write_concept(cfg: dict, m: dict, seg: dict, log=_log) -> dict:
    """{hook, card, scenes} for a concept Short of `seg`; a draft with any check_script problem is discarded
    (its problems are sent back); RuntimeError after 3 attempts."""
    problems: list[str] = []
    known = concept_facts(m, seg)
    for attempt in range(1, 4):
        log(f"Writing the Short script ({key(m)} · {seg['id']}, attempt {attempt}/3)...")
        pkg = _parse(generate_json(_concept_prompt(cfg, m, seg, problems), _models(cfg), temperature=0.8))
        problems = check_script(cfg, pkg, known)
        if not problems:
            for s in pkg["scenes"]:
                if s["id"] == "explain":
                    s["term"] = seg["term"]
            log(f"Short script: {_words(pkg['scenes'])} words · hook: {pkg['hook']}")
            return package(cfg, pkg, seg["term"], log)
        log(f"Discarding Short draft: {'; '.join(problems)}")
    raise RuntimeError(f"Could not write a valid Short in 3 attempts: {'; '.join(problems)}")


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
    return _Ctx(cfg, layout, _hex(cfg["video"].get("accent", "FFD400")),
                cfg["channel"].get("display_name", "CryptoFX Daily").upper(),
                CHIPS.get(m["source"]["kind"], "CRYPTO"), DISCLAIMER)


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


def hook_card(ctx: _Ctx, text: str) -> Image.Image:
    """Frame 0: the hook card words in huge type over an accent bar (no captions over it)."""
    img, d = _base(ctx)
    L = ctx.layout
    x0, y0, x1, y1 = L.content_box
    text = _clean(text).upper()
    y = _flow(d, [{"text": text, "size": _fit(d, text, 190, x1 - x0), "title": True, "fill": FG, "gap": 40,
                   "max_lines": 5}], (x0, y0, x1, y1 - 60), L, valign="center", who="hook card")
    d.rectangle([x0, y, x0 + 240, y + 22], fill=ctx.accent)
    return img


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


def text_slide(ctx: _Ctx, heading: str, text: str) -> Image.Image:
    img, d = _base(ctx)
    _flow(d, [{"text": heading, "size": 48, "bold": True, "fill": ctx.accent, "gap": 34, "max_lines": 1},
              {"text": text, "size": 64, "bold": True, "fill": FG, "max_lines": 9}],
          ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.2, who="Short text slide")
    return img


def _cover(ctx: _Ctx, card_text: str, follow_img: Image.Image, workdir: Path) -> tuple[dict, Path]:
    card = workdir / "thumbnail.jpg"
    hook_card(ctx, card_text).save(card, quality=92)
    follow = workdir / "short_01_follow.png"
    follow_img.save(follow)
    return {"image": card, "cover": True, "follow": {"image": follow, "reveal": None}, "reveal": None,
            "id": "hook"}, card


def render_slides(cfg: dict, m: dict, seg: dict, pkg: dict, workdir: Path) -> tuple[list[dict], Path]:
    """The concept Short's slides (one per scene) → (slides, hook card path = the thumbnail / Reel cover)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = _ctx(cfg, m)
    cover, card = _cover(ctx, pkg.get("card") or pkg["hook"], term_slide(ctx, seg["term"]), workdir)
    out = [cover]
    path = workdir / "short_02.png"
    if seg.get("diagram"):
        spec = seg["diagram"]
        diagram_slide(ctx, seg["term"], spec).save(path)
        slide = {"image": path, "reveal": None, "id": "explain"}
        slide["base"], slide["steps"] = diagrams.step_layers(
            lambda show: diagram_slide(ctx, seg["term"], spec, show=show), diagrams.steps(spec), workdir, "short_02")
    else:
        text_slide(ctx, seg["term"].upper(), seg["facts"][0]).save(path)
        slide = {"image": path, "reveal": None, "id": "explain"}
    out.append(slide)
    path = workdir / "short_03.png"
    text_slide(ctx, "REMEMBER", seg["facts"][0]).save(path)
    out.append({"image": path, "reveal": None, "id": "payoff"})
    return out, card


# ─── packaging ─────────────────────────────────────────────────────────────

def hashtags(m: dict, seg: dict | None = None) -> list[str]:
    tags = ["#Crypto", "#CryptoBasics" if m["source"]["kind"] == "basics" else "#Trading"]
    text = " ".join([m["source"]["title"], (seg or {}).get("term", "")]).lower()
    for word, tag in (("bitcoin", "#Bitcoin"), ("ethereum", "#Ethereum"), ("ether", "#Ethereum")):
        if word in text and tag not in tags:
            tags.append(tag)
    return tags[:4] + ["#Shorts"]


HASHTAG = re.compile(r"(?<![\w&])#\w+")


def _no_tags(text: str) -> str:
    return _clean(HASHTAG.sub("", text or ""))


def metadata(cfg: dict, m: dict, seg: dict | None, pkg: dict, extra: list[str] | None = None) -> dict:
    """YouTube metadata: title = the hook question (packaging rules already checked; any hashtag removed);
    description = hook → payoff → `extra` lines → source → the disclosure line once → hashtags (#Shorts last)."""
    line = rules.disclosure(cfg, "shorts")
    payoff = " ".join(s["text"] for s in pkg["scenes"] if s["id"] == pkg["scenes"][-1]["id"])
    body = rules.without_disclosure(_no_tags(payoff), line)
    tags = hashtags(m, seg)
    parts = [_no_tags(pkg["hook"]), body, *(extra or []), f"From the full video: {m['source']['title']}",
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
