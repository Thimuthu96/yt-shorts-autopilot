"""Crypto & forex market brief Shorts, up to 3 editions a day (Asia / London / New York open):
market data + news → grounded script → fact-check → voice → data graphics → render → upload.

    python main.py --session london   # one edition (what GitHub Actions does)
    python main.py                    # edition picked from the current UTC time
    python main.py --no-upload        # make the video only, saved in output/
    python main.py --force            # make it even if this edition is already up today
"""
import argparse
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
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


def auto_session(now: datetime) -> str:
    if now.hour < 5:
        return "asia"
    if now.hour < 12:
        return "london"
    return "newyork"


def news_since_last_brief(data: dict, history: History) -> None:
    """Keep only news newer than the previous brief, so each edition says something new."""
    last = history.last_upload_time()
    if not last or datetime.now(timezone.utc) - last > timedelta(hours=24):
        return
    cutoff = (last - timedelta(hours=1)).isoformat()
    fresh = [n for n in data["news"] if n.get("published") and n["published"] >= cutoff]
    if len(fresh) >= 6:  # too few fresh stories: keep the wider window rather than an empty brief
        data["news"] = fresh
        data["news_since"] = last.strftime("%H:%M UTC")


def make_brief(cfg: dict, history: History, args, session_key: str) -> dict:
    session = cfg.get("sessions", {}).get(session_key, {})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    workdir = ROOT / "output" / stamp
    workdir.mkdir(parents=True, exist_ok=True)

    log("Collecting market data and news...")
    data = sources.gather(cfg, log=log)
    news_since_last_brief(data, history)
    (workdir / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str))

    cover = thumbnail.choose(data)
    log(f"Thumbnail: {cover['template']} ({cover['facts']})")
    pkg = script.make_script(cfg, data, history.used_headlines(), cover, session, log=log)
    cover["hook"] = thumbnail.clean_hook(pkg.get("thumbnail_hook"), cover["default_hook"])
    pkg["thumbnail"] = {k: v for k, v in cover.items() if k != "series"}
    (workdir / "package.json").write_text(json.dumps(pkg, indent=2, ensure_ascii=False))
    log(f"Title: {pkg['title']} · hook: {cover['hook']}")
    thumb = thumbnail.render(cover, cfg, data["date_utc"], workdir / "thumbnail.jpg", session.get("short", ""))

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
    pics = slides.render_slides(cfg, data, scenes, workdir, cover=thumb, edition=session.get("label", ""))

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
        "session": session_key,
        "title": meta["title"],
        "video_id": video_id,
        "seconds": round(total, 1),
        "headlines": pkg.get("headlines_used", [])[:10],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-upload", action="store_true", help="render only")
    p.add_argument("--force", action="store_true", help="run even if this edition is already uploaded today")
    p.add_argument("--session", default="auto", help="asia | london | newyork | auto (from the UTC time)")
    p.add_argument("--scheduled", action="store_true", help="set by the daily schedule (applies the weekend rule)")
    args = p.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    history = History(ROOT / "data" / "history.json")

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    session_key = (args.session or "auto").strip().lower()
    if session_key in ("", "auto"):
        session_key = auto_session(now)
    if session_key not in cfg.get("sessions", {}):
        log(f"Unknown edition '{session_key}'. Choose one of: {', '.join(cfg.get('sessions', {}))}")
        return 1
    label = cfg["sessions"][session_key]["label"]

    if args.scheduled and now.weekday() >= 5 and session_key not in cfg.get("weekend_sessions", []):
        log(f"Weekend: forex is closed, so the {label} edition is skipped today.")
        return 0
    if not args.force and not args.no_upload and history.uploaded_on(today, session_key):
        log(f"The {label} brief for {today} is already uploaded; nothing to do. Tick 'force' to make another.")
        return 0

    log(f"Edition: {label}")
    try:
        entry = make_brief(cfg, history, args, session_key)
    except Exception as e:
        log(f"Brief failed: {e}")
        return 1
    if entry["video_id"]:
        history.add(entry)
        history.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
