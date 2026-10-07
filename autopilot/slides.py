"""Scene graphics (1080x1920 PNGs) drawn from the day's data with Pillow + matplotlib.

Layout keeps y 1230-1480 free for the burned-in captions.
"""
import io
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

W, H = 1080, 1920
BG = (14, 15, 18)
PANEL = (26, 28, 34)
FG = (245, 245, 245)
MUTED = (160, 165, 175)
UP = (34, 197, 94)
DOWN = (239, 68, 68)
CONTENT_BOTTOM = 1190

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/Library/Fonts",
             "C:/Windows/Fonts"]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = ["DejaVuSans-Bold.ttf", "arialbd.ttf"] if bold else ["DejaVuSans.ttf", "arial.ttf"]
    for d in FONT_DIRS:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


def _hex(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def fmt_price(p: float, fx: bool = False, pair: str = "") -> str:
    if fx:
        return f"{p:.2f}" if "JPY" in pair else f"{p:.4f}"
    if p >= 1000:
        return f"${p:,.0f}"
    if p >= 1:
        return f"${p:,.2f}"
    return f"${p:.4f}"


def fmt_change(c: float) -> str:
    return f"{'▲' if c >= 0 else '▼'} {abs(c):.2f}%"


def _wrap(draw, text: str, font, max_w: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > max_w:
            lines[-1] = lines[-1].rsplit(" ", 1)[0] if " " in lines[-1] else lines[-1][:-1]
        lines[-1] += "…"
    return lines


class Canvas:
    def __init__(self, cfg: dict, date_label: str):
        self.accent = _hex(cfg["video"].get("accent", "FFD400"))
        self.brand = cfg["channel"].get("display_name", "DAILY MARKET BRIEF").upper()
        self.footer = cfg["video"].get("footer", "Not financial advice")
        self.date_label = date_label

    def base(self):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.text((60, 80), self.brand, font=_font(34, True), fill=self.accent)
        f = _font(30)
        d.text((W - 60 - d.textlength(self.date_label, font=f), 82), self.date_label, font=f, fill=MUTED)
        d.line([(60, 140), (W - 60, 140)], fill=PANEL, width=3)
        f = _font(26)
        d.text(((W - d.textlength(self.footer, font=f)) / 2, 1830), self.footer, font=f, fill=MUTED)
        return img, d

    def chip(self, d, x, y, change: float, suffix: str = "", size: int = 40):
        txt = fmt_change(change) + (f"  {suffix}" if suffix else "")
        f = _font(size, True)
        w = d.textlength(txt, font=f)
        col = UP if change >= 0 else DOWN
        d.rounded_rectangle([x, y, x + w + 44, y + size + 30], radius=18, fill=col)
        d.text((x + 22, y + 12), txt, font=f, fill=(255, 255, 255))
        return x + w + 44


def _chart_png(values: list[float], labels: tuple[str, str], up: bool, w=960, h=600) -> Image.Image:
    col = tuple(c / 255 for c in (UP if up else DOWN))
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes([0.02, 0.1, 0.84, 0.86])
    x = list(range(len(values)))
    ax.plot(x, values, color=col, linewidth=5, solid_capstyle="round")
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.08 or hi * 0.01
    ax.set_ylim(lo - pad, hi + pad)
    ax.fill_between(x, values, lo - pad, color=col, alpha=0.14)
    ax.set_xlim(0, len(values) - 1)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=tuple(c / 255 for c in MUTED), labelsize=17, length=0)
    ax.yaxis.tick_right()
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(4))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"{v:,.0f}" if hi >= 1000 else (f"{v:.2f}" if hi >= 20 else f"{v:.4f}")))
    ax.set_xticks([0, len(values) - 1])
    lbls = ax.set_xticklabels(labels)
    lbls[0].set_horizontalalignment("left")
    lbls[-1].set_horizontalalignment("right")
    ax.grid(axis="y", color=tuple(c / 255 for c in PANEL), linewidth=1.5)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def _short_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt:%b} {dt.day}"
    except ValueError:
        return iso[:10]


# ─── slide types ───────────────────────────────────────────────────────────
# each returns (PIL image, reveal box or None)

def slide_title(cv: Canvas, data: dict, v: dict):
    img, d = cv.base()
    y = 300
    kicker = (v.get("kicker") or "TODAY").upper()
    d.text((60, y), kicker, font=_font(46, True), fill=cv.accent)
    y += 90
    f = _font(96, True)
    for line in _wrap(d, v.get("headline") or "", f, W - 120, 4):
        d.text((60, y), line, font=f, fill=FG)
        y += 112
    btc = data["crypto"].get("BTC")
    if btc and y < 1000:
        y += 50
        d.text((60, y + 12), f"BTC {fmt_price(btc['price'])}", font=_font(48, True), fill=FG)
        cv.chip(d, 60 + d.textlength(f"BTC {fmt_price(btc['price'])}", font=_font(48, True)) + 28,
                y, btc["change_24h"], "24h", size=36)
    return img, None


def _asset_slide(cv: Canvas, name: str, sym: str, price: str, change: float, change_label: str,
                 values, labels, note: str):
    img, d = cv.base()
    d.text((60, 210), name.upper(), font=_font(44, True), fill=MUTED)
    d.text((60 + d.textlength(name.upper() + "  ", font=_font(44, True)), 214), sym,
           font=_font(40), fill=MUTED)
    d.text((56, 270), price, font=_font(120, True), fill=FG)
    cv.chip(d, 60, 420, change, change_label)
    chart = _chart_png(values, labels, change >= 0)
    cx, cy = 60, 540
    img.paste(chart, (cx, cy), chart)
    d.text((60, cy + chart.height + 4), note, font=_font(28), fill=MUTED)
    return img, (cx, cy, chart.width, chart.height)


