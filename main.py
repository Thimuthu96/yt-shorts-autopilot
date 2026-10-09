"""Crypto & forex market brief Shorts (Asia / London / New York open) plus a daily gold outlook:
market data + news → lead story + research → grounded script → fact-check → voice → data
graphics → render → publish (YouTube Short + Facebook Reel, one render).
Plus Facebook-only news image posts (kind: post): story → headline + caption → card → Page photo.

    python main.py --session london   # one video, made and published now (a manual run)
    python main.py --session gold     # the daily gold (XAU/USD) outlook
    python main.py --session news_morning   # a Facebook news image post
    python main.py                    # market edition picked from the current UTC time
    python main.py --no-upload        # make it only, saved in output/
    python main.py --session asia --platforms facebook   # publish to Facebook only
    python main.py --session asia --scheduled   # timed run: weekend rule, late/early skip, once a day per platform
    python main.py --session asia --as-edition  # manual run that fills today's slot (timed run skips)
    python main.py --lesson-sample --no-upload  # sample trading lesson (16:9 + 9:16) on fixture candles

Manual runs always make and publish and don't stop the timed run of that edition.
"""
import argparse
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from autopilot import (facebook, focus, gold, images, lesson_meta, lesson_script, lesson_slides, lessons, news_post,
                       render, script, slides, sources, thumbnail, voice)
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
    "news_morning": {"label": "Morning News", "short": "News", "start_utc": "03:00", "kind": "post",
                     "platforms": ["facebook"]},
    "news_midday": {"label": "Midday News", "short": "News", "start_utc": "09:30", "kind": "post",
                    "platforms": ["facebook"]},
    "news_evening": {"label": "Evening News", "short": "News", "start_utc": "16:30", "kind": "post",
                     "platforms": ["facebook"]},
}
PLATFORMS = ("youtube", "facebook")
LESSON_MAX_SECONDS = 300  # lessons' own limit (cfg lessons.max_seconds); the Shorts keep video.max_seconds
# caption overrides per lesson shape: 16:9 smaller text; 9:16 keeps the Shorts' 84 px but 2 words a line,
# so a wrapped caption is at most 2 lines (libass never breaks inside a word) and fits the caption band
LESSON_CAPTIONS = {"16x9": {"size": 56, "outline": 5}, "9x16": {"words_per_line": 2}}
LESSON_CAPTION_PAD = 2  # px above the bottom of the caption band (outline, shadow and descender space come on top)
LESSON_PUSH_IN = 0.012  # push-in growth per scene: small enough that the slide footers stay in frame


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
        prev = (history.last("gold") or {}).get("outlook")  # a re-make gets history without today's slot
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
    fb_caption = facebook.reel_caption(meta, pkg, data, cfg)
    (workdir / "caption_fb.txt").write_text(fb_caption, encoding="utf-8")

    entry = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "brief_date": data["date_utc"],
        "session": session_key,
        "kind": kind,
        "title": meta["title"],
        "video_id": None,
        "seconds": round(total, 1),
        "headlines": pkg.get("headlines_used", [])[:10],
        **extra,
        "workdir": str(workdir.relative_to(ROOT)),
    }
    return {"entry": entry, "video": out, "thumbnail": thumb, "meta": meta, "fb_caption": fb_caption}


def lesson_video_cfg(cfg: dict, layout) -> dict:
    """A cfg copy for render.build_video in one lesson shape: the layout's size, captions sized for it and
    anchored at the bottom of the layout's caption band (slides never draw there; a wrapped caption grows
    upwards inside the band), and a push-in small enough to keep the slide footer in frame."""
    cap = {**cfg["video"]["captions"], **LESSON_CAPTIONS.get(layout.name, {})}
    cap["margin_v"] = layout.h - layout.caption_band[1] + int(cap.get("outline", 0)) + 3 + LESSON_CAPTION_PAD  # 3 = shadow
    return {**cfg, "video": {**cfg["video"], "width": layout.w, "height": layout.h, "captions": cap,
                             "push_in": LESSON_PUSH_IN}}


