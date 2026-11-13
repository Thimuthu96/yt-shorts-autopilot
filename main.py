"""Gus Explains: two odd-fact cartoon Shorts a day (YouTube Short + Facebook Reel).

One run = one edition: topic (topics/backlog.yaml) → Gemini writer (research, story, checks) → narration timeline →
music + SFX mixes (YouTube / Facebook) → studio render → mux → thumbnail → metadata → publish → history.

    python main.py --session short_a --no-upload                  # make one now, publish nowhere (output/<stamp>-short_a/)
    python main.py --session short_a --topic "Why ..." --no-upload # a topic of your own (the backlog is untouched)
    python main.py --session short_a --story stories/sample/lighthouse.json --no-upload   # no writer: render a story
    python main.py --session short_b --scheduled                  # timed run: gate, late/early skip, once a day
    python main.py --session short_a --platforms facebook         # publish to Facebook only
    python main.py --session short_a --as-edition                 # manual run that fills today's slot

Timed runs skip while gus.enabled is false. Manual runs always make (and publish unless --no-upload) and don't stop
the timed run of that edition unless --as-edition.
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from autopilot import metadata, soundtrack, studio, timeline, topics, writer
from autopilot import story as story_mod
from autopilot.history import ID_KEYS, PLATFORM_IDS, History

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.yaml"
HISTORY = ROOT / "data" / "history.json"
BACKLOG = ROOT / "topics" / "backlog.yaml"
OUTPUT = ROOT / "output"
PUBLISHED = ROOT / "stories" / "published"  # every published story, so a re-run for a missed platform re-renders it

DEFAULT_SESSIONS = {
    "short_a": {"label": "Short A", "start_utc": "16:25", "publish_note": "~17:00 UTC", "platforms": ["youtube", "facebook"]},
    "short_b": {"label": "Short B", "start_utc": "22:25", "publish_note": "~23:00 UTC", "platforms": ["youtube", "facebook"]},
}
PLATFORMS = ("youtube", "facebook")
GATE_OFF = "gus.enabled is false: timed runs skip until the owner turns it on after the rebrand."


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def minutes_late(now: datetime, start_utc: str) -> int:
    """Minutes since today's start time; negative if a bit early (within 12 h either way)."""
    h, m = (int(x) for x in str(start_utc).split(":"))
    diff = (now.hour * 60 + now.minute - (h * 60 + m)) % (24 * 60)
    return diff - 24 * 60 if diff > 12 * 60 else diff


def load_config(path: Path | None = None) -> dict:
    cfg = yaml.safe_load(Path(path or CONFIG).read_text(encoding="utf-8")) or {}
    if not cfg.get("sessions"):
        log("config.yaml has no 'sessions' section; using the built-in editions")
        cfg["sessions"] = DEFAULT_SESSIONS
    cfg.setdefault("max_late_minutes", 120)
    cfg.setdefault("upload", {})
    return cfg


def platform_off(platform: str, cfg: dict) -> str:
    """'' when the platform can be published to, else why not."""
    if platform == "youtube":
        return "" if cfg["upload"].get("enabled", True) else "upload.enabled is false in config.yaml"
    from autopilot import facebook
    return facebook.disabled_reason(cfg)


# ─── making one Short ──────────────────────────────────────────────────────
def _unique_slug(s: dict, history: History) -> None:
    taken, base, k = history.slugs(), s["slug"], 2
    while s["slug"] in taken:
        s["slug"] = f"{base[:44]}-{k}"
        k += 1


def _manual_topic(text: str) -> topics.Topic:
    fmt = "levels" if text.strip().lower().startswith("levels of") else "explainer"
    return topics.Topic("manual-" + topics.slugify(text), text.strip(), "levels" if fmt == "levels" else "", fmt, "")


