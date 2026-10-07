"""Narration with word timings via edge-tts (free Microsoft Edge neural voices)."""
import asyncio
from pathlib import Path

import edge_tts

from .media import probe_duration, run


async def _speak(text: str, voice: str, rate: str, mp3_path: Path) -> list[tuple]:
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7          # 100-ns ticks → seconds
                end = (chunk["offset"] + chunk["duration"]) / 1e7
                words.append((start, end, chunk["text"]))
    return words


def synthesize(scenes: list[dict], voice: str, rate: str, workdir: Path, log=print) -> list[dict]:
    """One audio file per scene, so scene lengths are exact.

    Returns [{"audio": wav_path, "duration": seconds, "words": [(start, end, text), ...]}]
    with word times relative to the start of that scene.
    """
    out = []
    for i, scene in enumerate(scenes):
        mp3 = workdir / f"voice_{i:02d}.mp3"
        wav = workdir / f"voice_{i:02d}.wav"
        for attempt in range(4):
            try:
                words = asyncio.run(_speak(scene["text"], voice, rate, mp3))
                if mp3.stat().st_size > 1000:
                    break
            except Exception as e:  # network hiccups from the TTS service
                log(f"TTS attempt {attempt + 1} failed for scene {i + 1}: {e}")
        else:
            raise RuntimeError(f"TTS failed for scene {i + 1}")
        # decode to wav so durations (and caption timing) are exact
        run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ar", "44100", "-ac", "1", str(wav)])
        out.append({"audio": wav, "duration": probe_duration(wav), "words": words})
    return out
