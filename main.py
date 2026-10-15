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
    python main.py --session lesson --scheduled  # trading lesson: next curriculum episode (YouTube + Facebook video)
    python main.py --session lesson --slot recap  # top-up: the next unpublished lesson, once, in today's recap slot
    python main.py --session lesson --no-upload  # make the next lesson only (works with lessons.enabled false)
    python main.py --lesson-sample --no-upload  # sample trading lesson (16:9 + 9:16) on fixture candles
    python main.py --session basics   # Crypto Basics: the next approved topic (basics/topics.yaml), 16:9 YouTube +
                                      # 9:16 Facebook (timed runs: off while basics.enabled is false); a topic with
                                      # a ready package (basics/ready/<id>.yaml) is published as it is
    python main.py --session evergreen --slot recap   # top-up: the next ready Basics episode, else the next lesson,
                                                      # once in today's recap slot (timed runs: evergreen.enabled)
    python main.py --session basics --prepare next   # write the next ready package (evergreen stock, for a PR)
    python main.py --session basics --stock          # how many ready, unpublished Basics episodes there are
    python main.py --session recap    # Saturday recap: the week's biggest moves and why (16:9, YouTube only; skipped
                                      # when a triggered video published this ISO week; timed runs: recap.enabled)
    python main.py --session short_a  # standalone Short (kind: short) from the Shorts material (data/material/);
                                      # YouTube Short + Facebook Reel (timed runs: off while shorts.enabled is false)
    python main.py --session triggered --trigger <id|fixture.json> --no-upload   # "why crypto just moved" (16:9,
                                                      # YouTube only; timed runs: off while triggers.enabled is false)

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

from autopilot import (basics, facebook, focus, gold, images, lesson_data, lesson_meta, lesson_script, lesson_slides,
                       lessons, material, news_post, recap, render, reveal, script, shorts, slides, sources,
                       thumbnail, triggered, triggers, voice)
from autopilot import detectors  # noqa: F401  (registers the lesson detectors)
from autopilot import lesson_material
from autopilot.history import ID_KEYS, PLATFORM_IDS, History

ROOT = Path(__file__).parent

# Used when config.yaml has no "sessions" section (e.g. an older config.yaml).
DEFAULT_SESSIONS = {
    "asia": {"label": "Asia Open", "short": "Asia", "start_utc": "00:30",
             "focus": "Cover what moved in crypto since the New York close: Bitcoin, Ether and the large coins "
                      "overnight, ETF flows, liquidations and regulation news, and what crypto traders watch next."},
    "london": {"label": "London Open", "short": "London", "start_utc": "05:40",
               "focus": "Cover what moved in crypto during the Asian session: Bitcoin, Ether and the large coins, "
                        "ETF flows, liquidations and regulation news, and what crypto traders watch next."},
    "newyork": {"label": "New York Open", "short": "New York", "start_utc": "12:30",
                "focus": "Cover crypto moves since the London open: Bitcoin, Ether and the large coins, spot ETF "
                         "flows, liquidations and regulation news, and what crypto traders watch for the rest of the day."},
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
LESSON_PATH_PLAYLIST = "Trading Lessons · The Path"  # cfg lessons.path_playlist
LESSON_TRACK_PLAYLIST = "Track {n} · {name}"  # cfg lessons.track_playlist
BASICS_MAX_SECONDS = 390  # Crypto Basics narration limit (cfg basics.max_seconds)
TRIGGERED_MAX_SECONDS = 250  # triggered narration limit (cfg triggers.max_seconds)
RECAP_MAX_SECONDS = 320  # recap narration limit (cfg recap.max_seconds)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # a session's `days`, datetime.weekday() order


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def faster_rate(rate: str, factor: float) -> str:
    pct = int(re.sub(r"[^\d-]", "", rate) or 0)
    new = int(round(((1 + pct / 100) * factor - 1) * 100)) + 2
    return f"{'+' if new >= 0 else ''}{min(new, 35)}%"


def narrate(v: dict, scenes: list[dict], limit: float, workdir: Path, pauses: bool = False,
            what: str = "Narration", log=log) -> tuple[list[dict], float]:
    """Voice the scenes at `voice.rate`; over `limit` seconds → re-recorded once, faster. `pauses` (briefs,
    gold): key-number / concept-term pauses (voice.paced) on both recordings. Returns (audio, seconds)."""
    audio = voice.synthesize(scenes, v["name"], v["rate"], workdir, log=log, fallback=v.get("fallback"), pauses=pauses)
    total = sum(a["duration"] for a in audio)
    if total > limit:
        rate = faster_rate(v["rate"], total / limit)
        log(f"{what} {total:.1f}s is over {limit}s, re-recording at {rate}")
        audio = voice.synthesize(scenes, v["name"], rate, workdir, log=log, fallback=v.get("fallback"), pauses=pauses)
        total = sum(a["duration"] for a in audio)
    log(f"{what}: {total:.1f}s")
    return audio, total


def ab_voice(v: dict, history: History, session_key: str) -> dict:
    """The voice settings for a brief or gold run (narration-rules.md A/B): with `voice.alternate` set, each
    edition alternates name / alternate, the other one from its latest uploaded edge-tts entry (Piper
    entries are skipped; none yet → name). Without it, `v` unchanged."""
    pair = (v["name"], v.get("alternate"))
    if not pair[1]:
        return v
    return {**v, "name": pair[1] if history.last_voice(session_key, pair) == pair[0] else pair[0]}


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

    scenes = pkg["scenes"]
    v = ab_voice(cfg["voice"], history, session_key)
    log(f"Voice: {v['name']}" + (" (A/B rotation)" if v.get("alternate") else ""))
    audio, total = narrate(v, scenes, cfg["video"]["max_seconds"], workdir, pauses=True)

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
    meta = youtube.build_metadata(pkg, data, cfg, session.get("label", ""), log=log)
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
        "voice": audio[0]["voice"] if audio else v["name"],
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
                next_entry: dict | None = None, log=log, examples: list[dict] | None = None) -> dict:
    """One curriculum entry → a 16:9 and a 9:16 lesson video from the same narration, the lesson
    thumbnail, chapters and metadata (written to the workdir; nothing is uploaded).
    `history` is lesson_data.fetch_history's {asset: {timeframe: candles}}; `examples` = what the
    entry's detector already found on it (the edition's hold check), else the detector is run here.
    Returns {"held": reason} when the detector finds no clean example (nothing is rendered), else
    {"videos": {"16x9", "9x16"}, "thumbnail", "meta", "chapters", "seconds", "examples", "workdir"}."""
    det = lessons.DETECTORS.get(entry.get("detector"))
    if examples is None:
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

    scenes = pkg["scenes"]
    audio, total = narrate(cfg["voice"], scenes, (cfg.get("lessons") or {}).get("max_seconds", LESSON_MAX_SECONDS),
                           workdir, what="Lesson narration", log=log)

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
        reveal.time_steps(pics, pkg["scenes"], audio, log=log)  # each mark fades in as the narration names it
        out = workdir / f"lesson_{layout.name}.mp4"
        render.build_video(audio, pics, lesson_video_cfg(cfg, layout), shape_dir, out, music=music)
        videos[layout.name] = out
        log(f"Rendered {out}")

    meta = lesson_meta.build_lesson_metadata(entry, examples, chapters, cfg, log=log)
    (workdir / "metadata.json").write_text(json.dumps({**meta, "chapters": chapters}, indent=2, ensure_ascii=False))
    log(f"Lesson title: {meta['title']}")
    return {"videos": videos, "thumbnail": thumb, "meta": meta, "chapters": chapters, "seconds": round(total, 1),
            "examples": examples, "workdir": workdir}


