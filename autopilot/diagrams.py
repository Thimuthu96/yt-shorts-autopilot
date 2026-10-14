"""Drawn concept diagrams with a step-by-step reveal (shared: Crypto Basics now, epics 3 and 4 later).

A diagram spec (YAML / dict) is shape-independent; the same spec lays itself out for lesson_slides.LANDSCAPE
(16:9) and PORTRAIT (9:16):

    type: flow       nodes: [{label, say, coin?, note?, arrow?}]  2-5 boxes joined by arrows; `arrow` = the label
                     on the arrow into this node (never on the first); horizontal in 16:9, vertical in 9:16
    type: compare    left / right: {label, say, coin?} column headers + rows: [{left, right, say}] (1-4);
                     two columns in both shapes
    type: timeline   events: [{label, say, note?}] (2-5) on an axis: horizontal in 16:9, vertical in 9:16
    any type         notes: [{text, say}] (at most 2): callouts under the diagram

`say` = the spoken aliases that reveal a part (a non-empty list, no digits); `coin` = a ticker of 2-5 uppercase
letters drawn as a round badge (BTC / ETH in their brand colours, any other in the accent; no image files).

    validate(spec) -> [reason]                  [] = usable; one reason per problem
    steps(spec) -> [{key, name, names, items}]  reveal order = spec order: flow node k with the arrow into it
                                                (arrow first); compare left header, right header, then each
                                                row (both cells); timeline event k with the axis segment into
                                                it; then the notes. name = the first `say` alias
    naming_order(spec) -> str                   '"fund", "shares", …' (the first alias of each step, in order)
    draw(img, box, spec, layout, accent, show=None, who="diagram") -> {item: bbox}
                                                lays out every part inside `box` and paints only the items in
                                                `show` (None = all), so every frame has the same layout; text
                                                never below layout.min_text; a spec that can't fit (or isn't
                                                valid) → ValueError naming `who`
    step_layers(frame, steps, workdir, stem) -> (base path, slide steps)
                                                frame(show) = the whole slide with only `show` painted → the
                                                base (nothing shown) + one diff-crop layer per item
                                                (reveal.diff_crops), grouped per step for reveal.time_steps

Same inputs → same pixels; the base with every layer pasted on in order == the full slide.
"""
import re
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace

from PIL import ImageDraw

from autopilot import reveal
from autopilot.lesson_slides import _font
from autopilot.slides import BG, FG, MUTED, PANEL

TYPES = ("flow", "compare", "timeline")
COUNTS = {"nodes": (2, 5), "events": (2, 5), "rows": (1, 4)}
MAX_NOTES = 2
COIN = re.compile(r"^[A-Z]{2,5}$")
COIN_COLOURS = {"BTC": (247, 147, 26), "ETH": (98, 126, 234)}  # brand colours; other tickers use the accent
COIN_INK = (255, 255, 255)
SCALES = [round(1.5 - 0.05 * k, 2) for k in range(21)]  # 1.5 → 0.5: the largest that fits wins

KEYS = {"node": {"label", "say", "coin", "note", "arrow"}, "header": {"label", "say", "coin"},
        "row": {"left", "right", "say"}, "event": {"label", "say", "note"}, "note": {"text", "say"}}
TOP_KEYS = {"flow": {"type", "nodes", "notes"}, "compare": {"type", "left", "right", "rows", "notes"},
            "timeline": {"type", "events", "notes"}}

_F = namedtuple("_F", "font lh")


# ─── spec ──────────────────────────────────────────────────────────────────

def _text(v) -> str:
    return " ".join(str(v).split()) if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""


def _say_problems(where: str, say) -> list[str]:
    if not isinstance(say, list) or not say:
        return [f"{where}: say must be a non-empty list of spoken aliases"]
    for a in say:
        if not _text(a):
            return [f"{where}: say has an empty alias"]
        if any(ch.isdigit() for ch in str(a)):
            return [f"{where}: say alias '{a}' has a digit (spoken aliases have no numbers)"]
    return []