def make_lesson(cfg: dict, entry: dict, glossary: dict, history: dict, workdir: Path | None = None,
                next_entry: dict | None = None, log=log) -> dict:
    """One curriculum entry → a 16:9 and a 9:16 lesson video from the same narration, the lesson
    thumbnail, chapters and metadata (written to the workdir; nothing is uploaded).
    `history` is lesson_data.fetch_history's {asset: {timeframe: candles}}.
    Returns {"held": reason} when the detector finds no clean example (nothing is rendered), else
    {"videos": {"16x9", "9x16"}, "thumbnail", "meta", "chapters", "seconds", "examples", "workdir"}."""
    det = lessons.DETECTORS.get(entry.get("detector"))
    examples = det.find(history) if det else []
    if not examples:
        reason = (f"{entry['id']}: no clean {entry.get('detector')} example in the price history" if det
                  else f"{entry['id']}: detector '{entry.get('detector')}' is not registered")
        log(f"Lesson held: {reason}")
        return {"held": reason}
    log(f"Lesson {entry['id']}: {len(examples)} example(s): "
        + ", ".join(f"{e['asset']} {e['timeframe']} {e['date']}" for e in examples))
    if workdir is None:
        workdir = ROOT / "output" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    plan = lessons.scene_plan(entry, examples, next_entry)
    pkg = lesson_script.make_lesson_script(cfg, entry, glossary, plan, examples, log=log)
    narration = [{"id": s["id"], "text": s["text"]} for s in pkg["scenes"]]  # visuals carry the candles
    (workdir / "package.json").write_text(json.dumps(
        {"entry": entry["id"], "title": entry["title"], "scenes": narration, "fact_check": pkg.get("fact_check"),
         "examples": examples}, indent=2, ensure_ascii=False, default=str))

    v = cfg["voice"]
    scenes = pkg["scenes"]
    audio = voice.synthesize(scenes, v["name"], v["rate"], workdir, log=log)
    total = sum(a["duration"] for a in audio)
    limit = (cfg.get("lessons") or {}).get("max_seconds", LESSON_MAX_SECONDS)
    if total > limit:
        rate = faster_rate(v["rate"], total / limit)
        log(f"Lesson narration {total:.1f}s is over {limit}s, re-recording at {rate}")
        audio = voice.synthesize(scenes, v["name"], rate, workdir, log=log)
        total = sum(a["duration"] for a in audio)
    log(f"Lesson narration: {total:.1f}s")

    chapters = lesson_meta.chapters(plan, audio, examples, glossary)
    log("Chapters: " + ", ".join(f"{c['time']} {c['title']}" for c in chapters))
    thumb = lesson_slides.render_lesson_thumbnail(cfg, entry, examples[0], workdir / "thumbnail.jpg")

    music_files = sorted((ROOT / "music").glob("*.mp3"))
    music = random.choice(music_files) if music_files else None  # same music in both shapes
    videos = {}
    for layout in (lesson_slides.LANDSCAPE, lesson_slides.PORTRAIT):
        log(f"Drawing and rendering the {layout.name} lesson...")
        shape_dir = workdir / layout.name  # each render keeps its own segments / captions
        pics = lesson_slides.render_lesson_slides(cfg, entry, plan, glossary, layout, shape_dir)
        out = workdir / f"lesson_{layout.name}.mp4"
        render.build_video(audio, pics, lesson_video_cfg(cfg, layout), shape_dir, out, music=music)
        videos[layout.name] = out
        log(f"Rendered {out}")

    meta = lesson_meta.build_lesson_metadata(entry, pkg, examples, chapters, cfg, log=log)
    (workdir / "metadata.json").write_text(json.dumps({**meta, "chapters": chapters}, indent=2, ensure_ascii=False))
    log(f"Lesson title: {meta['title']}")
    return {"videos": videos, "thumbnail": thumb, "meta": meta, "chapters": chapters, "seconds": round(total, 1),
            "examples": examples, "workdir": workdir}


def lesson_sample(cfg: dict) -> int:
    """The tests/lessons sample entry on fixture candles, made only (lessons aren't published yet)."""
    entry, glossary, history, nxt = lesson_script.sample_inputs()
    try:
        made = make_lesson(cfg, entry, glossary, history, next_entry=nxt)
    except Exception as e:
        log(f"Lesson failed: {e}")
        return 1
    if made.get("held"):
        return 1
    log(f"Made lesson {entry['id']} ({made['seconds']}s): " + ", ".join(str(p) for p in made["videos"].values()))
    return 0


