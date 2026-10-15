"""Step-by-step reveal of a slide's marks, timed to the narration (generic: no lesson vocabulary).

A revealed slide carries, next to its full `image`:
    "base":  the slide with none of the revealed marks painted (same layout as the full slide)
    "steps": [{"names": [spoken aliases], "layers": [{"image": path, "xy": (x, y)}]}]   in reveal order
Layer k is cumulative frame k cropped to what changed since frame k-1 (diff_crops), so overlaying the layers
in order on the base reproduces the full slide exactly. time_steps gives every layer its "at" (seconds into
the scene): each step starts at the first narration sentence naming it (searched forward from the previous
step's sentence; unnamed → the sentence after its predecessor's), its layers STAGGER apart (squeezed to at
least MIN_GAP when the next step comes sooner), all before the scene ends. render._segment fades each layer
in over FADE seconds at its time. Same inputs → same output.
"""
import re
from pathlib import Path

FADE = 0.25  # s, one layer's fade-in
STAGGER = 0.35  # s between the layers of one step
MIN_GAP = 0.25  # s, the tightest the layers ever get
NEAR = 3  # words either side of the proportional index searched for a sentence's first word
_SENTENCE = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"'”’)]))\s+")  # after . ! ? (and a closing quote)


def split_sentences(text: str) -> list[str]:
    """Sentences of a narration text (split after . ! ? followed by space); [] for empty text."""
    return [s.strip() for s in _SENTENCE.split(str(text or "").strip()) if s.strip()]


def _norm(word: str) -> str:
    return re.sub(r"[^0-9a-z]", "", str(word).lower())


def sentence_starts(text: str, words: list[tuple], duration: float) -> list[float]:
    """Start time (s, scene-relative) of each sentence of `text`. `words` = the voice's [(start, end, word)].
    Each sentence's first token is found in the word list: by index when the counts match, else the nearest
    word with the same normalized text within NEAR places of the proportional index, else proportional time.
    Never goes backwards."""
    tokens = str(text or "").split()
    sentences = split_sentences(text)
    n, m = len(tokens), len(words or [])
    out, idx, last = [], 0, 0.0
    for s in sentences:
        k = idx
        idx += len(s.split())
        if m and m == n:
            t = float(words[k][0])
        else:
            t = None
            if m and n:
                p = round(k * m / n)
                target = _norm(tokens[k]) if k < n else ""
                cands = [j for j in range(max(0, p - NEAR), min(m, p + NEAR + 1)) if target and _norm(words[j][2]) == target]
                if cands:
                    t = float(words[min(cands, key=lambda j: (abs(j - p), j))][0])
            if t is None:
                t = float(words[0][0]) if k == 0 and m else (duration * k / n if n else 0.0)
        last = max(last, t)
        out.append(last)
    return out


def _alias_rx(alias: str) -> re.Pattern:
    """An alias as a case-insensitive whole-phrase pattern: spaces / hyphens interchangeable, each word may
    take a plural ending, never inside a word or a contraction ("LL" is not "we'll")."""
    words = [re.escape(w) + r"(?:e?s)?" for w in re.split(r"[\s\-]+", alias.strip()) if w]
    return re.compile(r"(?<![\w'’])" + r"[\s\-]+".join(words) + r"(?![\w'’])", re.IGNORECASE)


def names_in(sentence: str, names: list[str]) -> bool:
    return any(_alias_rx(a).search(sentence) for a in names if str(a).strip())


def step_sentences(names_per_step: list[list[str]], sentences: list[str]) -> list[int]:
    """The sentence index each step starts at: the first sentence, from the previous step's on, that
    names one of its aliases; unnamed → the sentence after its predecessor's (clamped to the last)."""
    out, prev = [], -1
    last = max(len(sentences) - 1, 0)
    for names in names_per_step:
        start = max(prev, 0)
        k = next((i for i in range(start, len(sentences)) if names_in(sentences[i], names)), None)
        if k is None:
            k = min(prev + 1, last)
        out.append(k)
        prev = k
    return out


