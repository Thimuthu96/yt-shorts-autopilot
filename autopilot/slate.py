"""The crypto slate's upload budget (weekly-slate.md; crypto-pivot epic 5, epic-shorts-reach 6.5): at most 3 Shorts
per UTC day on YouTube, 1 long video a day for the planned editions (a triggered video comes on top: it is never held,
so a day with a planned long video and a trigger has 2 long videos, ≤ 5 uploads), and 2-4 long videos per ISO week (UTC).

    day_uploads(history, date)            YouTube uploads recorded for that UTC day (distinct video ids; manual ones too)
    day_shorts(history, date)             … of them the Shorts (kind short, plus legacy market / gold / none)
    day_longs(history, date)              … of them the long videos (LONG_KINDS: basics, lesson, triggered, recap)
    long_videos(history, now)             the ISO week's counting long uploads (basics, lesson, triggered, recap)
    short_skip(history, now, cfg) -> reason | ''
        A timed Short is skipped when the day already has `shorts_day_cap` (3) Shorts. Long videos never take a
        Short's slot (Short B no longer yields to a triggered video).
    Triggered videos are never held by the daily budget (owner, 2026-10-21: "trigger first, same day"): the trigger
    poll dispatches a due trigger within its own limits (autopilot/triggers.py), and Basics / Lesson still run that
    day. `long_day_cap` (1) limits the evergreen top-up (main.floor_top_up waits when the day has that many long
    videos, a triggered one included).
"""
from datetime import datetime, timezone

SHORTS_DAY_CAP = 3  # cfg slate.shorts_day_cap: YouTube Shorts per UTC day (old configs: slate.day_cap)
LONG_DAY_CAP = 1  # cfg slate.long_day_cap: long YouTube videos per UTC day before a top-up waits (triggers exempt)
WEEK_FLOOR = 2  # cfg slate.week_floor: long videos per ISO week (UTC) …
WEEK_CAP = 4  # cfg slate.week_cap: … and at most this many
LONG_KINDS = ("basics", "lesson", "triggered", "recap")


def limits(cfg: dict | None) -> dict:
    """The budget numbers from cfg `slate`; an old config's `day_cap` becomes the Shorts cap (`yield_days` ignored)."""
    sc = (cfg or {}).get("slate") or {}
    return {"shorts_day_cap": int(sc.get("shorts_day_cap", sc.get("day_cap", SHORTS_DAY_CAP))),
            "long_day_cap": int(sc.get("long_day_cap", LONG_DAY_CAP)),
            "week_floor": int(sc.get("week_floor", WEEK_FLOOR)), "week_cap": int(sc.get("week_cap", WEEK_CAP))}


def _rows(history) -> list[dict]:
    return history.uploaded() if hasattr(history, "uploaded") else list(history or [])


def day_uploads(history, date: str) -> list[dict]:
    """The YouTube uploads of that UTC day (brief_date), one row per video id."""
    seen, out = set(), []
    for v in _rows(history):
        vid = v.get("video_id")
        if vid and v.get("brief_date") == date and vid not in seen:
            seen.add(vid)
            out.append(v)
    return out


def day_shorts(history, date: str) -> list[dict]:
    """That UTC day's YouTube Shorts: every upload whose kind is not a long one."""
    return [v for v in day_uploads(history, date) if v.get("kind") not in LONG_KINDS]


def day_longs(history, date: str) -> list[dict]:
    """That UTC day's long YouTube videos (basics, lesson, triggered, recap)."""
    return [v for v in day_uploads(history, date) if v.get("kind") in LONG_KINDS]


def _week(date: str) -> tuple[int, int]:
    return datetime.fromisoformat(date[:10]).isocalendar()[:2]


def long_videos(history, now: datetime) -> list[dict]:
    """The ISO week's counting long YouTube uploads (manual review runs with counts: false left out)."""
    week, seen, out = now.astimezone(timezone.utc).isocalendar()[:2], set(), []
    for v in _rows(history):
        vid = v.get("video_id")
        if (vid and v.get("kind") in LONG_KINDS and v.get("counts", True) and v.get("brief_date")
                and _week(v["brief_date"]) == week and vid not in seen):
            seen.add(vid)
            out.append(v)
    return out


def short_skip(history, now: datetime, cfg: dict | None = None) -> str:
    """'' = the timed Short goes ahead, else why it skips (logged by main). Only the Shorts cap counts."""
    cap = limits(cfg)["shorts_day_cap"]
    shorts = day_shorts(history, now.astimezone(timezone.utc).strftime("%Y-%m-%d"))
    if len(shorts) >= cap:
        return f"today already has {len(shorts)} Shorts on YouTube (at most {cap} Shorts a day)"
    return ""
