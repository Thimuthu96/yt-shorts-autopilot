"""Facebook Page publishing (Graph API v26.0): Reels for the video editions, photos for news posts,
regular Page videos (chunked /videos upload) for long vertical lessons.

Secrets: FB_PAGE_ID and FB_PAGE_TOKEN (a never-expiring Page token, see README "Facebook Page").
Facebook is skipped with a log line when they are missing or `facebook.enabled` is false.

Errors are classified, never looped blindly:
  190 (token), 10 / 200-299 (permission), 100 (bad parameter), 368 (policy block) → fail fast with
  a hint; 4 / 17 / 32 / 613 / 80001 (throttled) → fail with a message; 1, 2, is_transient and
  HTTP 5xx → retried 3 times with backoff from ~5 s.
A Reel's `finish` call is sent once; if it seems to fail, the video's status is checked before
it is ever sent again, so a Reel is never published twice. Long videos follow the same rule.
"""
import os
import re
import time
from pathlib import Path

import requests

from . import seo, thumbnail

GRAPH = "https://graph.facebook.com/{v}"
RUPLOAD = "https://rupload.facebook.com/video-upload/{v}"

# swapped out by the offline test
_http = requests
_sleep = time.sleep

FATAL_HINTS = {
    190: "the Page token is invalid or expired: regenerate FB_PAGE_TOKEN (README → Facebook Page)",
    10: "permission missing: the token needs pages_manage_posts, pages_read_engagement, pages_show_list "
        "and the Meta app must be in Live mode (README → Facebook Page)",
    100: "Facebook rejected a parameter of the request",
    368: "Facebook blocked this post (policy / spam protection); check the Page's Page Quality",
}
THROTTLED = {4, 17, 32, 613, 80001}
TRANSIENT = {1, 2}


class GraphError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, subcode: int | None = None,
                 transient: bool = False, status: int | None = None):
        super().__init__(message)
        self.code, self.subcode, self.transient, self.status = code, subcode, transient, status
        self.video_id: str | None = None  # set by publish_video once the video exists


def disabled_reason(cfg: dict) -> str:
    """'' when Facebook publishing is on, else why it is skipped."""
    fb = cfg.get("facebook") or {}
    if not fb.get("enabled", False):
        return "facebook.enabled is false in config.yaml"
    missing = [k for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN") if not os.environ.get(k)]
    if missing:
        return f"secret{'s' if len(missing) > 1 else ''} {', '.join(missing)} not set"
    return ""


def enabled(cfg: dict) -> bool:
    return not disabled_reason(cfg)


def _version(cfg: dict) -> str:
    return str((cfg.get("facebook") or {}).get("graph_version") or "v26.0")


def _creds() -> tuple[str, str]:
    return os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]


def _error(r, body) -> GraphError:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        e = body["error"]
        code, sub = e.get("code"), e.get("error_subcode")
        msg = e.get("message") or "Graph API error"
        transient = bool(e.get("is_transient")) or code in TRANSIENT or r.status_code >= 500
        if code == 190:
            hint = FATAL_HINTS[190]
        elif code == 10 or (isinstance(code, int) and 200 <= code <= 299):
            hint = FATAL_HINTS[10]
        elif code in (100, 368):
            hint = FATAL_HINTS[code]
        elif code in THROTTLED:
            hint = "Facebook rate limit reached; it resets within the hour (API Reels: 30 per Page per 24 h)"
        else:
            hint = ""
        if code in FATAL_HINTS or code in THROTTLED or (isinstance(code, int) and 200 <= code <= 299):
            transient = False
        text = f"Facebook error {code}" + (f"/{sub}" if sub else "") + f": {msg}" + (f" → {hint}" if hint else "")
        return GraphError(text, code, sub, transient, r.status_code)
    if isinstance(body, dict) and isinstance(body.get("debug_info"), dict):  # rupload's error shape
        d = body["debug_info"]
        return GraphError(f"Facebook upload error: {d.get('message') or d.get('type')}",
                          transient=bool(d.get("retriable")) or r.status_code >= 500, status=r.status_code)
    return GraphError(f"Facebook HTTP {r.status_code}: {str(body)[:300]}", transient=r.status_code >= 500,
                      status=r.status_code)