def _bbox(a, b) -> tuple[int, int, int, int] | None:
    from PIL import ImageChops
    return ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox()


def diff_crops(frames: list, workdir: Path, stem: str) -> list[dict | None]:
    """Cumulative frames [frame 0 (nothing revealed), frame 1, …, frame N] → N layers: frame k cropped to the
    box where it differs from frame k-1 (edges on even pixels, for yuv420), saved as <stem>_<k>.png;
    None when frame k adds nothing (e.g. a mark outside the zoomed chart)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    out = []
    for k in range(1, len(frames)):
        box = _bbox(frames[k], frames[k - 1])
        if box is None:
            out.append(None)
            continue
        w, h = frames[k].size
        x0, y0 = box[0] - box[0] % 2, box[1] - box[1] % 2
        x1, y1 = min(w, box[2] + box[2] % 2), min(h, box[3] + box[3] % 2)
        path = workdir / f"{stem}_{k:02d}.png"
        frames[k].convert("RGB").crop((x0, y0, x1, y1)).save(path)
        out.append({"image": path, "xy": (x0, y0)})
    return out


def layer_times(step_starts: list[float], counts: list[int], duration: float) -> list[list[float]]:
    """Times of each step's layers: step k's from its start, STAGGER apart, squeezed (≥ MIN_GAP) when the
    next step comes sooner; never backwards, at least MIN_GAP apart overall, all fully in before `duration`
    (pulled earlier when the scene is too short, evenly spread if even that can't fit)."""
    starts = [max(0.0, float(t)) for t in step_starts]
    flat = []
    for k, (t, n) in enumerate(zip(starts, counts)):
        if not n:
            continue
        nxt = next((starts[j] for j in range(k + 1, len(starts)) if counts[j]), None)
        gap = STAGGER if nxt is None else max(MIN_GAP, min(STAGGER, (nxt - t) / n))
        flat += [t + j * gap for j in range(n)]
    for j in range(1, len(flat)):  # never backwards, never closer than MIN_GAP
        flat[j] = max(flat[j], flat[j - 1] + MIN_GAP)
    limit = max(0.0, duration - FADE - 0.05)
    if flat and flat[-1] > limit:  # pull the tail in so every layer is in before the scene ends
        n = len(flat)
        for j in range(n):
            flat[j] = min(flat[j], limit - (n - 1 - j) * MIN_GAP)
        if flat[0] < 0:
            step = limit / max(n - 1, 1)
            flat = [j * step if n > 1 else 0.0 for j in range(n)]
    out, i = [], 0
    for n in counts:
        out.append([round(x, 3) for x in flat[i:i + n]])
        i += n
    return out


def time_steps(slides: list[dict], scenes: list[dict], audio: list[dict], log=lambda m: None) -> list[dict]:
    """Set each layer's "at" (seconds into its scene) on every slide that has `steps`, from that scene's
    narration text and voice word timings; logs one line per stepped slide (each step's sentence, named
    or fallback). Returns `slides` (changed in place)."""
    for slide, scene, a in zip(slides, scenes, audio):
        steps = slide.get("steps")
        if not steps:
            continue
        text = scene.get("text", "")
        sentences = split_sentences(text)
        starts = sentence_starts(text, a.get("words") or [], a["duration"])
        at = step_sentences([s.get("names") or [] for s in steps], sentences)
        times = layer_times([starts[k] if starts else 0.0 for k in at], [len(s["layers"]) for s in steps],
                            a["duration"])
        for s, ts in zip(steps, times):
            for layer, t in zip(s["layers"], ts):
                layer["at"] = t
        log(f"Step reveal {slide.get('id')}: " + ", ".join(
            f"{s.get('key') or s.get('name') or n} → sentence {k + 1}"
            + ("" if k < len(sentences) and names_in(sentences[k], s.get("names") or []) else " (fallback)")
            for n, (s, k) in enumerate(zip(steps, at), 1)))
    return slides
