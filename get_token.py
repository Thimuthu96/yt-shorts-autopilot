"""Run once on your own computer to authorise uploads to your channel.

    pip install google-auth-oauthlib
    python get_token.py

A browser opens; sign in with the Google account that owns the channel and pick the
channel. The script prints the three values to paste into GitHub secrets.

Scopes: youtube.upload (daily Shorts and lessons). Only if you turn on automatic lesson playlists
(config.yaml lessons.playlists: true), run `python get_token.py --lesson-scopes` instead: it also asks
for youtube (playlists, deleting test uploads) and yt-analytics.readonly, after you add those scopes to
the OAuth consent screen; then replace YT_REFRESH_TOKEN. The daily uploader always asks only for
youtube.upload, so either token works for it.
"""
import sys
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]  # daily Shorts + lessons
if "--lesson-scopes" in sys.argv:  # only for lessons.playlists: true
    SCOPES += ["https://www.googleapis.com/auth/youtube",  # lesson playlists, test-video delete
               "https://www.googleapis.com/auth/yt-analytics.readonly"]  # lesson analytics (read only)
SECRET_FILE = Path(__file__).parent / "client_secret.json"

if not SECRET_FILE.exists():
    raise SystemExit("Put the OAuth client file you downloaded from Google Cloud next to this "
                     "script and name it client_secret.json")

flow = InstalledAppFlow.from_client_secrets_file(str(SECRET_FILE), SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
client = json.loads(SECRET_FILE.read_text())
client = client.get("installed") or client.get("web")

print("\nAdd these as GitHub repository secrets:\n")
print(f"YT_CLIENT_ID      = {client['client_id']}")
print(f"YT_CLIENT_SECRET  = {client['client_secret']}")
print(f"YT_REFRESH_TOKEN  = {creds.refresh_token}")
print("\nKeep them private. Delete client_secret.json or keep it out of git.")
