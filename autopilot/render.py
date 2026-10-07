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
    """words: [(start, end, text)] in absolute seconds."""
    color, hi = _ass_color(cap["color"]), _ass_color(cap["highlight"])
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{cap['font']},{cap['size']},{color},{color},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{cap['outline']},3,2,80,80,{int(height * 0.30)},1

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


def _segment(slide: dict, dur: float, out: Path, w: int, h: int, fps: int, bg: str = "0x0E0F12") -> None:
    """One scene: a still slide, either with a chart that draws itself left-to-right
    (a background-coloured box slides off the chart) or with a gentle push-in."""
    img = str(Path(slide["image"]).resolve())
    base = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", img]
    enc = ["-t", f"{dur:.3f}", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p", str(out)]
    if slide.get("reveal"):
        x, y, cw, ch = slide["reveal"]
        rev = max(min(dur * 0.6, 2.2), 0.5)
        filt = (f"[0:v][1:v]overlay=x='{x}+{cw}*min(t/{rev:.3f},1)':y={y}:eval=frame,"
                f"setsar=1,format=yuv420p[v]")
        run(base + ["-f", "lavfi", "-i", f"color=c={bg}:s={cw}x{ch}:r={fps}:d={dur:.3f}",
                    "-filter_complex", filt, "-map", "[v]"] + enc)
    else:
        zoom = 0.035
        vf = (f"scale=w='trunc({w}*(1+{zoom}*t/{dur:.3f})/2)*2':h=-2:eval=frame:flags=bicubic,"
              f"crop={w}:{h},setsar=1,format=yuv420p")
        run(base + ["-vf", vf] + enc)


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

    # 2) one video segment per scene, same length as that scene's narration
    with open(workdir / "seg_list.txt", "w") as f:
        for i, (sa, slide) in enumerate(zip(scene_audio, slides)):
            seg = workdir / f"seg_{i:02d}.mp4"
            _segment(slide, sa["duration"], seg, w, h, fps)
            f.write(f"file '{seg.resolve()}'\n")
    silent = workdir / "video_silent.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", workdir / "seg_list.txt", "-c", "copy", silent])

    # 3) captions
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
    cmd += ["-filter_complex", filt, "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(Path(out_path).resolve())]
    run(cmd, cwd=workdir)  # cwd so the subtitle path needs no escaping
    return total
