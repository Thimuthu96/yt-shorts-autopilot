"""News post card (1080x1350 JPEG) on a story-matched background.

background():  Cloudflare Workers AI FLUX.1 schnell (free tier: 10k neurons/day ≈ 60 per image;
               secrets CF_ACCOUNT_ID + CF_API_TOKEN) → a random image from assets/backgrounds/<topic>/
               → a drawn branded background. Prompts are symbolic scenes only: no text, logos, real
               people or realistic depictions of the actual event.
render_card(): full-bleed background, brand + date chip, kicker pill, huge 2-3 line headline (one
               line in the accent colour), subline, source, and "AI illustration" when the image is AI.
"""
import base64
import os
import random
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

from .thumbnail import BG, GREEN, RED, _anton, _fit, _grotesk, _hex, _mini_logo

W, H = 1080, 1350
ROOT = Path(__file__).resolve().parents[1]
CF_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
STYLE = ("Editorial illustration, cinematic lighting, deep shadows, dark navy and amber palette, "
         "dark calm lower half. No text, no letters, no numbers, no logos, no watermark, "
         "no recognisable people, no faces.")
TINT = {"rates": (40, 70, 140), "central_bank": (40, 70, 140), "geopolitics": (120, 40, 40),
        "tariffs": (150, 90, 30), "regulation": (80, 60, 140), "macro": (30, 110, 120),
        "crypto": (160, 110, 20), "gold": (170, 130, 40), "fx": (30, 120, 80), "markets": (50, 80, 120)}

_http = requests  # swapped out by the offline test


def _cover(img: Image.Image, w: int = W, h: int = H) -> Image.Image:
    img = img.convert("RGB")
    scale = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * scale)), max(h, round(img.height * scale))), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def cloudflare(prompt: str, cfg: dict, log=print) -> Image.Image | None:
    account, token = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not account or not token:
        log("Background: CF_ACCOUNT_ID / CF_API_TOKEN not set, no AI image")
        return None
    im = cfg.get("images") or {}
    model = im.get("model") or "@cf/black-forest-labs/flux-1-schnell"
    steps = min(max(int(im.get("steps", 6)), 1), 8)
    url = CF_URL.format(account=account, model=model)
    for attempt in range(2):
        try:
            r = _http.post(url, headers={"Authorization": f"Bearer {token}"}, timeout=(15, 120),
                           json={"prompt": f"{prompt}. {STYLE}"[:2000], "steps": steps})
        except requests.RequestException as e:
            log(f"Background: Cloudflare request failed ({e})")
            continue
        if r.status_code >= 500 and attempt == 0:
            log(f"Background: Cloudflare busy ({r.status_code}), retrying once")
            continue
        try:
            js = r.json()
        except ValueError:
            js = {}
        if r.status_code >= 400 or not js.get("success", False):
            errs = js.get("errors") or r.text[:200]
            log(f"Background: Cloudflare error {r.status_code}: {str(errs)[:200]}")
            return None
        try:
            return Image.open(BytesIO(base64.b64decode(js["result"]["image"]))).convert("RGB")
        except (KeyError, TypeError, ValueError, OSError) as e:
            log(f"Background: Cloudflare image unreadable ({e})")
            return None
    return None


def library(topic: str) -> Path | None:
    for name in (topic, "general"):
        d = ROOT / "assets" / "backgrounds" / name
        files = sorted(p for p in d.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")) \
            if d.is_dir() else []
        if files:
            return random.choice(files)
    return None


def drawn(topic: str, accent=(255, 212, 0)) -> Image.Image:
    """Branded background: tinted gradient, glow, faint grid, rising candlesticks."""
    tint = TINT.get(topic, TINT["markets"])
    img = Image.new("RGB", (W, H), BG)
    px = ImageDraw.Draw(img)
    for y in range(H):  # top: topic tint → bottom: brand dark
        k = max(0.0, 1 - y / (H * 0.85))
        px.line([(0, y), (W, y)], fill=tuple(int(BG[i] + (tint[i] - BG[i]) * 0.55 * k) for i in range(3)))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W * 0.35, -H * 0.25, W * 1.25, H * 0.55], fill=150)
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img = Image.composite(Image.new("RGB", (W, H), tuple(min(255, c + 60) for c in tint)), img, glow)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x in range(0, W, 90):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 14), width=2)
    for y in range(0, H, 90):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 14), width=2)
    rnd = random.Random(topic)
    level, x = 0.62, 60
    while x < W - 40:  # candles drifting upward across the top half (decorative, not data)
        o = level
        c = o + rnd.uniform(-0.05, 0.035)
        hi, lo = max(o, c) + rnd.uniform(0.005, 0.03), min(o, c) - rnd.uniform(0.005, 0.03)
        col = (GREEN if c < o else RED) + (70,)
        d.line([(x + 14, hi * H * 0.75), (x + 14, lo * H * 0.75)], fill=col, width=4)
        d.rectangle([x, min(o, c) * H * 0.75, x + 28, max(o, c) * H * 0.75 + 4], fill=col)
        level, x = c, x + 48
    img.paste(layer, (0, 0), layer)
    return img


