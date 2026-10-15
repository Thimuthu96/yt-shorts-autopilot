"""Narration with word timings via edge-tts (free Microsoft Edge neural voices).

Microsoft's endpoint sometimes refuses GitHub's runners for a while (403 on the websocket, Oct 2026),
so each scene is retried with growing waits (EDGE_WAITS). If a scene still fails, the whole video is
voiced by the `fallback` Piper voice instead (free, runs on the runner, can't be blocked; one voice
per video), and the rest of the run goes straight to Piper. Piper gives no word timings, so caption
timings are estimated from word lengths over the spoken span.

Delivery (narration-rules.md, CAP-7): rate +0% (config), and `pauses=True` (briefs, gold) speaks
`paced(text)`: a comma after a spoken key number and before the scene's concept term. edge-tts 7.2.8
XML-escapes the text, so SSML (<break>, <emphasis>) never reaches the service: pauses are punctuation
and emphasis is dropped. Captions keep the script's words (edge-tts: commas aren't words; Piper: the
estimate over the paced text is shown with the script's words).
"""
import asyncio
import os
import re
import time
import wave
from pathlib import Path

import edge_tts

from .media import probe_duration, run

EDGE_WAITS = (0, 10, 30, 60)  # seconds before each edge-tts attempt (~100 s per scene before falling back)
PIPER_DIR = Path(os.environ.get("PIPER_VOICES", Path.home() / ".cache" / "piper"))
_edge_down = False  # set once edge-tts failed in this run: later calls (e.g. a faster re-record) use Piper

_NUM = (r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
        r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
        r"hundred|thousand|million|billion|trillion|half")
_BIG = r"hundred|thousand|million|billion|trillion"
_W = rf"(?:[a-z]+-)?(?:{_NUM})"  # one spoken number word ("sixty", "sixty-two")
_DIGITS = r"\d+(?:,\d{3})*(?:\.\d+)?"
# words after which a pause sounds natural; a number used as an adjective ("a five percent drop") or bound to
# a noun ("$500 million in outflows") gets none, nor a range ("2% to 3%", "forty-one hundred and fifty")
_PAUSE_BEFORE = (r"to|after|as|and|but|while|since|on|at|from|with|for|over|today|overnight|this|"
                 r"against|versus|so|then|before|which")
# "to / and / or" + another number of the same kind is a range ("2% to 3%", "$1,200 to $63,000"): no pause.
# Of another kind it is a move then a level ("two percent, to about sixty-two thousand dollars"): pause.
_NEXT_NUMBER = re.compile(
    rf"\s+(?:to|and|or)\s+(?:about\s+|around\s+|roughly\s+|nearly\s+)?"
    rf"(\$?{_DIGITS}\s?%?|(?:{_W})(?:\s+(?:{_W}|point))*)(?![\w-])(\s+(?:percentage points?|percent|per cent|basis points?|points)\b)?",
    re.I)


def _percent_like(number: str) -> bool:
    return bool(re.search(r"%|\b(?:percent|per cent|points?)\b", number, re.I))


# a price or a percentage, spoken ("two point one percent", "sixty-two thousand dollars", the gold edition's
# "forty-one forty-three": two or more number words, or one ending in hundred/thousand/…) or in digits
KEY_NUMBER = re.compile(
    rf"(?:\${_DIGITS}(?:\s+(?:{_BIG}))?|{_DIGITS}\s?%"
    rf"|(?<![\w-])(?:{_DIGITS}|{_W})\s+(?:percentage points?|percent|per cent|dollars|basis points?|points)"
    rf"|(?<![\w-])(?:{_W}\s+)+(?:{_W})(?<![a-z]-)\b|(?<![\w-])(?:{_W}\s+)*(?:{_BIG})\b)"
    rf"(?=\s+(?:{_PAUSE_BEFORE})\b)", re.I)
_NAMING = r"\b(?:is|are|was|were|called|named|means)"  # the verbs a concept term's pause follows


def paced(text: str, term: str | None = None) -> str:
    """The text with a comma (a short spoken pause) after each key number that runs straight into an
    allow-listed word, and before the first `term` (with its article) right after a naming verb ("this is
    called, a liquidity sweep"). Only commas are added to existing words; the words themselves are unchanged."""
    def pause(m: re.Match) -> str:
        nxt = _NEXT_NUMBER.match(m.string, m.end())
        if nxt and _percent_like(m.group(0)) == _percent_like(nxt.group(0)):
            return m.group(0)  # a range: keep it together
        return m.group(0) + ","
    out = KEY_NUMBER.sub(pause, text)
    if term and term.strip():
        m = re.search(rf"{_NAMING}(\s+)((?:a|an|the)\s+)?{re.escape(term.strip())}(?:e?s)?(?![\w-])", out, re.I)
        if m:
            out = out[:m.start(1)] + "," + out[m.start(1):]
    return out


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


def _spoken(scene: dict, pauses: bool) -> str:
    return paced(scene["text"], scene.get("term")) if pauses else scene["text"]


