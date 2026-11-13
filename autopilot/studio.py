"""Studio bridge: run the Node renderer, mux the voice track, cut the thumbnail.

    render(story, timeline, workdir, log=print, node="node", scale=1.0, timeout_minutes=45) -> Path
                                            workdir/video.mp4 (silent); RenderError (scale < 1 renders smaller, for
                                            local previews / tests). render.js's lines (progress every 150 frames,
                                            "rendered N frames in Xs") are logged as they come; a render still
                                            running after timeout_minutes is killed → RenderError("render timed out …")
    mux(video, audio, out) -> Path          1080x1920 30 fps H.264, AAC 48 kHz stereo, -g 60, two-pass loudnorm -14 LUFS
    thumbnail(video, out) -> Path           frame 0 as a jpg
    stills(story, timeline, workdir, times, node="node") -> list[Path]
"""
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDER_JS = ROOT / "studio" / "render.js"
LOUDNORM = "I=-14:TP=-1.5:LRA=11"
# the voice's peak sits near full scale, so the +dB the target needs would clip: a limiter first (both passes)
LIMIT = "alimiter=limit=0.45:level=false"


class RenderError(RuntimeError):
    pass


def _kill(p: subprocess.Popen) -> None:
    """node and the Chromium it started (own process group)."""
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, AttributeError):
        p.kill()


def _node(args: list[str], node: str, log, timeout_minutes: float | None = None) -> str:
    """Run render.js, logging each output line as it comes (the Actions log shows render progress)."""
    t0 = time.monotonic()
    p = subprocess.Popen([node, str(RENDER_JS), *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         cwd=ROOT, start_new_session=True)
    lines: list[str] = []

    def pump():
        for line in p.stdout:
            line = line.rstrip()
            lines.append(line)
            if line:
                log(f"studio: {line}")

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        code = p.wait(timeout=timeout_minutes * 60 if timeout_minutes else None)
    except subprocess.TimeoutExpired:
        _kill(p)
        p.wait()
        reader.join(5)
        last = next((x for x in reversed(lines) if "frame" in x), "")
        raise RenderError(f"render timed out after {timeout_minutes:g} min" + (f" (last: {last})" if last else ""))
    reader.join(10)
    out = "\n".join(lines)
    if code != 0:
        tail = "\n".join(out.strip().splitlines()[-20:])
        raise RenderError(f"studio render failed (exit {code}):\n{tail}")
    log(f"studio: node finished in {time.monotonic() - t0:.0f}s")
    return out


def _write(story: dict, timeline: dict, workdir: Path) -> tuple[Path, Path]:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    s, t = workdir / "story.json", workdir / "timeline.json"
    s.write_text(json.dumps(story))
    t.write_text(json.dumps(timeline))
    return s, t


def render(story: dict, timeline: dict, workdir: Path, log=print, node: str = "node", scale: float = 1.0,
           timeout_minutes: float | None = 45) -> Path:
    s, t = _write(story, timeline, workdir)
    log(f"studio: rendering {timeline.get('duration')}s" + (f" at scale {scale:g}" if scale != 1 else ""))
    _node([str(s), "--timeline", str(t), "--out", str(workdir)] + (["--scale", str(scale)] if scale != 1 else []),
          node, log, timeout_minutes)
    video = Path(workdir) / "video.mp4"
    if not video.exists():
        raise RenderError("studio render finished without video.mp4")
    return video


def stills(story: dict, timeline: dict, workdir: Path, times: list[float], node: str = "node", log=print) -> list[Path]:
    s, t = _write(story, timeline, workdir)
    _node([str(s), "--timeline", str(t), "--out", str(workdir), "--stills", ",".join(str(x) for x in times)], node, log)
    return [Path(workdir) / f"still_{float(x):.1f}.jpg" for x in times]


def _measure(audio: Path) -> dict:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(audio), "-af",
                        f"{LIMIT},loudnorm={LOUDNORM}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    txt = p.stderr
    return json.loads(txt[txt.rindex("{"):txt.rindex("}") + 1])


def mux(video: Path, audio: Path, out: Path) -> Path:
    m = _measure(audio)
    af = (f"{LIMIT},loudnorm={LOUDNORM}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
          "linear=true,aresample=48000")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
                    "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-movflags", "+faststart",
                    "-af", af, "-ac", "2", "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)],
                   check=True)
    return Path(out)


def thumbnail(video: Path, out: Path) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)], check=True)
    return Path(out)
