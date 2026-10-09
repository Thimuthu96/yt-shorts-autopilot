"""Lesson graphics in two shapes: one PNG per `lessons.scene_plan` scene, plus the lesson thumbnail.

    LANDSCAPE  1920x1080  (the YouTube lesson)     caption band y 880-1010, footer ~1040
    PORTRAIT   1080x1920  (the vertical version)   caption band y 1230-1480, footer ~1830

    render_lesson_slides(cfg, entry, plan, glossary, layout, workdir)
        -> [{"image": path, "reveal": (x, y, w, h) | None, "id": scene id}]   (same shape as slides.render_slides)
    render_lesson_thumbnail(cfg, entry, example, path) -> path                 (1280x720 JPEG)
    draw_chart(img, box, example, layout, zoom=False, primitives=None, label=None) -> info dict
    draw_mtf(img, box, example, layout, label=None) -> [higher info, lower info]

Scene types (RENDERERS): title, concept, chart, mtf, schematic, misreads, outro. An unknown type raises
ValueError. Charts are drawn with Pillow from the example's own candles and primitives (swing, level,
trendline, zone, label); every number on a chart comes from them. Real charts carry the strip
"Historical example · asset · date · timeframe" + "Data: source"; a schematic is labelled "Schematic"
and draws no numbers. Portrait charts zoom to the example's region (± 3 candles, ± 8% of its range);
landscape shows every candle. Both use the full content width (no crop, no letterbox). A daily
reference fix (o = h = l = c, e.g. EUR/USD) is drawn as a line. Same inputs → same pixels.
An `mtf` scene draws the example (higher timeframe) and its `lower` panel with draw_chart, each with a
"<timeframe> · Higher/Lower timeframe" title and its own strip: side by side in 16:9 (higher left),
stacked in 9:16 (higher on top), 40 px apart, with headroom for the swing texts. The higher panel
marks the lower panel's window with a zone labelled with the lower timeframe. The draw-in box never
covers a title or label strip (9:16: only the lower chart draws in).

Look: channel ground, accent from config, up/down colours, brand header and disclaimer footer as in
slides.py; fonts from assets/fonts (DejaVu fallback). The caption band is never drawn into.
The daily editions' modules are only imported from (helpers), never changed.
"""
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date as _date, datetime
from functools import lru_cache
from math import ceil, floor, log10
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from autopilot import lessons
from autopilot.slides import BG, DOWN, FG, MUTED, PANEL, UP, _font as _dejavu, _hex, _wrap
from autopilot.thumbnail import FONT_DIR, GRID, _fit, _mini_logo


@dataclass(frozen=True)
class Layout:
    name: str
    w: int
    h: int
    caption_band: tuple[int, int]  # (y0, y1): slides never draw here
    content_box: tuple[int, int, int, int]  # (x0, y0, x1, y1)
    header_y: int = 40  # top of the brand line
    rule_y: int = 108  # header divider
    footer_y: int = 1040  # top of the (last) footer line
    footer_lines: int = 1
    min_text: int = 30  # px, every text on the slide


LANDSCAPE = Layout("16x9", 1920, 1080, (880, 1010), (60, 130, 1860, 860),
                   header_y=40, rule_y=108, footer_y=1036, footer_lines=1, min_text=30)
PORTRAIT = Layout("9x16", 1080, 1920, (1230, 1480), (40, 170, 1040, 1190),
                  header_y=80, rule_y=140, footer_y=1830, footer_lines=2, min_text=34)
THUMB = Layout("thumb", 1280, 720, (720, 720), (0, 0, 1280, 720), min_text=24)

SCHEMATIC = "Schematic"
TRACKS = {0: "Structure", 1: "Trendlines", 2: "Liquidity", 3: "SMC", 4: "ICT concepts", 5: "MSNR",
          6: "Putting it together"}
PROVIDERS = ("Coinbase", "Kraken", "Swissquote", "Frankfurter")  # named in the footer's data credit
DISCLAIMER = "Education only · Not financial advice"
NON_AFFILIATION = "Not affiliated with The Inner Circle Trader. \"ICT\" is used only as a descriptive term."
SWING_HIGH = {"HH", "LH", "high"}
ZOOM_CANDLES = 3  # portrait zoom: candles either side of the region
ZOOM_PAD = 0.08  # portrait zoom: share of the region's range above and below
FULL_PAD = 0.12
SWING_ROOM = 18  # px between a swing's price and the far edge of its kind text (label_room)
MTF_GUTTER = 40  # px between the two mtf panels
MTF_ROLES = ("Higher timeframe", "Lower timeframe")


# ─── fonts / text ──────────────────────────────────────────────────────────

