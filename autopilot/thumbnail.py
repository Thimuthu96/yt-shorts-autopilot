"""Daily thumbnail / opening frame (1080x1920), in four templates:

  move   — one asset made a big move ("−6.2%" + chart + "WHAT HAPPENED?")
  event  — a high-impact event is due soon ("CPI DAY" on yellow)
  split  — crypto and the US dollar moved opposite ways (green/red split)
  level  — BTC/ETH/gold is close to a round number ("1.2% AWAY FROM $100K")
  gold   — the daily gold outlook ("BEARISH" + "BELOW $4,143" + 1H/4H chips + chart)

choose() picks the template from the day's data (staying on the brief's focus assets when
focus.pick() ran); choose_gold() builds the gold outlook card; render() draws it. Every number
comes from the data. Top and bottom 150 px are kept clear (YouTube crops them in the grid).
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BG = (14, 15, 18)
GRID = (23, 25, 30)
GREEN = (34, 197, 94)
RED = (239, 68, 68)
RED_DARK = (220, 38, 38)
MUTED = (169, 173, 182)
CHIP = (58, 61, 69)
TRACK = (35, 38, 45)
WHITE = (255, 255, 255)
FG = (245, 245, 245)
GOLD = (212, 175, 55)

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"


def _anton(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / "Anton-Regular.ttf"), size)


def _grotesk(size: int, weight: int = 700) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_DIR / "SpaceGrotesk-Variable.ttf"), size)
    try:
        f.set_variation_by_axes([weight])
    except OSError:
        pass
    return f


def _hex(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _fit(text: str, make, max_w: int, start: int, minimum: int = 40):
    size = start
    while size > minimum:
        f = make(size)
        if f.getlength(text) <= max_w:
            return f
        size -= 6
    return make(minimum)


def _draw_text_top(d: ImageDraw.ImageDraw, xy, text, font, fill):
    """Draw so the glyphs' visible top sits at xy[1] (fonts carry different top padding)."""
    x, y = xy
    d.text((x, y - font.getbbox(text)[1]), text, font=font, fill=fill)


def _short_money(v: float) -> str:
    if v >= 1000:
        k = v / 1000
        return f"${k:,.0f}K" if k == int(k) else f"${k:,.1f}K"
    return f"${v:,.0f}"


def _pct(v: float, signed: bool = True) -> str:
    s = f"{abs(v):.1f}%"
    return (("+" if v >= 0 else "−") + s) if signed else s


# ─── choosing a template ───────────────────────────────────────────────────

BANKS = {"USD": "FED", "EUR": "ECB", "GBP": "BOE", "JPY": "BOJ", "AUD": "RBA", "CAD": "BOC",
         "CHF": "SNB", "NZD": "RBNZ", "CNY": "PBOC"}
EVENT_WORDS = [("FOMC", "FED"), ("Federal Funds", "FED"), ("Fed Chair", "FED"), ("Powell", "FED"),
               ("Non-Farm", "NFP"), ("Core PCE", "PCE"), ("PCE", "PCE"), ("CPI", "CPI"), ("PPI", "PPI"),
               ("GDP", "GDP"), ("Retail Sales", "RETAIL"), ("PMI", "PMI"), ("Unemployment", "JOBS"),
               ("Employment", "JOBS"), ("Jobless", "JOBS")]
RATE_WORDS = ("Rate Statement", "Rate Decision", "Cash Rate", "Official Bank Rate",
              "Main Refinancing Rate", "Monetary Policy", "Policy Rate", "Interest Rate")


def _event_word(ev: dict) -> str:
    title = ev.get("event", "")
    if any(w.lower() in title.lower() for w in RATE_WORDS):
        return BANKS.get(ev.get("currency", ""), "RATES")
    for key, word in EVENT_WORDS:
        if key.lower() in title.lower():
            return word
    first = re.sub(r"[^A-Za-z]", "", title.split(" ")[0]).upper() if title else ""
    return first if 2 <= len(first) <= 6 else "DATA"


def _usd_strength(fx: dict) -> float | None:
    """Average daily change of the dollar against the other currencies we track (+ = dollar up)."""
    vals = []
    for pair, f in fx.items():
        if pair.startswith("USD"):
            vals.append(f["change_1d"])
        elif pair.endswith("USD"):
            vals.append(-f["change_1d"])
    return sum(vals) / len(vals) if vals else None