def slide_price(cv: Canvas, data: dict, v: dict):
    sym = v["asset"]
    c = data["crypto"][sym]
    labels = (_short_date(c["series_times"][0]), "now")
    note = f"7-day chart · 24h range {fmt_price(c['low_24h'])} – {fmt_price(c['high_24h'])}"
    return _asset_slide(cv, c["name"], sym, fmt_price(c["price"]), c["change_24h"], "24h",
                        c["series"], labels, note)


def slide_fx(cv: Canvas, data: dict, v: dict):
    pair = v["asset"]
    f = data["fx"][pair]
    labels = (_short_date(f["series_times"][0]), _short_date(f["series_times"][-1]))
    note = f"30-day chart · daily reference rate, {_short_date(f['as_of'])}"
    return _asset_slide(cv, f["name"], "", fmt_price(f["price"], True, pair), f["change_1d"], "1 day",
                        f["series"], labels, note)


def slide_board(cv: Canvas, data: dict, v: dict):
    img, d = cv.base()
    d.text((60, 200), "MARKETS AT A GLANCE", font=_font(46, True), fill=cv.accent)
    rows = [(c["name"], fmt_price(c["price"]), c["change_24h"]) for c in data["crypto"].values()]
    rows += [(f["name"], fmt_price(f["price"], True, p), f["change_1d"]) for p, f in data["fx"].items()]
    rows = rows[:9]
    y, row_h = 290, min(100, (CONTENT_BOTTOM - 290) // max(len(rows), 1))
    fname, fval, fchg = _font(40, True), _font(40), _font(36, True)
    for name, price, chg in rows:
        d.rounded_rectangle([50, y, W - 50, y + row_h - 14], radius=16, fill=PANEL)
        mid = y + (row_h - 14) / 2
        d.text((80, mid - 24), name, font=fname, fill=FG)
        d.text((560 - d.textlength(price, font=fval) / 2 + 60, mid - 24), price, font=fval, fill=FG)
        txt = fmt_change(chg)
        d.text((W - 80 - d.textlength(txt, font=fchg), mid - 21), txt, font=fchg, fill=UP if chg >= 0 else DOWN)
        y += row_h
    f = _font(26)
    d.text((60, y + 6), "Crypto: 24h change · Forex: last daily change", font=f, fill=MUTED)
    return img, None


def slide_news(cv: Canvas, data: dict, v: dict):
    img, d = cv.base()
    src = (v.get("source") or "News").upper()
    f = _font(36, True)
    w = d.textlength(src, font=f)
    d.rounded_rectangle([60, 260, 60 + w + 48, 260 + 70], radius=35, fill=cv.accent)
    d.text((84, 274), src, font=f, fill=BG)
    y = 400
    fh = _font(84, True)
    for line in _wrap(d, v.get("headline") or "", fh, W - 120, 6):
        d.text((60, y), line, font=fh, fill=FG)
        y += 100
    return img, None


def slide_calendar(cv: Canvas, data: dict, v: dict):
    img, d = cv.base()
    d.text((60, 200), "HIGH-IMPACT EVENTS", font=_font(46, True), fill=cv.accent)
    d.text((60, 262), "Next 24 hours · times in GMT", font=_font(30), fill=MUTED)
    events = data["calendar"][:6]
    y = 340
    if not events:
        d.text((60, y), "No high-impact events scheduled.", font=_font(48, True), fill=FG)
        return img, None
    row_h = min(140, (CONTENT_BOTTOM - y) // len(events))
    for ev in events:
        d.rounded_rectangle([50, y, W - 50, y + row_h - 14], radius=16, fill=PANEL)
        d.text((80, y + 22), ev["time_utc"], font=_font(40, True), fill=FG)
        d.text((230, y + 22), ev["currency"], font=_font(40, True), fill=cv.accent)
        name = _wrap(d, ev["event"], _font(36), W - 360 - 80, 1)[0]
        d.text((360, y + 24), name, font=_font(36), fill=FG)
        extra = " · ".join(x for x in (f"fcst {ev['forecast']}" if ev["forecast"] else "",
                                       f"prev {ev['previous']}" if ev["previous"] else "") if x)
        if extra and row_h >= 120:
            d.text((360, y + 74), extra, font=_font(28), fill=MUTED)
        y += row_h
    return img, None


def slide_outro(cv: Canvas, data: dict, v: dict):
    img, d = cv.base()
    f = _font(84, True)
    y = 380
    for line in _wrap(d, f"That's your brief for {cv.date_label.title()}.", f, W - 120, 3):
        d.text((60, y), line, font=f, fill=FG)
        y += 100
    y += 40
    for line in ("Not financial advice.", "Do your own research.", "New brief every day."):
        d.text((60, y), line, font=_font(48, True), fill=cv.accent if line.startswith("New") else MUTED)
        y += 70
    return img, None


RENDERERS = {"title": slide_title, "price": slide_price, "fx": slide_fx, "board": slide_board,
             "news": slide_news, "calendar": slide_calendar, "outro": slide_outro}


def render_slides(cfg: dict, data: dict, scenes: list[dict], workdir: Path) -> list[dict]:
    """Returns [{"image": path, "reveal": (x, y, w, h) | None}] per scene."""
    dt = datetime.fromisoformat(data["date_utc"])
    date_label = f"{dt:%b} {dt.day}, {dt.year}".upper()
    cv = Canvas(cfg, date_label)
    out = []
    for i, s in enumerate(scenes):
        v = s.get("visual") or {"type": "board"}
        img, reveal = RENDERERS.get(v.get("type"), slide_board)(cv, data, v)
        path = workdir / f"slide_{i:02d}.png"
        img.save(path)
        out.append({"image": path, "reveal": reveal})
    return out