@lru_cache(maxsize=None)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    p = FONT_DIR / "SpaceGrotesk-Variable.ttf"
    if not p.exists():
        return _dejavu(size, bold)
    f = ImageFont.truetype(str(p), size)
    try:
        f.set_variation_by_axes([700 if bold else 400])
    except OSError:
        pass
    return f


@lru_cache(maxsize=None)
def _title_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    p = FONT_DIR / "Anton-Regular.ttf"
    return ImageFont.truetype(str(p), size) if p.exists() else _dejavu(size, True)


def _flow(d: ImageDraw.ImageDraw, items: list[dict], box, layout: Layout, valign: str = "top",
          max_scale: float = 1.0, who: str = "") -> int:
    """Draw text blocks top to bottom inside `box`: may grow up to max_scale, shrinks (never below
    layout.min_text), then caps lines of the cuttable items until they fit.
    item: {text, size, bold, fill, gap, title, bullet, bullet_fill, max_lines, keep}. `keep` items (approved
    key points, the closing lines) are never cut; if everything still doesn't fit, ValueError naming `who`
    (nothing is ever silently dropped)."""
    x0, y0, x1, y1 = box
    avail = y1 - y0

    def measure(scale, caps):
        rows, total = [], 0
        for it, cap in zip(items, caps):
            size = max(layout.min_text, round(it["size"] * scale))
            font = (_title_font if it.get("title") else _font)(size, it.get("bold", False))
            indent = round(size * 1.4) if it.get("bullet") else 0
            lines = _wrap(d, it["text"], font, x1 - x0 - indent, cap)
            lh = round(size * (1.08 if it.get("title") else 1.28))
            gap = round(it.get("gap", 0) * scale)
            rows.append((it, font, lines, lh, gap, indent))
            total += len(lines) * lh + gap
        return rows, total

    caps = [10 ** 6 if it.get("keep") else it.get("max_lines", 6) for it in items]
    scale = max_scale
    rows, total = measure(scale, caps)
    while total > avail and scale > 0.4:
        scale = round(scale - 0.05, 2)
        rows, total = measure(scale, caps)
    while total > avail:
        cuttable = [j for j in range(len(rows)) if not items[j].get("keep") and len(rows[j][2]) > 1]
        if not cuttable:
            raise ValueError(f"{who or 'slide'}: text doesn't fit at the minimum size "
                             f"({layout.name}, {total} px of {avail})")
        k = max(cuttable, key=lambda j: len(rows[j][2]))
        caps[k] = len(rows[k][2]) - 1
        rows, total = measure(scale, caps)
    y = y0 if valign == "top" else y0 + max(0, (avail - total) // 2)
    for it, font, lines, lh, gap, indent in rows:
        if it.get("bullet") and lines:
            d.text((x0, y), it["bullet"], font=font, fill=it.get("bullet_fill", it.get("fill", FG)))
        for line in lines:
            d.text((x0 + indent, y), line, font=font, fill=it.get("fill", FG))
            y += lh
        y += gap
    return y


# ─── chart ─────────────────────────────────────────────────────────────────

def _ts(v) -> float:
    if isinstance(v, datetime):
        return v.timestamp()
    if isinstance(v, _date):
        return datetime(v.year, v.month, v.day).timestamp()
    return datetime.fromisoformat(v).timestamp()


def _ticks(lo: float, hi: float, n: int = 4) -> tuple[list[float], int]:
    raw = (hi - lo) / n or abs(hi) * 0.01 or 1.0
    mag = 10 ** floor(log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    dec = max(0, -floor(log10(step) + 1e-9)) + (1 if round(step / mag, 6) == 2.5 and step < 10 else 0)
    k0 = ceil(lo / step - 1e-9)
    vals = []
    k = k0
    while k * step <= hi + 1e-9:
        vals.append(round(k * step, 10))
        k += 1
    return vals, dec


def _fmt_tick(v: float, dec: int) -> str:
    return f"{v:,.{dec}f}"


def _time_label(t, timeframe: str) -> str:
    dt = datetime.fromisoformat(t) if isinstance(t, str) else t
    day = f"{dt:%b} {dt.day}, {dt.year}" if timeframe == "1D" else f"{dt:%b} {dt.day} {dt:%H:%M}"
    return day + ("" if timeframe == "1D" else " UTC")


def _is_line(example: dict) -> bool:
    if (example.get("facts") or {}).get("daily_reference_fix"):
        return True
    return all(c["o"] == c["h"] == c["l"] == c["c"] for c in example["candles"])


def _strip_lines(example: dict, label: str) -> list[tuple[str, bool, tuple]]:
    """(text, bold, colour) blocks for the label strip under the chart."""
    if label == SCHEMATIC:
        return [(f"{SCHEMATIC} · a drawing of the idea, not real prices", True, FG)]
    out = [(f"{label} · {example.get('timeframe', '')}".rstrip(" ·"), True, FG)]
    src = (example.get("facts") or {}).get("source")
    if src:
        out.append((f"Data: {src}", False, MUTED))
    return out


def draw_chart(img: Image.Image, box, example: dict, layout: Layout, zoom: bool = False,
               primitives: list[dict] | None = None, label: str | None = None, axes: bool = True,
               accent: tuple = (255, 212, 0), label_room: bool = False) -> dict:
    """Candles (or a line for a daily fix) + primitives inside box (x0, y0, x1, y1), the label strip at
    its bottom. `primitives` limits what is drawn (None = all of the example's; [] = candles only).
    label None = lessons.example_label(example); SCHEMATIC = no numbers; "" = no strip.
    label_room (mtf panels): pad the price range so the highest / lowest price sits at least one swing
    marker + kind text inside the plot, so those texts fit above / below their swings.
    Returns {box: reveal (x, y, w, h), x_range: (i0, i1), y_range: (lo, hi), drawn: [types], label, line}."""
    x0, y0, x1, y1 = box
    schematic = label == SCHEMATIC
    if label is None:
        label = lessons.example_label(example)
    show_numbers = axes and not schematic
    d = ImageDraw.Draw(img)
    fs = layout.min_text
    f_reg, f_bold = _font(fs), _font(fs, True)
    line_h = round(fs * 1.3)

    # label strip (bottom) and time row
    strip = []
    if label:
        for text, bold, col in _strip_lines(example, label):
            strip += [(ln, bold, col) for ln in _wrap(d, text, f_bold if bold else f_reg, x1 - x0, 2)]
    strip_h = len(strip) * line_h + (10 if strip else 0)
    time_h = line_h if show_numbers else 0
    py1 = y1 - strip_h - time_h

    candles = example["candles"]
    n = len(candles)
    times = [_ts(c["t"]) for c in candles]
    prims = list(example.get("primitives") or []) if primitives is None else list(primitives)
    region = example.get("region")

    def index(t) -> int:
        ts = _ts(t)
        j = bisect_left(times, ts)
        if j <= 0:
            return 0
        if j >= n:
            return n - 1
        return j if times[j] - ts < ts - times[j - 1] else j - 1

    if zoom and region:
        i0 = max(0, index(region["start"]) - ZOOM_CANDLES)
        i1 = min(n - 1, index(region["end"]) + ZOOM_CANDLES)
        lo, hi = region["low"], region["high"]
        pad = (hi - lo) * ZOOM_PAD or abs(hi) * 0.01 or 1.0
    else:
        i0, i1 = 0, n - 1
        prices = [c["l"] for c in candles] + [c["h"] for c in candles]
        for p in prims:
            prices += [p[k] for k in ("price", "low", "high") if isinstance(p.get(k), (int, float))]
        lo, hi = min(prices), max(prices)
        pad = (hi - lo) * FULL_PAD or abs(hi) * 0.01 or 1.0
    if label_room:
        room = SWING_ROOM + max(10, round(fs * 0.42)) + round(fs * 1.2)  # gap + marker + kind text, px
        plot_h = py1 - y0
        if plot_h > 2 * room + 20:
            pad = max(pad, (hi - lo) * room / (plot_h - 2 * room))
    lo, hi = lo - pad, hi + pad

    ticks, dec = _ticks(lo, hi)
    tick_txt = [_fmt_tick(v, dec) for v in ticks]
    axis_w = (max(d.textlength(t, font=f_reg) for t in tick_txt) + 18) if show_numbers and ticks else 0
    px0, px1, py0 = x0, int(x1 - axis_w), y0
    pw, ph = px1 - px0, py1 - py0
    count = i1 - i0 + 1
    slot = pw / count

    def X(i: float) -> float:
        return (i - i0 + 0.5) * slot

    def Y(p: float) -> float:
        return ph - (p - lo) / (hi - lo) * ph

    def xt(t) -> float:  # fractional candle position of a time (between candles when it falls between)
        ts = _ts(t)
        j = bisect_left(times, ts)
        if j < n and times[j] == ts or j == 0:
            return X(min(j, n - 1))
        if j >= n:
            return X(n - 1)
        frac = (ts - times[j - 1]) / (times[j] - times[j - 1])
        return X(j - 1 + frac)

    layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    placed: list[tuple[float, float, float, float]] = []  # text boxes already on the chart
    ld = ImageDraw.Draw(layer)
    drawn = []

    # grid
    for v in ticks:
        y = round(Y(v))
        ld.line([(0, y), (pw, y)], fill=PANEL + (255,), width=2)

    # zones (under the candles)
    for p in prims:
        if p.get("type") != "zone":
            continue
        zx0, zx1 = sorted((xt(p["t1"]), xt(p["t2"])))
        zx0, zx1 = zx0 - slot / 2, zx1 + slot / 2
        zy0, zy1 = Y(p["high"]), Y(p["low"])
        if zx1 < 0 or zx0 > pw or zy1 < 0 or zy0 > ph:
            continue
        ld.rectangle([zx0, zy0, zx1, zy1], fill=accent + (52,), outline=accent + (170,), width=2)
        if p.get("label"):
            tx = min(max(zx0 + 8, 4), pw - d.textlength(p["label"], font=f_bold) - 4)
            ty = min(max(zy0 + 6, 4), ph - fs - 6)
            if label_room and zy1 - zy0 < fs * 1.2 + 12:  # a flat zone: its label sits just above it
                ty = zy0 - fs * 1.25 - 2 if zy0 - fs * 1.25 - 2 >= 0 else min(zy1 + 4, ph - fs - 6)
            ld.text((tx, ty), p["label"], font=f_bold, fill=accent + (255,))
            placed.append((tx, ty, tx + d.textlength(p["label"], font=f_bold), ty + fs * 1.2))
        drawn.append("zone")

    # price
    line = _is_line(example)
    if line:
        pts = [(X(i), Y(candles[i]["c"])) for i in range(i0, i1 + 1)]
        col = UP if candles[i1]["c"] >= candles[i0]["c"] else DOWN
        if len(pts) > 1:
            ld.line(pts, fill=col + (255,), width=max(4, round(fs / 7)), joint="curve")
    else:
        body = max(3.0, slot * 0.62)
        wick = max(2, min(round(slot * 0.14), 4))
        for i in range(i0, i1 + 1):
            c = candles[i]
            col = (UP if c["c"] >= c["o"] else DOWN) + (255,)
            cx = X(i)
            ld.line([(cx, Y(c["h"])), (cx, Y(c["l"]))], fill=col, width=wick)
            top, bot = Y(max(c["o"], c["c"])), Y(min(c["o"], c["c"]))
            if bot - top < 2:
                top, bot = (top + bot) / 2 - 1, (top + bot) / 2 + 1
            ld.rectangle([cx - body / 2, top, cx + body / 2, bot], fill=col)

    def free(r) -> bool:
        return all(r[2] <= q[0] or r[0] >= q[2] or r[3] <= q[1] or r[1] >= q[3] for q in placed)

    # level lines (their labels go last, into the space the other texts leave)
    levels = []
    for p in prims:
        if p.get("type") != "level":
            continue
        y = Y(p["price"])
        if not 0 <= y <= ph:
            continue
        x = 0.0
        while x < pw:
            ld.line([(x, y), (min(x + 20, pw), y)], fill=accent + (235,), width=3)
            x += 32
        levels.append((y, p.get("label")))
        drawn.append("level")

    # trendlines, extended to the chart's right edge
    for p in prims:
        if p.get("type") != "trendline":
            continue
        ax, ay, bx, by = xt(p["t1"]), Y(p["p1"]), xt(p["t2"]), Y(p["p2"])
        if bx == ax:
            ex_, ey = bx, by
        else:
            ex_, ey = pw, ay + (by - ay) / (bx - ax) * (pw - ax)
        if ax > pw or max(ay, ey) < 0 or min(ay, ey) > ph:
            continue
        ld.line([(ax, ay), (ex_, ey)], fill=FG + (235,), width=4)
        drawn.append("trendline")

    # swings: triangle above a high / below a low, kind text beyond it (beside it at the chart's edge)
    tri = max(10, round(fs * 0.42))
    th = round(fs * 1.2)
    for p in prims:
        if p.get("type") != "swing":
            continue
        i = index(p["t"])
        if not (i0 <= i <= i1 and lo <= p["price"] <= hi):
            continue
        x, y = X(i), Y(p["price"])
        kind = p.get("kind", "")
        col = (UP if kind in ("HH", "HL") else DOWN if kind in ("LH", "LL") else MUTED) + (255,)
        tw = d.textlength(kind, font=f_bold)
        high = kind in SWING_HIGH
        sgn = -1 if high else 1
        ld.polygon([(x, y + sgn * 8), (x - tri * 0.7, y + sgn * (8 + tri)), (x + tri * 0.7, y + sgn * (8 + tri))],
                   fill=col)
        ty = y - 14 - tri - th if high else y + 12 + tri
        tx = x - tw / 2
        if ty < 0 or ty + th > ph:  # no room beyond the triangle: put the text beside it
            ty = min(max(y + sgn * (8 + tri / 2) - th / 2, 0), ph - th)
            tx = x + tri + 6 if x + tri + 6 + tw <= pw else x - tri - 6 - tw
        tx = min(max(tx, 2), pw - tw - 2)
        ld.text((tx, ty), kind, font=f_bold, fill=col)
        placed.append((tx, ty, tx + tw, ty + th))
        drawn.append("swing")

    # text labels at (t, price): a boxed text next to a dot, on the first free side
    for p in prims:
        if p.get("type") != "label":
            continue
        x, y = xt(p["t"]), Y(p["price"])
        if not (0 <= x <= pw and 0 <= y <= ph):
            continue
        tw = d.textlength(p["text"], font=f_bold)
        bw, bh = tw + 24, fs + 18
        cands = []
        for cx, cy in ((x + 14, y - 14 - bh), (x - 14 - bw, y - 14 - bh), (x + 14, y + 14), (x - 14 - bw, y + 14)):
            cx, cy = max(0, min(cx, pw - bw)), max(0, min(cy, ph - bh))
            cands.append((cx, cy, cx + bw, cy + bh))
        r = next((c for c in cands if free(c)), cands[0])
        ld.ellipse([x - 6, y - 6, x + 6, y + 6], fill=FG + (255,))
        ld.rounded_rectangle(r, radius=10, fill=PANEL + (240,), outline=accent + (255,), width=2)
        ld.text((r[0] + 12, r[1] + 6), p["text"], font=f_bold, fill=FG + (255,))
        placed.append(r)
        drawn.append("label")

    # level labels at the right end of their line, moved left / below until they are clear
    for y, text in levels:
        if not text:
            continue
        tw = d.textlength(text, font=f_bold)
        h_ = fs + 8
        r = None
        for ty in (y - h_ - 4, y + 6):
            if ty < 0 or ty + h_ > ph:
                continue
            rx1 = pw - 4
            while rx1 - tw - 12 >= 0:
                c = (rx1 - tw - 12, ty, rx1, ty + h_)
                if free(c):
                    r = c
                    break
                rx1 -= 24
            if r:
                break
        if r is None:
            ty = y - h_ - 4 if y - h_ - 4 >= 0 else y + 6
            r = (pw - tw - 16, ty, pw - 4, ty + h_)
        ld.rectangle(r, fill=BG + (210,))
        ld.text((r[0] + 6, r[1] + 2), text, font=f_bold, fill=accent + (255,))
        placed.append(r)

    base = img.convert("RGBA") if img.mode != "RGBA" else img
    base.alpha_composite(layer, (px0, py0))
    if base is not img:
        img.paste(base.convert(img.mode))
    d = ImageDraw.Draw(img)

    if show_numbers:
        for v, t in zip(ticks, tick_txt):
            d.text((px1 + 14, py0 + Y(v)), t, font=f_reg, fill=MUTED, anchor="lm")
        tf = example.get("timeframe", "")
        d.text((px0, py1 + 6), _time_label(candles[i0]["t"], tf), font=f_reg, fill=MUTED)
        last = _time_label(candles[i1]["t"], tf)
        d.text((px1 - d.textlength(last, font=f_reg), py1 + 6), last, font=f_reg, fill=MUTED)
    y = py1 + time_h + 10
    for text, bold, col in strip:
        d.text((x0, y), text, font=f_bold if bold else f_reg, fill=col)
        y += line_h

    return {"box": (int(x0), int(y0), int(x1 - x0), int(py1 + time_h - y0)), "x_range": (i0, i1),
            "y_range": (lo, hi), "drawn": drawn, "label": " ".join(t for t, _, _ in strip), "line": line}


def _day(t) -> str:
    return (datetime.fromisoformat(t) if isinstance(t, str) else t).date().isoformat()


def mtf_panels(example: dict) -> tuple[dict, dict]:
    """(higher, lower) chart examples of an mtf example. The higher one gets a zone over the lower
    panel's window (its region; it ends with the higher candle holding the window's end), labelled with
    the lower timeframe; the lower one carries the asset,
    the date its window ends and the data source. Every value comes from the example."""
    lower = example.get("lower")
    if not isinstance(lower, dict):
        raise ValueError("mtf visual needs an example with a `lower` panel")
    r = lower["region"]
    # the zone ends with the higher-timeframe candle that contains the lower window's end
    end = _ts(r["end"])
    t2 = next((c["t"] for c in reversed(example["candles"]) if _ts(c["t"]) <= end), r["end"])
    zone = {"type": "zone", "t1": r["start"], "t2": t2, "low": r["low"], "high": r["high"],
            "label": lower["timeframe"]}
    higher = {k: v for k, v in example.items() if k != "lower"}
    higher["primitives"] = list(example.get("primitives") or []) + [zone]
    facts = {k: v for k, v in (example.get("facts") or {}).items() if k in ("source", "daily_reference_fix")}
    panel = {"asset": example.get("asset"), "timeframe": lower["timeframe"], "date": _day(r["end"]),
             "candles": lower["candles"], "region": r, "primitives": list(lower.get("primitives") or []),
             "facts": facts}
    return higher, panel


def draw_mtf(img: Image.Image, box, example: dict, layout: Layout, label: str | None = None,
             accent: tuple = (255, 212, 0)) -> list[dict]:
    """The two panels of an mtf example inside box: side by side in landscape (higher left), stacked in
    portrait (higher on top). Each: a "<timeframe> · Higher/Lower timeframe" title, then draw_chart with
    its own strip ("Historical example · asset · date · timeframe", "Data: …"). `label` overrides the
    higher panel's strip label. Panels get label_room (swing texts fit inside the plot).
    Returns draw_chart's info per panel plus panel, title_box, strip_box (x, y, w, h), timeframe, title."""
    x0, y0, x1, y1 = box
    g = MTF_GUTTER
    portrait = layout is PORTRAIT
    if portrait:
        h = (y1 - y0 - g) // 2
        boxes = [(x0, y0, x1, y0 + h), (x0, y1 - h, x1, y1)]
    else:
        w = (x1 - x0 - g) // 2
        boxes = [(x0, y0, x0 + w, y1), (x1 - w, y0, x1, y1)]
    higher, lower = mtf_panels(example)
    labels = (label or lessons.example_label(higher), lessons.example_label(lower))
    d = ImageDraw.Draw(img)
    f = _font(layout.min_text, True)
    title_h = round(layout.min_text * 1.3) + 8
    out = []
    for (bx0, by0, bx1, by1), panel, lab, role in zip(boxes, (higher, lower), labels, MTF_ROLES):
        tf = panel["timeframe"]
        d.text((bx0, by0), tf, font=f, fill=accent)
        d.text((bx0 + d.textlength(f"{tf}  ", font=f), by0), f"· {role}", font=f, fill=MUTED)
        info = draw_chart(img, (bx0, by0 + title_h, bx1, by1), panel, layout, zoom=portrait, label=lab,
                          accent=accent, label_room=True)
        d = ImageDraw.Draw(img)
        cy1 = info["box"][1] + info["box"][3]  # the strip starts below the chart box
        info.update(panel=(int(bx0), int(by0), int(bx1 - bx0), int(by1 - by0)), timeframe=tf, title=f"{tf} · {role}",
                    title_box=(int(bx0), int(by0), int(bx1 - bx0), title_h), strip_box=(int(bx0), cy1, int(bx1 - bx0), int(by1 - cy1)))
        out.append(info)
    return out


def mtf_reveal(infos: list[dict], layout: Layout) -> tuple[int, int, int, int]:
    """Draw-in box of an mtf slide that never covers a panel title or label strip (they show from the
    first frame): 9:16 = the lower panel's chart (the higher one is shown at once); 16:9 = both charts,
    down to the shorter chart's bottom."""
    if layout is PORTRAIT:
        return infos[1]["box"]
    rx0 = min(i["box"][0] for i in infos)
    ry0 = max(i["box"][1] for i in infos)
    rx1 = max(i["box"][0] + i["box"][2] for i in infos)
    ry1 = min(i["box"][1] + i["box"][3] for i in infos)
    return rx0, ry0, rx1 - rx0, ry1 - ry0


# ─── slides ────────────────────────────────────────────────────────────────

@dataclass
class _Ctx:
    cfg: dict
    entry: dict
    glossary: dict
    layout: Layout
    accent: tuple
    brand: str
    footer: str


def _track(entry: dict) -> str:
    t = entry.get("track")
    return f"TRACK {t} · {TRACKS[t].upper()}" if t in TRACKS else f"TRACK {t}"


def _providers(source: str) -> list[str]:
    found = [p for p in PROVIDERS if p in source]
    return found or [source]


def footer_text(plan: list[dict]) -> str:
    """Disclaimer + the data credit of every real example in the plan (schematics have no data)."""
    names: list[str] = []
    for s in plan:
        v = s.get("visual") or {}
        if v.get("type") == SCHEMATIC.lower() or not isinstance(v.get("example"), dict):
            continue
        for n in _providers((v["example"].get("facts") or {}).get("source") or ""):
            if n and n not in names:
                names.append(n)
    return f"{DISCLAIMER} · Data: {', '.join(names)}" if names else DISCLAIMER


def _base(ctx: _Ctx):
    L = ctx.layout
    img = Image.new("RGB", (L.w, L.h), BG)
    d = ImageDraw.Draw(img)
    x0, x1 = L.content_box[0], L.content_box[2]
    size = max(34, L.min_text)
    d.text((x0, L.header_y), ctx.brand, font=_font(size, True), fill=ctx.accent)
    track, f = _track(ctx.entry), _font(L.min_text)
    d.text((x1 - d.textlength(track, font=f), L.header_y + 2), track, font=f, fill=MUTED)
    d.line([(x0, L.rule_y), (x1, L.rule_y)], fill=PANEL, width=3)
    f = _font(L.min_text)
    lines = _wrap(d, ctx.footer, f, x1 - x0, L.footer_lines)
    lh = round(L.min_text * 1.3)
    y = L.footer_y - (len(lines) - 1) * lh
    for ln in lines:
        d.text(((L.w - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill=MUTED)
        y += lh
    return img, d


def _heading(ctx: _Ctx, text: str) -> dict:
    return {"text": text, "size": 48, "bold": True, "fill": ctx.accent, "gap": 34, "max_lines": 1}


def slide_title(ctx: _Ctx, v: dict):
    img, d = _base(ctx)
    title = v.get("title") or ctx.entry.get("title") or ""
    pre, _, post = title.partition(":")
    items = [{"text": _track(dict(ctx.entry, track=v.get("track", ctx.entry.get("track")))), "size": 44,
              "bold": True, "fill": ctx.accent, "gap": 28, "max_lines": 1}]
    if post.strip():
        items += [{"text": pre.strip(), "size": 60, "bold": True, "fill": MUTED, "gap": 18, "max_lines": 2},
                  {"text": post.strip(), "size": 150, "title": True, "fill": FG, "max_lines": 4}]
    else:
        items.append({"text": title, "size": 150, "title": True, "fill": FG, "max_lines": 5})
    _flow(d, items, ctx.layout.content_box, ctx.layout, valign="center", max_scale=1.3)
    return img, None


def slide_concept(ctx: _Ctx, v: dict):
    img, d = _base(ctx)
    items = [_heading(ctx, "THE CONCEPT")]
    for key in v.get("concepts") or ctx.entry.get("concepts") or []:
        g = ctx.glossary.get(key)
        if not g or not str(g.get("definition") or "").strip():
            raise ValueError(f"glossary key '{key}' is missing or has no definition")
        items += [{"text": g.get("term") or key, "size": 54, "bold": True, "fill": FG, "gap": 8, "max_lines": 2},
                  {"text": g["definition"], "size": 44, "fill": MUTED, "gap": 40, "max_lines": 5}]
    _flow(d, items, ctx.layout.content_box, ctx.layout, max_scale=1.4)
    return img, None


def _chart_heading(ctx: _Ctx, ex: dict, fallback: str) -> str:
    g = ctx.glossary.get(ex.get("glossary") or "")
    return (g or {}).get("term") or fallback  # glossary casing (CHoCH, not CHOCH)


def _chart_slide(ctx: _Ctx, v: dict, schematic: bool):
    ex = v.get("example")
    if not isinstance(ex, dict):
        raise ValueError(f"{v.get('type')} visual needs an example")
    img, d = _base(ctx)
    L = ctx.layout
    x0, y0, x1, y1 = L.content_box
    head = _chart_heading(ctx, ex, "How it looks" if schematic else "Real example")
    y = _flow(d, [_heading(ctx, head)], (x0, y0, x1, y1), L)
    label = SCHEMATIC if schematic else (v.get("label") or lessons.example_label(ex))
    info = draw_chart(img, (x0, y, x1, y1), ex, L, zoom=L.h > L.w, label=label, accent=ctx.accent)
    return img, info["box"]


def slide_chart(ctx: _Ctx, v: dict):
    return _chart_slide(ctx, v, schematic=False)


def slide_mtf(ctx: _Ctx, v: dict):
    ex = v.get("example")
    if not isinstance(ex, dict):
        raise ValueError("mtf visual needs an example")
    img, d = _base(ctx)
    L = ctx.layout
    x0, y0, x1, y1 = L.content_box
    y = _flow(d, [_heading(ctx, _chart_heading(ctx, ex, "Top-down reading"))], (x0, y0, x1, y1), L)
    infos = draw_mtf(img, (x0, y, x1, y1), ex, L, label=v.get("label"), accent=ctx.accent)
    return img, mtf_reveal(infos, L)


def slide_schematic(ctx: _Ctx, v: dict):
    return _chart_slide(ctx, v, schematic=True)


def slide_misreads(ctx: _Ctx, v: dict):
    img, d = _base(ctx)
    items = [_heading(ctx, "COMMON MISREADS"),
             {"text": "Check each read against the rules:", "size": 40, "fill": MUTED, "gap": 30, "max_lines": 2}]
    for n, kp in enumerate(ctx.entry.get("key_points") or [], 1):
        items.append({"text": kp, "size": 46, "fill": FG, "gap": 30, "bullet": f"{n}", "bullet_fill": ctx.accent,
                      "keep": True})
    _flow(d, items, ctx.layout.content_box, ctx.layout, max_scale=1.4, who=f"{ctx.entry.get('id')} misreads")
    return img, None


def slide_outro(ctx: _Ctx, v: dict):
    img, d = _base(ctx)
    items = [_heading(ctx, "RECAP")]
    for kp in ctx.entry.get("key_points") or []:
        items.append({"text": kp, "size": 42, "fill": FG, "gap": 20, "bullet": "•", "bullet_fill": ctx.accent,
                      "keep": True})
    if v.get("next"):
        items.append({"text": f"Next: {v['next']}", "size": 46, "bold": True, "fill": ctx.accent, "gap": 26,
                      "keep": True})
    if v.get("disclaimer", True):
        items.append({"text": "Education only. Not financial advice.", "size": 40, "bold": True, "fill": MUTED,
                      "gap": 14, "keep": True})
    if v.get("non_affiliation"):
        items.append({"text": NON_AFFILIATION, "size": 36, "fill": MUTED, "keep": True})
    _flow(d, items, ctx.layout.content_box, ctx.layout, max_scale=1.4, who=f"{ctx.entry.get('id')} recap")
    return img, None


RENDERERS = {"title": slide_title, "concept": slide_concept, "chart": slide_chart, "mtf": slide_mtf,
             "schematic": slide_schematic, "misreads": slide_misreads, "outro": slide_outro}


def render_lesson_slides(cfg: dict, entry: dict, plan: list[dict], glossary: dict, layout: Layout,
                         workdir: Path) -> list[dict]:
    """One PNG per scene of `lessons.scene_plan` in `layout`'s shape.
    Returns [{"image": path, "reveal": (x, y, w, h) | None, "id": scene id}] (reveal = chart draw-in box)."""
    for s in plan:
        t = (s.get("visual") or {}).get("type")
        if t not in RENDERERS:
            raise ValueError(f"unknown lesson visual type '{t}' (scene '{s.get('id')}')")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = _Ctx(cfg, entry, glossary, layout, _hex(cfg["video"].get("accent", "FFD400")),
               cfg["channel"].get("display_name", "CryptoFX Daily").upper(), footer_text(plan))
    out = []
    for i, s in enumerate(plan):
        img, reveal = RENDERERS[s["visual"]["type"]](ctx, s["visual"])
        path = workdir / f"lesson_{layout.name}_{i:02d}.png"
        img.save(path)
        out.append({"image": path, "reveal": reveal, "id": s.get("id")})
    return out


# ─── thumbnail (1280x720) ──────────────────────────────────────────────────

def render_lesson_thumbnail(cfg: dict, entry: dict, example: dict, path: Path) -> Path:
    """Lesson thumbnail: brand, track chip, title, mini chart of the real example (labelled)."""
    W, H = THUMB.w, THUMB.h
    accent = _hex(cfg["video"].get("accent", "FFD400"))
    name = cfg["channel"].get("display_name", "CryptoFX Daily")
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 64):
        d.rectangle([x, 0, x + 1, H], fill=GRID)
    for y in range(0, H, 64):
        d.rectangle([0, y, W, y + 1], fill=GRID)
    _mini_logo(img, 44, 30, 64, accent, [UP, DOWN, UP])
    d.text((120, 62), name, font=_font(34, True), fill=FG, anchor="lm")
    chip, fc = _track(entry), _font(28, True)
    cw = d.textlength(chip, font=fc)
    d.rounded_rectangle([W - 48 - cw - 44, 36, W - 48, 88], radius=26, fill=accent)
    d.text((W - 48 - cw - 22, 62), chip, font=fc, fill=BG, anchor="lm")

    # title, left column
    title = entry.get("title") or ""
    pre, _, post = title.partition(":")
    hero = (post if post.strip() else title).strip()  # the entry's own casing (CHoCH)
    kicker = pre.strip() if post.strip() else ""
    y, col_w = 140, 600
    if kicker:
        d.text((56, y), kicker, font=_fit(kicker, lambda s: _font(s, True), col_w, 46, 28), fill=accent)
        y += 70
    size, lines = 120, []
    while size >= 56:
        f = _title_font(size)
        lines = _wrap(d, hero, f, col_w, 4)
        if len(lines) * size * 1.06 <= H - 60 - y and not any(ln.endswith("…") for ln in lines):
            break
        size -= 6
    f = _title_font(max(size, 56))
    for ln in lines:
        d.text((56, y), ln, font=f, fill=FG)
        y += round(f.size * 1.06)

    # mini chart, right column
    bx0, by0, bx1, by1 = 690, 130, 1236, 610
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=22, fill=BG, outline=PANEL, width=3)
    draw_chart(img, (bx0 + 18, by0 + 18, bx1 - 18, by1 - 18), example, THUMB, zoom=True, label="", axes=False,
               accent=accent)
    cap = f"{lessons.example_label(example)} · {example.get('timeframe', '')}".rstrip(" ·")
    fcap = _fit(cap, lambda s: _font(s), bx1 - bx0, 26, 18)
    d.text((bx0, by1 + 16), cap, font=fcap, fill=MUTED)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=92)
    return path