def _part_problems(where: str, part, kind: str, texts: tuple[str, ...], optional: tuple[str, ...] = ()) -> list[str]:
    if not isinstance(part, dict):
        return [f"{where}: must be a mapping"]
    out = []
    unknown = sorted(set(part) - KEYS[kind])
    if unknown:
        out.append(f"{where}: unknown key(s) {', '.join(map(str, unknown))}")
    for k in texts:
        if not _text(part.get(k)):
            out.append(f"{where}: empty {k}")
    for k in optional:
        if part.get(k) is not None and not _text(part.get(k)):
            out.append(f"{where}: empty {k}")
    out += _say_problems(where, part.get("say"))
    if part.get("coin") is not None and not COIN.fullmatch(str(part["coin"])):
        out.append(f"{where}: coin '{part['coin']}' must be 2-5 uppercase letters")
    return out


def _list_problems(spec: dict, key: str) -> tuple[list, list[str]]:
    items = spec.get(key)
    lo, hi = COUNTS[key]
    if not isinstance(items, list):
        return [], [f"{spec['type']} needs a list of {lo}-{hi} {key}"]
    if not lo <= len(items) <= hi:
        return [], [f"{spec['type']} needs {lo}-{hi} {key} (got {len(items)})"]
    return items, []


def validate(spec) -> list[str]:
    """Every problem with a diagram spec, one reason each ([] = usable)."""
    if not isinstance(spec, dict):
        return ["diagram must be a mapping"]
    t = spec.get("type")
    if t not in TYPES:
        return [f"diagram type '{t}' is not one of {', '.join(TYPES)}"]
    out = []
    unknown = sorted(set(spec) - TOP_KEYS[t])
    if unknown:
        out.append(f"{t} diagram: unknown key(s) {', '.join(map(str, unknown))}")
    if t == "flow":
        nodes, out_n = _list_problems(spec, "nodes")
        out += out_n
        for k, n in enumerate(nodes):
            out += _part_problems(f"nodes[{k}]", n, "node", ("label",), ("note", "arrow"))
            if k == 0 and isinstance(n, dict) and n.get("arrow") is not None:
                out.append("nodes[0]: the first node has no incoming arrow")
    elif t == "compare":
        for side in ("left", "right"):
            out += _part_problems(side, spec.get(side), "header", ("label",))
        rows, out_r = _list_problems(spec, "rows")
        out += out_r
        for k, r in enumerate(rows):
            out += _part_problems(f"rows[{k}]", r, "row", ("left", "right"))
    else:
        events, out_e = _list_problems(spec, "events")
        out += out_e
        for k, e in enumerate(events):
            out += _part_problems(f"events[{k}]", e, "event", ("label",), ("note",))
    notes = spec.get("notes")
    if notes is not None:
        if not isinstance(notes, list) or len(notes) > MAX_NOTES:
            out.append(f"notes must be a list of at most {MAX_NOTES}")
        else:
            for k, n in enumerate(notes):
                out += _part_problems(f"notes[{k}]", n, "note", ("text",))
    return out


def steps(spec: dict) -> list[dict]:
    """Reveal steps in spec order: [{key, name (first alias), names (all aliases), items (drawn parts)}]."""
    out = []

    def add(key, say, items):
        names = [_text(a) for a in say]
        out.append({"key": key, "name": names[0], "names": names, "items": items})
    t = spec["type"]
    if t == "flow":
        for k, n in enumerate(spec["nodes"]):
            add(f"node_{k + 1}", n["say"], ([f"arrow:{k}"] if k else []) + [f"node:{k}"])
    elif t == "compare":
        add("left", spec["left"]["say"], ["left"])
        add("right", spec["right"]["say"], ["right"])
        for k, r in enumerate(spec["rows"]):
            add(f"row_{k + 1}", r["say"], [f"row:{k}:left", f"row:{k}:right"])
    else:
        for k, e in enumerate(spec["events"]):
            add(f"event_{k + 1}", e["say"], ([f"segment:{k}"] if k else []) + [f"event:{k}"])
    for k, n in enumerate(spec.get("notes") or []):
        add(f"note_{k + 1}", n["say"], [f"note:{k}"])
    return out


