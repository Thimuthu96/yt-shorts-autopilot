"""Small ffmpeg helpers."""
import subprocess
from pathlib import Path


def run(cmd: list, cwd: Path | None = None) -> None:
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd[:8]))} ...\n{r.stderr[-3000:]}")


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Could not read duration of {path}: {r.stderr}")
