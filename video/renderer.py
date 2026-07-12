"""Slideshow video renderer: scenes -> MP4 + .srt + narration script.

Each scene becomes a rendered slide (Pillow) plus narrated audio (video.tts).
Per-scene segments are built with ffmpeg and concatenated. If ffmpeg is missing
we still emit the narration script and .srt so the pipeline never hard-fails.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from video import tts

W, H = 1280, 720
BG = (15, 23, 42)        # slate-900
ACCENT = (56, 189, 248)  # sky-400
FG = (226, 232, 240)     # slate-200
MUTED = (148, 163, 184)  # slate-400

FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


@dataclass
class Scene:
    title: str
    bullets: list[str]
    narration: str
    subtitle_label: str = ""
    duration: float = 0.0
    max_duration: float | None = None  # hard cap on this scene's length (seconds)
    audio: Path | None = field(default=None)


# Rough spoken-word pace used to trim narration so the audio finishes within a
# scene's max_duration (rather than cutting mid-word).
_WORDS_PER_SEC = 2.6


def _trim_to_duration(text: str, seconds: float) -> str:
    """Shorten narration to comfortably fit `seconds` of speech, ending on a
    sentence boundary when possible."""
    budget = max(8, int(seconds * _WORDS_PER_SEC))
    words = text.split()
    if len(words) <= budget:
        return text
    clipped = " ".join(words[:budget])
    for end in (". ", "! ", "? "):
        idx = clipped.rfind(end)
        if idx > len(clipped) * 0.5:
            return clipped[: idx + 1]
    return clipped.rstrip(",;:") + "."


@dataclass
class VideoResult:
    mp4_path: Path | None
    srt_path: Path
    script_path: Path
    duration: float
    narration: str
    # Per-scene timeline — what the UI uses to keep captions and the narration
    # script in sync with playback: [{index, title, narration, start, end}]
    scenes: list[dict] = field(default_factory=list)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render(scenes: list[Scene], out_dir: Path, basename: str = "executive_summary") -> VideoResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="pm_video_"))

    # 1. narration + audio + durations (respecting each scene's max_duration)
    for i, scene in enumerate(scenes):
        if scene.max_duration:
            scene.narration = _trim_to_duration(scene.narration, scene.max_duration)
        audio_path = work / f"scene_{i}.wav"
        audio, dur = tts.synthesize(scene.narration, audio_path)
        scene.audio = audio
        scene.duration = min(dur, scene.max_duration) if scene.max_duration else dur

    # 2. script + srt always
    script_path = out_dir / f"{basename}.txt"
    script_path.write_text(_script(scenes))
    srt_path = out_dir / f"{basename}.srt"
    srt_path.write_text(_srt(scenes))

    total = round(sum(s.duration for s in scenes), 2)
    narration = "\n\n".join(s.narration for s in scenes)

    # Cumulative timeline, so captions/narration can follow the playhead.
    timeline: list[dict] = []
    t = 0.0
    for i, scene in enumerate(scenes):
        timeline.append({
            "index": i,
            "title": scene.title,
            "label": scene.subtitle_label or scene.title,
            "narration": scene.narration,
            "start": round(t, 2),
            "end": round(t + scene.duration, 2),
        })
        t += scene.duration

    # 3. render slides + segments + concat (needs ffmpeg)
    mp4_path: Path | None = None
    if shutil.which("ffmpeg"):
        try:
            mp4_path = _render_mp4(scenes, work, out_dir / f"{basename}.mp4")
        except Exception as exc:
            print(f"[renderer] ffmpeg render failed, script/srt still produced ({exc})")

    return VideoResult(mp4_path, srt_path, script_path, total, narration, timeline)


def _render_mp4(scenes: list[Scene], work: Path, out: Path) -> Path:
    segments: list[Path] = []
    for i, scene in enumerate(scenes):
        slide = work / f"slide_{i}.png"
        _draw_slide(scene, slide)
        seg = work / f"seg_{i}.mp4"
        _segment(slide, scene, seg)
        segments.append(seg)

    concat_file = work / "concat.txt"
    concat_file.write_text("".join(f"file '{s}'\n" for s in segments))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
         "-c", "copy", str(out)],
        check=True, capture_output=True,
    )
    return out


def _segment(slide: Path, scene: Scene, out: Path) -> None:
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(slide)]
    if scene.audio and scene.audio.exists():
        cmd += ["-i", str(scene.audio), "-c:a", "aac", "-b:a", "128k"]
    # Bound the segment to the (possibly capped) scene duration. This truncates
    # audio that runs past a scene's max_duration and sets length when muted.
    cmd += ["-t", str(round(scene.duration, 2))]
    cmd += ["-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
            "-vf", f"scale={W}:{H}", "-r", "30", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def _draw_slide(scene: Scene, path: Path) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # brand bar
    d.rectangle([0, 0, W, 8], fill=ACCENT)
    d.text((64, 40), "Genuine Passion · ProjectMatch AI", font=_font(22), fill=MUTED)
    # title (wrapped)
    y = 130
    for line in _wrap(scene.title, 30):
        d.text((64, y), line, font=_font(52), fill=FG)
        y += 64
    y += 20
    for bullet in scene.bullets:
        for j, line in enumerate(_wrap(bullet, 64)):
            prefix = "•  " if j == 0 else "    "
            d.text((80, y), prefix + line, font=_font(30), fill=FG)
            y += 44
        y += 6
    img.save(path)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]


def _script(scenes: list[Scene]) -> str:
    parts = []
    for i, s in enumerate(scenes, 1):
        parts.append(f"# Scene {i}: {s.title}\n{s.narration}")
    return "\n\n".join(parts)


def _srt(scenes: list[Scene]) -> str:
    blocks, t = [], 0.0
    for i, s in enumerate(scenes, 1):
        start, end = t, t + s.duration
        blocks.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{s.subtitle_label or s.title}\n")
        t = end
    return "\n".join(blocks)


def _ts(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d},{ms:03d}"
