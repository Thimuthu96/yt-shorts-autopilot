"""Record of uploaded briefs: avoids double posts and repeating earlier stories."""
import json
from datetime import datetime
from pathlib import Path


class History:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"videos": []}

    def uploaded(self) -> list[dict]:
        return [v for v in self.data["videos"] if v.get("video_id")]

    def used_headlines(self) -> list[str]:
        out = []
        for v in self.uploaded()[-15:]:
            out += v.get("headlines", [])
        return out

    def uploaded_on(self, date: str, session: str) -> bool:
        # briefs from before sessions existed count as the London edition
        return any(v.get("brief_date") == date and v.get("session", "london") == session for v in self.uploaded())

    def last_upload_time(self) -> datetime | None:
        times = []
        for v in self.uploaded():
            try:
                times.append(datetime.fromisoformat(v["date"]))
            except (KeyError, ValueError):
                pass
        return max(times) if times else None

    def add(self, entry: dict) -> None:
        self.data["videos"].append(entry)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