def naming_order(spec: dict) -> str:
    """The parts' spoken names in reveal order, quoted: '"fund", "shares", "stock exchange"'."""
    return ", ".join(f'"{s["name"]}"' for s in steps(spec))


# ─── drawing primitives (ops: painted in a fixed order, so every frame has the same layout) ─────

def _rect(box, fill, outline=None, width=0, radius=0):
    return ("rect", tuple(int(v) for v in box), fill, outline, width, radius)


def _txt(xy, text, font, fill, anchor="la"):
    return ("text", (int(xy[0]), int(xy[1])), text, font, fill, anchor)


def _line(pts, fill, width):
    return ("line", tuple((int(x), int(y)) for x, y in pts), fill, width)


def _poly(pts, fill):
    return ("poly", tuple((int(round(x)), int(round(y))) for x, y in pts), fill)


def _ellipse(box, fill, outline=None, width=0):
    return ("ellipse", tuple(int(v) for v in box), fill, outline, width)


def _paint(d: ImageDraw.ImageDraw, ops: list) -> None:
    for op in ops:
        kind = op[0]
        if kind == "rect":
            _, box, fill, outline, width, radius = op
            d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
        elif kind == "text":
            _, xy, text, font, fill, anchor = op
            d.text(xy, text, font=font, fill=fill, anchor=anchor)
        elif kind == "line":
            _, pts, fill, width = op
            d.line(pts, fill=fill, width=width)
        elif kind == "poly":
            _, pts, fill = op
            d.polygon(pts, fill=fill)
        else:
            _, box, fill, outline, width = op
            d.ellipse(box, fill=fill, outline=outline, width=width)


def _bounds(d: ImageDraw.ImageDraw, ops: list) -> tuple[int, int, int, int]:
    boxes = []
    for op in ops:
        kind = op[0]
        if kind in ("rect", "ellipse"):
            boxes.append(op[1])
        elif kind == "text":
            _, xy, text, font, _, anchor = op
            boxes.append(d.textbbox(xy, text, font=font, anchor=anchor))
        else:
            pts = op[1]
            w = (op[3] + 1) // 2 if kind == "line" else 0
            boxes.append((min(x for x, _ in pts) - w, min(y for _, y in pts) - w,
                          max(x for x, _ in pts) + w, max(y for _, y in pts) + w))
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _wrap_all(d, text: str, font, width: int) -> list[str] | None:
    """Every word of `text` on lines no wider than `width` (never cut); None when one word is wider."""
    lines, cur = [], ""
    for w in _text(text).split():
        if d.textlength(w, font=font) > width:
            return None
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=font) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _block(lines: list[str], f: _F, x: int, y: int, fill, align: str = "center") -> list:
    anchor = "ma" if align == "center" else "la"
    return [_txt((x, y + i * f.lh), ln, f.font, fill, anchor) for i, ln in enumerate(lines)]


def _darker(c: tuple) -> tuple:
    return tuple(int(v * 0.72) for v in c)


def _badge_size(d, coin: str, font) -> int:
    return max(round(font.size * 2.1), round(d.textlength(coin, font=font) + font.size * 0.7))


