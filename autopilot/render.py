"""Assemble the Short: footage per scene + narration + word-highlighted captions."""
from pathlib import Path

from .media import probe_duration, run


def _ass_color(rgb: str) -> str:
    rgb = rgb.lstrip("#")
    return f"&H00{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}".upper()


def _clean(word: str, upper: bool) -> str:
    w = word.replace("\\", "").replace("{", "(").replace("}", ")")
    return w.upper() if upper else w


def _fmt(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def build_captions(words: list[tuple], cap: dict, width: int, height: int, path: Path) -> None:
    """words: [(start, end, text)] in absolute seconds. The line sits `cap["margin_v"]` px above the
    bottom edge (default 30% of the height, the Shorts' caption spot)."""
    color, hi = _ass_color(cap["color"]), _ass_color(cap["highlight"])
    margin_v = int(cap["margin_v"]) if cap.get("margin_v") is not None else int(height * 0.30)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{cap['font']},{cap['size']},{color},{color},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{cap['outline']},3,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    n = max(1, int(cap.get("words_per_line", 3)))
    groups, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= n or w[2].rstrip().endswith((".", "?", "!", ",")):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)

    lines = []
    for gi, g in enumerate(groups):
        next_start = groups[gi + 1][0][0] if gi + 1 < len(groups) else g[-1][1] + 0.4
        for wi, (start, end, _) in enumerate(g):
            stop = g[wi + 1][0] if wi + 1 < len(g) else min(next_start, end + 0.35)
            stop = max(stop, start + 0.05)
            parts = []
            for wj, (_, _, txt) in enumerate(g):
                t = _clean(txt, cap.get("uppercase", True))
                parts.append(f"{{\\c{hi}&}}{t}{{\\c{color}&}}" if wj == wi else t)
            pop = "{\\fscx108\\fscy108\\t(0,90,\\fscx100\\fscy100)}" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{_fmt(start)},{_fmt(stop)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


COVER_HOLD = 1.0      # seconds the opening card (thumbnail design) holds before the lead chart takes over
COVER_PUNCH = 0.06    # the opening card (frame 0 = the exact design) pushes in this much...
COVER_PUNCH_S = 0.35  # ...within this many seconds (eased out), then holds


def _segment(slide: dict, dur: float, out: Path, w: int, h: int, fps: int, bg: str = "0x0E0F12",
             zoom: float = 0.035) -> None:
    """One scene: a still slide, either with a chart that draws itself left-to-right
    (a background-coloured box slides off the chart) or with a gentle push-in (`zoom` = growth by the end).
    A slide with `base` + timed `steps` layers (autopilot.reveal) shows its marks one at a time under the wipe."""
    img = str(Path(slide["image"]).resolve())
    base = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", img]
    enc = ["-t", f"{dur:.3f}", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p", str(out)]
    if slide.get("cover"):
        # opening card = thumbnail design: frame 0 is the exact design (the auto-thumbnail), then a quick
        # eased push-in (1.0 → 1.06 in 0.35 s) and hold, so the feed sees motion in the first second
        k = f"{COVER_PUNCH}*(1-pow(max(0,1-t/{COVER_PUNCH_S}),2))"
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
              f"scale=w='trunc({w}*(1+{k})/2)*2':h=-2:eval=frame:flags=bicubic,"
              f"crop={w}:{h},setsar=1,format=yuv420p")
        run(base + ["-vf", vf] + enc)
    elif (slide.get("base") and any(s["layers"] for s in slide.get("steps") or [])
          and all("at" in ly for s in slide["steps"] for ly in s["layers"])):  # every layer timed
        # step reveal (autopilot.reveal): the base (no marks) → each mark's layer fades in at its time →
        # the draw-in box on top, so no mark ever shows ahead of the wipe
        from .reveal import FADE
        layers = [ly for s in slide["steps"] for ly in s["layers"]]
        loop = ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i"]
        cmd = ["ffmpeg", "-y", "-v", "error"] + loop + [str(Path(slide["base"]).resolve())]
        chain, cur = [], "[0:v]"
        for n, ly in enumerate(layers, 1):
            cmd += loop + [str(Path(ly["image"]).resolve())]
            x, y = ly["xy"]
            chain.append(f"[{n}:v]format=rgba,fade=t=in:st={float(ly['at']):.3f}:d={FADE}:alpha=1[l{n}]")
            chain.append(f"{cur}[l{n}]overlay=x={int(x)}:y={int(y)}[s{n}]")
            cur = f"[s{n}]"
        if slide.get("reveal"):
            x, y, cw, ch = slide["reveal"]
            rev = max(min(dur * 0.6, 2.2), 0.5)
            cmd += ["-f", "lavfi", "-i", f"color=c={bg}:s={cw}x{ch}:r={fps}:d={dur:.3f}"]
            chain.append(f"{cur}[{len(layers) + 1}:v]overlay=x='{x}+{cw}*min(t/{rev:.3f},1)':y={y}:eval=frame[w]")
            cur = "[w]"
        chain.append(f"{cur}setsar=1,format=yuv420p[v]")
        run(cmd + ["-filter_complex", ";".join(chain), "-map", "[v]"] + enc)
    elif slide.get("reveal"):
        x, y, cw, ch = slide["reveal"]
        rev = max(min(dur * 0.6, 2.2), 0.5)
        filt = (f"[0:v][1:v]overlay=x='{x}+{cw}*min(t/{rev:.3f},1)':y={y}:eval=frame,"
                f"setsar=1,format=yuv420p[v]")
        run(base + ["-f", "lavfi", "-i", f"color=c={bg}:s={cw}x{ch}:r={fps}:d={dur:.3f}",
                    "-filter_complex", filt, "-map", "[v]"] + enc)
    else:
        vf = (f"scale=w='trunc({w}*(1+{zoom}*t/{dur:.3f})/2)*2':h=-2:eval=frame:flags=bicubic,"
              f"crop={w}:{h},setsar=1,format=yuv420p")
        run(base + ["-vf", vf] + enc)


def page_parts(slide: dict, dur: float) -> list[tuple[dict, float, str]]:
    """[(part, seconds, tag)] of a slide with `pages`: the slide, then each page, sharing `dur` in proportion to
    their `words` (each at least 1); the last part takes the remainder so the scene's length is exact."""
    parts = [slide] + list(slide["pages"])
    ws = [max(1, int(p.get("words") or 1)) for p in parts]
    total, out, used = sum(ws), [], 0.0
    for k, (p, w) in enumerate(zip(parts, ws)):
        d = dur - used if k == len(parts) - 1 else dur * w / total
        used += d
        out.append((p, d, f"p{k}" if k else ""))
    return out


def build_video(scene_audio: list[dict], slides: list[dict], cfg: dict, workdir: Path,
                out_path: Path, music: Path | None = None) -> float:
    v = cfg["video"]
    w, h, fps = v["width"], v["height"], v["fps"]

    # 1) narration: concatenate per-scene wavs, collect absolute word timings
    words, offset = [], 0.0
    with open(workdir / "voice_list.txt", "w") as f:
        for sa in scene_audio:
            f.write(f"file '{Path(sa['audio']).resolve()}'\n")
            words += [(s + offset, e + offset, t) for s, e, t in sa["words"]]
            offset += sa["duration"]
    total = offset
    narration = workdir / "narration.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", workdir / "voice_list.txt", "-c", "copy", narration])

    # 2) one video segment per scene, same length as that scene's narration. A Shorts opening card
    #    (`cover` + `follow`) holds ~COVER_HOLD s, then scene 1's follow-up slide (the lead chart) runs
    #    for the rest of that scene. A slide with `pages` (a long Shorts text, autopilot.shorts.text_scene) shows
    #    itself, then each page, splitting the scene's time in proportion to each part's `words`.
    skip = 0.0
    with open(workdir / "seg_list.txt", "w") as f:
        for i, (sa, slide) in enumerate(zip(scene_audio, slides)):
            parts = [(slide, sa["duration"], "")]
            if slide.get("cover"):
                skip = sa["duration"]
                if slide.get("follow"):
                    skip = min(COVER_HOLD, sa["duration"] / 2)
                    parts = [(slide, skip, ""), (slide["follow"], sa["duration"] - skip, "b")]
            elif slide.get("pages"):
                parts = page_parts(slide, sa["duration"])
            for part, dur, tag in parts:
                seg = workdir / f"seg_{i:02d}{tag}.mp4"
                _segment(part, dur, seg, w, h, fps, zoom=v.get("push_in", 0.035))
                f.write(f"file '{seg.resolve()}'\n")
    silent = workdir / "video_silent.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", workdir / "seg_list.txt", "-c", "copy", silent])

    # 3) captions (none over the opening card, so it stays clean as a thumbnail); a word already
    #    being spoken when the card hands over gets its caption from that moment
    if skip:
        words = [(max(s, skip), e, t) for s, e, t in words if e > skip]
    build_captions(words, v["captions"], w, h, workdir / "captions.ass")

    # 4) final mix: burn captions, loudness-normalise voice, optional quiet music
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", silent.name, "-i", narration.name]
    voice_chain = "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000"
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(Path(music).resolve())]
        fade_at = max(total - 1.5, 0)
        audio = (f"{voice_chain}[vo];"
                 f"[2:a]volume={v['music_volume']},afade=t=out:st={fade_at:.2f}:d=1.5,"
                 f"aresample=48000[mu];[vo][mu]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        audio = f"{voice_chain}[a]"
    filt = f"[0:v]ass=captions.ass[v];{audio}"
    # closed ~2 s GOP and stereo AAC: the Facebook Reels spec (YouTube accepts it too)
    cmd += ["-filter_complex", filt, "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-g", str(2 * fps), "-flags", "+cgop",
            "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart",
            str(Path(out_path).resolve())]
    run(cmd, cwd=workdir)  # cwd so the subtitle path needs no escaping
    return total
