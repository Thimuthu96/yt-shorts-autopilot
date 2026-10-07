"""Record of uploaded briefs: avoids double posts and repeating yesterday's lead story."""
import json
from pathlib import Path


class History:
    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"videos": []}

    def used_headlines(self) -> list[str]:
        out = []
        for v in self.data["videos"][-7:]:
            out += v.get("headlines", [])
        return out

    def uploaded_on(self, date: str) -> bool:
        return any(v.get("brief_date") == date and v.get("video_id") for v in self.data["videos"])

    def add(self, entry: dict) -> None:
        self.data["videos"].append(entry)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