def _badge(cx: int, cy: int, size: int, coin: str, font, accent: tuple) -> list:
    """A drawn coin: a filled circle (brand colour, else the accent) with a darker ring and the ticker."""
    fill = COIN_COLOURS.get(coin, accent)
    ink = COIN_INK if coin in COIN_COLOURS else BG
    r = size // 2
    return [_ellipse((cx - r, cy - r, cx - r + size, cy - r + size), fill, _darker(fill), max(3, size // 18)),
            _txt((cx, cy), coin, font, ink, "mm")]


def _arrow(p0, p1, fill, width: int, head: int) -> list:
    (x0, y0), (x1, y1) = p0, p1
    if y0 == y1:  # left → right
        return [_line([(x0, y0), (x1 - head + 2, y1)], fill, width),
                _poly([(x1, y1), (x1 - head, y1 - head * 0.6), (x1 - head, y1 + head * 0.6)], fill)]
    return [_line([(x0, y0), (x1, y1 - head + 2)], fill, width),  # top → bottom
            _poly([(x1, y1), (x1 - head * 0.6, y1 - head), (x1 + head * 0.6, y1 - head)], fill)]


def _content(d, label: str, note: str | None, coin: str | None, width: int, F, lf: _F, inline: bool = False,
             align: str = "center", fill=FG):
    """A label (+ a muted note, + a coin badge) fitted into `width` → (w, h, place(x, top) -> ops), x = the
    centre (align center) or the left edge (align left); None when a word can't fit."""
    D = _badge_size(d, coin, F.coin) if coin else 0
    gap = F.gap
    text_w = width - (D + gap if coin and inline else 0)
    if text_w <= 0 or D > width:
        return None
    ll = _wrap_all(d, label, lf.font, text_w)
    nl = _wrap_all(d, note, F.note.font, text_w) if note else []
    if ll is None or nl is None:
        return None
    lw = max([d.textlength(s, font=lf.font) for s in ll] + [d.textlength(s, font=F.note.font) for s in nl])
    th = len(ll) * lf.lh + (F.small_gap + len(nl) * F.note.lh if nl else 0)
    if coin and inline:
        w, h = D + gap + round(lw), max(D, th)
    elif coin:
        w, h = max(D, round(lw)), D + gap + th
    else:
        w, h = round(lw), th

    def place(x: int, top: int) -> list:
        ops = []
        if coin and inline:
            left = x - w // 2 if align == "center" else x
            ops += _badge(left + D // 2, top + h // 2, D, coin, F.coin, F.accent)
            tx, ty = left + D + gap, top + (h - th) // 2
            ops += _block(ll, lf, tx, ty, fill, "left")
            if nl:
                ops += _block(nl, F.note, tx, ty + len(ll) * lf.lh + F.small_gap, MUTED, "left")
            return ops
        y = top
        if coin:
            bx = x if align == "center" else x + D // 2
            ops += _badge(bx, top + D // 2, D, coin, F.coin, F.accent)
            y += D + gap
        ops += _block(ll, lf, x, y, fill, align)
        if nl:
            ops += _block(nl, F.note, x, y + len(ll) * lf.lh + F.small_gap, MUTED, align)
        return ops
    return w, h, place


def _fonts(layout, s: float, accent: tuple):
    def f(base, bold=False):
        size = max(layout.min_text, round(base * s))
        return _F(_font(size, bold), round(size * 1.25))

    def px(base, least=2):
        return max(least, round(base * s))
    return SimpleNamespace(label=f(44, True), note=f(32), small=f(30, True), head=f(46, True), cell=f(38),
                           notes=f(36), coin=_font(max(layout.min_text, round(30 * s)), True),
                           gap=px(14), small_gap=px(8), px=px, accent=accent)


# ─── layouts: each returns (height, place(top) -> {item: ops}) or None when it can't fit ───────────

def _flow_across(d, x0: int, x1: int, spec: dict, F):
    nodes, px, accent = spec["nodes"], F.px, F.accent
    W, n = x1 - x0, len(spec["nodes"])
    pad, aw, head = px(22, 10), px(5, 3), px(18, 10)
    labels = [_text(nd.get("arrow")) for nd in nodes[1:]]
    word = max((d.textlength(w, font=F.small.font) for a in labels for w in a.split()), default=0)
    full = max((d.textlength(a, font=F.small.font) for a in labels if a), default=0)
    G = max(px(96), round(word) + px(20), min(round(full) + px(20), round(W * 0.16)))
    NW = (W - (n - 1) * G) // n
    if NW <= 2 * pad:
        return None
    cs = [_content(d, nd["label"], nd.get("note"), nd.get("coin"), NW - 2 * pad, F, F.label) for nd in nodes]
    if None in cs:
        return None
    alabels = [_wrap_all(d, a, F.small.font, G - px(16)) if a else [] for a in labels]
    if None in alabels:
        return None
    NH = max(max(c[1] for c in cs) + 2 * pad, px(150))
    ah = max((len(a) * F.small.lh for a in alabels), default=0)
    h = max(NH, 2 * (ah + px(14)) + aw)
    off = x0 + (W - (n * NW + (n - 1) * G)) // 2

    def place(top: int) -> dict:
        cy, items = top + h // 2, {}
        for k, c in enumerate(cs):
            bx0 = off + k * (NW + G)
            if k:
                ops = _arrow((bx0 - G + px(10), cy), (bx0 - px(10), cy), accent, aw, head)
                lines = alabels[k - 1]
                if lines:
                    ops += _block(lines, F.small, bx0 - G // 2, cy - px(14) - len(lines) * F.small.lh, MUTED)
                items[f"arrow:{k}"] = ops
            items[f"node:{k}"] = [_rect((bx0, cy - NH // 2, bx0 + NW, cy - NH // 2 + NH), PANEL, accent, 3, px(18))] \
                + c[2](bx0 + NW // 2, cy - c[1] // 2)
        return items
    return h, place


def _flow_down(d, x0: int, x1: int, spec: dict, F):
    nodes, px, accent = spec["nodes"], F.px, F.accent
    W = x1 - x0
    pad, aw, head = px(22, 10), px(5, 3), px(18, 10)
    inset = px(40)
    NW = W - 2 * inset
    cx = x0 + W // 2
    cs = [_content(d, nd["label"], nd.get("note"), nd.get("coin"), NW - 2 * pad, F, F.label, inline=True)
          for nd in nodes]
    if None in cs:
        return None
    alabels = [_wrap_all(d, _text(nd.get("arrow")), F.small.font, x1 - (cx + px(24))) if nd.get("arrow") else []
               for nd in nodes[1:]]
    if None in alabels:
        return None
    gaps = [max(px(64), len(a) * F.small.lh + px(16)) for a in alabels]
    NHs = [max(c[1] + 2 * pad, px(100)) for c in cs]
    h = sum(NHs) + sum(gaps)

    def place(top: int) -> dict:
        y, items = top, {}
        for k, (c, NH) in enumerate(zip(cs, NHs)):
            if k:
                g, lines = gaps[k - 1], alabels[k - 1]
                ops = _arrow((cx, y + px(8)), (cx, y + g - px(8)), accent, aw, head)
                if lines:
                    ops += _block(lines, F.small, cx + px(24), y + (g - len(lines) * F.small.lh) // 2, MUTED, "left")
                items[f"arrow:{k}"] = ops
                y += g
            items[f"node:{k}"] = [_rect((x0 + inset, y, x1 - inset, y + NH), PANEL, accent, 3, px(18))] \
                + c[2](cx, y + (NH - c[1]) // 2)
            y += NH
        return items
    return h, place


def _compare(d, x0: int, x1: int, spec: dict, F):
    px, accent = F.px, F.accent
    W = x1 - x0
    CG, pad, RG = px(28, 16), px(20, 10), px(14, 8)
    CW = (W - CG) // 2
    heads = [_content(d, spec[s]["label"], None, spec[s].get("coin"), CW - 2 * pad, F, F.head) for s in ("left", "right")]
    rows = [[_content(d, r[s], None, None, CW - 2 * pad, F, F.cell) for s in ("left", "right")] for r in spec["rows"]]
    if None in heads or any(None in r for r in rows):
        return None
    HH = max(c[1] for c in heads) + 2 * pad
    RHs = [max(c[1] for c in r) + 2 * pad for r in rows]
    h = HH + sum(RG + rh for rh in RHs)
    lx = x0 + (W - 2 * CW - CG) // 2
    cols = (lx, lx + CW + CG)

    def place(top: int) -> dict:
        items = {}
        for side, c, cx0 in zip(("left", "right"), heads, cols):
            items[side] = [_rect((cx0, top, cx0 + CW, top + HH), PANEL, accent, 3, px(16))] \
                + c[2](cx0 + CW // 2, top + (HH - c[1]) // 2)
        y = top + HH
        for k, (r, rh) in enumerate(zip(rows, RHs)):
            y += RG
            for side, c, cx0 in zip(("left", "right"), r, cols):
                items[f"row:{k}:{side}"] = [_rect((cx0, y, cx0 + CW, y + rh), PANEL, None, 0, px(12))] \
                    + c[2](cx0 + CW // 2, y + (rh - c[1]) // 2)
            y += rh
        return items
    return h, place


def _timeline_across(d, x0: int, x1: int, spec: dict, F):
    events, px, accent = spec["events"], F.px, F.accent
    W, n = x1 - x0, len(spec["events"])
    C, r, lw = W // n, px(16, 10), px(6, 4)
    cs = [_content(d, e["label"], e.get("note"), None, C - px(24), F, F.label) for e in events]
    if None in cs:
        return None
    h = 2 * r + px(22) + max(c[1] for c in cs)
    xs = [x0 + (W - n * C) // 2 + k * C + C // 2 for k in range(n)]

    def place(top: int) -> dict:
        ay, items = top + r, {}
        for k, (c, x) in enumerate(zip(cs, xs)):
            if k:
                items[f"segment:{k}"] = [_line([(xs[k - 1] + r + px(6), ay), (x - r - px(6), ay)], accent, lw)]
            items[f"event:{k}"] = [_ellipse((x - r, ay - r, x + r, ay + r), accent)] + c[2](x, ay + r + px(22))
        return items
    return h, place


def _timeline_down(d, x0: int, x1: int, spec: dict, F):
    events, px, accent = spec["events"], F.px, F.accent
    r, lw = px(16, 10), px(6, 4)
    ax = x0 + px(20) + r
    tx = ax + r + px(30)
    cs = [_content(d, e["label"], e.get("note"), None, x1 - tx, F, F.label, align="left") for e in events]
    if None in cs:
        return None
    RG = px(56, 24)
    hs = [max(c[1], 2 * r) for c in cs]
    h = sum(hs) + RG * (len(cs) - 1)
    dy = round(F.label.font.size * 0.62)  # the dot sits beside the label's first line

    def place(top: int) -> dict:
        y, items, prev = top, {}, None
        for k, (c, hk) in enumerate(zip(cs, hs)):
            cy = y + max(dy, r)
            if k:
                items[f"segment:{k}"] = [_line([(ax, prev + r + px(6)), (ax, cy - r - px(6))], accent, lw)]
            items[f"event:{k}"] = [_ellipse((ax - r, cy - r, ax + r, cy + r), accent)] + c[2](tx, y)
            prev, y = cy, y + hk + RG
        return items
    return h, place


def _notes(d, x0: int, x1: int, notes: list[dict], F, across: bool):
    px, accent = F.px, F.accent
    W = x1 - x0
    pad, bar, NG = px(18, 10), px(8, 6), px(20, 12)
    nw = (W - (len(notes) - 1) * NG) // len(notes) if across else W
    inner = nw - px(10) - bar - px(16) - pad
    wrapped = [_wrap_all(d, n["text"], F.notes.font, inner) for n in notes]
    if None in wrapped:
        return None
    hs = [len(w) * F.notes.lh + 2 * pad for w in wrapped]
    if across:
        hs = [max(hs)] * len(hs)
    h = max(hs) if across else sum(hs) + NG * (len(hs) - 1)

    def place(top: int) -> dict:
        items, y = {}, top
        for k, (lines, hk) in enumerate(zip(wrapped, hs)):
            bx0 = x0 + k * (nw + NG) if across else x0
            by0 = top if across else y
            ops = [_rect((bx0, by0, bx0 + nw, by0 + hk), PANEL, None, 0, px(12)),
                   _rect((bx0 + px(10), by0 + px(12), bx0 + px(10) + bar, by0 + hk - px(12)), accent, None, 0, bar // 2)]
            ops += _block(lines, F.notes, bx0 + px(10) + bar + px(16), by0 + (hk - len(lines) * F.notes.lh) // 2, FG,
                          "left")
            items[f"note:{k}"] = ops
            y += hk + NG
        return items
    return h, place


def _try(d, box, spec: dict, layout, accent: tuple, s: float) -> dict | None:
    x0, y0, x1, y1 = box
    F = _fonts(layout, s, accent)
    across = layout.w > layout.h
    main = {"flow": _flow_across if across else _flow_down, "compare": _compare,
            "timeline": _timeline_across if across else _timeline_down}[spec["type"]](d, x0, x1, spec, F)
    notes = _notes(d, x0, x1, spec["notes"], F, across) if spec.get("notes") else (0, lambda top: {})
    if main is None or notes is None:
        return None
    gap = F.px(28, 14) if spec.get("notes") else 0
    total = main[0] + gap + notes[0]
    if total > y1 - y0:
        return None
    top = y0 + (y1 - y0 - total) // 2
    items = main[1](top)
    items.update(notes[1](top + main[0] + gap))
    for ops in items.values():  # every part fully inside the box, or the scale doesn't fit
        bx = _bounds(d, ops)
        if bx[0] < x0 or bx[1] < y0 or bx[2] > x1 or bx[3] > y1:
            return None
    return items


def draw(img, box, spec: dict, layout, accent: tuple, show=None, who: str = "diagram") -> dict:
    """Lay out every part of `spec` inside box (x0, y0, x1, y1) at the largest text scale that fits (never
    below layout.min_text) and paint only the items in `show` (None = all). → {item: bbox}.
    An invalid spec or one that can't fit → ValueError naming `who`."""
    problems = validate(spec)
    if problems:
        raise ValueError(f"{who}: invalid diagram: {'; '.join(problems)}")
    d = ImageDraw.Draw(img)
    inner = (box[0], box[1], box[2] - 1, box[3] - 1)  # Pillow boxes include their far edge: stay in [x0, x1)
    for s in SCALES:
        items = _try(d, inner, spec, layout, accent, s)
        if items is not None:
            break
    else:
        raise ValueError(f"{who}: the {spec['type']} diagram doesn't fit at the minimum text size "
                         f"({layout.name}, {box[2] - box[0]}x{box[3] - box[1]} px)")
    for name, ops in items.items():
        if show is None or name in show:
            _paint(d, ops)
    return {name: _bounds(d, ops) for name, ops in items.items()}


def step_layers(frame, steps_: list[dict], workdir: Path, stem: str) -> tuple[Path, list[dict]]:
    """frame(show) = the whole slide with only the items in `show` painted. → (base path, slide steps):
    the base (nothing shown) and, per step, one layer per item in reveal order (reveal.diff_crops over the
    cumulative frames) as [{key, name, names, layers: [{image, xy}]}]."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    order = [it for s in steps_ for it in s["items"]]
    frames = [frame(frozenset(order[:n])) for n in range(len(order) + 1)]
    base = workdir / f"{stem}_base.png"
    frames[0].save(base)
    crops = reveal.diff_crops(frames, workdir, f"{stem}_layer")
    out, k = [], 0
    for s in steps_:
        n = len(s["items"])
        out.append({"key": s["key"], "name": s["name"], "names": list(s["names"]),
                    "layers": [c for c in crops[k:k + n] if c is not None]})
        k += n
    return base, out