def publish(made: dict, platforms: list[str], cfg: dict) -> tuple[dict, list[str]]:
    """Publish one rendered edition to each platform on its own: a failure on one is logged and
    never blocks (or repeats) the other. Returns (entry with the ids it got, failed platforms)."""
    entry, failed = made["entry"], []
    if "youtube" in platforms:
        try:
            from autopilot import youtube
            entry["video_id"] = youtube.upload(made["video"], made["meta"], cfg, log=log)
            if cfg["upload"].get("set_thumbnail", True):
                youtube.set_thumbnail(entry["video_id"], made["thumbnail"], log=log)
        except Exception as e:
            log(f"YouTube upload failed: {e}")
            failed.append("youtube")
    if "facebook" in platforms:
        try:
            entry["fb_reel_id"] = facebook.publish_reel(made["video"], made["fb_caption"], cfg,
                                                        cover=made["thumbnail"], log=log)
        except Exception as e:
            log(f"Facebook Reel failed: {e}")
            failed.append("facebook")
    return entry, failed


def make_post(cfg: dict, history: History, args, session_key: str, platforms: list[str]) -> tuple[dict, list[str]]:
    """Facebook news image post: one story → headline + caption → background → card → /photos."""
    session = cfg.get("sessions", {}).get(session_key, {})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    workdir = ROOT / "output" / stamp
    workdir.mkdir(parents=True, exist_ok=True)

    log("Collecting news (48 h) and market data...")
    data = sources.gather(cfg, "post", log=log)
    last = history.last("post") or {}
    story = news_post.pick_story(data, history.fb_post_headlines(), history.used_headlines(), cfg,
                                 last_topic=last.get("topic"), log=log)
    post = news_post.write_post(cfg, data, story, log=log)
    log(f"Card: [{post['kicker']}] {' / '.join(post['headline'])} ({post['writer']})")
    bg, bg_source = images.background(post["image_prompt"], story["topic"], cfg, log=log)
    card = images.render_card(post, bg, cfg, data["date_utc"], workdir / "post.jpg", ai=bg_source == "ai",
                              source=story["source"])
    text = news_post.caption(post, story, data, cfg, ai_image=bg_source == "ai")
    (workdir / "caption_fb.txt").write_text(text, encoding="utf-8")
    (workdir / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str))
    (workdir / "post.json").write_text(json.dumps({"story": story, "post": post, "background": bg_source},
                                                  indent=2, ensure_ascii=False, default=str))

    entry = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "brief_date": data["date_utc"],
        "session": session_key,
        "kind": "post",
        "title": " ".join(post["headline"]),
        "fb_post_id": None,
        "headlines": [story["title"]],
        "topic": story["topic"],
        "source": story["source"],
        "background": bg_source,
        "workdir": str(workdir.relative_to(ROOT)),
    }
    failed = []
    if "facebook" in platforms:  # a news post never goes to YouTube
        try:
            entry["fb_post_id"] = facebook.publish_photo(card, text, cfg, log=log)
        except Exception as e:
            log(f"Facebook photo post failed: {e}")
            failed.append("facebook")
    log(f"Made {session.get('label', session_key)} post: {(workdir / 'post.jpg').relative_to(ROOT)}")
    return entry, failed


def session_platforms(session: dict) -> list[str]:
    default = ["facebook"] if session.get("kind") == "post" else list(PLATFORMS)
    out = [str(p).strip().lower() for p in (session.get("platforms") or default)]
    if session.get("kind") == "post":
        out = [p for p in out if p != "youtube"]
    return [p for p in out if p in PLATFORMS]