def lesson_sample(cfg: dict) -> int:
    """The tests/lessons sample entry on fixture candles, made only (the sample is never published)."""
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


def lesson_playlists(cfg: dict, track: int) -> tuple[str, str]:
    """(track playlist, Path playlist) titles for a lesson of this track."""
    lc = cfg.get("lessons") or {}
    name = lesson_slides.TRACKS.get(track, f"Track {track}")
    track_title = str(lc.get("track_playlist") or LESSON_TRACK_PLAYLIST).format(n=track, name=name)
    return track_title, str(lc.get("path_playlist") or LESSON_PATH_PLAYLIST)


def publish_lesson(made: dict, pending: list[str], cfg: dict) -> tuple[dict, list[str]]:
    """Publish one made lesson to each pending platform on its own (as publish() does for the daily
    editions): YouTube gets the 16:9 video through youtube.upload_lesson (review window; playlists only
    with lessons.playlists: true, which needs the lesson-scope token), Facebook the 9:16 video through facebook.publish_video. A failure on one is logged
    and never blocks (or repeats) the other. Returns (entry with the ids it got, failed platforms)."""
    entry, failed = made["entry"], []
    lc = cfg.get("lessons") or {}
    meta = made["meta"]
    if "youtube" in pending:
        try:
            from autopilot import youtube
            track_pl, path_pl = lesson_playlists(cfg, made["track"])
            res = youtube.upload_lesson(made["videos"]["16x9"], meta, made["thumbnail"], track_pl, path_pl,
                                        review_hours=lc.get("review_window_hours", 0),
                                        notify=cfg["upload"].get("notify_subscribers", True), log=log,
                                        playlists=bool(lc.get("playlists", False)))
            entry["video_id"] = res["video_id"]
            if res.get("publish_at"):
                entry["publish_at"] = res["publish_at"]
            for err in res.get("errors") or []:
                log(f"YouTube lesson uploaded, but: {err}")
        except Exception as e:
            log(f"YouTube lesson upload failed: {e}")
            failed.append("youtube")
    if "facebook" in pending:
        try:
            entry["fb_video_id"] = facebook.publish_video(
                made["videos"]["9x16"], meta.get("fb_title") or meta["title"],
                meta.get("fb_description") or meta["description"], cfg,
                published=bool(lc.get("fb_published", True)), log=log)
        except Exception as e:
            vid = getattr(e, "video_id", None)
            log(f"Facebook lesson video failed: {e}"
                + (f" (video {vid} exists on the Page; check or delete it there)" if vid else ""))
            failed.append("facebook")
    return entry, failed


def example_id(ex: dict) -> dict:
    """What identifies an example in history (never the candles): asset, timeframe, region start/end."""
    region = ex.get("region") or {}
    return {"asset": ex.get("asset"), "timeframe": ex.get("timeframe"),
            "start": str(region["start"]) if region.get("start") is not None else None,
            "end": str(region["end"]) if region.get("end") is not None else None}


def make_lesson_edition(cfg: dict, history: History, date: str, session_key: str, pending: list[str],
                        no_upload: bool = False, counts: bool = True,
                        force: bool = False) -> tuple[dict | None, list[str]]:
    """Pick and make this slot's lesson. Returns (made, pending) with made = make_lesson's result plus
    "entry" and "track", or (None, pending) when there is nothing to publish in this slot.

    The curriculum is validated first (problems → logged, RuntimeError). lessons.pick chooses the
    episode: on a counting run (`counts`: timed or --as-edition) of a slot that recorded `episode: X`,
    X again with the recorded examples where they are found again (only the platforms X is still
    missing, unless `force`; X can't be re-made → RuntimeError); else the first unpublished entry
    whose detector finds a clean example in the price history (held entries are logged, never stored)."""
    curriculum = lessons.load_curriculum(ROOT / "lessons" / "curriculum.yaml")
    glossary = lessons.load_glossary(ROOT / "lessons" / "glossary.yaml")
    problems = lessons.validate(curriculum, glossary)
    if problems:
        for msg in problems:
            log(f"Curriculum problem: {msg}")
        raise RuntimeError(f"lessons/curriculum.yaml has {len(problems)} problem(s) (listed above); "
                           "fix them (python tests/test_lessons.py) before lessons can run")

    candles: dict = {}
    found: dict[str, list[dict]] = {}  # entry id → examples, so make_lesson doesn't search again

    def price_history() -> dict:
        if not candles:
            log("Fetching the lesson price history...")
            candles.update(lesson_data.fetch_history(log=log))
            if not candles:
                raise RuntimeError("no lesson price history could be loaded (every source failed)")
        return candles

    def hold(e: dict) -> str | None:
        det = lessons.DETECTORS.get(e.get("detector"))
        if det is None:
            return f"detector '{e.get('detector')}' is not registered"
        found[e["id"]] = det.find(price_history())
        return None if found[e["id"]] else f"no clean {e['detector']} example in the price history"

    picked = lessons.pick(curriculum, history, date, session_key, hold, slot_rerun=counts)
    for eid, reason in picked.held:
        log(f"Lesson {eid} held: {reason}")
    if picked.entry is None and picked.rerun:
        raise RuntimeError("this slot's recorded episode is no longer in the curriculum, so it can't be "
                           "re-made for the missing platform(s)")
    if picked.entry is None:
        why = "the curriculum is empty" if not curriculum else "every episode is published or held"
        log(f"Lessons: nothing to publish in this slot ({why}).")
        return None, pending
    entry = picked.entry
    if picked.rerun:
        log(f"This slot already recorded episode {entry['id']}: making it again")
        if not force:
            done = [x for x in pending if history.published_on(date, session_key, x)]
            if done:
                log(f"Episode {entry['id']} is already published on {', '.join(done)} for this slot.")
                pending = [x for x in pending if x not in done]
                if not pending and not no_upload:
                    log("Nothing to do.")
                    return None, pending
        hold(entry)  # re-run the detector (pick skipped the hold check for the recorded episode)
        again = found.get(entry["id"]) or []
        recorded = [x for v in history.uploaded() if v.get("brief_date") == date
                    and v.get("session", "london") == session_key and v.get("counts", True)
                    and v.get("episode") == entry["id"] for x in (v.get("examples") or []) if isinstance(x, dict)]
        same = [ex for ex in again if example_id(ex) in recorded]
        if recorded and again and not same:
            log(f"The recorded examples of {entry['id']} weren't found again; using the ones found now")
        if not again:
            raise RuntimeError(f"this slot's recorded episode {entry['id']} can't be re-made: no clean "
                               f"{entry.get('detector')} example in the price history now")
        found[entry["id"]] = same or again
    log(f"Lesson episode: {entry['id']} · {entry['title']} (track {entry['track']})")

    i = next(n for n, e in enumerate(curriculum) if e is entry)
    next_entry = curriculum[i + 1] if i + 1 < len(curriculum) else None
    workdir = ROOT / "output" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    made = make_lesson(cfg, entry, glossary, price_history(), workdir, next_entry, log=log,
                       examples=found.get(entry["id"]))
    if made.get("held"):
        if picked.rerun:
            raise RuntimeError(f"this slot's recorded episode can't be re-made: {made['held']}")
        log(f"Lessons: nothing to publish in this slot ({made['held']}).")
        return None, pending
    made["track"] = entry["track"]
    made["entry"] = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "brief_date": date,
        "session": session_key,
        "kind": "lesson",
        "episode": entry["id"],
        "track": entry["track"],
        "title": made["meta"]["title"],
        "video_id": None,
        "fb_video_id": None,
        "seconds": made["seconds"],
        "examples": [example_id(e) for e in made["examples"]],  # a re-run re-makes these
        "workdir": str(Path(made["workdir"]).relative_to(ROOT)),
    }
    return made, pending