def _call(method: str, url: str, *, retries: int = 3, log=print, timeout=(15, 120), **kw) -> dict:
    """One Graph request with classified retries. Request bodies must be re-sendable (bytes, not files)."""
    for attempt in range(retries + 1):
        try:
            r = _http.request(method, url, timeout=timeout, **kw)
            try:
                body = r.json()
            except ValueError:
                body = r.text
            if r.status_code < 400 and not (isinstance(body, dict) and "error" in body):
                return body if isinstance(body, dict) else {"raw": body}
            err = _error(r, body)
        except requests.RequestException as e:
            err = GraphError(f"Facebook network error: {e}", transient=True)
        if not err.transient or attempt >= retries:
            raise err
        wait = 5 * 2 ** attempt
        log(f"{err}; retrying in {wait}s")
        _sleep(wait)
    raise AssertionError("unreachable")


# ─── Reels ─────────────────────────────────────────────────────────────────

def _status(video_id: str, token: str, v: str, log=print) -> dict:
    # token in a header, never in the URL (URLs can end up in error messages / logs)
    res = _call("GET", f"{GRAPH.format(v=v)}/{video_id}", params={"fields": "status"},
                headers={"Authorization": f"OAuth {token}"}, log=log)
    return res.get("status") or {}


def _phase_errors(st: dict) -> list[str]:
    out = []
    if st.get("video_status") in ("error", "upload_failed"):
        out.append(f"video_status {st['video_status']}")
    for name in ("uploading_phase", "processing_phase", "publishing_phase"):
        p = st.get(name) or {}
        if p.get("status") == "error":
            errs = p.get("errors") or p.get("error") or ""
            out.append(f"{name} error {errs}".strip())
    return out


def _published(st: dict) -> bool:
    pub = st.get("publishing_phase") or {}
    return pub.get("status") in ("complete", "completed") or pub.get("publish_status") in ("published", "completed")


def _finish_took(st: dict) -> bool:
    pub = st.get("publishing_phase") or {}
    return _published(st) or pub.get("status") in ("in_progress",) or pub.get("publish_status") == "scheduled"


def publish_reel(video: Path, description: str, cfg: dict, cover: Path | None = None, log=print) -> str:
    """start → upload bytes → finish (once) → poll until published (≤ facebook.poll_minutes).
    Returns the Reel's video id."""
    page, token = _creds()
    v = _version(cfg)
    url = f"{GRAPH.format(v=v)}/{page}/video_reels"
    res = _call("POST", url, data={"upload_phase": "start", "access_token": token}, log=log)
    vid = str(res["video_id"])
    blob = Path(video).read_bytes()
    up = _call("POST", res.get("upload_url") or f"{RUPLOAD.format(v=v)}/{vid}",
               headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(blob))},
               data=blob, timeout=(15, 600), log=log)
    if not up.get("success", True):
        raise GraphError(f"Facebook upload of Reel {vid} was not accepted: {up}")
    log(f"Facebook: Reel {vid} uploaded ({len(blob) / 1e6:.1f} MB), publishing")

    finish = {"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
              "description": description[:2200], "access_token": token}
    for attempt in range(3):
        try:
            _call("POST", url, data=finish, retries=0, log=log)
            break
        except GraphError as e:
            if not e.transient:
                raise
            log(f"Facebook: finish call unclear ({e}); checking the Reel's status before anything else")
            _sleep(5 * 2 ** attempt)
            try:
                took = _finish_took(_status(vid, token, v, log))
            except GraphError as se:  # can't tell: a missed Reel beats a duplicate one
                log(f"Facebook: Reel {vid} status unreadable ({se}); not sending finish again")
                break
            if took:
                log("Facebook: the finish went through after all")
                break
            if attempt == 2:
                raise
            log("Facebook: not publishing yet, sending finish again")

    poll = float((cfg.get("facebook") or {}).get("poll_minutes", 10)) * 60
    every = float((cfg.get("facebook") or {}).get("poll_every_seconds", 10))
    waited = 0.0
    while True:
        try:
            st = _status(vid, token, v, log)
        except Exception as e:  # the finish went through: never lose the id over a status read
            log(f"Facebook: Reel {vid} status unknown ({e}); logged so it isn't posted twice")
            break
        errs = _phase_errors(st)
        if errs:
            raise GraphError(f"Facebook Reel {vid} failed: {'; '.join(errs)}")
        if _published(st):
            log(f"Facebook: Reel published https://www.facebook.com/reel/{vid}")
            break
        if waited >= poll:
            log(f"Facebook: Reel {vid} still processing after {poll / 60:.0f} min ({st.get('video_status')}); "
                "it normally appears on the Page shortly. Logged so it isn't posted twice.")
            break
        _sleep(every)
        waited += every

    if cover and Path(cover).exists():  # best effort; Facebook may refuse custom Reel covers
        try:
            _call("POST", f"{GRAPH.format(v=v)}/{vid}/thumbnails", retries=0, log=log,
                  data={"is_preferred": "true", "access_token": token},
                  files={"source": (Path(cover).name, Path(cover).read_bytes(), "image/jpeg")})
            log("Facebook: Reel cover set")
        except Exception as e:  # never fail the run over a cover
            log(f"Facebook: Reel cover not set ({e})")
    return vid


