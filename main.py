"""Crypto & forex market brief Shorts (Asia / London / New York open) plus a daily gold outlook:
market data + news → lead story + research → grounded script → fact-check → voice → data
graphics → render → upload.

    python main.py --session london   # one video, made and uploaded now (a manual run)
    python main.py --session gold     # the daily gold (XAU/USD) outlook
    python main.py                    # market edition picked from the current UTC time
    python main.py --no-upload        # make the video only, saved in output/
    python main.py --session asia --scheduled   # timed run: weekend rule, late/early skip, once a day
    python main.py --session asia --as-edition  # manual run that fills today's slot (timed run skips)

Manual runs always make and upload a video and don't stop the timed run of that edition.
"""
import argparse
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from autopilot import focus, gold, render, script, slides, sources, thumbnail, voice
from autopilot.history import History

ROOT = Path(__file__).parent

# Used when config.yaml has no "sessions" section (e.g. an older config.yaml).
DEFAULT_SESSIONS = {
    "asia": {"label": "Asia Open", "short": "Asia", "start_utc": "00:30",
             "focus": "Cover what moved since the New York close, crypto overnight, the yen and the "
                      "Australian dollar, and events coming up in the Asian and European sessions."},
    "london": {"label": "London Open", "short": "London", "start_utc": "05:40",
               "focus": "Cover what happened in the Asian session, the euro and the pound, and the "
                        "day's biggest scheduled events."},
    "newyork": {"label": "New York Open", "short": "New York", "start_utc": "12:30",
                "focus": "Cover moves since the London open, the US dollar, Bitcoin and Ethereum, and "
                         "what is still ahead on today's calendar."},
    "gold": {"label": "Gold Outlook", "short": "Gold", "start_utc": "06:15", "kind": "gold"},
}


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


def minutes_late(now: datetime, start_utc: str) -> int:
    """Minutes since today's start time; negative if a bit early (within 12 h either way)."""
    h, m = (int(x) for x in str(start_utc).split(":"))
    diff = (now.hour * 60 + now.minute - (h * 60 + m)) % (24 * 60)
    return diff - 24 * 60 if diff > 12 * 60 else diff


def news_since_last_brief(data: dict, history: History) -> None:
    """Keep only news newer than the previous brief, so each edition says something new."""
    last = history.last_upload_time("market")
    if not last or datetime.now(timezone.utc) - last > timedelta(hours=24):
        return
    cutoff = (last - timedelta(hours=1)).isoformat()
    fresh = [n for n in data["news"] if n.get("published") and n["published"] >= cutoff]
    if len(fresh) >= 6:  # too few fresh stories: keep the wider window rather than an empty brief
        data["news"] = fresh
        data["news_since"] = last.strftime("%H:%M UTC")


