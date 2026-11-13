"""Record of published Gus Explains editions (data/history.json): avoids double posts and repeated stories.

One entry per run that published anywhere. It carries the id of each platform it reached: "video_id" (YouTube
Short) and "fb_reel_id" (Facebook Reel). A run that publishes a platform the edition missed earlier (e.g. Facebook
after a failure) adds a second entry for the same edition, so each platform's guard is checked on its own.
Entries carry "trigger" (timed | manual) and "counts" (does it fill that day's edition slot?): manual runs don't
count unless started with --as-edition, so they never stop the autopilot.
The crypto channel's history is kept in data/archive/crypto-history.json (not read by anything).

    python -m autopilot.history add output/*/history_entry.json       # merge (used by the workflow)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID_KEYS = ("video_id", "fb_reel_id")
PLATFORM_IDS = {"youtube": ("video_id",), "facebook": ("fb_reel_id",)}


class History:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"videos": []}

    def uploaded(self) -> list[dict]:
        """Entries that reached at least one platform."""
        return [v for v in self.data["videos"] if any(v.get(k) for k in ID_KEYS)]

    def stories(self) -> list[dict]:
        """Uploaded Gus Explains entries, oldest first."""
        return [v for v in self.uploaded() if v.get("slug")]

    def titles(self) -> list[str]:
        return [v["title"] for v in self.stories() if v.get("title")]

    def slugs(self) -> set[str]:
        return {v["slug"] for v in self.stories()}

    def last_category(self) -> str | None:
        s = self.stories()
        return s[-1].get("category") if s else None

    def today_story(self, date: str, session: str) -> dict | None:
        """The counting entry already published in that slot today (a re-run for a missed platform reuses it)."""
        for v in reversed(self.stories()):
            if v.get("brief_date") == date and v.get("session") == session and v.get("counts", True):
                return v
        return None

    def published_on(self, date: str, session: str, platform: str) -> bool:
        """Is today's slot of this edition already on that platform? (manual runs don't count)"""
        keys = PLATFORM_IDS[platform]
        return any(v.get("brief_date") == date and v.get("session") == session and v.get("counts", True)
                   and any(v.get(k) for k in keys) for v in self.uploaded())

    def add(self, entry: dict) -> bool:
        """Append unless an entry with any of the same platform ids is logged (merging twice is harmless)."""
        for k in ID_KEYS:
            i = entry.get(k)
            if i and any(v.get(k) == i for v in self.data["videos"]):
                return False
        self.data["videos"].append(entry)
        return True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "add":
        sys.exit("usage: python -m autopilot.history add <entry.json>...")
    h = History(ROOT / "data" / "history.json")
    added = [p for p in sys.argv[2:] if h.add(json.loads(Path(p).read_text(encoding="utf-8")))]
    h.save()
    print(f"history: {len(added)} new entr{'y' if len(added) == 1 else 'ies'}")