def refill(cfg: dict, history: History, backlog: list[dict], log=log) -> None:
    """Gemini proposes new topics when the queue runs low; a failure is logged, never fatal."""
    gus = cfg.get("gus") or {}
    if not topics.needs_refill(backlog, int(gus.get("min_backlog", 10))):
        return
    try:
        existing = history.titles() + [e.get("title_idea", "") for e in backlog]
        props = writer.propose_topics(int(gus.get("refill_count", 15)), existing, cfg)
        if topics.add(backlog, props, history.titles(), log=log):
            topics.save(BACKLOG, backlog)
    except Exception as e:
        log(f"Topic refill failed (the backlog stays as it is): {e}")


def _write_story(cfg, history, date, catalog, topic_text, workdir, log):
    """topic → writer → timeline, up to gus.max_topics topics. Returns (story, timeline, topic, backlog)."""
    gus = cfg.get("gus") or {}
    vcfg, max_s = cfg["voice"], float((cfg.get("video") or {}).get("max_seconds", 60))
    backlog = None if topic_text else topics.load(BACKLOG)
    refilled, tried = False, 0
    for tried in range(1, int(gus.get("max_topics", 3)) + 1):
        if topic_text:
            topic = _manual_topic(topic_text)
        else:
            topic = topics.next_topic(backlog, history.titles(), history.stories(), log=log)
            if topic is None and not refilled:
                log("The topic backlog has no usable queued topic; asking Gemini for more.")
                refill(cfg, history, backlog, log)
                refilled = True
                topic = topics.next_topic(backlog, history.titles(), history.stories(), log=log)
            if topic is None:
                raise RuntimeError("the topic backlog has no usable queued topic")
        log(f"Topic {tried}: {topic.title_idea} ({topic.category or 'any category'}, {topic.format})")
        try:
            s = writer.write(topic, cfg, catalog, log=log)
            _unique_slug(s, history)
            tl = timeline.build(s, vcfg, workdir, max_s, log=log)
            return s, tl, topic, backlog
        except writer.WriteFailed as e:
            reason = str(e)
        except timeline.TooLong as e:
            reason = f"too long: narration {e.seconds:.1f}s"
        log(f"Topic {topic.id} failed: {reason}")
        if topic_text:
            raise RuntimeError(f"the topic {topic_text!r} failed: {reason}")
        topics.mark(backlog, topic.id, "failed", reason[:300], date)
        topics.save(BACKLOG, backlog)
    raise RuntimeError(f"{tried} topics failed in a row; nothing to publish")


def make_short(cfg: dict, history: History, session: str, date: str, story_path: str | None = None,
               topic_text: str | None = None, log=log) -> dict | None:
    """Make one Short in output/<stamp>-<session>/: short.mp4 (YouTube mix), short_fb.mp4 (Facebook mix),
    thumbnail.jpg, story.json, timeline.json, metadata.json. Raises on failure (nothing is published)."""
    workdir = OUTPUT / f"{now_utc().strftime('%Y%m%d-%H%M%S')}-{session}"
    workdir.mkdir(parents=True, exist_ok=True)
    catalog = story_mod.load_catalog()
    video_cfg = cfg.get("video") or {}
    topic = backlog = None
    if story_path:
        s = json.loads(Path(story_path).read_text(encoding="utf-8"))
        problems = story_mod.validate(s, catalog)
        if problems:
            raise RuntimeError(f"story {story_path} is invalid: " + "; ".join(problems[:8]))
        log(f"Story from {story_path}: {s['title']}")
        tl = timeline.build(s, cfg["voice"], workdir, float(video_cfg.get("max_seconds", 60)), log=log)
    else:
        s, tl, topic, backlog = _write_story(cfg, history, date, catalog, topic_text, workdir, log)

    tracks = soundtrack.load_tracks(log=log)
    yt = soundtrack.pick_track(tracks, s["music_mood"], "youtube", s["slug"])
    fb = soundtrack.pick_track(tracks, s["music_mood"], "facebook", s["slug"])
    log(f"Music: YouTube {yt['file'] if yt else 'none'}, Facebook {fb['file'] if fb else 'none'}"
        + ("" if fb else " (no track cleared for Facebook: the Reel has no music)"))
    db = float(video_cfg.get("music_db", -20))
    mix_yt = soundtrack.mix(workdir / "voice.wav", tl, s, yt, workdir / "mix_yt.wav", db)
    mix_fb = mix_yt if fb is yt else soundtrack.mix(workdir / "voice.wav", tl, s, fb, workdir / "mix_fb.wav", db)
    video = studio.render(s, tl, workdir, log=log, scale=float(video_cfg.get("render_scale") or 1.0))
    short = studio.mux(video, mix_yt, workdir / "short.mp4")
    short_fb = workdir / "short_fb.mp4"
    if mix_fb is mix_yt:
        shutil.copyfile(short, short_fb)
    else:
        studio.mux(video, mix_fb, short_fb)
    thumb = studio.thumbnail(short, workdir / "thumbnail.jpg")
    meta = metadata.build(s, yt, cfg)
    caption = metadata.reel_caption(s, fb, cfg)
    (workdir / "metadata.json").write_text(json.dumps({**meta, "fb_caption": caption}, indent=2, ensure_ascii=False))
    (workdir / "story.json").write_text(json.dumps(s, indent=2, ensure_ascii=False))
    entry = {"date": date, "brief_date": date, "published_at": now_utc().isoformat(timespec="seconds"),
             "session": session, "kind": "short", "slug": s["slug"], "title": meta["title"],
             "category": s.get("category"), "format": s.get("format"), "topic_id": topic.id if topic else None,
             "voice": tl.get("voice"), "music_yt": yt["file"] if yt else None, "music_fb": fb["file"] if fb else None,
             "seconds": round(float(tl["duration"]), 1)}
    log(f"Made {s['slug']}: {tl['duration']:.1f}s → {short}")
    return {"video": short, "video_fb": short_fb, "thumbnail": thumb, "meta": meta, "fb_caption": caption,
            "entry": entry, "story": s, "topic": topic, "backlog": backlog, "workdir": workdir}