def choose(data: dict) -> dict:
    crypto, fx, gold = data.get("crypto", {}), data.get("fx", {}), data.get("gold") or {}
    moves = [(abs(c["change_24h"]) / 4.0, sym, c["name"], c["change_24h"], "crypto") for sym, c in crypto.items()]
    if not data.get("weekend"):
        moves += [(abs(f["change_1d"]) / 0.8, pair, f["name"], f["change_1d"], "fx") for pair, f in fx.items()]
        if gold:
            moves.append((abs(gold["change_24h"]) / 1.5, "XAU", "Gold", gold["change_24h"], "gold"))
    moves.sort(reverse=True)
    focus = data.get("focus") or {}
    in_focus = set(focus.get("assets") or [])
    if in_focus:  # the thumbnail stays on the brief's story
        moves = [m for m in moves if m[1] in in_focus] or moves
    currencies = set(focus.get("currencies") or [])

    def move_spec(m):
        score, key, name, chg, kind = m
        up = chg >= 0
        if kind == "crypto":
            series, label, badge, sub = crypto[key]["series"][-48:], name.upper(), key, "24-HOUR MOVE"
        elif kind == "gold":
            series, label, badge, sub = gold["series"][-48:], "GOLD", "XAU", "24-HOUR MOVE"
        else:
            series, label, badge, sub = fx[key]["series"][-15:], name, "FX", "DAILY MOVE"
        return {"template": "move", "label": label, "badge": badge, "sublabel": sub, "up": up,
                "hero": _pct(chg), "series": series,
                "default_hook": "WHAT HAPPENED?" if not up else "WHAT'S DRIVING IT?",
                "facts": f"{name} {'up' if up else 'down'} {abs(chg):.1f}% ({sub.lower()})"}

    # 1) a genuinely big move
    if moves and moves[0][0] >= 1:
        return move_spec(moves[0])

    # 2) a high-impact event within the next 12 hours
    now = datetime.now(timezone.utc)
    for ev in data.get("calendar", []):
        try:
            when = datetime.fromisoformat(ev["datetime"])
        except (KeyError, ValueError):
            continue
        if currencies and ev.get("currency") not in currencies:
            continue
        if now - timedelta(minutes=30) <= when <= now + timedelta(hours=12):
            word = _event_word(ev)
            return {"template": "event", "word": word, "currency": ev["currency"], "time": ev["time_utc"],
                    "default_hook": f"WATCH BEFORE {ev['time_utc']}",
                    "facts": f"{ev['currency']} {ev['event']} at {ev['time_utc']} GMT today (shown as '{word} DAY')"}

    # 3) bitcoin and the dollar moving opposite ways
    btc, usd = crypto.get("BTC"), _usd_strength(fx) if not data.get("weekend") else None
    if in_focus and "BTC" not in in_focus:
        btc = None
    if btc and usd is not None and abs(btc["change_24h"]) >= 1.5 and abs(usd) >= 0.3 \
            and (btc["change_24h"] > 0) != (usd > 0):
        b = ("BITCOIN", btc["change_24h"])
        u = ("US DOLLAR", usd)
        top, bottom = (b, u) if btc["change_24h"] > 0 else (u, b)
        return {"template": "split", "top_label": top[0], "top_hero": _pct(top[1]),
                "bottom_label": bottom[0], "bottom_hero": _pct(bottom[1]), "default_hook": "WHY THE SPLIT?",
                "facts": f"Bitcoin {_pct(btc['change_24h'])} in 24h while the US dollar moved {_pct(usd)} "
                         f"on average against major currencies"}

    # 4) close to a round number
    for sym, step in (("BTC", 5000), ("ETH", 500), ("XAU", 100)):
        c = gold if sym == "XAU" and not data.get("weekend") else crypto.get(sym)
        if not c or (in_focus and sym not in in_focus):
            continue
        price = c["price"]
        level = (int(price // step) + 1) * step
        dist = (level - price) / price * 100
        if 0.15 <= dist <= 2.0:
            return {"template": "level", "label": f"{c['name'].upper()} IS", "dist": f"{dist:.1f}% AWAY",
                    "level": _short_money(level), "now": f"NOW ${price:,.0f}", "target": f"${level:,.0f}",
                    "fill": 0.72 + 0.26 * (1 - dist / 2.0), "default_hook": "SO CLOSE.",
                    "facts": f"{c['name']} at ${price:,.0f}, {dist:.1f}% below ${level:,.0f}"}

    # 5) fallback: the day's biggest mover
    if moves:
        return move_spec(moves[0])
    return {"template": "event", "word": "MARKET", "currency": "", "time": "", "default_hook": "TODAY'S BRIEF",
            "facts": "daily market brief"}


def choose_gold(data: dict) -> dict:
    """Opening card of the daily gold outlook, from gold.analyze()."""
    a = data["gold_analysis"]
    daily = a["bias"]["Daily"]["bias"]
    sc = a["scenarios"]
    if daily == "bullish" and a.get("invalidation"):
        hero, line = "BULLISH", f"ABOVE ${a['invalidation']['price']:,.0f}"
    elif daily == "bearish" and a.get("invalidation"):
        hero, line = "BEARISH", f"BELOW ${a['invalidation']['price']:,.0f}"
    else:
        lo = sc["bear"]["trigger"]["price"] if sc.get("bear") else a["today"]["low"]
        hi = sc["bull"]["trigger"]["price"] if sc.get("bull") else a["today"]["high"]
        hero, line = "RANGE", f"${lo:,.0f} – ${hi:,.0f}"
    h1, h4 = a["bias"]["1H"]["bias"].upper(), a["bias"]["4H"]["bias"].upper()
    words = {"BULLISH": "bullish", "BEARISH": "bearish", "RANGE": "neutral (range)"}
    return {"template": "gold", "hero": hero, "line": line, "h1": h1, "h4": h4,
            "series": data["gold"]["series"][-48:], "up": data["gold"]["change_24h"] >= 0,
            "default_hook": "KEY LEVELS TODAY",
            "facts": f"Gold's daily bias is {words[hero]}, {line.lower().replace('–', 'to')} "
                     f"(1H {h1.lower()}, 4H {h4.lower()}); gold at ${a['price']:,.0f}"}


BANNED = {"MOON", "BUY", "SELL", "GUARANTEED", "GUARANTEE", "RICH", "100X", "1000X", "INCOMING", "WILL",
          "SECRET", "SCAM", "NOW!"}


def clean_hook(hook: str | None, fallback: str) -> str:
    """2-4 words, short, no hype or predictions; otherwise the template's fallback."""
    if not hook:
        return fallback
    h = re.sub(r"\s+", " ", str(hook)).strip().upper()
    h = h.replace("’", "'")
    words = h.split(" ")
    if not 1 <= len(words) <= 4 or len(h) > 22:
        return fallback
    if not re.fullmatch(r"[A-Z0-9 $%.,!?'&:/+−]+", h):
        return fallback
    if any(w.strip("?!.,") in BANNED for w in words):
        return fallback
    return h


# ─── drawing ───────────────────────────────────────────────────────────────

def _grid_bg() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 90):
        d.rectangle([x, 0, x + 1, H], fill=GRID)
    for y in range(0, H, 90):
        d.rectangle([0, y, W, y + 1], fill=GRID)
    return img


def _mini_logo(img: Image.Image, x: int, y: int, size: int, ring, candles, hollow_mid=False):
    s = size / 800
    d = ImageDraw.Draw(img)
    r, cx, cy = 300 * s, x + 400 * s, y + 400 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ring, width=max(int(44 * s), 3))
    boxes = [(230, 410, 320, 560), (355, 340, 445, 510), (480, 230, 570, 460)]
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        rect = [x + x0 * s, y + y0 * s, x + x1 * s, y + y1 * s]
        if hollow_mid and i == 1:
            d.rounded_rectangle(rect, radius=max(int(10 * s), 1), outline=candles[i], width=max(int(16 * s), 2))
        else:
            d.rounded_rectangle(rect, radius=max(int(10 * s), 1), fill=candles[i])