def background(prompt: str, topic: str, cfg: dict, log=print) -> tuple[Image.Image, str]:
    """(1080x1350 image, "ai" | "library" | "drawn")"""
    provider = str((cfg.get("images") or {}).get("provider", "cloudflare")).lower()
    if provider == "cloudflare":
        img = cloudflare(prompt, cfg, log=log)
        if img is not None:
            log("Background: AI image (Cloudflare FLUX.1 schnell)")
            return _cover(img), "ai"
    path = library(topic)
    if path:
        try:
            log(f"Background: library image {path.relative_to(ROOT)}")
            return _cover(Image.open(path)), "library"
        except OSError as e:
            log(f"Background: library image unreadable ({e})")
    log(f"Background: drawn ({topic})")
    accent = _hex((cfg.get("video") or {}).get("accent", "FFD400"))
    return drawn(topic, accent), "drawn"


# ─── the card ──────────────────────────────────────────────────────────────

def _wrap(text: str, font, max_w: int, max_lines: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        trial = f"{cur} {w}".strip()
        if cur and font.getlength(trial) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and font.getlength(lines[-1] + "…") > max_w:
            lines[-1] = lines[-1].rsplit(" ", 1)[0] if " " in lines[-1] else lines[-1][:-1]
        lines[-1] += "…"
    return lines


def _shade(img: Image.Image) -> Image.Image:
    """Darken the top (brand) and the lower ~60% (text) so white type stays readable on any image."""
    mask = Image.new("L", (1, H))
    for y in range(H):
        top = max(0.0, 1 - y / 230) * 150
        k = (y - H * 0.30) / (H * 0.32)
        bottom = 236 * min(max(k, 0.0), 1.0) ** 1.3
        mask.putpixel((0, y), int(max(top, bottom)))
    mask = mask.resize((W, H))
    return Image.composite(Image.new("RGB", (W, H), (8, 9, 12)), img, mask)


def _text(img: Image.Image, xy, text: str, font, fill, anchor="la", shadow=110):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((xy[0], xy[1] + 4), text, font=font, fill=(0, 0, 0, shadow), anchor=anchor)
    layer = layer.filter(ImageFilter.GaussianBlur(4))
    img.paste(layer, (0, 0), layer)
    ImageDraw.Draw(img).text(xy, text, font=font, fill=fill, anchor=anchor)


def render_card(post: dict, bg: Image.Image, cfg: dict, date_utc: str, path: Path, ai: bool = False,
                source: str = "") -> Path:
    from datetime import datetime
    accent = _hex((cfg.get("video") or {}).get("accent", "FFD400"))
    name = (cfg.get("channel") or {}).get("display_name", "CryptoFX Daily")
    img = _shade(_cover(bg))
    d = ImageDraw.Draw(img)
    margin, max_w = 56, W - 2 * 56

    # brand + date chip
    _mini_logo(img, margin - 8, 40, 76, accent, [GREEN, RED, GREEN])
    _text(img, (margin + 76, 78), name, _fit(name, _grotesk, 560, 40, 26), (245, 245, 245), anchor="lm")
    dt = datetime.fromisoformat(date_utc)
    chip = f"{dt:%b} {dt.day}".upper()
    fc = _grotesk(32)
    cw = fc.getlength(chip)
    d.rounded_rectangle([W - margin - cw - 48, 52, W - margin, 104], radius=26, fill=(14, 15, 18),
                        outline=(90, 94, 104), width=2)
    d.text((W - margin - cw - 24, 78), chip, font=fc, fill=(225, 227, 232), anchor="lm")

    # bottom-up: footer, subline, headline, kicker
    y = H - 52
    foot = _grotesk(28, 500)
    if source:
        d.text((margin, y), f"Source: {source}", font=foot, fill=(170, 174, 182), anchor="ls")
    if ai:
        d.text((W - margin, y), "AI illustration", font=foot, fill=(170, 174, 182), anchor="rs")
    y -= 58

    subline = (post.get("subline") or "").strip()
    if subline:
        fs = _grotesk(40, 500)
        sub_lines = _wrap(subline, fs, max_w, 2)
        for line in reversed(sub_lines):
            _text(img, (margin, y), line, fs, (226, 228, 233), anchor="ls", shadow=140)
            y -= 52
        y -= 22

    lines = [ln for ln in (post.get("headline") or []) if ln] or ["MARKET NEWS"]
    acc = min(max(int(post.get("accent_line", len(lines) - 1)), 0), len(lines) - 1)
    max_h = 640 if len(lines) <= 3 else 700
    size = 200
    while size > 72:
        f = _anton(size)
        cap = f.getbbox("H")[3] - f.getbbox("H")[1]
        pitch = int(cap * 1.18)
        if max(f.getlength(ln) for ln in lines) <= max_w and pitch * (len(lines) - 1) + cap <= max_h:
            break
        size -= 4
    f = _anton(size)
    top_off, cap = f.getbbox("H")[1], f.getbbox("H")[3] - f.getbbox("H")[1]
    pitch = int(cap * 1.18)
    block_top = y - (pitch * (len(lines) - 1) + cap)
    for i, ln in enumerate(lines):
        ly = block_top + i * pitch - top_off
        _text(img, (margin - 4, ly), ln, f, accent if i == acc else (255, 255, 255), shadow=150)

    kicker = (post.get("kicker") or "").strip().upper()
    if kicker:
        fk = _grotesk(34, 700)
        kw = fk.getlength(kicker)
        ky = block_top - 40 - 60
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([margin, ky, margin + kw + 44, ky + 60], radius=10, fill=accent)
        d.text((margin + 22, ky + 30), kicker, font=fk, fill=BG, anchor="lm")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=90, optimize=True)
    return path