def publish(made: dict, pending: list[str], cfg: dict) -> tuple[dict, list[str]]:
    """Each platform on its own: a failure is logged and never blocks (or repeats) the other.
    Returns (entry with the ids it got, failed platforms)."""
    entry, failed = dict(made["entry"]), []
    if "youtube" in pending:
        try:
            from autopilot import youtube
            entry["video_id"] = youtube.upload(made["video"], made["meta"], cfg, log=log)
            if cfg["upload"].get("set_thumbnail", True):
                youtube.set_thumbnail(entry["video_id"], made["thumbnail"], log=log)
        except Exception as e:
            log(f"YouTube upload failed: {e}")
            failed.append("youtube")
    if "facebook" in pending:
        try:
            from autopilot import facebook
            entry["fb_reel_id"] = facebook.publish_reel(made["video_fb"], made["fb_caption"], cfg,
                                                        cover=made["thumbnail"], log=log)
        except Exception as e:
            log(f"Facebook Reel failed: {e}")
            failed.append("facebook")
    return entry, failed


def _after_publish(made: dict, cfg: dict, history: History, date: str) -> None:
    """Save the story (stories/published/<slug>.json), mark its topic used, refill a low backlog."""
    PUBLISHED.mkdir(parents=True, exist_ok=True)
    (PUBLISHED / f"{made['story']['slug']}.json").write_text(json.dumps(made["story"], indent=2, ensure_ascii=False))
    backlog, topic = made.get("backlog"), made.get("topic")
    if backlog is None or topic is None:
        return
    try:
        topics.mark(backlog, topic.id, "used", None, date)
    except KeyError:
        return
    topics.save(BACKLOG, backlog)
    refill(cfg, history, backlog)