def _brand(img, d, date_label: str, dark_text: bool, accent, name: str = "CryptoFX Daily"):
    ink = BG if dark_text else FG
    if dark_text:
        _mini_logo(img, 64, 170, 72, BG, [BG, BG, BG], hollow_mid=True)
    else:
        _mini_logo(img, 64, 170, 72, accent, [GREEN, RED, GREEN])
    f = _grotesk(40)
    d.text((154, 206), name, font=_fit(name, _grotesk, 560, 40, 24), fill=ink, anchor="lm")
    fc = _grotesk(34)
    w = fc.getlength(date_label)
    x1 = W - 64
    d.rounded_rectangle([x1 - w - 50, 178, x1, 234], radius=28, outline=BG if dark_text else CHIP, width=3)
    d.text((x1 - w - 25, 206), date_label, font=fc, fill=ink if dark_text else (199, 202, 209), anchor="lm")


def _hook(img: Image.Image, text: str, top: int, fill, ink, shadow, start_size: int = 128):
    f = _fit(text, _anton, 900, start_size, 70)
    bbox = f.getbbox(text)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y, sh = 44, 26, 14
    box = Image.new("RGBA", (tw + 2 * pad_x + sh, th + 2 * pad_y + sh), (0, 0, 0, 0))
    bd = ImageDraw.Draw(box)
    if shadow:
        bd.rectangle([sh, sh, tw + 2 * pad_x + sh - 1, th + 2 * pad_y + sh - 1], fill=shadow)
    bd.rectangle([0, 0, tw + 2 * pad_x - 1, th + 2 * pad_y - 1], fill=fill)
    bd.text((pad_x - bbox[0], pad_y - bbox[1]), text, font=f, fill=ink)
    rot = box.rotate(3, resample=Image.BICUBIC, expand=True)
    img.paste(rot, (60, top), rot)