def basics_topics() -> list:
    """basics/topics.yaml, validated (problems → logged, RuntimeError)."""
    topics = basics.load_topics(ROOT / "basics" / "topics.yaml")
    problems = basics.validate_topics(topics)
    if problems:
        for msg in problems:
            log(f"Basics topic problem: {msg}")
        raise RuntimeError(f"basics/topics.yaml has {len(problems)} problem(s) (listed above); fix them "
                           "(python tests/test_offline.py) before Crypto Basics can run")
    return topics


def basics_ready_dir() -> Path:
    return ROOT / "basics" / "ready"


def basics_topic(history: History) -> dict | None:
    """The next Basics topic: basics/topics.yaml validated (problems → logged, RuntimeError), then basics.pick
    (the first approved topic no uploaded kind: basics entry has published). None = nothing to publish."""
    topic = basics.pick(basics_topics(), history)
    if topic is None:
        log("Basics: nothing to publish (no approved, unpublished topic in basics/topics.yaml).")
    return topic


def make_basics(cfg: dict, history: History, session_key: str, date: str, topic: dict | None = None,
                ready_only: bool = False) -> dict | None:
    """One Crypto Basics edition (kind: basics) from the next approved topic (basics_topic; None = nothing
    to publish): narration of its approved points with the subscribe ask after the first payoff
    (basics.write_script: 3 attempts, then the fact-check, whose failure stops it), the A/B voice with pauses,
    a 16:9 and a 9:16 render of the same narration, the thumbnail, chapters and the metadata (written to
    the workdir; nothing is uploaded).
    Returns {"entry", "videos": {"16x9", "9x16"}, "thumbnail", "meta", "seconds", "workdir"}."""
    bc = cfg.get("basics") or {}
    if topic is None:
        topic = basics_topic(history)
    if topic is None:
        return None
    log(f"Basics topic: {topic['id']} · {topic['question']}")
    problems = basics.packaging_problems(topic)  # the title / thumbnail rules stop it before anything is made
    if problems:
        raise RuntimeError(f"Basics packaging ({topic['id']}): {'; '.join(problems)}")
    workdir = ROOT / "output" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)

    plan = basics.scene_plan(topic)
    ready = basics.load_ready(basics.ready_path(basics_ready_dir(), topic["id"]))
    if ready is not None:  # the evergreen stock: a reviewed narration, used as it is (no LLM call)
        problems = basics.validate_ready(ready, topic, cfg)
        if problems:
            raise RuntimeError(f"Basics ready package basics/ready/{topic['id']}.yaml: {'; '.join(problems)}")
        log(f"Basics: using the ready package basics/ready/{topic['id']}.yaml (no LLM call)")
        pkg = basics.ready_script(ready, topic)
    elif ready_only:
        raise RuntimeError(f"{topic['id']} has no ready package (basics/ready/{topic['id']}.yaml)")
    else:
        pkg = basics.write_script(cfg, topic, plan, log=log)
    (workdir / "package.json").write_text(json.dumps(
        {"topic": topic["id"], "title": topic["question"],
         "scenes": [{"id": s["id"], "text": s["text"]} for s in pkg["scenes"]],
         "fact_check": pkg.get("fact_check")}, indent=2, ensure_ascii=False))
    # the Shorts material must be makeable before anything is published (≥ 5 segments, rules, diagrams)
    problems = material.validate(material.build_basics(topic, pkg["scenes"], {"video_id": "-", "date": date}, cfg))
    if problems:
        raise RuntimeError(f"Basics Shorts material ({topic['id']}): {'; '.join(problems)}")

    v = ab_voice(cfg["voice"], history, session_key)
    log(f"Voice: {v['name']}" + (" (A/B rotation)" if v.get("alternate") else ""))
    audio, total = narrate(v, pkg["scenes"], bc.get("max_seconds", BASICS_MAX_SECONDS), workdir, pauses=True,
                           what="Basics narration", log=log)
    thumb = basics.render_thumbnail(cfg, topic, workdir / "thumbnail.jpg", log=log)
    chapters = basics.chapters(plan, audio)
    log("Chapters: " + ", ".join(f"{c['time']} {c['title']}" for c in chapters))

    music_files = sorted((ROOT / "music").glob("*.mp3"))
    music = random.choice(music_files) if music_files else None  # same music in both shapes
    videos = {}
    for layout in (lesson_slides.LANDSCAPE, lesson_slides.PORTRAIT):
        log(f"Drawing and rendering the {layout.name} Basics video...")
        shape_dir = workdir / layout.name  # each render keeps its own segments / captions
        pics = basics.render_slides(cfg, topic, plan, layout, shape_dir)
        reveal.time_steps(pics, pkg["scenes"], audio, log=log)  # each diagram part fades in as the narration names it
        out = workdir / f"basics_{layout.name}.mp4"
        render.build_video(audio, pics, lesson_video_cfg(cfg, layout), shape_dir, out, music=music)
        videos[layout.name] = out
        log(f"Rendered {out}")

    meta = basics.metadata(cfg, topic, chapters, log=log)
    (workdir / "metadata.json").write_text(json.dumps({**meta, "chapters": chapters}, indent=2, ensure_ascii=False))
    log(f"Basics title: {meta['title']}")
    entry = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "brief_date": date,
        "session": session_key,
        "kind": "basics",
        "topic": topic["id"],
        "title": meta["title"],
        "video_id": None,
        "fb_video_id": None,
        "seconds": round(total, 1),
        "voice": audio[0]["voice"] if audio else v["name"],
        "workdir": str(workdir.relative_to(ROOT)),
    }
    return {"entry": entry, "videos": videos, "thumbnail": thumb, "meta": meta, "seconds": round(total, 1),
            "workdir": workdir, "topic": topic, "scenes": pkg["scenes"]}


