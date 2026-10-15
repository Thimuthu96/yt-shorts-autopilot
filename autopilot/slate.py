"""The crypto slate's upload budget (weekly-slate.md; crypto-pivot epic 5): at most 3 YouTube uploads per UTC day,
and 3-4 long videos per ISO week (UTC).

    day_uploads(history, date)            YouTube uploads recorded for that UTC day (distinct video ids)
    long_videos(history, now)             the ISO week's counting long uploads (basics, lesson, triggered, recap)
    short_skip(history, state, key, now, cfg) -> reason | ''
        A timed Short is skipped when the day already has `day_cap` YouTube uploads; Short B (23:00) also yields
        its slot to a triggered video that published or is due that day on Wednesday or Thursday (`yield_days`),
        or on any other day that already has a long video (a recap or a top-up), so the day stays at 3.
    hold_reason(history, now, cfg) -> reason | ''
        The trigger poll's check before it dispatches: a triggered video that would be the day's fourth upload
        holds to 00:00 UTC next day (triggers.check moves its due time).
"""
from datetime import datetime, timedelta, timezone

DAY_CAP = 3  # cfg slate.day_cap: YouTube uploads per UTC day
WEEK_FLOOR = 3  # cfg slate.week_floor: long videos per ISO week (UTC) …
WEEK_CAP = 4  # cfg slate.week_cap: … and at most this many
YIELD_DAYS = ("wed", "thu")  # cfg slate.yield_days: a triggered video takes Short B's slot on these days
LONG_KINDS = ("basics", "lesson", "triggered", "recap")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def limits(cfg: dict | None) -> dict:
    sc = (cfg or {}).get("slate") or {}
    return {"day_cap": int(sc.get("day_cap", DAY_CAP)), "week_floor": int(sc.get("week_floor", WEEK_FLOOR)),
            "week_cap": int(sc.get("week_cap", WEEK_CAP)),
            "yield_days": [str(d).lower()[:3] for d in sc.get("yield_days", YIELD_DAYS)]}


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


def _trigger_today(history, state: dict | None, date: str) -> str:
    """'' or why a triggered video belongs to that day (published, or a pending / dispatched trigger due then)."""
    if any(v.get("kind") == "triggered" for v in day_uploads(history, date)):
        return "a triggered video published today"
    for t in (state or {}).get("triggers") or []:
        if t.get("status") in ("pending", "dispatched") and str(t.get("due_utc", ""))[:10] == date:
            return f"trigger {t.get('id')} is due today"
    return ""


def short_skip(history, state: dict | None, session_key: str, now: datetime, cfg: dict | None = None) -> str:
    """'' = the timed Short goes ahead, else why it skips (logged by main)."""
    lim = limits(cfg)
    now = now.astimezone(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    ups = day_uploads(history, date)
    if len(ups) >= lim["day_cap"]:
        return f"today already has {len(ups)} YouTube uploads (at most {lim['day_cap']} a day)"
    if session_key != "short_b":
        return ""
    why = _trigger_today(history, state, date)
    if not why:
        return ""
    day = WEEKDAYS[now.weekday()]
    if day in lim["yield_days"]:
        return f"{why}; on {day.title()} a triggered video takes Short B's slot (at most {lim['day_cap']} uploads a day)"
    longs = [v for v in ups if v.get("kind") in LONG_KINDS and v.get("kind") != "triggered"]
    if longs:
        return (f"{why} and today already has a long video ({longs[0].get('kind')}): the triggered video takes "
                f"Short B's slot (at most {lim['day_cap']} uploads a day)")
    return ""


def hold_reason(history, now: datetime, cfg: dict | None = None) -> str:
    """'' = a due triggered video may publish now, else why it holds to 00:00 UTC next day."""
    lim = limits(cfg)
    ups = day_uploads(history, now.astimezone(timezone.utc).strftime("%Y-%m-%d"))
    if len(ups) >= lim["day_cap"]:
        return f"today already has {len(ups)} YouTube uploads (at most {lim['day_cap']} a day)"
    return ""


def next_day(now: datetime) -> datetime:
    """00:00 UTC of the next UTC day."""
    now = now.astimezone(timezone.utc)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