def _chart(img: Image.Image, series: list[float], up: bool, box=(30, 1010, 1000, 1420)):
    col = GREEN if up else RED
    x0, y0, x1, y1 = box
    n = len(series)
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1
    pts = [(x0 + (x1 - x0) * i / max(n - 1, 1), y1 - (v - lo) / span * (y1 - y0)) for i, v in enumerate(series)]
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.polygon(pts + [(x1, y1 + 40), (x0, y1 + 40)], fill=col + (40,))
    ld.line(pts, fill=col + (255,), width=18, joint="curve")
    # arrowhead along the overall direction of the last stretch
    (ax, ay), (bx, by) = pts[max(0, n - 6)], pts[-1]
    dx, dy = bx - ax, by - ay
    length = (dx * dx + dy * dy) ** 0.5 or 1
    ux, uy = dx / length, dy / length
    tip = (bx + ux * 46, by + uy * 46)
    base = (bx - ux * 14, by - uy * 14)
    px, py = -uy * 38, ux * 38
    ld.polygon([tip, (base[0] + px, base[1] + py), (base[0] - px, base[1] - py)], fill=col + (255,))
    img.paste(layer, (0, 0), layer)


def _render_move(spec, accent, date_label, name):
    img = _grid_bg()
    d = ImageDraw.Draw(img)
    _brand(img, d, date_label, False, accent, name)
    d.ellipse([64, 310, 194, 440], fill=accent)
    fb = _fit(spec["badge"], lambda s: _grotesk(s), 110, 46, 24)
    d.text((129, 375), spec["badge"], font=fb, fill=BG, anchor="mm")
    d.text((222, 352), spec["label"], font=_fit(spec["label"], _grotesk, 790, 72, 40), fill=FG, anchor="lm")
    d.text((224, 414), spec["sublabel"], font=_grotesk(36, 600), fill=MUTED, anchor="lm")
    hero = _fit(spec["hero"], _anton, 1000, 420, 200)
    _draw_text_top(d, (44, 520), spec["hero"], hero, GREEN if spec["up"] else RED)
    _chart(img, spec["series"], spec["up"])
    return img


def _render_event(spec, accent, date_label, name):
    img = Image.new("RGB", (W, H), accent)
    d = ImageDraw.Draw(img)
    _brand(img, d, date_label, True, accent, name)
    d.text((64, 320), "HIGH-IMPACT EVENT TODAY", font=_fit("HIGH-IMPACT EVENT TODAY", _grotesk, 950, 54), fill=BG)
    word = spec["word"]
    size = min(_fit(word, _anton, 990, 520, 200).size, _fit("DAY", _anton, 990, 520, 200).size)
    f = _anton(size)
    _draw_text_top(d, (48, 420), word, f, BG)
    _draw_text_top(d, (48, 420 + int(size * 0.92)), "DAY", f, BG)
    if spec.get("time"):
        chip = f"{spec['currency']} · {spec['time']} GMT".strip(" ·")
        fc = _fit(chip, _grotesk, 900, 64, 40)
        w = fc.getlength(chip)
        d.rounded_rectangle([64, 1390, 64 + w + 80, 1390 + 100], radius=50, fill=BG)
        d.text((104, 1440), chip, font=fc, fill=accent, anchor="lm")
    _hook(img, spec["hook"], 1530, BG, accent, (0, 0, 0, 60), start_size=104)
    return img


