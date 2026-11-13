"""Soundtrack: music manifest, synthesized SFX, the mix.

    load_tracks(dir)                      music/tracks.yaml entries whose file exists (missing ones logged)
    pick_track(tracks, mood, platform, seed)  facebook -> only facebook_ok; prefers the mood; deterministic by seed
    SFX_TYPES                             whoosh, boom, splash, impact, pop, ding, crackle, creak (= catalog "sfx")
    sfx(name) -> np.ndarray               mono float32 at SR
    sfx_times(story, timeline)            [(seconds, type)]: shot sfx + word-anchored sfx_mark events
    mix(voice_wav, timeline, story, track, out, music_db=-20) -> Path   48 kHz stereo wav
    attribution_line(track)               "Music: <title> by <artist>. <attribution>" or ""
"""
import hashlib
import subprocess
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
SR = 48000
SFX_TYPES = ("whoosh", "boom", "splash", "impact", "pop", "ding", "crackle", "creak")
MOODS = ("curious", "tense", "upbeat", "epic")


def log(*a):
    print(*a, flush=True)


# ─── manifest ────────────────────────────────────────────────────────────
def load_tracks(dir=None, log=log) -> list[dict]:
    d = Path(dir or ROOT / "music")
    f = d / "tracks.yaml"
    if not f.exists():
        return []
    out = []
    for t in yaml.safe_load(f.read_text()) or []:
        if not (d / str(t.get("file", ""))).is_file():
            log(f"music: {t.get('file')!r} listed in tracks.yaml but missing, skipped")
            continue
        out.append({**t, "path": d / t["file"]})
    return out


def pick_track(tracks: list[dict], mood: str, platform: str, seed: str) -> dict | None:
    pool = [t for t in tracks if platform != "facebook" or t.get("facebook_ok")]
    if not pool:
        return None
    match = [t for t in pool if mood in (t.get("moods") or [])]
    pool = match or pool
    pool = sorted(pool, key=lambda t: t["file"])
    k = int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(pool)
    return pool[k]


def attribution_line(track: dict | None) -> str:
    if not track or not track.get("attribution"):
        return ""
    return f"Music: {track['title']} by {track['artist']}. {track['attribution']}".strip()


# ─── synthesized effects ─────────────────────────────────────────────────
def _t(d):
    return np.arange(int(d * SR)) / SR


def _lp(x, k):
    return np.convolve(x, np.ones(k) / k, mode="same")


def sfx(name: str) -> np.ndarray:
    if name not in SFX_TYPES:
        raise ValueError(f"unknown sfx type {name!r}")
    rng = np.random.default_rng(SFX_TYPES.index(name))
    if name == "whoosh":
        t = _t(0.5)
        n = rng.standard_normal(len(t))
        a = _lp(n, 40) - _lp(n, 400)
        return (a / (np.abs(a).max() + 1e-9) * np.sin(np.pi * t / 0.5) ** 2 * 0.6).astype(np.float32)
    if name == "boom":
        t = _t(0.9)
        f = 80 * np.exp(-t * 3) + 28
        a = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4)
        a += _lp(rng.standard_normal(len(t)), 30) * np.exp(-t * 9) * 0.5
        return (np.tanh(a * 1.6) * 0.8).astype(np.float32)
    if name == "splash":
        t = _t(0.7)
        n = rng.standard_normal(len(t))
        a = (n - _lp(n, 12)) * np.exp(-t * 6) * (0.6 + 0.4 * np.sin(t * 60))
        return (a / (np.abs(a).max() + 1e-9) * 0.5).astype(np.float32)
    if name == "impact":
        t = _t(0.35)
        a = np.sin(2 * np.pi * 120 * t * np.exp(-t * 3)) * np.exp(-t * 14)
        a += _lp(rng.standard_normal(len(t)), 6) * np.exp(-t * 25) * 0.7
        return (np.tanh(a * 1.4) * 0.8).astype(np.float32)
    if name == "pop":
        t = _t(0.12)
        return (np.sin(2 * np.pi * (500 + 1500 * np.exp(-t * 40)) * t) * np.exp(-t * 35) * 0.7).astype(np.float32)
    if name == "ding":
        t = _t(0.9)
        a = (np.sin(2 * np.pi * 1320 * t) + 0.4 * np.sin(2 * np.pi * 2640 * t)) * np.exp(-t * 5)
        return (a * 0.35).astype(np.float32)
    if name == "crackle":
        t = _t(0.7)
        a = np.zeros(len(t))
        for p in rng.integers(0, len(t) - 200, 40):
            a[p:p + 150] += rng.standard_normal(150) * np.exp(-np.arange(150) / 25) * rng.uniform(0.2, 1)
        a = a * np.exp(-t * 2.5)
        return (a / (np.abs(a).max() + 1e-9) * 0.5).astype(np.float32)
    t = _t(0.8)  # creak
    f = 180 + 60 * np.sin(2 * np.pi * 3 * t) + 40 * t
    a = (np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.5 * np.sign(np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR)))
    return (a * np.sin(np.pi * t / 0.8) * 0.18).astype(np.float32)


