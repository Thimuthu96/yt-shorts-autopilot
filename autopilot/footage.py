"""Stock footage for each scene.

Sources (free, no attribution required):
  - Pixabay  → set PIXABAY_API_KEY  (default; https://pixabay.com/api/docs/)
  - Pexels   → set PEXELS_API_KEY   (optional extra source if you already have a key)
If both keys are set, Pixabay is searched first and Pexels is used as a fallback.
"""
import os
import random
from pathlib import Path

import requests


# ─── providers: each returns a list of candidates ──────────────────────────
# candidate = {"id": "source:123", "url": ..., "width": int, "height": int,
#              "duration": float, "author": str, "source": "Pixabay"}

def _pixabay(query: str, key: str) -> list[dict]:
    r = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": key, "q": query[:100], "per_page": 30, "safesearch": "true",
                "video_type": "film"},
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for hit in r.json().get("hits", []):
        sizes = [s for s in (hit.get("videos") or {}).values()
                 if s.get("url") and s.get("width") and s.get("height")]
        # big enough for 1080x1920 after cropping, but skip 4K files that slow rendering
        usable = [s for s in sizes if min(s["width"], s["height"]) >= 720 and max(s["width"], s["height"]) <= 2600]
        if not usable:
            continue
        best = max(usable, key=lambda s: s["width"] * s["height"])
        out.append({"id": f"pixabay:{hit['id']}", "url": best["url"], "width": best["width"],
                    "height": best["height"], "duration": hit.get("duration", 0),
                    "author": hit.get("user", ""), "source": "Pixabay"})
    return out


def _pexels(query: str, key: str) -> list[dict]:
    r = requests.get(
        "https://api.pexels.com/videos/search",
        params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 20},
        headers={"Authorization": key},
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("width") and f.get("height") and f.get("file_type") == "video/mp4"
                 and min(f["width"], f["height"]) >= 720 and max(f["width"], f["height"]) <= 2600]
        if not files:
            continue
        best = max(files, key=lambda f: f["width"] * f["height"])
        out.append({"id": f"pexels:{v['id']}", "url": best["link"], "width": best["width"],
                    "height": best["height"], "duration": v.get("duration", 0),
                    "author": (v.get("user") or {}).get("name", ""), "source": "Pexels"})
    return out


def _providers() -> list:
    provs = []
    if os.environ.get("PIXABAY_API_KEY"):
        provs.append((_pixabay, os.environ["PIXABAY_API_KEY"]))
    if os.environ.get("PEXELS_API_KEY"):
        provs.append((_pexels, os.environ["PEXELS_API_KEY"]))
    if not provs:
        raise RuntimeError("Set PIXABAY_API_KEY (or PEXELS_API_KEY) for stock footage")
    return provs


def _download(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def _rank(cands: list[dict], need: float) -> list[dict]:
    # keep the API's relevance order, but prefer vertical clips that are long enough
    def score(c):
        return (c["height"] < c["width"], c["duration"] < need)
    return sorted(cands, key=score)


def fetch_clips(scenes: list[dict], durations: list[float], used_ids: set, workdir: Path,
                fallback_query: str = "nature close up", log=print) -> tuple[list[Path], str]:
    """Pick one fresh clip per scene.

    Returns (clip paths, credit line for the description). Adds the chosen clip ids to used_ids.
    """
    providers = _providers()
    clips, picked, credits = [], [], {}
    for i, (scene, need) in enumerate(zip(scenes, durations)):
        path = None
        queries = [q for q in (scene.get("visual"), scene.get("visual_alt"), fallback_query) if q]
        for q in queries:
            for search, key in providers:
                try:
                    cands = search(q, key)
                except requests.RequestException as e:
                    log(f"{search.__name__.strip('_')} search failed for '{q}': {e}")
                    continue
                fresh = [c for c in cands if c["id"] not in used_ids and c["id"] not in picked]
                for c in _rank(fresh, need)[:6]:
                    dest = workdir / f"clip_{i:02d}.mp4"
                    try:
                        _download(c["url"], dest)
                    except requests.RequestException as e:
                        log(f"Download failed ({c['id']}): {e}")
                        continue
                    path = dest
                    picked.append(c["id"])
                    if c["author"]:
                        credits.setdefault(c["source"], [])
                        if c["author"] not in credits[c["source"]]:
                            credits[c["source"]].append(c["author"])
                    log(f"Scene {i + 1}: '{q}' → {c['id']} ({c['width']}x{c['height']})")
                    break
                if path:
                    break
            if path:
                break
        if not path:
            if not clips:
                raise RuntimeError(f"No footage found for scene {i + 1}")
            path = random.choice(clips)  # reuse an earlier clip rather than fail
            log(f"Scene {i + 1}: no fresh footage, reusing an earlier clip")
        clips.append(path)
    used_ids.update(picked)
    credit_line = "; ".join(f"{src} — {', '.join(names[:6])}" for src, names in credits.items())
    return clips, credit_line
