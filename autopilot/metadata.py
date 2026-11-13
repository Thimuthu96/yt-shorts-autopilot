"""Titles, the YouTube description and the Facebook Reel caption for a Gus Explains story.

    build(story, track_yt, cfg) -> {"title", "description", "tags", "category_id": "27"}
        description: hook line → summary → "Sources:" bullet URLs → music attribution (if any) → disclosure line
        (exactly once) → 3-5 hashtags + #Shorts last
    reel_caption(story, track_fb, cfg) -> str
        the same without links (sources named by site), without #Shorts, < 2,200 chars
    hook_line(story) -> str           the narration's first sentence
"""
import re
from urllib.parse import urlparse

from autopilot import rules, soundtrack

TITLE_MAX = 60
LINK = re.compile(r"https?://\S+|www\.\S+", re.I)
SAFE = re.compile(r"[<>]")


def _safe(text: str) -> str:
    return " ".join(SAFE.sub("", str(text or "")).split())


def title(story: dict) -> str:
    t = _safe(story.get("title", ""))
    if len(t) > TITLE_MAX:
        t = t[:TITLE_MAX + 1].rsplit(" ", 1)[0].rstrip(" ,:;-")
    return t


def hook_line(story: dict) -> str:
    words = []
    for b in story.get("beats", []):
        words += b.get("text", "").split()
        if re.search(r"[.!?]$", words[-1] if words else ""):
            break
    return _safe(" ".join(words))


def hashtags(story: dict, youtube: bool) -> list[str]:
    out, seen = [], set()
    for h in story.get("hashtags", []):
        h = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(h).lstrip("#"))
        if len(h) > 2 and h.lower() not in seen and h.lower() not in ("#shorts", "#short"):
            seen.add(h.lower())
            out.append(h)
    out = out[:5]
    return out + ["#Shorts"] if youtube else out


def site(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in ("co", "ac", "gov", "org", "com", "edu"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def tags(story: dict) -> list[str]:
    out, seen, total = [], set(), 0
    seeds = [h.lstrip("#") for h in hashtags(story, False)] + [story.get("category", "").replace("_", " "),
                                                               "gus explains", "explained", "did you know"]
    seeds += [w for w in re.findall(r"[A-Za-z]{4,}", story.get("title", "")) if w.lower() not in ("why", "that", "this")]
    for t in seeds:
        t = _safe(t).replace(",", "")
        cost = len(t) + (2 if " " in t else 0) + 1
        if t and t.lower() not in seen and total + cost <= 480:
            seen.add(t.lower())
            out.append(t)
            total += cost
    return out


def build(story: dict, track_yt: dict | None, cfg: dict) -> dict:
    line = rules.disclosure(cfg)
    summary = rules.without_disclosure(_safe(story.get("summary", "")), line)
    parts = [hook_line(story), summary,
             "Sources:\n" + "\n".join(f"• {s['url']}" for s in story.get("sources", []) if s.get("url"))]
    attr = soundtrack.attribution_line(track_yt)
    if attr:
        parts.append(attr)
    tail = line + "\n\n" + " ".join(hashtags(story, True))
    body = "\n\n".join(p for p in parts if p)
    return {"title": title(story), "description": body[:4900 - len(tail) - 2].rstrip() + "\n\n" + tail,
            "tags": tags(story), "category_id": "27"}


def reel_caption(story: dict, track_fb: dict | None, cfg: dict) -> str:
    line = rules.disclosure(cfg)
    clean = lambda t: " ".join(LINK.sub("", _safe(t)).split())  # noqa: E731
    names = list(dict.fromkeys(site(s["url"]) for s in story.get("sources", []) if s.get("url")))
    parts = [clean(hook_line(story)), clean(rules.without_disclosure(story.get("summary", ""), line))]
    if names:
        parts.append("Sources: " + ", ".join(names[:5]))
    attr = clean(soundtrack.attribution_line(track_fb))
    if attr:
        parts.append(attr)
    tail = line + "\n\n" + " ".join(hashtags(story, False))
    body = "\n\n".join(p for p in parts if p)
    return (body[:2190 - len(tail) - 2].rstrip() + "\n\n" + tail).strip()