# ─── mix ─────────────────────────────────────────────────────────────────
def _read(path: Path, ch: int) -> np.ndarray:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", str(ch), "-ar", str(SR), "pipe:1"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(pcm, dtype=np.float32)
    return a.reshape(-1, ch).copy() if ch > 1 else a.copy()


def sfx_times(story: dict, timeline: dict) -> list[tuple[float, str]]:
    """(seconds, sfx type) for every shot `sfx` entry (shot start + at) and every `sfx_mark` event (its word's start
    in the timeline + delay), sorted."""
    beats = {b["i"]: b for b in timeline["beats"]}
    out = []
    for i, sb in enumerate(story.get("beats", [])):
        tb = beats.get(i, {"start": 0, "words": []})
        for s in sb.get("sfx", []):
            out.append((tb["start"] + s.get("at", 0), s["type"]))
        for e in sb.get("events", []):
            if e.get("do") != "sfx_mark":
                continue
            if e.get("sfx") not in SFX_TYPES:
                raise ValueError(f"unknown sfx type {e.get('sfx')!r}")
            w = tb["words"][e.get("at_word", 0)] if e.get("at_word", 0) < len(tb["words"]) else {"s": tb["start"]}
            out.append((w["s"] + float(e.get("delay") or 0), e["sfx"]))
    return sorted(out)


def mix(voice_wav: Path, timeline: dict, story: dict, track: dict | None, out: Path, music_db: float = -20) -> Path:
    voice = _read(voice_wav, 1)
    n = len(voice)
    for b in story.get("beats", []):  # guard: the validator catches this earlier
        for s in b.get("sfx", []):
            if s.get("type") not in SFX_TYPES:
                raise ValueError(f"unknown sfx type {s.get('type')!r}")
    mono = voice.copy()
    if track is not None:
        m = _read(Path(track["path"]), 1)
        if len(m):
            m = np.tile(m, int(np.ceil(n / len(m))))[:n].copy()
            fade = min(int(1.5 * SR), n // 2)
            m[:fade] *= np.linspace(0, 1, fade)
            m[-fade:] *= np.linspace(1, 0, fade)
            hop = SR // 30  # duck under the voice: smoothed voice envelope
            env = np.array([np.sqrt(np.mean(voice[i:i + hop] ** 2) + 1e-12) for i in range(0, n, hop)])
            duck = 1 - 0.55 * np.clip(env / 0.08, 0, 1)
            duck = np.convolve(duck, np.ones(9) / 9, mode="same")
            g = np.interp(np.arange(n), np.arange(len(duck)) * hop + hop / 2, duck)
            mono += m * g * 10 ** (music_db / 20) / (np.sqrt(np.mean(m ** 2)) + 1e-9) * 0.1
    for t, name in sfx_times(story, timeline):
        x = sfx(name)
        p = int(t * SR)
        if 0 <= p < n:
            mono[p:p + len(x)] += x[:n - p] * 0.5
    peak = np.abs(mono).max()
    if peak > 0.95:
        mono *= 0.95 / peak
    st = np.repeat(mono[:, None], 2, axis=1)
    out = Path(out)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "pipe:0",
                    "-c:a", "pcm_s16le", str(out)], input=st.astype(np.float32).tobytes(), check=True)
    return out