# ─── long videos (lessons) ─────────────────────────────────────────────────

def _video_not_started(st: dict) -> bool:
    """True only when the status clearly shows the upload itself never completed, so the finish
    can't have taken. Everything else (incl. processing not started yet, or a missing phase)
    counts as taken, so finish is never re-sent on a guess."""
    up = (st.get("uploading_phase") or {}).get("status")
    return (up is not None and up not in ("complete", "completed") and not _finish_took(st)
            and st.get("video_status") != "ready")


def publish_video(video: Path, title: str, description: str, cfg: dict, published: bool = True,
                  poll_minutes: float | None = None, log=print) -> str:
    """A long (up to ~5 min) vertical lesson as a regular Page video: chunked upload to
    /{page}/videos (start → transfer the byte ranges Facebook asks for → finish once with title and
    description) → poll until ready (≤ poll_minutes, default facebook.poll_minutes).
    published=False uploads it unpublished (owner's test). Returns the video id.
    Any error after start carries the id as `video_id`, so a caller can log or delete it."""
    page, token = _creds()
    v = _version(cfg)
    url = f"{GRAPH.format(v=v)}/{page}/videos"
    blob = Path(video).read_bytes()
    res = _call("POST", url, log=log,
                data={"upload_phase": "start", "file_size": str(len(blob)), "access_token": token})
    vid = str(res["video_id"])
    try:
        _video_upload(vid, res, url, blob, Path(video).name, title, description, published, token, v, log)
        _video_poll(vid, page, token, v, cfg, published, poll_minutes, log)
    except Exception as e:  # the video exists on the Page: never lose its id
        if getattr(e, "video_id", None) is None:
            e.video_id = vid
        raise
    return vid


def _video_upload(vid, res, url, blob, name, title, description, published, token, v, log) -> None:
    sid = str(res["upload_session_id"])
    start, end = int(res["start_offset"]), int(res["end_offset"])
    log(f"Facebook: video {vid} upload started ({len(blob) / 1e6:.1f} MB)")
    while start < end:
        # a chunk is bytes, so _call can re-send it on a transient error without restarting
        res = _call("POST", url, timeout=(15, 600), log=log,
                    data={"upload_phase": "transfer", "upload_session_id": sid, "start_offset": str(start),
                          "access_token": token},
                    files={"video_file_chunk": (name, blob[start:end], "application/octet-stream")})
        nxt, nend = int(res["start_offset"]), int(res["end_offset"])
        if nxt <= start and nxt != nend:
            raise GraphError(f"Facebook video {vid} upload stuck at byte {start} (answer: {res})")
        start, end = nxt, nend
    log(f"Facebook: video {vid} uploaded, finishing ({'published' if published else 'unpublished'})")

    finish = {"upload_phase": "finish", "upload_session_id": sid, "title": title[:255],
              "description": description[:5000], "published": "true" if published else "false",
              "access_token": token}
    for attempt in range(3):
        try:
            done = _call("POST", url, data=finish, retries=0, log=log)
            if done.get("success") is False:
                raise GraphError(f"Facebook video {vid} finish was not accepted: {done}")
            return
        except GraphError as e:
            # first finish clearly refused → fail; unclear, or a re-sent finish refused → look first
            if not e.transient and attempt == 0:
                raise
            log(f"Facebook: finish call {'unclear' if e.transient else 'refused'} ({e}); "
                "checking the video's status before anything else")
            _sleep(5 * 2 ** attempt)
            try:
                st = _status(vid, token, v, log)
            except GraphError as se:  # can't tell: a missed video beats a duplicate one
                log(f"Facebook: video {vid} status unreadable ({se}); not sending finish again")
                return
            if not _video_not_started(st):
                log(f"Facebook: the finish of video {vid} went through after all")
                return
            if attempt == 2 or not e.transient:
                raise
            log("Facebook: upload not complete yet, sending finish again")


