"""YouTube Shorts autopilot: topic → script → fact-check → voice → footage → render → upload.

    python main.py                      # full run (what GitHub Actions does)
    python main.py --no-upload          # make the video only, saved in output/
    python main.py --topic "Why do cats purr?" --no-upload
"""
import argparse
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from autopilot import content, footage, render, voice
from autopilot.history import History

ROOT = Path(__file__).parent


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def faster_rate(rate: str, factor: float) -> str:
    pct = int(re.sub(r"[^\d-]", "", rate) or 0)
    new = int(round(((1 + pct / 100) * factor - 1) * 100)) + 2
    return f"{'+' if new >= 0 else ''}{min(new, 35)}%"


def make_one(cfg: dict, history: History, args) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    workdir = ROOT / "output" / stamp
    workdir.mkdir(parents=True, exist_ok=True)

    pkg = content.make_package(cfg, history.topics(), forced_topic=args.topic, log=log)
    (workdir / "package.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False))
    log(f"Title: {pkg['title']}")

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

    used = history.used_footage()
    before = set(used)
    clips, credits = footage.fetch_clips(scenes, [a["duration"] for a in audio], used, workdir,
                                         subject=pkg.get("subject_keywords"), log=log)

    music_files = sorted((ROOT / "music").glob("*.mp3"))
    music = random.choice(music_files) if music_files else None
    out = workdir / "short.mp4"
    render.build_video(audio, clips, cfg, workdir, out, music=music)
    log(f"Rendered {out.relative_to(ROOT)}")

    from autopilot import youtube  # imported late so --no-upload needs no Google libs configured
    meta = youtube.build_metadata(pkg, credits)
    (workdir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    video_id = None
    if cfg["upload"]["enabled"] and not args.no_upload:
        video_id = youtube.upload(out, meta, cfg, log=log)

    return {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "topic": pkg["topic"],
        "title": meta["title"],
        "video_id": video_id,
        "seconds": round(total, 1),
        "footage_ids": sorted(used - before),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-upload", action="store_true", help="render only")
    p.add_argument("--topic", help="force a topic instead of letting the AI pick")
    p.add_argument("--count", type=int, help="videos to make this run")
    args = p.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    history = History(ROOT / "data" / "history.json")
    count = args.count or cfg["upload"].get("videos_per_run", 1)

    failures = 0
    for i in range(count):
        try:
            entry = make_one(cfg, history, args)
            # local test renders (--no-upload) don't use up topics or footage
            if entry["video_id"] or not cfg["upload"]["enabled"]:
                history.add(entry)
                history.save()
            args.topic = None
        except Exception as e:  # keep going with the next video, fail the run at the end
            failures += 1
            log(f"Video {i + 1} failed: {e}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