def _render_split(spec, accent, date_label, name):
    img = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 960, W, H], fill=RED_DARK)
    _brand(img, d, date_label, True, accent, name)
    d.text((64, 320), spec["top_label"], font=_grotesk(84), fill=BG)
    _draw_text_top(d, (54, 450), spec["top_hero"], _fit(spec["top_hero"], _anton, 980, 360, 180), BG)
    d.ellipse([420, 840, 660, 1080], fill=BG, outline=accent, width=12)
    d.text((540, 960), "VS", font=_anton(118), fill=accent, anchor="mm")
    _draw_text_top(d, (54, 1120), spec["bottom_hero"], _fit(spec["bottom_hero"], _anton, 980, 360, 180), WHITE)
    d.text((64, 1460), spec["bottom_label"], font=_grotesk(84), fill=WHITE)
    _hook(img, spec["hook"], 1590, accent, BG, BG + (255,), start_size=116)
    return img


def _render_level(spec, accent, date_label, name):
    img = _grid_bg()
    d = ImageDraw.Draw(img)
    _brand(img, d, date_label, False, accent, name)
    d.text((64, 320), spec["label"], font=_fit(spec["label"], _grotesk, 950, 80), fill=FG)
    _draw_text_top(d, (58, 440), spec["dist"], _fit(spec["dist"], _anton, 960, 210, 120), WHITE)
    d.text((64, 690), "FROM", font=_grotesk(64), fill=MUTED)
    _draw_text_top(d, (48, 790), spec["level"], _fit(spec["level"], _anton, 990, 470, 220), accent)
    f = _grotesk(42)
    d.text((64, 1250), spec["now"], font=f, fill=GREEN)
    d.text((W - 64, 1250), spec["target"], font=f, fill=accent, anchor="ra")
    d.rounded_rectangle([64, 1316, 1016, 1380], radius=32, fill=TRACK)
    fill_w = int(952 * max(0.1, min(spec["fill"], 0.98)))
    d.rounded_rectangle([64, 1316, 64 + fill_w, 1380], radius=32, fill=GREEN)
    d.rounded_rectangle([1004, 1296, 1016, 1400], radius=6, fill=accent)
    _hook(img, spec["hook"], 1490, accent, BG, (0, 0, 0, 255), start_size=150)
    return img


def _render_gold(spec, accent, date_label, name):
    img = _grid_bg()
    d = ImageDraw.Draw(img)
    _brand(img, d, date_label, False, accent, name)
    d.ellipse([64, 310, 194, 440], fill=GOLD)
    d.text((129, 375), "XAU", font=_grotesk(44), fill=BG, anchor="mm")
    d.text((222, 352), "GOLD OUTLOOK", font=_fit("GOLD OUTLOOK", _grotesk, 790, 72, 40), fill=FG, anchor="lm")
    d.text((224, 414), "DAILY BIAS · XAU/USD", font=_grotesk(36, 600), fill=MUTED, anchor="lm")
    col = {"BULLISH": GREEN, "BEARISH": RED}.get(spec["hero"], GOLD)
    hero = _fit(spec["hero"], _anton, 990, 320, 180)
    _draw_text_top(d, (44, 500), spec["hero"], hero, col)
    top = 500 + hero.getbbox(spec["hero"])[3] - hero.getbbox(spec["hero"])[1] + 40
    d.text((64, top), spec["line"], font=_fit(spec["line"], _grotesk, 950, 92, 50), fill=WHITE)
    x, y = 64, top + 130
    for label, val in (("1H", spec["h1"]), ("4H", spec["h4"])):
        c = {"BULLISH": GREEN, "BEARISH": RED}.get(val, CHIP)
        txt = f"{label} {val}"
        fc = _grotesk(40)
        w = fc.getlength(txt)
        d.rounded_rectangle([x, y, x + w + 56, y + 72], radius=36, fill=c)
        d.text((x + 28, y + 36), txt, font=fc, fill=WHITE, anchor="lm")
        x += w + 80
    _chart(img, spec["series"], spec["up"], box=(30, max(y + 110, 1060), 1000, 1400))
    return img


def render(spec: dict, cfg: dict, date_utc: str, path: Path, edition_short: str = "") -> Path:
    accent = _hex(cfg["video"].get("accent", "FFD400"))
    dt = datetime.fromisoformat(date_utc)
    date_label = f"{dt:%b} {dt.day}".upper() + (f" · {edition_short.upper()}" if edition_short else "")
    spec.setdefault("hook", spec["default_hook"])
    fn = {"move": _render_move, "event": _render_event, "split": _render_split, "level": _render_level,
          "gold": _render_gold}[spec["template"]]
    img = fn(spec, accent, date_label, cfg["channel"].get("display_name", "CryptoFX Daily"))
    if spec["template"] in ("move", "gold"):
        _hook(img, spec["hook"], 1450, accent, BG, BG + (255,))
    img.save(path, quality=92)
    return path
