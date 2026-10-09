"""Upload to YouTube with SEO metadata (YouTube Data API v3).

Daily Shorts: upload() / set_thumbnail() request only SCOPES (youtube.upload), as always.
Lessons: upload_lesson() / delete_video() use their own client with LESSON_SCOPES (adds playlists and
analytics read); they need a refresh token made by get_token.py with those scopes.
Owner's live test: python -m autopilot.youtube test-lesson <mp4> <thumbnail> [--days 30]
"""
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
LESSON_SCOPES = SCOPES + ["https://www.googleapis.com/auth/youtube",  # playlists, delete
                          "https://www.googleapis.com/auth/yt-analytics.readonly"]
PUBLISH_AT = "%Y-%m-%dT%H:%M:%S.000Z"
QUOTA_MESSAGE = ("YouTube upload limit reached for today (the API allows about 6 uploads a day: 1,600 of "
                 "10,000 quota units each; it resets at midnight Pacific time). The video is saved in the "
                 "run's artifacts.")
LESSON_BRAND = "CryptoFX Daily trading lessons"


def _client(scopes: list[str] = SCOPES):
    missing = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing YouTube secrets: {', '.join(missing)}")
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=list(scopes),
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
        status["publishAt"] = publish_at.strftime(PUBLISH_AT)

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
    vid = _insert(yt, video_path, body, bool(up.get("notify_subscribers", True)), log)
    log(f"Uploaded: https://youtube.com/shorts/{vid} (status: {status['privacyStatus']}"
        + (f", goes public {status['publishAt']}" if "publishAt" in status else "") + ")")
    return vid


def _insert(yt, video_path: Path, body: dict, notify: bool, log=print) -> str:
    """Resumable videos.insert with 5xx retries and the clear quota error; returns the video id."""
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media, notifySubscribers=notify)
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
                raise RuntimeError(QUOTA_MESSAGE) from e
            raise
    return response["id"]


def set_thumbnail(video_id: str, image: Path, log=print) -> bool:
    """Try to set a custom thumbnail. YouTube only allows this for some channels/Shorts,
    so a refusal is logged and ignored (the video's opening frame is the thumbnail design)."""
    return _set_thumbnail(None, video_id, image, log, "the opening frame is used instead")


def _set_thumbnail(yt, video_id: str, image: Path, log, fallback: str) -> bool:
    try:
        yt = yt if yt is not None else _client()
        yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(image), mimetype="image/jpeg")).execute()
        log("Custom thumbnail set")
        return True
    except HttpError as e:
        reason = getattr(e, "reason", "") or str(e)[:200]
        log(f"Custom thumbnail not accepted ({e.resp.status}: {reason}); {fallback}")
    except Exception as e:  # never fail the run over a thumbnail
        log(f"Custom thumbnail skipped: {e}")
    return False


# ─── lessons (long-form 16:9, Education) ───────────────────────────────────

def find_playlist(yt, title: str) -> str | None:
    """Id of the channel's own playlist with exactly this title (all pages), or None."""
    token = None
    while True:
        kw = {"part": "snippet", "mine": True, "maxResults": 50}
        if token:
            kw["pageToken"] = token
        res = yt.playlists().list(**kw).execute()
        for item in res.get("items", []):
            if (item.get("snippet") or {}).get("title") == title:
                return item["id"]
        token = res.get("nextPageToken")
        if not token:
            return None


def ensure_playlist(yt, title: str, description: str, log=print, privacy: str = "public") -> str:
    """The channel's playlist with this exact title; created (public by default) if there is none."""
    pid = find_playlist(yt, title)
    if pid:
        return pid
    res = yt.playlists().insert(part="snippet,status", body={
        "snippet": {"title": title, "description": description},
        "status": {"privacyStatus": privacy},
    }).execute()
    log(f"Created playlist '{title}' ({res['id']})")
    return res["id"]