def prepare_basics(cfg: dict, history: History, which: str) -> int:
    """--prepare <topic id|next>: narrate an approved, unpublished topic as the edition does (narration rules,
    subscribe ask, fact-check, packaging, Shorts material) and write its ready package basics/ready/<id>.yaml
    for a PR. `next` = the first such topic (list order) without a package. Never uploads or records history.
    0 = written; 1 = nothing written (why logged)."""
    try:
        topics = basics_topics()
    except Exception as e:
        log(f"Prepare failed: {e}")
        return 1
    published = {v["topic"] for v in history.uploaded() if v.get("kind") == "basics" and v.get("topic")}
    folder = basics_ready_dir()
    which = (which or "").strip()
    if which == "next":
        topic = next((t for t in topics if t.get("approved") is True and t["id"] not in published
                      and not basics.ready_path(folder, t["id"]).exists()), None)
        if topic is None:
            log("Prepare: nothing to prepare (every approved, unpublished topic already has a ready package).")
            return 1
    else:
        topic = next((t for t in topics if t.get("id") == which), None)
        why = ("is not in basics/topics.yaml" if topic is None else
               "is a draft (approved: false)" if topic.get("approved") is not True else
               "is already published" if which in published else "")
        if why:
            log(f"Prepare: topic '{which}' {why}; nothing written.")
            return 1
    path = basics.ready_path(folder, topic["id"])
    log(f"Preparing the ready package for {topic['id']} · {topic['question']}"
        + (" (replacing the existing one)" if path.exists() else ""))
    try:
        problems = basics.packaging_problems(topic)
        if problems:
            raise RuntimeError(f"Basics packaging ({topic['id']}): {'; '.join(problems)}")
        pkg = basics.write_script(cfg, topic, basics.scene_plan(topic), log=log)
        problems = material.validate(material.build_basics(topic, pkg["scenes"], {"video_id": "-", "date": "-"}, cfg))
        if problems:
            raise RuntimeError(f"Basics Shorts material ({topic['id']}): {'; '.join(problems)}")
        package = basics.ready_package(topic, pkg, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        problems = basics.validate_ready(package, topic, cfg)
        if problems:
            raise RuntimeError(f"ready package: {'; '.join(problems)}")
    except Exception as e:
        log(f"Prepare failed: {e}; nothing written.")
        return 1
    basics.save_ready(package, path)
    log(f"Wrote {path.relative_to(ROOT)}: read it, then merge it by PR (the evergreen stock).")
    return 0


def basics_stock(cfg: dict, history: History) -> int:
    """--stock: each approved topic's state and the number of ready, unpublished Basics episodes."""
    try:
        report = basics.stock(basics_topics(), history, basics_ready_dir(), cfg)
    except Exception as e:
        log(f"Stock report failed: {e}")
        return 1
    for r in report["rows"]:
        state = ("published" if r["published"] else "ready" if r["ready"] else
                 "package invalid: " + "; ".join(r["problems"]) if r["problems"] else "no package")
        log(f"  {r['id']}: {state}")
    log(f"Ready, unpublished Basics episodes: {len(report['ready'])}"
        + (f" ({', '.join(report['ready'])})" if report["ready"] else ""))
    return 0


def make_evergreen(cfg: dict, history: History, date: str, slot_key: str, pending: list[str], no_upload: bool,
                   force: bool) -> tuple[dict | None, list[str], str]:
    """"Publish next evergreen" (CAP-6 top-up; `--session evergreen --slot <session>`): the next ready Basics
    episode (approved, unpublished, a valid basics/ready package) into today's `slot_key` slot, else the next
    lesson through make_lesson_edition under that slot's key (only while lessons.enabled). A slot that already
    recorded a Basics topic or a lesson today re-makes that one for its missing platforms. Returns (made,
    pending, "basics" | "lesson"); made None = nothing to publish."""
    recorded = [v for v in history.uploaded() if v.get("brief_date") == date
                and v.get("session", "london") == slot_key and v.get("counts", True)]
    rec_topic = next((v.get("topic") for v in recorded if v.get("kind") == "basics" and v.get("topic")), None)
    if not any(v.get("episode") for v in recorded):
        topics = basics_topics()
        if rec_topic:
            topic = next((t for t in topics if t.get("id") == rec_topic), None)
            if topic is None:
                raise RuntimeError(f"this slot's recorded Basics topic {rec_topic} is no longer in basics/topics.yaml")
            log(f"This slot already recorded Basics topic {rec_topic}: making it again for {', '.join(pending)}")
            hist = history.excluding_slot(date, slot_key)
        else:
            ready = basics.stock(topics, history, basics_ready_dir(), cfg)["ready"]
            topic = next((t for t in topics if ready and t.get("id") == ready[0]), None)
            hist = history
        if topic is not None:
            log(f"Evergreen: the ready Basics episode {topic['id']} fills today's {slot_key} slot")
            return make_basics(cfg, hist, slot_key, date, topic=topic, ready_only=True), pending, "basics"
        log("Evergreen: no ready Basics episode in the stock; falling back to the next lesson")
    if not (cfg.get("lessons") or {}).get("enabled", False) and not no_upload:
        log("Evergreen: lessons are off (lessons.enabled is false), so nothing to publish in this slot.")
        return None, pending, "lesson"
    made, pending = make_lesson_edition(cfg, history, date, slot_key, pending, no_upload, counts=True, force=force)
    return made, pending, "lesson"


def build_material(made: dict, entry: dict, cfg: dict) -> dict:
    """The Shorts material of a made long video: Basics (concept segments) or triggered / recap (market)."""
    kind = entry.get("kind")
    if kind == "triggered":
        return material.build_triggered(made["trigger"], made["meta"], entry)
    if kind == "recap":
        return material.build_recap(made["recap"], made["meta"], entry)
    return material.build_basics(made["topic"], made["scenes"], entry, cfg)


def save_material(made: dict, entry: dict, cfg: dict, workdir: Path) -> None:
    """After a Basics / triggered / recap publish: its Shorts material (autopilot/material.py) merged into
    data/material/ (a later run for a missed platform adds its id) and a copy in the run's folder, which the
    workflow merges again after resetting to the latest main. A failure here is logged, never fatal (published)."""
    try:
        m = build_material(made, entry, cfg)
        material.save(m, workdir / "material.json")
        path = material.write(m, ROOT)
        log(f"Shorts material: {path.relative_to(ROOT)} ({len(m['segments'])} segments"
            + (f", {len(m['market']['hooks'])} hooks" if m.get("market") else "") + ")")
    except Exception as e:  # the video is out; the material can be rebuilt from package.json
        log(f"Shorts material not saved: {e}")


def publish_basics(made: dict, pending: list[str], cfg: dict) -> tuple[dict, list[str]]:
    """Publish one made Basics edition to each pending platform on its own (as publish_lesson): YouTube gets
    the 16:9 video through youtube.upload_lesson (no playlists; basics.review_window_hours), Facebook the 9:16
    video through facebook.publish_video (basics.fb_published). A failure on one is logged and never blocks
    (or repeats) the other. Returns (entry with the ids it got, failed platforms)."""
    entry, failed = made["entry"], []
    bc = cfg.get("basics") or {}
    meta = made["meta"]
    if "youtube" in pending:
        try:
            from autopilot import youtube
            res = youtube.upload_lesson(made["videos"]["16x9"], {k: meta[k] for k in ("title", "description", "tags",
                                                                                      "category_id")},
                                        made["thumbnail"], None, None, review_hours=bc.get("review_window_hours", 0),
                                        notify=cfg["upload"].get("notify_subscribers", True), log=log,
                                        playlists=False)
            entry["video_id"] = res["video_id"]
            if res.get("publish_at"):
                entry["publish_at"] = res["publish_at"]
            for err in res.get("errors") or []:
                log(f"YouTube Basics video uploaded, but: {err}")
        except Exception as e:
            log(f"YouTube Basics upload failed: {e}")
            failed.append("youtube")
    if "facebook" in pending:
        try:
            entry["fb_video_id"] = facebook.publish_video(
                made["videos"]["9x16"], meta.get("fb_title") or meta["title"],
                meta.get("fb_description") or meta["description"], cfg,
                published=bool(bc.get("fb_published", True)), log=log)
        except Exception as e:
            vid = getattr(e, "video_id", None)
            log(f"Facebook Basics video failed: {e}"
                + (f" (video {vid} exists on the Page; check or delete it there)" if vid else ""))
            failed.append("facebook")
    return entry, failed


def make_triggered(cfg: dict, history: History, trigger: dict, session_key: str, date: str) -> dict:
    """One triggered video (kind: triggered) from a trigger (autopilot/triggers.py): narration of the trigger's
    fetched data (triggered.write_script: 3-4 minutes, the subscribe ask after the cause, narration rules and the
    fact-check, whose failure stops it), the A/B voice with pauses, a 16:9 render with the coins diagram revealed
    step by step (YouTube only) and its package (written to the workdir; nothing is uploaded). Returns {"entry", "videos": {"16x9"}, "seconds", "workdir", "trigger", "scenes"}."""
    tc = cfg.get("triggers") or {}
    log(f"Trigger: {trigger['id']} · rule {trigger['rule']} ({trigger.get('rule_name', '')}) · "
        f"{', '.join(trigger.get('coins') or [])}" + (f" · cause: {trigger['cause']['title']}" if trigger.get("cause") else ""))
    try:  # the title / thumbnail rules stop it before anything is made
        title, words = triggered.check_packaging(trigger)
    except ValueError as e:
        raise RuntimeError(str(e)) from None
    log(f"Triggered title: {title} · thumbnail: {words}")
    workdir = ROOT / "output" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)
    plan = triggered.scene_plan(trigger)
    pkg = triggered.write_script(cfg, trigger, plan, log=log)  # narration rules + fact-check: a failure stops it
    (workdir / "package.json").write_text(json.dumps(
        {"trigger": trigger["id"], "scenes": [{"id": s["id"], "text": s["text"]} for s in pkg["scenes"]],
         "fact_check": pkg.get("fact_check")}, indent=2, ensure_ascii=False))
    (workdir / "trigger.json").write_text(json.dumps(trigger, indent=1, ensure_ascii=False))
    v = ab_voice(cfg["voice"], history, session_key)
    log(f"Voice: {v['name']}" + (" (A/B rotation)" if v.get("alternate") else ""))
    audio, total = narrate(v, pkg["scenes"], tc.get("max_seconds", TRIGGERED_MAX_SECONDS), workdir, pauses=True,
                           what="Triggered narration", log=log)
    music_files = sorted((ROOT / "music").glob("*.mp3"))
    music = random.choice(music_files) if music_files else None
    layout = lesson_slides.LANDSCAPE  # YouTube only: 16:9
    shape_dir = workdir / layout.name
    pics = triggered.render_slides(cfg, trigger, plan, layout, shape_dir)
    reveal.time_steps(pics, pkg["scenes"], audio, log=log)  # the diagram's parts fade in as they are named
    out = workdir / f"triggered_{layout.name}.mp4"
    render.build_video(audio, pics, lesson_video_cfg(cfg, layout), shape_dir, out, music=music)
    log(f"Rendered {out}")
    thumb = triggered.render_thumbnail(cfg, trigger, workdir / "thumbnail.jpg")
    meta = triggered.metadata(cfg, trigger)
    (workdir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    entry = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "brief_date": date,
        "session": session_key,
        "kind": "triggered",
        "trigger_id": trigger["id"],
        "title": meta["title"],
        "rule": trigger["rule"],
        "coins": list(trigger.get("coins") or []),
        "video_id": None,
        "seconds": round(total, 1),
        "voice": audio[0]["voice"] if audio else v["name"],
        "workdir": str(workdir.relative_to(ROOT)),
    }
    made = {"entry": entry, "videos": {layout.name: out}, "thumbnail": thumb, "meta": meta, "seconds": round(total, 1),
            "workdir": workdir, "trigger": trigger, "scenes": pkg["scenes"]}
    problems = material.validate(build_material(made, {**entry, "video_id": "-"}, cfg))  # makeable before publishing
    if problems:
        raise RuntimeError(f"Triggered Shorts material ({trigger['id']}): {'; '.join(problems)}")
    return made