def platform_off(platform: str, cfg: dict) -> str:
    """'' when the platform can be published to, else why not."""
    if platform == "youtube":
        return "" if cfg["upload"].get("enabled", True) else "upload.enabled is false in config.yaml"
    return facebook.disabled_reason(cfg)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-upload", action="store_true", help="make it only, publish nowhere")
    p.add_argument("--force", action="store_true", help="timed run: make it even if this edition is already up today")
    p.add_argument("--session", default="auto",
                   help="asia | london | newyork | gold | news_morning | news_midday | news_evening | "
                        "auto (market edition by UTC time)")
    p.add_argument("--platforms", default="all",
                   help="all | youtube | facebook | youtube,facebook (limited to the edition's own platforms)")
    p.add_argument("--scheduled", action="store_true",
                   help="timed run (schedule / outside timer): weekend rule, late/early skip, once per edition per day")
    p.add_argument("--as-edition", action="store_true",
                   help="manual run that counts as today's edition, so its timed run then skips")
    p.add_argument("--lesson-sample", action="store_true",
                   help="make the sample trading lesson on fixture candles (never uploaded; use with --no-upload)")
    args = p.parse_args(argv)

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    if not cfg.get("sessions"):
        log("config.yaml has no 'sessions' section; using the built-in editions")
        cfg["sessions"] = DEFAULT_SESSIONS
    cfg.setdefault("weekend_sessions", ["london", "news_morning", "news_midday", "news_evening"])
    cfg.setdefault("max_late_minutes", 180)
    if args.lesson_sample:
        if not args.no_upload:
            log("Lessons aren't published yet: --lesson-sample makes it only (as with --no-upload).")
        return lesson_sample(cfg)
    history = History(ROOT / "data" / "history.json")

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    session_key = (args.session or "auto").strip().lower()
    if session_key in ("", "auto"):
        session_key = auto_session(now)
    if session_key not in cfg.get("sessions", {}):
        log(f"Unknown edition '{session_key}'. Choose one of: {', '.join(cfg.get('sessions', {}))}")
        return 1
    session = cfg["sessions"][session_key]
    label = session["label"]
    kind = session.get("kind", "market")
    start = session.get("start_utc") or DEFAULT_SESSIONS.get(session_key, {}).get("start_utc")

    wanted = session_platforms(session)
    asked = (args.platforms or "all").strip().lower()
    if asked not in ("", "all", "auto"):
        req = {x.strip() for x in asked.split(",") if x.strip()}
        unknown = req - set(PLATFORMS)
        if unknown:
            log(f"Unknown platform(s) {sorted(unknown)}. Choose from: all, {', '.join(PLATFORMS)}")
            return 1
        wanted = [x for x in wanted if x in req]
        if not wanted:
            log(f"The {label} edition isn't published to {asked} ({', '.join(session_platforms(session))} only); "
                "nothing to do.")
            return 0

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

    # pending = edition platforms ∩ enabled − already published today (timed runs)
    pending = []
    for plat in wanted:
        why = platform_off(plat, cfg)
        if why:
            log(f"{plat.title()} skipped: {why}")
        else:
            pending.append(plat)
    if args.no_upload:
        pending = []
    remake = False
    if args.scheduled and not args.force and not args.no_upload:
        done = [x for x in pending if history.published_on(today, session_key, x)]
        if done:
            log(f"The {label} edition for {today} is already published on {', '.join(done)}.")
        if done and len(done) == len(pending):
            log("Nothing to do.")
            return 0
        if not pending:
            log(f"No platform to publish the {label} edition to; nothing to do.")
            return 0
        remake = bool(done)
        pending = [x for x in pending if x not in done]
    if not args.scheduled:
        log("Manual run: makes and publishes now" +
            (" and fills today's slot (the timed run will skip)." if args.as_edition
             else "; the timed run of this edition still goes ahead."))
    if not pending and not args.no_upload:
        log("No platform to publish to; making it only.")

    log(f"Edition: {label} → {', '.join(pending) or 'no upload'}")
    try:
        if kind == "post":
            entry, failed = make_post(cfg, history, args, session_key, pending)
        else:
            # re-making an edition for a platform it missed: use the history the first run saw
            made = make_brief(cfg, history.excluding_slot(today, session_key) if remake else history,
                              args, session_key)
            entry, failed = publish(made, pending, cfg)
    except Exception as e:
        log(f"{'Post' if kind == 'post' else 'Brief'} failed: {e}")
        return 1
    if any(entry.get(k) for k in ("video_id", "fb_reel_id", "fb_post_id")):
        entry["trigger"] = "timed" if args.scheduled else "manual"
        entry["counts"] = bool(args.scheduled or args.as_edition)
        entry["platforms"] = [x for x, k in (("youtube", "video_id"), ("facebook", "fb_reel_id"),
                                             ("facebook", "fb_post_id")) if entry.get(k)]
        workdir = ROOT / entry.pop("workdir")
        # the workflow merges this file into the latest data/history.json (safe with parallel runs)
        (workdir / "history_entry.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False))
        history.add(entry)
        history.save()
    if failed:
        log(f"Not published on: {', '.join(failed)} (see the errors above)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
