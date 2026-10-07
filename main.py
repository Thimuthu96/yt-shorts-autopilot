"""Daily crypto & forex market brief Short:
market data + news → grounded script → fact-check → voice → data graphics → render → upload.

    python main.py                 # full run (what GitHub Actions does)
    python main.py --no-upload     # make the video only, saved in output/
    python main.py --force         # make another one even if today's brief is already up
"""
import argparse
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from autopilot import render, script, slides, sources, thumbnail, voice
from autopilot.history import History

ROOT = Path(__file__).parent


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def faster_rate(rate: str, factor: float) -> str:
    pct = int(re.sub(r"[^\d-]", "", rate) or 0)
    new = int(round(((1 + pct / 100) * factor - 1) * 100)) + 2
    return f"{'+' if new >= 0 else ''}{min(new, 35)}%"


def make_brief(cfg: dict, history: History, args) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    workdir = ROOT / "output" / stamp
    workdir.mkdir(parents=True, exist_ok=True)

    log("Collecting market data and news...")
    data = sources.gather(cfg, log=log)
    (workdir / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str))

    cover = thumbnail.choose(data)
    log(f"Thumbnail: {cover['template']} ({cover['facts']})")
    pkg = script.make_script(cfg, data, history.used_headlines(), cover, log=log)
    cover["hook"] = thumbnail.clean_hook(pkg.get("thumbnail_hook"), cover["default_hook"])
    pkg["thumbnail"] = {k: v for k, v in cover.items() if k != "series"}
    (workdir / "package.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False))
    log(f"Title: {pkg['title']} · hook: {cover['hook']}")
    thumb = thumbnail.render(cover, cfg, data["date_utc"], workdir / "thumbnail.jpg")

    v = cfg["voice"]
    scenes = pkg["scenes"]
    audio = voice.synthesize(scenes, v["name"], v["rate"], workdir, log=log)
    total = sum(a["duration"] for a in audio)
    limit = cfg["video"]["max_seconds"]
    if total > limit:
        rate = faster_rate(v["rate"], total / limit)
        log(f"Narration {total:.1f}s is over {limit}s, re-recording at {rate}")
        audio = voice.synthesize(scenes, v["name"], rate, workdir, log=log)
        total = sum(a["duration"] for a in audio)
    log(f"Narration: {total:.1f}s")

    log("Drawing the graphics...")
    pics = slides.render_slides(cfg, data, scenes, workdir, cover=thumb)

    music_files = sorted((ROOT / "music").glob("*.mp3"))
    music = random.choice(music_files) if music_files else None
    out = workdir / "short.mp4"
    render.build_video(audio, pics, cfg, workdir, out, music=music)
    log(f"Rendered {out.relative_to(ROOT)}")

    from autopilot import youtube  # imported late so --no-upload needs no Google libs configured
    meta = youtube.build_metadata(pkg, data, cfg)
    (workdir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    video_id = None
    if cfg["upload"]["enabled"] and not args.no_upload:
        video_id = youtube.upload(out, meta, cfg, log=log)
        if cfg["upload"].get("set_thumbnail", True):
            youtube.set_thumbnail(video_id, thumb, log=log)

    return {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "brief_date": data["date_utc"],
        "title": meta["title"],
        "video_id": video_id,
        "seconds": round(total, 1),
        "headlines": pkg.get("headlines_used", [])[:10],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-upload", action="store_true", help="render only")
    p.add_argument("--force", action="store_true", help="run even if today's brief is already uploaded")
    args = p.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    history = History(ROOT / "data" / "history.json")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not args.force and not args.no_upload and history.uploaded_on(today):
        log(f"Today's brief ({today}) is already uploaded; nothing to do. Use --force to make another.")
        return 0

    try:
        entry = make_brief(cfg, history, args)
    except Exception as e:
        log(f"Brief failed: {e}")
        return 1
    if entry["video_id"]:
        history.add(entry)
        history.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