def publish_triggered(made: dict, pending: list[str], cfg: dict, section: str = "triggers",
                      what: str = "triggered") -> tuple[dict, list[str]]:
    """Publish a made triggered (or recap: section "recap") video to YouTube only (16:9 through
    youtube.upload_lesson: no playlists, private then public after <section>.review_window_hours; its thumbnail).
    Facebook never gets it. Returns (entry with the id it got, failed platforms)."""
    entry, failed = made["entry"], []
    tc = cfg.get(section) or {}
    if "youtube" in pending:
        meta = made["meta"]
        try:
            from autopilot import youtube
            res = youtube.upload_lesson(made["videos"]["16x9"], {k: meta[k] for k in ("title", "description", "tags",
                                                                                      "category_id")},
                                        made["thumbnail"], None, None, review_hours=tc.get("review_window_hours", 0),
                                        notify=cfg["upload"].get("notify_subscribers", True), log=log,
                                        playlists=False)
            entry["video_id"] = res["video_id"]
            if res.get("publish_at"):
                entry["publish_at"] = res["publish_at"]
            for err in res.get("errors") or []:
                log(f"YouTube {what} video uploaded, but: {err}")
        except Exception as e:
            log(f"YouTube {what} upload failed: {e}")
            failed.append("youtube")
    return entry, failed


