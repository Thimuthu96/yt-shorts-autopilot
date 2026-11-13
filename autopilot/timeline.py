"""Narration timeline: voice every shot, lay the shots on one track, write voice.wav + timeline.json.

    faster_rate(rate, factor) -> str
    build(story, vcfg, workdir, max_seconds=60, log=print) -> dict   timeline + "voice"; raises TooLong(seconds)

Layout: 0.15 s lead (owned by shot 0, so frame 0 already shows the hook), each shot's audio trimmed of
silence, 0.06 s between shots of one sentence, 0.12 s after a shot that ends one (. ! ? :), 0.6 s tail.
Caption words are `text.split()`; the voice's word times are mapped to them by index (stretched when the
counts differ). `mouth` = one RMS envelope value 0..1 per frame.
"""
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np

from autopilot import voice
from autopilot.story import spoken

SR, FPS = 48000, 30
LEAD, GAP, GAP_IN, TAIL = 0.15, 0.12, 0.06, 0.6


class TooLong(Exception):
    def __init__(self, seconds: float):
        super().__init__(f"narration is {seconds:.1f}s, over the limit even re-recorded faster")
        self.seconds = seconds


def faster_rate(rate: str, factor: float) -> str:
    pct = int(re.sub(r"[^\d-]", "", rate) or 0)
    new = int(round(((1 + pct / 100) * factor - 1) * 100)) + 2
    return f"{'+' if new >= 0 else ''}{min(new, 35)}%"


def _read(path) -> np.ndarray:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "pipe:1"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(pcm, dtype=np.float32).copy()


def _trim(a: np.ndarray, thr: float = 0.01) -> tuple[np.ndarray, float]:
    idx = np.where(np.abs(a) > thr)[0]
    if not len(idx):
        return a, 0.0
    s = max(0, idx[0] - int(0.02 * SR))
    e = min(len(a), idx[-1] + int(0.06 * SR))
    return a[s:e], s / SR


def _split_merged(ws: list[tuple]) -> list[tuple]:
    out = []
    for s, e, w in ws:  # a boundary holding two words ("in 1823"): split its span by character length
        parts = str(w).split() or [str(w)]
        tot = sum(len(p) for p in parts) or 1
        t = s
        for p in parts:
            d = (e - s) * len(p) / tot
            out.append((t, t + d, p))
            t += d
    return out


def _align(caps: list[str], ws: list[tuple], dur: float) -> list[tuple]:
    ws = _split_merged(ws)
    if not ws:
        ws = voice.estimate_words(" ".join(caps), dur)
    if len(ws) != len(caps):
        idx = [round(i * (len(ws) - 1) / max(1, len(caps) - 1)) for i in range(len(caps))]
        ws = [ws[k] for k in idx]
    return [(c, max(0.0, min(s, dur)), max(0.0, min(e, dur))) for c, (s, e, _) in zip(caps, ws)]


def _mouth(audio: np.ndarray) -> list[float]:
    hop = SR // FPS
    n = int(math.ceil(len(audio) / SR * FPS))
    pad = np.zeros(n * hop, np.float32)
    pad[:len(audio)] = audio
    env = np.sqrt(np.mean(pad.reshape(n, hop) ** 2, axis=1) + 1e-12)
    env = np.clip(env / (np.percentile(env, 95) + 1e-6), 0, 1)
    env = np.clip(np.convolve(env, [0.25, 0.5, 0.25], mode="same"), 0, 1)
    return [round(float(x), 2) for x in env]


def _record(story, vcfg, rate, workdir, log):
    scenes = [{"text": spoken(b)} for b in story["beats"]]
    return voice.synthesize(scenes, vcfg["name"], rate, workdir, log=log, fallback=vcfg.get("fallback"))


def build(story: dict, vcfg: dict, workdir: Path, max_seconds: float = 60, log=print) -> dict:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    rate = vcfg.get("rate", "+0%")
    scenes = _record(story, vcfg, rate, workdir, log)
    total = LEAD + sum(s["duration"] for s in scenes) + TAIL
    if total > max_seconds:
        rate2 = faster_rate(rate, total / max_seconds)
        log(f"narration {total:.1f}s is over {max_seconds}s, re-recording at {rate2}")
        scenes = _record(story, vcfg, rate2, workdir, log)

    chunks, beats, t = [np.zeros(int(LEAD * SR), np.float32)], [], LEAD
    for i, (b, sc) in enumerate(zip(story["beats"], scenes)):
        a, off = _trim(_read(sc["audio"]))
        dur = len(a) / SR
        ws = _align(b["text"].split(), [(s - off, e - off, w) for s, e, w in sc["words"]], dur)
        beats.append({"i": i, "start": round(t, 3), "end": round(t + dur, 3),
                      "words": [{"w": w, "s": round(t + s, 3), "e": round(t + e, 3)} for w, s, e in ws]})
        gap = GAP if b["text"].rstrip()[-1:] in (".", "!", "?", ":") else GAP_IN
        chunks += [a, np.zeros(int(gap * SR), np.float32)]
        t += dur + gap
    beats[0]["start"] = 0.0
    chunks.append(np.zeros(int(TAIL * SR), np.float32))
    audio = np.concatenate(chunks)
    seconds = len(audio) / SR
    if seconds > max_seconds:
        raise TooLong(seconds)
    audio = audio / max(1e-6, float(np.abs(audio).max())) * 0.89
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "pipe:0",
                    str(workdir / "voice.wav")], input=audio.astype(np.float32).tobytes(), check=True)
    tl = {"fps": FPS, "duration": round(seconds, 3), "beats": beats, "mouth": _mouth(audio)}
    (workdir / "timeline.json").write_text(json.dumps(tl))
    who = scenes[0]["voice"] if scenes else vcfg["name"]
    log(f"timeline: {seconds:.1f}s, {len(beats)} shots, voice {who}")
    return {**tl, "voice": who}
