"""The crypto slate's upload budget (weekly-slate.md; crypto-pivot epic 5, epic-shorts-reach 6.5): at most 3 Shorts
and 1 long video per UTC day on YouTube (≤ 4 uploads a day), and 2-4 long videos per ISO week (UTC).

    day_uploads(history, date)            YouTube uploads recorded for that UTC day (distinct video ids; manual ones too)
    day_shorts(history, date)             … of them the Shorts (kind short, plus legacy market / gold / none)
    day_longs(history, date)              … of them the long videos (LONG_KINDS: basics, lesson, triggered, recap)
    long_videos(history, now)             the ISO week's counting long uploads (basics, lesson, triggered, recap)
    short_skip(history, state, key, now, cfg) -> reason | ''
        A timed Short is skipped when the day already has `shorts_day_cap` (3) Shorts. Long videos never take a
        Short's slot (Short B no longer yields to a triggered video); `state` (the trigger state) is unused.
    hold_reason(history, now, cfg) -> reason | ''
        The trigger poll's check before it dispatches: a triggered video holds to 00:00 UTC next day when the day
        already has `long_day_cap` (1) long video, or when a standing long edition (an enabled Basics / Lesson
        session due today: `days`, `start_utc` + `max_late_minutes` not passed) is still to come.
"""
from datetime import datetime, timedelta, timezone

SHORTS_DAY_CAP = 3  # cfg slate.shorts_day_cap: YouTube Shorts per UTC day (old configs: slate.day_cap)
LONG_DAY_CAP = 1  # cfg slate.long_day_cap: long YouTube videos per UTC day
WEEK_FLOOR = 2  # cfg slate.week_floor: long videos per ISO week (UTC) …
WEEK_CAP = 4  # cfg slate.week_cap: … and at most this many
LONG_KINDS = ("basics", "lesson", "triggered", "recap")
STANDING = {"basics": "basics", "lesson": "lessons"}  # standing long editions: session kind → its config section
MAX_LATE_MINUTES = 180  # cfg max_late_minutes (main's late window)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


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


def short_skip(history, state: dict | None, session_key: str, now: datetime, cfg: dict | None = None) -> str:
    """'' = the timed Short goes ahead, else why it skips (logged by main). Only the Shorts cap counts."""
    cap = limits(cfg)["shorts_day_cap"]
    shorts = day_shorts(history, now.astimezone(timezone.utc).strftime("%Y-%m-%d"))
    if len(shorts) >= cap:
        return f"today already has {len(shorts)} Shorts on YouTube (at most {cap} Shorts a day)"
    return ""


def _still_due(history, now: datetime, cfg: dict | None) -> str:
    """'' or the label + time of a standing long edition (enabled Basics / Lesson) still to come today."""
    cfg = cfg or {}
    now = now.astimezone(timezone.utc)
    date, day = now.strftime("%Y-%m-%d"), WEEKDAYS[now.weekday()]
    late = int(cfg.get("max_late_minutes", MAX_LATE_MINUTES))
    ups = day_uploads(history, date)
    for key, s in (cfg.get("sessions") or {}).items():
        section = STANDING.get((s or {}).get("kind"))
        start = (s or {}).get("start_utc")
        if not section or not start or not (cfg.get(section) or {}).get("enabled", False):
            continue
        days = [str(d).strip().lower()[:3] for d in s.get("days") or []]
        if days and day not in days:
            continue
        if any(v.get("session") == key or v.get("kind") == s["kind"] for v in ups):
            continue  # already published today
        h, m = (int(x) for x in str(start).split(":"))
        if now <= now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(minutes=late):
            return f"today's {s.get('label') or key} ({start} UTC)"
    return ""


def hold_reason(history, now: datetime, cfg: dict | None = None) -> str:
    """'' = a due triggered video may publish now, else why it holds to 00:00 UTC next day."""
    cap = limits(cfg)["long_day_cap"]
    longs = day_longs(history, now.astimezone(timezone.utc).strftime("%Y-%m-%d"))
    if len(longs) >= cap:
        what = f"a {longs[0].get('kind')} long video" if longs else f"{len(longs)} long videos"
        return f"today already has {what} (at most {cap} long video{'s' * (cap != 1)} a day)"
    due = _still_due(history, now, cfg)
    if due:
        return f"{due} is still to come (at most {cap} long video{'s' * (cap != 1)} a day)"
    return ""


def next_day(now: datetime) -> datetime:
    """00:00 UTC of the next UTC day."""
    now = now.astimezone(timezone.utc)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