def make_recap(cfg: dict, history: History, session_key: str, date: str) -> dict:
    """The Saturday recap (kind: recap): the week's 2-3 biggest 7-day moves and their headline causes (recap.build
    on Coinbase 7-day candles + the CoinGecko top 50), narrated (recap.write_script: 4-5 minutes, the subscribe ask
    after the first move, narration rules + fact-check), the A/B voice, a 16:9 render, the mini-board thumbnail and
    the metadata. Returns made (as make_triggered)."""
    rc = cfg.get("recap") or {}
    problems = recap.packaging_problems()
    if problems:
        raise RuntimeError(f"Recap packaging: {'; '.join(problems)}")
    data, overview = recap.fetch(cfg, log=log)
    week = recap.build(data, overview)
    log("Recap moves: " + ", ".join(f"{s} {week['moves'][s]['change_7d']:+.1f}%" for s in week["coins"]))
    workdir = ROOT / "output" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)
    plan = recap.scene_plan(week)
    pkg = recap.write_script(cfg, week, plan, log=log)
    (workdir / "package.json").write_text(json.dumps(
        {"recap": week["id"], "scenes": [{"id": s["id"], "text": s["text"]} for s in pkg["scenes"]],
         "fact_check": pkg.get("fact_check")}, indent=2, ensure_ascii=False))
    (workdir / "recap.json").write_text(json.dumps(week, indent=1, ensure_ascii=False))
    v = ab_voice(cfg["voice"], history, session_key)
    log(f"Voice: {v['name']}" + (" (A/B rotation)" if v.get("alternate") else ""))
    audio, total = narrate(v, pkg["scenes"], rc.get("max_seconds", RECAP_MAX_SECONDS), workdir, pauses=True,
                           what="Recap narration", log=log)
    music_files = sorted((ROOT / "music").glob("*.mp3"))
    music = random.choice(music_files) if music_files else None
    layout = lesson_slides.LANDSCAPE
    shape_dir = workdir / layout.name
    pics = recap.render_slides(cfg, week, plan, layout, shape_dir)
    out = workdir / f"recap_{layout.name}.mp4"
    render.build_video(audio, pics, lesson_video_cfg(cfg, layout), shape_dir, out, music=music)
    log(f"Rendered {out}")
    thumb = recap.render_thumbnail(cfg, week, workdir / "thumbnail.jpg")
    meta = recap.metadata(cfg, week)
    (workdir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    entry = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "brief_date": date,
             "session": session_key, "kind": "recap", "week": week["week"], "title": meta["title"],
             "coins": list(week["coins"]), "video_id": None, "seconds": round(total, 1),
             "voice": audio[0]["voice"] if audio else v["name"], "workdir": str(workdir.relative_to(ROOT))}
    made = {"entry": entry, "videos": {layout.name: out}, "thumbnail": thumb, "meta": meta, "seconds": round(total, 1),
            "workdir": workdir, "recap": week, "scenes": pkg["scenes"]}
    problems = material.validate(build_material(made, {**entry, "video_id": "-"}, cfg))
    if problems:
        raise RuntimeError(f"Recap Shorts material ({week['id']}): {'; '.join(problems)}")
    return made


def short_lesson_materials(history: History) -> list[dict]:
    """Shorts material rebuilt from published BTC / ETH lessons (autopilot/lesson_material.py); [] when there
    are none or the curriculum can't be read (logged)."""
    if not any(v.get("kind") == "lesson" and v.get("episode") for v in history.uploaded()):
        return []
    try:
        curriculum = lessons.load_curriculum(ROOT / "lessons" / "curriculum.yaml")
        glossary = lessons.load_glossary(ROOT / "lessons" / "glossary.yaml")
    except Exception as e:
        log(f"Shorts: lesson material skipped (curriculum / glossary unreadable: {e})")
        return []
    return lesson_material.from_history(history, curriculum, glossary, log=log)