# ─── the edition ───────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gus Explains: make and publish one Short")
    p.add_argument("--session", default="", help="short_a | short_b (the edition; required)")
    p.add_argument("--platforms", default="all", help="all | youtube | facebook | youtube,facebook")
    p.add_argument("--scheduled", action="store_true",
                   help="timed run (outside timer / backup cron): gate, late/early skip, once per edition per day")
    p.add_argument("--as-edition", action="store_true", help="manual run that fills today's slot (timed run skips)")
    p.add_argument("--force", action="store_true", help="timed run: make it even if this edition is already up today")
    p.add_argument("--no-upload", action="store_true", help="make it only, publish nowhere")
    p.add_argument("--story", default="", metavar="PATH", help="render this story JSON (skips the writer)")
    p.add_argument("--topic", default="", metavar="TEXT", help="write about this topic instead of the backlog's next")
    args = p.parse_args(argv)

    cfg = load_config()
    now = now_utc()
    today = now.strftime("%Y-%m-%d")
    session_key = (args.session or "").strip().lower()
    if session_key not in cfg["sessions"]:
        log(f"Unknown edition {session_key!r}. Choose one of: {', '.join(cfg['sessions'])}")
        return 1
    session = cfg["sessions"][session_key]
    label = session.get("label", session_key)

    if args.scheduled and not (cfg.get("gus") or {}).get("enabled", False):
        log(GATE_OFF)
        return 0
    if args.scheduled and session.get("start_utc"):
        late = minutes_late(now, session["start_utc"])
        log(f"Timed run for the {label} edition (due {session['start_utc']} UTC, started {late:+d} min)")
        if late > cfg["max_late_minutes"]:
            log(f"Started more than {cfg['max_late_minutes']} min late, so the {label} edition is skipped "
                "(it would clash with the next edition). Use Run workflow to make it anyway.")
            return 0
        if late < -30:
            log(f"Started {-late} min before {session['start_utc']} UTC, so the {label} edition is skipped. "
                "Check the timer's time and time zone.")
            return 0

    wanted = [x for x in (session.get("platforms") or PLATFORMS) if x in PLATFORMS]
    asked = (args.platforms or "all").strip().lower()
    if asked not in ("", "all"):
        req = {x.strip() for x in asked.split(",") if x.strip()}
        if req - set(PLATFORMS):
            log(f"Unknown platform(s) {sorted(req - set(PLATFORMS))}. Choose from: all, {', '.join(PLATFORMS)}")
            return 1
        wanted = [x for x in wanted if x in req]
    pending = []
    for plat in wanted:
        why = platform_off(plat, cfg)
        if why:
            log(f"{plat.title()} skipped: {why}")
        else:
            pending.append(plat)
    if args.no_upload:
        pending = []

    history = History(HISTORY)
    story_path = args.story or None
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
        pending = [x for x in pending if x not in done]
        if done and not story_path:  # a re-run for the platform the first run missed: the same story
            prev = history.today_story(today, session_key)
            saved = PUBLISHED / f"{prev['slug']}.json" if prev else None
            if saved and saved.exists():
                story_path = str(saved)
                log(f"Re-making {prev['slug']} for {', '.join(pending)} from {saved}")
            else:
                log("The earlier story of this slot isn't saved; a new one is made for the missing platform.")
    if not args.scheduled:
        log("Manual run: " + ("makes it only (--no-upload)." if args.no_upload else "makes and publishes now"
                              + (" and fills today's slot." if args.as_edition else
                                 "; the timed run of this edition still goes ahead.")))
    log(f"Edition: {label} → {', '.join(pending) or 'no upload'}")

    try:
        made = make_short(cfg, history, session_key, today, story_path=story_path, topic_text=args.topic or None)
    except Exception as e:
        log(f"Short failed: {e}")
        return 1
    if made is None:
        return 1
    if not pending:
        log(f"Made only (nothing published): {made['workdir']}")
        return 0
    entry, failed = publish(made, pending, cfg)
    if any(entry.get(k) for k in ID_KEYS):
        entry["trigger"] = "timed" if args.scheduled else "manual"
        entry["counts"] = bool(args.scheduled or args.as_edition)
        entry["platforms"] = [x for x, keys in PLATFORM_IDS.items() if any(entry.get(k) for k in keys)]
        # the workflow merges this file into the latest data/history.json (safe with parallel runs)
        (Path(made["workdir"]) / "history_entry.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False))
        history.add(entry)
        history.save()
        _after_publish(made, cfg, history, today)
    if failed:
        log(f"Not published on: {', '.join(failed)} (see the errors above)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
