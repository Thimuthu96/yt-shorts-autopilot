"""Upload to YouTube with SEO metadata (YouTube Data API v3)."""
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import seo

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _client():
    missing = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing YouTube secrets: {', '.join(missing)}")
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _safe(text: str) -> str:
    return re.sub(r"[<>]", "", text or "").strip()


def _stories(pkg: dict, data: dict) -> list[str]:
    """'Source: headline (link)' for the news items the script used."""
    by_title = {n["title"].lower(): n for n in data.get("news", [])}
    out = []
    for t in pkg.get("headlines_used", [])[:6]:
        n = by_title.get(str(t).lower())
        if not n:
            continue
        link = n["link"] if n.get("link") and "news.google.com" not in n["link"] else ""
        out.append(f"• {n['source']}: {_safe(n['title'])}" + (f" {link}" if link else ""))
    return out


def _credits(data: dict) -> str:
    if data.get("kind") == "gold":
        return ("Method: rule-based technical read of hourly XAU/USD (EMA trend, market structure, prior-day, "
                "Asian-session and weekly ranges, liquidity sweeps, ATR ranges), not a forecast of certainty. "
                "Data: gold prices from PAXG hourly candles (Kraken/Coinbase) aligned to spot XAU/USD "
                "(Swissquote); US yields from the US Treasury; CPI from the BLS; forex reference rates via "
                "Frankfurter; economic calendar from ForexFactory.")
    extra = []
    if data.get("gold"):
        extra.append("gold from PAXG hourly candles aligned to spot XAU/USD")
    if data.get("macro"):
        extra.append("US yields from the US Treasury and CPI from the BLS")
    return ("Data: crypto prices from Coinbase; forex reference rates via Frankfurter (ECB and other central "
            "banks); economic calendar from ForexFactory" + "".join(f"; {x}" for x in extra) + ".")


def build_metadata(pkg: dict, data: dict, cfg: dict, edition: str = "") -> dict:
    """Title, description and tags tuned for search (see seo.py); falls back to the writer's
    output when there is no lead story (e.g. tests with plain data)."""
    title = _safe(seo.title(pkg.get("title", ""), data, edition))[:95]
    hashtags = seo.hashtags(data, pkg.get("hashtags", []))
    parts = [_safe(pkg.get("description", ""))]
    numbers = seo.key_numbers(data)
    if numbers:
        parts.append(("Key levels:\n" if data.get("kind") == "gold" else "Key numbers:\n") + "\n".join(numbers))
    stories = _stories(pkg, data)
    if stories:
        parts.append("Stories mentioned:\n" + "\n".join(stories))
    ahead = seo.watch(data)
    if ahead:
        parts.append("What to watch:\n" + "\n".join(ahead))
    parts.append(seo.schedule(cfg))
    parts.append(_credits(data))
    disclaimer = (cfg.get("upload", {}).get("disclaimer") or "").strip()
    if disclaimer:
        parts.append("⚠️ " + disclaimer)
    parts.append(" ".join(hashtags))
    description = "\n\n".join(p for p in parts if p)[:4900]

    tags, seen, total = [], set(), 0
    for t in seo.tag_seeds(data, edition) + list(pkg.get("tags", [])):
        t = _safe(t).replace(",", "")
        cost = len(t) + (2 if " " in t else 0) + 1  # YouTube counts quotes + separator
        if t and t.lower() not in seen and total + cost <= 480:
            seen.add(t.lower())
            tags.append(t)
            total += cost
    return {"title": title, "description": description, "tags": tags}


def upload(video_path: Path, meta: dict, cfg: dict, log=print) -> str:
    up = cfg["upload"]
    status = {
        "privacyStatus": up["privacy_status"],
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": bool(up.get("contains_synthetic_media", False)),
    }
    hours = float(up.get("review_window_hours") or 0)
    if hours > 0 and up["privacy_status"] == "public":
        publish_at = datetime.now(timezone.utc) + timedelta(hours=hours)
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    lang = cfg["channel"].get("language", "en")
    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": str(up.get("category_id", "27")),
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": status,
    }
    yt = _client()
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media,
                             notifySubscribers=bool(up.get("notify_subscribers", True)))
    response, retries = None, 0
    while response is None:
        try:
            st, response = req.next_chunk()
            if st:
                log(f"Upload {int(st.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retries < 5:
                retries += 1
                time.sleep(2 ** retries)
                continue
            if e.resp.status in (400, 403) and re.search(r"quotaExceeded|uploadLimitExceeded|dailyLimitExceeded",
                                                         str(e)):
                raise RuntimeError("YouTube upload limit reached for today (the API allows about 6 uploads "
                                   "a day: 1,600 of 10,000 quota units each; it resets at midnight Pacific "
                                   "time). The video is saved in the run's artifacts.") from e
            raise
    vid = response["id"]
    log(f"Uploaded: https://youtube.com/shorts/{vid} (status: {status['privacyStatus']}"
        + (f", goes public {status['publishAt']}" if "publishAt" in status else "") + ")")
    return vid


def set_thumbnail(video_id: str, image: Path, log=print) -> bool:
    """Try to set a custom thumbnail. YouTube only allows this for some channels/Shorts,
    so a refusal is logged and ignored (the video's opening frame is the thumbnail design)."""
    try:
        yt = _client()
        yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(image), mimetype="image/jpeg")).execute()
        log("Custom thumbnail set")
        return True
    except HttpError as e:
        reason = getattr(e, "reason", "") or str(e)[:200]
        log(f"Custom thumbnail not accepted ({e.resp.status}: {reason}); the opening frame is used instead")
    except Exception as e:  # never fail the run over a thumbnail
        log(f"Custom thumbnail skipped: {e}")
    return False