def make_short(cfg: dict, history: History, session_key: str, date: str) -> dict | None:
    """One standalone Short (kind: short; autopilot/shorts.py) from the Shorts material in data/material/
    (shorts.pick: a market Short from a triggered / recap video under 3 days old with an unused hook candidate,
    else a concept Short from the oldest Basics / Lesson material with an unused segment): a new 30-40 s script
    (Gemini + shorts.check_script, 3 attempts; packaging rules), the A/B voice with pauses, 9:16 slides (hook card
    = frame 0), render, metadata. None = nothing to make (logged). Returns made for main.publish."""
    now = datetime.now(timezone.utc)
    materials = shorts.load_materials(ROOT, log=log) + short_lesson_materials(history)
    earlier, hooks, skip = shorts.fingerprints(history), shorts.used_hooks(history), set()
    while True:  # originality guard: a segment whose script stays too close to an earlier Short's is passed over
        picked = shorts.pick(materials, history, now, log=log, skip=skip)
        if picked is None:
            log("Shorts: no market hook or Basics / Lesson segment left unused; nothing to publish in this slot.")
            return None
        what, m, which = picked
        seg, segment = (None, shorts.hook_id(which)) if what == "market" else (which, which["id"])
        log(f"Short ({what}): {shorts.key(m)} · {segment} ("
            + (m["market"]["hooks"][which] if what == "market" else seg["term"]) + ")")
        try:
            pkg = (shorts.write_market(cfg, m, which, log=log, earlier=earlier, hooks=hooks) if what == "market"
                   else shorts.write_concept(cfg, m, seg, log=log, earlier=earlier, hooks=hooks))
            break
        except shorts.TooClose as e:
            log(f"Originality guard: {shorts.key(m)} · {segment}: {e}; moving to another segment")
            skip.add((shorts.key(m), segment))
    workdir = ROOT / "output" / now.strftime("%Y%m%d-%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "package.json").write_text(json.dumps({"material": shorts.key(m), "segment": segment, **pkg},
                                                     indent=2, ensure_ascii=False))
    v = ab_voice(cfg["voice"], history, session_key)
    log(f"Voice: {v['name']}" + (" (A/B rotation)" if v.get("alternate") else ""))
    audio, total = narrate(v, pkg["scenes"], cfg["video"]["max_seconds"], workdir, pauses=True,
                           what="Short narration", log=log)
    if what == "market":
        pics, thumb = shorts.render_market_slides(cfg, m, pkg, workdir)
    else:
        pics, thumb = shorts.render_slides(cfg, m, seg, pkg, workdir)
    reveal.time_steps(pics, pkg["scenes"], audio, log=log)
    music_files = sorted((ROOT / "music").glob("*.mp3"))
    out = workdir / "short.mp4"
    render.build_video(audio, pics, cfg, workdir, out, music=random.choice(music_files) if music_files else None)
    log(f"Rendered {out}")
    meta = shorts.metadata(cfg, m, seg, pkg)
    (workdir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    fb_caption = shorts.reel_caption(meta, cfg)
    (workdir / "caption_fb.txt").write_text(fb_caption, encoding="utf-8")
    entry = {"date": now.isoformat(timespec="seconds"), "brief_date": date, "session": session_key, "kind": "short",
             "short_kind": what, "material": shorts.key(m), "segment": segment, "source_video": m.get("youtube_id"),
             "hook": pkg["hook"], "fingerprint": pkg["fingerprint"], "title": meta["title"], "video_id": None,
             "seconds": round(total, 1),
             "voice": audio[0]["voice"] if audio else v["name"], "workdir": str(workdir.relative_to(ROOT))}
    return {"entry": entry, "video": out, "thumbnail": thumb, "meta": meta, "fb_caption": fb_caption, "material": m}


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
                   help="asia | london | newyork | gold | news_morning | news_midday | news_evening | lesson | basics | triggered | recap | "
                        "short_a | short_b | "
                        "auto (market edition by UTC time)")
    p.add_argument("--platforms", default="all",
                   help="all | youtube | facebook | youtube,facebook (limited to the edition's own platforms)")
    p.add_argument("--scheduled", action="store_true",
                   help="timed run (schedule / outside timer): weekend rule, late/early skip, once per edition per day")
    p.add_argument("--as-edition", action="store_true",
                   help="manual run that counts as today's edition, so its timed run then skips")
    p.add_argument("--prepare", default="", metavar="TOPIC_ID|next",
                   help="Crypto Basics (with --session basics): write the ready package of an approved topic to "
                        "basics/ready/<id>.yaml (narrated + checked; never uploaded)")
    p.add_argument("--stock", action="store_true",
                   help="Crypto Basics (with --session basics): report the ready, unpublished episodes")
    p.add_argument("--slot", default="",
                   help="top-up (session lesson only): fill today's slot of this edition (a config.yaml session) "
                        "with the next unpublished episode, once per slot; the lesson's days and time window "
                        "don't apply")
    p.add_argument("--trigger", default="", metavar="ID|PATH",
                   help="triggered edition (with --session triggered): the trigger to answer (a fixture path)")
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
            log("The sample lesson is never published: --lesson-sample makes it only (as with --no-upload).")
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
    if args.prepare or args.stock:
        if kind != "basics":
            log("--prepare / --stock work only with --session basics.")
            return 1
        return basics_stock(cfg, history) if args.stock else prepare_basics(cfg, history, args.prepare)
    # slot_key: the edition slot this run fills and is recorded under (a top-up fills another edition's)
    slot_key = (args.slot or "").strip().lower() or session_key
    topup = bool((args.slot or "").strip())
    if topup and kind not in ("lesson", "evergreen"):
        log(f"--slot works only with --session lesson or evergreen (the {label} edition can't top up another slot).")
        return 1
    if kind == "evergreen" and not topup:
        log("The evergreen edition needs --slot <session>: the slot it fills (e.g. --slot recap).")
        return 1
    if kind == "evergreen" and slot_key == session_key:
        log("--slot evergreen can't fill itself; name another edition's slot.")
        return 1
    if topup and slot_key not in cfg.get("sessions", {}):
        log(f"Unknown slot '{slot_key}'. Choose one of: {', '.join(cfg.get('sessions', {}))}")
        return 1
    if topup and cfg["sessions"][slot_key].get("kind") == "post":
        log(f"The {slot_key} slot is a Facebook news post; a {'lesson' if kind == 'lesson' else 'video'} top-up "
            "can't fill it.")
        return 1
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

    if topup:
        log(f"Top-up: the {label} edition fills today's {slot_key} slot (once per slot; the lesson's days and "
            "time window don't apply).")
    elif args.scheduled and now.weekday() >= 5 and session_key not in cfg.get("weekend_sessions", []):
        log(f"Weekend: forex is closed, so the {label} edition is skipped today.")
        return 0
    days = [str(d).strip().lower()[:3] for d in session.get("days") or []]
    if args.scheduled and not topup and days and WEEKDAYS[now.weekday()] not in days:
        log(f"The {label} edition runs only on {', '.join(days)}; skipped today ({WEEKDAYS[now.weekday()]}).")
        return 0
    if kind == "lesson" and not (cfg.get("lessons") or {}).get("enabled", False) \
            and (args.scheduled or not args.no_upload):
        log("Lessons are off (lessons.enabled is false in config.yaml), so the lesson is skipped. "
            "Use --no-upload on a manual run to make one anyway.")
        return 0
    if kind == "evergreen" and args.scheduled and not (cfg.get("evergreen") or {}).get("enabled", False):
        log("evergreen.enabled is false in config.yaml (the evergreen top-up is dark), so the timed run is skipped. "
            "A manual run (Run workflow with `slot`, no `scheduled`) still tops the slot up.")
        return 0
    if kind == "basics" and args.scheduled and not (cfg.get("basics") or {}).get("enabled", False):
        log("basics.enabled is false in config.yaml (Crypto Basics is dark), so the timed run is skipped. "
            "A manual run (Run workflow, no `scheduled`) still makes and publishes it.")
        return 0
    trigger = None
    if kind == "triggered":
        if args.scheduled and not (cfg.get("triggers") or {}).get("enabled", False):
            log("triggers.enabled is false in config.yaml (triggered videos are dark), so the timed run is skipped. "
                "A manual run (Run workflow with `trigger`, no `scheduled`) still makes it.")
            return 0
        if not (args.trigger or "").strip():
            log("The triggered edition needs --trigger <trigger id|fixture path>.")
            return 1
        try:
            trigger = triggers.load(args.trigger.strip(), ROOT)
        except Exception as e:
            log(f"Trigger {args.trigger}: {e}")
            return 1
        if args.scheduled:  # a timed triggered run goes by the trigger's due time, not start_utc
            late = round((now - datetime.fromisoformat(trigger["due_utc"])).total_seconds() / 60)
            window = int(float((cfg.get("triggers") or {}).get("publish_window_hours", 3)) * 60)
            log(f"Timed run for trigger {trigger['id']} (due {trigger['due_utc']}, started {late:+d} min)")
            if late < -30:
                log(f"Trigger {trigger['id']} is not due yet (due {trigger['due_utc']}); skipped.")
                return 0
            if late > window:
                log(f"Trigger {trigger['id']} is more than {window} min past its due time; skipped.")
                return 0
    if kind == "short" and args.scheduled and not (cfg.get("shorts") or {}).get("enabled", False):
        log("shorts.enabled is false in config.yaml (standalone Shorts are dark), so the timed run is skipped. "
            "A manual run (Run workflow, no `scheduled`) still makes and publishes one.")
        return 0
    if kind == "recap" and args.scheduled and not (cfg.get("recap") or {}).get("enabled", False):
        log("recap.enabled is false in config.yaml (the Saturday recap is dark), so the timed run is skipped. "
            "A manual run (Run workflow, no `scheduled`) still makes it.")
        return 0
    if args.scheduled and not topup and start:
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
    if topup and not args.force and not args.no_upload:
        other = sorted({v.get("kind", "market") for v in history.uploaded() if v.get("brief_date") == today
                        and v.get("session", "london") == slot_key and v.get("counts", True)
                        and not v.get("episode") and not (kind == "evergreen" and v.get("kind") == "basics")})
        if other:
            log(f"Today's {slot_key} slot already published a {', '.join(other)} upload; no "
                f"{'lesson' if kind == 'lesson' else 'evergreen'} top-up.")
            return 0
    if (args.scheduled or topup) and not args.force and not args.no_upload and kind != "triggered":
        done = [x for x in pending if history.published_on(today, slot_key, x)]
        if done:
            log((f"Today's {slot_key} slot ({today}) is" if topup else f"The {label} edition for {today} is")
                + f" already published on {', '.join(done)}.")
        if done and len(done) == len(pending):
            log("Nothing to do.")
            return 0
        if not pending:
            log(f"No platform to publish the {label} edition to; nothing to do.")
            return 0
        remake = bool(done)
        pending = [x for x in pending if x not in done]
    if not args.scheduled and not topup:
        log("Manual run: makes and publishes now" +
            (" and fills today's slot (the timed run will skip)." if args.as_edition
             else "; the timed run of this edition still goes ahead."))
    if not pending and not args.no_upload:
        log("No platform to publish to; making it only.")

    log(f"Edition: {label} → {', '.join(pending) or 'no upload'}")
    try:
        if kind == "post":
            entry, failed = make_post(cfg, history, args, session_key, pending)
        elif kind == "lesson":
            made, pending = make_lesson_edition(cfg, history, today, slot_key, pending, args.no_upload,
                                                counts=bool(args.scheduled or args.as_edition or topup),
                                                force=args.force)
            if made is None:
                return 0
            entry, failed = publish_lesson(made, pending, cfg)
        elif kind == "evergreen":
            made, pending, what = make_evergreen(cfg, history, today, slot_key, pending, args.no_upload, args.force)
            if made is None:
                return 0
            entry, failed = (publish_basics if what == "basics" else publish_lesson)(made, pending, cfg)
            entry["evergreen"] = True
        elif kind == "triggered":
            done = [v for v in history.uploaded() if v.get("trigger_id") == trigger["id"] and v.get("video_id")]
            if done and pending and not args.force:
                log(f"Trigger {trigger['id']} is already published (video {done[0]['video_id']}); nothing to do.")
                return 0
            made = make_triggered(cfg, history, trigger, session_key, today)
            entry, failed = publish_triggered(made, [x for x in pending if x == "youtube"], cfg)
        elif kind == "recap":
            if not args.force and recap.week_has_triggered(history, now):
                log("Recap skipped: a triggered video already published this ISO week (the recap covers quiet weeks).")
                return 0
            made = make_recap(cfg, history, session_key, today)
            entry, failed = publish_triggered(made, [x for x in pending if x == "youtube"], cfg, "recap", "recap")
        elif kind == "short":
            made = make_short(cfg, history.excluding_slot(today, session_key) if remake else history,
                              session_key, today)
            if made is None:
                return 0
            entry, failed = publish(made, pending, cfg)
            task = shorts.studio_task(entry.get("video_id"), made["material"])
            if task:
                log(task)
        elif kind == "basics":
            # re-making for a platform it missed: the history the first run saw (same A/B voice)
            made = make_basics(cfg, history.excluding_slot(today, session_key) if remake else history,
                               session_key, today)
            if made is None:
                return 0
            entry, failed = publish_basics(made, pending, cfg)
        else:
            # re-making an edition for a platform it missed: use the history the first run saw
            made = make_brief(cfg, history.excluding_slot(today, session_key) if remake else history,
                              args, session_key)
            entry, failed = publish(made, pending, cfg)
    except Exception as e:
        what = dict(post="Post", lesson="Lesson", basics="Basics", evergreen="Evergreen", triggered="Triggered",
                    recap="Recap", short="Short")
        log(f"{what.get(kind, 'Brief')} "
            f"failed: {e}")
        return 1
    if any(entry.get(k) for k in ID_KEYS):
        entry["trigger"] = "topup" if topup else "timed" if args.scheduled else "manual"
        entry["counts"] = bool(args.scheduled or args.as_edition or topup)
        entry["platforms"] = [x for x, keys in PLATFORM_IDS.items() if any(entry.get(k) for k in keys)]
        workdir = ROOT / entry.pop("workdir")
        # the workflow merges this file into the latest data/history.json (safe with parallel runs)
        (workdir / "history_entry.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False))
        history.add(entry)
        history.save()
        if entry.get("kind") in ("basics", "triggered", "recap"):
            save_material(made, entry, cfg, workdir)
    if failed:
        log(f"Not published on: {', '.join(failed)} (see the errors above)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