def _edge(scenes: list[dict], voice: str, rate: str, workdir: Path, log, pauses: bool = False) -> list[dict] | None:
    """edge-tts for every scene, or None when a scene still fails after all EDGE_WAITS."""
    out = []
    for i, scene in enumerate(scenes):
        text = _spoken(scene, pauses)
        mp3 = workdir / f"voice_{i:02d}.mp3"
        wav = workdir / f"voice_{i:02d}.wav"
        for attempt, wait in enumerate(EDGE_WAITS):
            if wait:
                time.sleep(wait)
            try:
                words = asyncio.run(_speak(text, voice, rate, mp3))
                if mp3.stat().st_size > 1000:
                    break
            except Exception as e:  # network hiccups or a refused runner (403)
                log(f"TTS attempt {attempt + 1} failed for scene {i + 1}: {str(e)[:120]}")
        else:
            return None
        # decode to wav so durations (and caption timing) are exact
        run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ar", "44100", "-ac", "1", str(wav)])
        out.append({"audio": wav, "duration": probe_duration(wav), "words": words, "voice": voice})
    return out


def _piper_voice(model: str):
    """The Piper voice, downloaded once into PIPER_DIR (~60-120 MB from Hugging Face)."""
    from piper import PiperVoice
    PIPER_DIR.mkdir(parents=True, exist_ok=True)
    onnx = PIPER_DIR / f"{model}.onnx"
    if not (onnx.exists() and onnx.with_suffix(".onnx.json").exists()):
        from piper.download_voices import download_voice
        download_voice(model, PIPER_DIR)
    return PiperVoice.load(str(onnx))


def length_scale(rate: str) -> float:
    """edge-tts rate ("+10%") → Piper length_scale (smaller = faster)."""
    pct = int(re.sub(r"[^\d-]", "", rate) or 0)
    return round(1 / max(1 + pct / 100, 0.5), 3)


def estimate_words(text: str, duration: float, lead: float = 0.08, tail: float = 0.2) -> list[tuple]:
    """Word timings spread over the spoken span by word length (+ a pause after punctuation)."""
    words = text.split()
    if not words:
        return []
    weights = [len(w) + 1 + (3 if w.endswith((".", ",", "?", "!", ";", ":")) else 0) for w in words]
    span = max(duration - lead - tail, 0.1)
    unit, t, out = span / sum(weights), lead, []
    for w, k in zip(words, weights):
        talk = (len(w) + 1) * unit
        out.append((round(t, 3), round(t + talk, 3), w))
        t += k * unit
    return out


def _piper(scenes: list[dict], model: str, rate: str, workdir: Path, pauses: bool = False) -> list[dict]:
    from piper.config import SynthesisConfig
    pv = _piper_voice(model)
    syn = SynthesisConfig(length_scale=length_scale(rate))
    out = []
    for i, scene in enumerate(scenes):
        text = _spoken(scene, pauses)
        raw = workdir / f"voice_{i:02d}_piper.wav"
        wav = workdir / f"voice_{i:02d}.wav"
        with wave.open(str(raw), "wb") as w:
            pv.synthesize_wav(text, w, syn_config=syn)
        run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-ar", "44100", "-ac", "1", str(wav)])
        dur = probe_duration(wav)
        # timed over the spoken text (its commas count as pauses), shown as the script's own words
        est, shown = estimate_words(text, dur), scene["text"].split()
        words = [(a, b, w) for (a, b, _), w in zip(est, shown)] if len(est) == len(shown) else est
        out.append({"audio": wav, "duration": dur, "words": words, "voice": model})
    return out


def synthesize(scenes: list[dict], voice: str, rate: str, workdir: Path, log=print,
               fallback: str | None = None, pauses: bool = False) -> list[dict]:
    """One audio file per scene, so scene lengths are exact.

    Returns [{"audio": wav_path, "duration": seconds, "words": [(start, end, text), ...], "voice": who}]
    with word times relative to the start of that scene; "voice" = the edge-tts voice or Piper model that spoke. `fallback` = Piper voice name
    (e.g. "en_US-ryan-high") used when edge-tts keeps failing; None = fail instead. `pauses` speaks
    `paced()` text (key-number and concept-term pauses; scene["term"] is optional).
    """
    global _edge_down
    if not _edge_down:
        out = _edge(scenes, voice, rate, workdir, log, pauses)
        if out is not None:
            return out
        _edge_down = True
        if not fallback:
            raise RuntimeError("TTS failed (edge-tts) and no fallback voice is set (voice.fallback)")
        log(f"edge-tts keeps failing; voicing this video with the fallback Piper voice {fallback}")
    elif not fallback:
        raise RuntimeError("TTS failed (edge-tts) and no fallback voice is set (voice.fallback)")
    out = _piper(scenes, fallback, rate, workdir, pauses)
    log(f"Narration by Piper ({fallback}); caption timings estimated")
    return out