def make_brief(cfg: dict, history: History, args, session_key: str) -> dict:
    session = cfg.get("sessions", {}).get(session_key, {})
    kind = session.get("kind", "market")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    workdir = ROOT / "output" / stamp
    workdir.mkdir(parents=True, exist_ok=True)

    log("Collecting market data and news...")
    data = sources.gather(cfg, kind, log=log)
    extra = {}
    if kind == "gold":
        prev = (history.last("gold") or {}).get("outlook")
        data["gold_analysis"] = gold.analyze(data, prev)
        a = data["gold_analysis"]
        log(f"Gold {a['price']:,.1f}: bias 1H {a['bias']['1H']['bias']}, 4H {a['bias']['4H']['bias']}, "
            f"daily {a['bias']['Daily']['bias']}" + (f"; last call {'played out' if a['review']['played_out'] else 'missed'}"
                                                     if a.get("review") else ""))
        extra["outlook"] = gold.record(a)
        cover = thumbnail.choose_gold(data)
    else:
        news_since_last_brief(data, history)
        f = focus.pick(data, (history.last("market") or {}).get("lead"), history.used_headlines())
        if f:
            log(f"Lead: {f['label']} ({', '.join(f['why'])}) · assets {f['assets']} · story: "
                f"{(f.get('story') or {}).get('title', '(price move)')}")
            extra["lead"] = f["lead"]
        cover = thumbnail.choose(data)
    (workdir / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str))

    log(f"Thumbnail: {cover['template']} ({cover['facts']})")
    if kind == "gold":
        pkg = script.make_gold_script(cfg, data, history.used_headlines(), cover, log=log)
    else:
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
    footer = (cfg.get("gold") or {}).get("footer") if kind == "gold" else None
    pics = slides.render_slides(cfg, data, scenes, workdir, cover=thumb, edition=session.get("label", ""),
                                footer=footer)

    music_files = sorted((ROOT / "music").glob("*.mp3"))
    music = random.choice(music_files) if music_files else None
    out = workdir / "short.mp4"
    render.build_video(audio, pics, cfg, workdir, out, music=music)
    log(f"Rendered {out.relative_to(ROOT)}")

    from autopilot import youtube  # imported late so --no-upload needs no Google libs configured
    meta = youtube.build_metadata(pkg, data, cfg, session.get("label", ""))
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
        "kind": kind,
        "title": meta["title"],
        "video_id": video_id,
        "seconds": round(total, 1),
        "headlines": pkg.get("headlines_used", [])[:10],
        **extra,
        "workdir": str(workdir.relative_to(ROOT)),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-upload", action="store_true", help="render only")
    p.add_argument("--force", action="store_true", help="timed run: make it even if this edition is already up today")
    p.add_argument("--session", default="auto", help="asia | london | newyork | gold | auto (market edition by UTC time)")
    p.add_argument("--scheduled", action="store_true",
                   help="timed run (schedule / outside timer): weekend rule, late/early skip, once per edition per day")
    p.add_argument("--as-edition", action="store_true",
                   help="manual run that counts as today's edition, so its timed run then skips")
    args = p.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    if not cfg.get("sessions"):
        log("config.yaml has no 'sessions' section; using the built-in Asia/London/New York editions")
        cfg["sessions"] = DEFAULT_SESSIONS
    cfg.setdefault("weekend_sessions", ["london"])
    cfg.setdefault("max_late_minutes", 180)
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
    start = cfg["sessions"][session_key].get("start_utc") or DEFAULT_SESSIONS.get(session_key, {}).get("start_utc")

    if args.scheduled and now.weekday() >= 5 and session_key not in cfg.get("weekend_sessions", []):
        log(f"Weekend: forex is closed, so the {label} edition is skipped today.")
        return 0
    if args.scheduled and start:
        late = minutes_late(now, start)
        log(f"Timed run for the {label} edition (due {start} UTC, started {late:+d} min)")
        if late > cfg["max_late_minutes"]:
            log(f"Started more than {cfg['max_late_minutes']} min late, so the {label} edition is skipped "
                "(it would clash with the next edition). Use Run workflow to make it anyway.")
            return 0
        if late < -30:
            log(f"Started {-late} min before {start} UTC, so the {label} edition is skipped. "
                "Check the timer's time and time zone.")
            return 0
    if args.scheduled and not args.force and not args.no_upload and history.uploaded_on(today, session_key):
        log(f"The {label} brief for {today} is already uploaded; nothing to do.")
        return 0
    if not args.scheduled:
        log("Manual run: makes and uploads a video now" +
            (" and fills today's slot (the timed run will skip)." if args.as_edition
             else "; the timed run of this edition still goes ahead."))

    log(f"Edition: {label}")
    try:
        entry = make_brief(cfg, history, args, session_key)
    except Exception as e:
        log(f"Brief failed: {e}")
        return 1
    if entry["video_id"]:
        entry["trigger"] = "timed" if args.scheduled else "manual"
        entry["counts"] = bool(args.scheduled or args.as_edition)
        workdir = ROOT / entry.pop("workdir")
        # the workflow merges this file into the latest data/history.json (safe with parallel runs)
        (workdir / "history_entry.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False))
        history.add(entry)
        history.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
