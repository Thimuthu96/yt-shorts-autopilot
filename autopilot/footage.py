"""Stock footage for each scene.

Sources (free, no attribution required):
  - Pixabay  → set PIXABAY_API_KEY  (videos + photos; https://pixabay.com/api/docs/)
  - Pexels   → set PEXELS_API_KEY   (optional extra video source)

Search order for each scene, stopping at the first fresh, relevant result:
  1. videos for the scene's own searches
  2. photos for the scene's own searches (shown with a slow zoom)
  3. videos, then photos, for the video's subject keywords (e.g. "pineapple")
  4. reuse an earlier clip from this video
Pixabay results must carry at least one of the searched words in their tags, so a search
never silently returns unrelated footage.
"""
import os
import random
import re
import time
from pathlib import Path

import requests

STOP = {"the", "and", "with", "for", "close", "closeup", "up", "of", "on", "in", "a", "an", "shot", "view"}
_cache: dict = {}


def _words(q: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", q.lower()) if len(w) >= 3 and w not in STOP}


def _relevant(query: str, tags: str) -> bool:
    words = _words(query)
    if not words:
        return True
    tags = tags.lower()
    # "tomatoes" should match tag "tomato" and vice versa
    return any(w in tags or w.rstrip("s") in tags for w in words)


def _get(url: str, params: dict, headers: dict | None = None) -> dict:
    for attempt in range(3):
        r = requests.get(url, params=params, headers=headers or {}, timeout=30)
        if r.status_code == 429:
            time.sleep(30)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}


# ─── providers: each returns candidates ────────────────────────────────────
# {"id", "url", "width", "height", "duration", "author", "source", "kind": "video"|"photo"}

def _pixabay_videos(query: str, key: str) -> list[dict]:
    data = _get("https://pixabay.com/api/videos/",
                {"key": key, "q": query[:100], "per_page": 50, "safesearch": "true"})
    out = []
    for hit in data.get("hits", []):
        if not _relevant(query, hit.get("tags", "")):
            continue
        sizes = [s for s in (hit.get("videos") or {}).values()
                 if s.get("url") and s.get("width") and s.get("height")]
        usable = [s for s in sizes if min(s["width"], s["height"]) >= 720 and max(s["width"], s["height"]) <= 2600]
        if not usable:
            continue
        best = max(usable, key=lambda s: s["width"] * s["height"])
        out.append({"id": f"pixabay:{hit['id']}", "url": best["url"], "width": best["width"],
                    "height": best["height"], "duration": hit.get("duration", 0),
                    "author": hit.get("user", ""), "source": "Pixabay", "kind": "video"})
    return out


def _pixabay_photos(query: str, key: str) -> list[dict]:
    data = _get("https://pixabay.com/api/",
                {"key": key, "q": query[:100], "image_type": "photo", "per_page": 50,
                 "safesearch": "true", "min_height": 1000})
    out = []
    for hit in data.get("hits", []):
        if not _relevant(query, hit.get("tags", "")) or not hit.get("largeImageURL"):
            continue
        out.append({"id": f"pixabay-img:{hit['id']}", "url": hit["largeImageURL"],
                    "width": hit.get("imageWidth", 0), "height": hit.get("imageHeight", 0),
                    "duration": 999, "author": hit.get("user", ""), "source": "Pixabay", "kind": "photo"})
    return out


def _pexels_videos(query: str, key: str) -> list[dict]:
    data = _get("https://api.pexels.com/videos/search",
                {"query": query, "orientation": "portrait", "size": "medium", "per_page": 20},
                {"Authorization": key})
    out = []
    for v in data.get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("width") and f.get("height") and f.get("file_type") == "video/mp4"
                 and min(f["width"], f["height"]) >= 720 and max(f["width"], f["height"]) <= 2600]
        if not files:
            continue
        best = max(files, key=lambda f: f["width"] * f["height"])
        out.append({"id": f"pexels:{v['id']}", "url": best["link"], "width": best["width"],
                    "height": best["height"], "duration": v.get("duration", 0),
                    "author": (v.get("user") or {}).get("name", ""), "source": "Pexels", "kind": "video"})
    return out


def _search(query: str, kind: str, log) -> list[dict]:
    """All candidates of one kind for a query, across configured providers (cached)."""
    ck = (query.lower(), kind)
    if ck in _cache:
        return _cache[ck]
    pix, pex = os.environ.get("PIXABAY_API_KEY"), os.environ.get("PEXELS_API_KEY")
    if not pix and not pex:
        raise RuntimeError("Set PIXABAY_API_KEY (or PEXELS_API_KEY) for stock footage")
    jobs = []
    if kind == "video":
        if pix:
            jobs.append((_pixabay_videos, pix))
        if pex:
            jobs.append((_pexels_videos, pex))
    elif pix:
        jobs.append((_pixabay_photos, pix))
    results = []
    for fn, key in jobs:
        try:
            results += fn(query, key)
        except requests.RequestException as e:
            log(f"{fn.__name__.strip('_')} search failed for '{query}': {e}")
    _cache[ck] = results
    return results


def _download(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def _rank(cands: list[dict], need: float) -> list[dict]:
    # keep relevance order, but prefer vertical media and clips long enough not to loop
    return sorted(cands, key=lambda c: (c["height"] < c["width"], c["duration"] < need))


def fetch_clips(scenes: list[dict], durations: list[float], used_ids: set, workdir: Path,
                subject: list[str] | None = None, log=print) -> tuple[list[Path], str]:
    """Pick one fresh, relevant clip (or photo) per scene.

    Returns (media paths, credit line). Adds the chosen ids to used_ids.
    """
    from .content import scene_queries  # local import avoids a cycle

    subject = [s for s in (subject or []) if isinstance(s, str) and s.strip()]
    clips, picked, credits = [], [], {}
    for i, (scene, need) in enumerate(zip(scenes, durations)):
        own = scene_queries(scene)
        plan = ([(q, "video") for q in own] + [(q, "photo") for q in own]
                + [(q, "video") for q in subject] + [(q, "photo") for q in subject])
        path = None
        for q, kind in plan:
            fresh = [c for c in _search(q, kind, log) if c["id"] not in used_ids and c["id"] not in picked]
            for c in _rank(fresh, need)[:5]:
                ext = ".jpg" if c["kind"] == "photo" else ".mp4"
                dest = workdir / f"clip_{i:02d}{ext}"
                try:
                    _download(c["url"], dest)
                except requests.RequestException as e:
                    log(f"Download failed ({c['id']}): {e}")
                    continue
                path = dest
                picked.append(c["id"])
                if c["author"]:
                    names = credits.setdefault(c["source"], [])
                    if c["author"] not in names:
                        names.append(c["author"])
                log(f"Scene {i + 1}: {kind} '{q}' → {c['id']} ({c['width']}x{c['height']})")
                break
            if path:
                break
        if not path:
            if not clips:
                raise RuntimeError(f"No footage found for scene 1 (searched: {', '.join(own + subject)})")
            path = random.choice(clips)
            log(f"Scene {i + 1}: nothing relevant found for {own}, reusing an earlier clip")
        clips.append(path)
    used_ids.update(picked)
    credit_line = "; ".join(f"{src} — {', '.join(names[:6])}" for src, names in credits.items())
    return clips, credit_line
