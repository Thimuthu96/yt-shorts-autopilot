"""Upload to YouTube (YouTube Data API v3). The title / description / tags come from autopilot/metadata.py.

upload() / set_thumbnail() request only SCOPES (youtube.upload). delete_video() needs MANAGE_SCOPES (adds the
`youtube` scope): a refresh token made by `python get_token.py --lesson-scopes`.
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


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
MANAGE_SCOPES = SCOPES + ["https://www.googleapis.com/auth/youtube",  # delete videos (scripts/delete_old_content.py)
                          "https://www.googleapis.com/auth/yt-analytics.readonly"]
PUBLISH_AT = "%Y-%m-%dT%H:%M:%S.000Z"
QUOTA_MESSAGE = ("YouTube upload limit reached for today (the API allows about 6 uploads a day: 1,600 of "
                 "10,000 quota units each; it resets at midnight Pacific time). The video is saved in the "
                 "run's artifacts.")


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


def delete_video(video_id: str, log=print) -> None:
    """Delete a video; needs MANAGE_SCOPES."""
    _client(MANAGE_SCOPES).videos().delete(id=video_id).execute()
    log(f"Deleted video {video_id}")