def _video_poll(vid, page, token, v, cfg, published, poll_minutes, log) -> None:
    fb = cfg.get("facebook") or {}
    poll = float(fb.get("poll_minutes", 10) if poll_minutes is None else poll_minutes) * 60
    every = float(fb.get("poll_every_seconds", 10))
    waited = 0.0
    while True:
        try:
            st = _status(vid, token, v, log)
        except Exception as e:  # the finish went through: never lose the id over a status read
            log(f"Facebook: video {vid} status unknown ({e}); logged so it isn't posted twice")
            return
        errs = _phase_errors(st)
        if errs:
            raise GraphError(f"Facebook video {vid} failed: {'; '.join(errs)}")
        if st.get("video_status") == "ready" and (not published or _published(st)):
            log(f"Facebook: video {'published' if published else 'ready (unpublished)'} "
                f"https://www.facebook.com/{page}/videos/{vid}")
            return
        if waited >= poll:
            log(f"Facebook: video {vid} still processing after {poll / 60:.0f} min ({st.get('video_status')}); "
                "it normally appears on the Page shortly. Logged so it isn't posted twice.")
            return
        _sleep(every)
        waited += every


def delete_video(video_id: str, cfg: dict, log=print) -> None:
    """Delete a Page video (used after the owner's unpublished test upload)."""
    _, token = _creds()
    res = _call("DELETE", f"{GRAPH.format(v=_version(cfg))}/{video_id}",
                headers={"Authorization": f"OAuth {token}"}, log=log)
    if res.get("success") is False:
        raise GraphError(f"Facebook video {video_id} was not deleted: {res}")
    log(f"Facebook: video {video_id} deleted")


# ─── photos ────────────────────────────────────────────────────────────────

def publish_photo(image: Path, caption: str, cfg: dict, log=print) -> str:
    """Post one image with its caption to the Page. Returns the post id."""
    page, token = _creds()
    blob = Path(image).read_bytes()
    if len(blob) > 10 * 1024 * 1024:
        raise GraphError(f"{image} is {len(blob) / 1e6:.1f} MB; Facebook photos must be under 10 MB")
    res = _call("POST", f"{GRAPH.format(v=_version(cfg))}/{page}/photos", log=log,
                data={"caption": caption, "published": "true", "access_token": token},
                files={"source": (Path(image).name, blob, "image/jpeg")})
    pid = str(res.get("post_id") or res["id"])
    log(f"Facebook: photo posted https://www.facebook.com/{pid}")
    return pid


# ─── captions ──────────────────────────────────────────────────────────────

URL = re.compile(r"https?://\S+|www\.\S+", re.I)


def clean_text(text: str) -> str:
    """No links (Meta reach) and no angle brackets."""
    return re.sub(r"[ \t]+", " ", URL.sub("", re.sub(r"[<>]", "", text or ""))).strip()


TAG = re.compile(r"^#[A-Za-z][A-Za-z0-9_]{1,40}$")
INLINE_TAG = re.compile(r"(?<![\w&])#\w+")