def upload_lesson(video: Path, meta: dict, thumbnail: Path, track_playlist: str, path_playlist: str,
                  review_hours: float = 24, notify: bool = True, log=print,
                  playlist_privacy: str = "public") -> dict:
    """Upload a 16:9 lesson (Education), private with publishAt review_hours later; set its custom
    thumbnail; add it to its track playlist and the master Path playlist (each created if missing).

    meta = lesson_meta.build_lesson_metadata() ({title, description, tags, category_id}); chapters are the
    "0:00 Intro" lines of its description. A thumbnail refusal or a playlist failure is logged and reported,
    never raised; the video id is always returned once the upload succeeded. Quota → RuntimeError.
    -> {"video_id", "publish_at", "thumbnail_set", "playlists": {title: id|None}, "errors": [...]}
    """
    status = {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}
    publish_at = None
    if review_hours and review_hours > 0:
        publish_at = (datetime.now(timezone.utc) + timedelta(hours=review_hours)).strftime(PUBLISH_AT)
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    body = {
        "snippet": {
            "title": _safe(meta["title"])[:100],
            "description": meta["description"],
            "tags": list(meta.get("tags") or []),
            "categoryId": str(meta.get("category_id") or "27"),
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": status,
    }
    yt = _client(LESSON_SCOPES)
    vid = _insert(yt, video, body, bool(notify), log)
    log(f"Uploaded lesson: https://youtube.com/watch?v={vid} (status: {status['privacyStatus']}"
        + (f", goes public {publish_at}" if publish_at else "") + ")")
    result = {"video_id": vid, "publish_at": publish_at, "thumbnail_set": False, "playlists": {}, "errors": []}
    result["thumbnail_set"] = _set_thumbnail(yt, vid, thumbnail, log, "YouTube picks a frame instead")

    for title, desc in ((track_playlist, f"{LESSON_BRAND} · {track_playlist}"),
                        (path_playlist, f"{LESSON_BRAND} in curriculum order")):
        result["playlists"][title] = None
        try:
            pid = ensure_playlist(yt, title, desc, log, privacy=playlist_privacy)
            yt.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
            result["playlists"][title] = pid
            log(f"Added to playlist '{title}'")
        except Exception as e:  # the uploaded video id is never lost over a playlist
            msg = f"playlist '{title}': {getattr(e, 'reason', '') or str(e)[:200]}"
            result["errors"].append(msg)
            log(f"Could not add the lesson to {msg}")
    return result


def delete_video(video_id: str, log=print) -> None:
    """Delete a video (the owner's test upload); needs LESSON_SCOPES."""
    _client(LESSON_SCOPES).videos().delete(id=video_id).execute()
    log(f"Deleted video {video_id}")


# ─── owner's test: python -m autopilot.youtube test-lesson <mp4> <thumbnail> [--days 30] ──

TEST_TRACK, TEST_PATH = "TEST Track", "TEST Path"


def _test_meta(duration: float) -> dict:
    """Throwaway metadata; 3 chapters (each ≥ 10 s) when the video is long enough to show them."""
    lines = ["CryptoFX Daily test upload: checks private scheduling, chapters, thumbnail and playlists. "
             "Deleted right after the check."]
    if duration >= 30:
        third = int(duration // 3)
        lines.append("Chapters:\n" + "\n".join(f"{s // 60}:{s % 60:02d} {n}" for s, n in
                                                 ((0, "Intro"), (third, "Middle"), (2 * third, "End"))))
    return {"title": "TEST lesson upload (will be deleted)", "description": "\n\n".join(lines),
            "tags": ["test"], "category_id": "27"}


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys

    from .media import probe_duration

    ap = argparse.ArgumentParser(prog="python -m autopilot.youtube")
    sub = ap.add_subparsers(dest="cmd", required=True)
    tl = sub.add_parser("test-lesson", help="upload a lesson privately into TEST playlists, print the result, "
                                            "then delete the video and the test playlists")
    tl.add_argument("mp4", type=Path)
    tl.add_argument("thumbnail", type=Path)
    tl.add_argument("--days", type=float, default=30, help="publishAt this many days ahead (default 30)")
    args = ap.parse_args(argv)

    missing = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        print(f"set {', '.join(missing)} first (a refresh token from get_token.py with the lesson scopes)")
        return 2
    for f in (args.mp4, args.thumbnail):
        if not f.is_file():
            print(f"{f} not found")
            return 2
    try:
        duration = probe_duration(args.mp4)
    except Exception as e:
        duration = 0.0
        print(f"could not read the video's duration ({e}); the test description has no chapters")
    vid, rc = None, 0
    try:
        res = upload_lesson(args.mp4, _test_meta(duration), args.thumbnail, TEST_TRACK, TEST_PATH,
                            review_hours=args.days * 24, notify=False, playlist_privacy="private")
        vid = res["video_id"]
        print(json.dumps(res, indent=2))
        rc = 1 if res["errors"] or not res["thumbnail_set"] else 0
        if sys.stdin.isatty():
            input(f"Check https://studio.youtube.com/video/{vid}/edit (private, chapters, thumbnail, playlists), "
                  "then press Enter to delete it… ")
    except Exception as e:
        print(f"test upload failed: {e}")
        rc = 1
    finally:  # never leave the test video or test playlists on the channel
        rc = max(rc, _cleanup_test(vid))
    return rc


def _cleanup_test(vid: str | None) -> int:
    """Delete what the test created; playlists are only made after a successful upload."""
    if not vid:
        print("nothing to clean up (no video was uploaded)")
        return 0
    rc = 0
    try:
        delete_video(vid)
    except Exception as e:
        print(f"could not delete test video {vid} ({e}); delete it in YouTube Studio")
        rc = 1
    try:
        yt = _client(LESSON_SCOPES)
    except Exception as e:
        print(f"could not check the TEST playlists ({e}); delete '{TEST_TRACK}' / '{TEST_PATH}' in YouTube Studio")
        return 1
    for title in (TEST_TRACK, TEST_PATH):
        try:
            pid = find_playlist(yt, title)
            if pid:
                yt.playlists().delete(id=pid).execute()
                print(f"deleted playlist '{title}'")
        except Exception as e:
            print(f"could not delete playlist '{title}' ({e}); delete it in YouTube Studio")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(_main())