def strip_hashtags(text: str) -> str:
    """Remove #tags from body text (the caption's tag line is added separately)."""
    text = INLINE_TAG.sub("", text or "")
    return "\n".join(re.sub(r"[ \t]{2,}", " ", ln).strip() for ln in text.split("\n")).strip()


def fb_hashtags(tags: list[str], limit: int = 5) -> list[str]:
    seen, out = set(), []
    for h in tags:
        h = "".join(str(h).split())
        h = h if h.startswith("#") else f"#{h}"
        if not TAG.match(h) or h[1:].upper() in thumbnail.BANNED:
            continue
        if h.lower() not in seen and h.lower() not in ("#shorts", "#short"):
            seen.add(h.lower())
            out.append(h)
    return out[:limit]


def reel_caption(meta: dict, pkg: dict, data: dict, cfg: dict) -> str:
    """Facebook Reel description from the YouTube metadata: hook first (Facebook cuts at ~280
    characters), the summary, key numbers, sources named (no links), disclaimer, ≤5 hashtags."""
    parts = [clean_text(meta.get("title", "")), clean_text(pkg.get("description", ""))]
    numbers = seo.key_numbers(data)
    if numbers:
        parts.append(("Key levels:\n" if data.get("kind") == "gold" else "Key numbers:\n") + "\n".join(numbers))
    by_title = {n["title"].lower(): n["source"] for n in data.get("news", [])}
    sources = list(dict.fromkeys(by_title[t.lower()] for t in pkg.get("headlines_used", []) if t.lower() in by_title))
    if sources:
        parts.append("Sources: " + ", ".join(sources[:4]) + ".")
    disclaimer = (cfg.get("upload", {}).get("disclaimer") or "").strip()
    if disclaimer:
        parts.append("⚠️ " + " ".join(disclaimer.split()))
    tags = fb_hashtags(seo.hashtags(data, pkg.get("hashtags", [])), int((cfg.get("facebook") or {}).get("max_hashtags", 5)))
    tail = " ".join(tags)
    body = "\n\n".join(p for p in (strip_hashtags(x) for x in parts) if p)
    return (body[:2190 - len(tail) - 2].rstrip() + "\n\n" + tail).strip()


# ─── owner's test: python -m autopilot.facebook test-video <mp4> [--title T] ──

def _main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    import yaml

    ap = argparse.ArgumentParser(prog="python -m autopilot.facebook")
    sub = ap.add_subparsers(dest="cmd", required=True)
    tv = sub.add_parser("test-video", help="upload an mp4 unpublished, print its id and status, then delete it")
    tv.add_argument("mp4", type=Path)
    tv.add_argument("--title", default=None)
    args = ap.parse_args(argv)

    missing = [k for k in ("FB_PAGE_ID", "FB_PAGE_TOKEN") if not os.environ.get(k)]
    if missing:
        print(f"set {', '.join(missing)} first")
        return 2
    if not args.mp4.is_file():
        print(f"{args.mp4} not found")
        return 2
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text(encoding="utf-8")) or {}
    title = args.title or f"Test upload: {args.mp4.stem}"
    vid, rc = None, 0
    try:
        vid = publish_video(args.mp4, title, "CryptoFX Daily test upload (unpublished, deleted right after).",
                            cfg, published=False)
        print(f"video id: {vid}")
        _, token = _creds()
        info = _call("GET", f"{GRAPH.format(v=_version(cfg))}/{vid}",
                     params={"fields": "title,description,status"}, headers={"Authorization": f"OAuth {token}"})
        print(f"title: {info.get('title')}")
        print(f"description: {info.get('description')}")
        print("status:", json.dumps(info.get("status") or {}, indent=2))
    except Exception as e:
        vid = vid or getattr(e, "video_id", None)
        print(f"test upload failed: {e}" + (f" (video id {vid})" if vid else ""))
        rc = 1
    finally:
        if vid:  # never leave the test video on the Page
            try:
                delete_video(vid, cfg)
            except Exception as e:
                print(f"could not delete test video {vid} ({e}); delete it in Meta Business Suite")
                rc = 1
    return rc

if __name__ == "__main__":
    raise SystemExit(_main())
