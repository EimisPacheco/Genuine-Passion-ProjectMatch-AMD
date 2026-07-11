"""Shared media helpers — ffmpeg compositing, PIL caption rendering, macOS TTS.

Provider-agnostic building blocks used by the video scripts: caption overlay,
narration (macOS `say`), audio duration, scene compose, and stitching. The
text-to-video generation backend lives in `veo_video.py` (Veo 3).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

from PIL import Image, ImageDraw, ImageFont

FFMPEG = os.environ.get("FFMPEG_PATH", shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH", shutil.which("ffprobe") or os.path.join(os.path.dirname(FFMPEG), "ffprobe"))
NARRATOR_VOICE = os.environ.get("NARRATOR_VOICE", "Samantha")  # one consistent macOS voice
# This ffmpeg build has no drawtext (no libfreetype), so captions are rendered as
# a Pillow PNG and composited via the core `overlay` filter.
_FONTS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _font(size: int):
    for f in _FONTS:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _caption_png(lines: list[str], png_path: str, size=(1280, 720)) -> None:
    """Render a bottom caption block (title bold, body lighter) as a PNG overlay."""
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    title_f = _font(46)
    body_f = _font(32)
    pad, x = 36, 64
    fonts = [title_f] + [body_f] * (len(lines) - 1)
    heights = [(d.textbbox((0, 0), ln or " ", font=f)[3]) + 14 for ln, f in zip(lines, fonts)]
    block_h = sum(heights) + 2 * pad
    widths = [d.textbbox((0, 0), ln or " ", font=f)[2] for ln, f in zip(lines, fonts)]
    block_w = min(max(widths) + 2 * pad, W - 2 * 40)
    y0 = H - block_h - 56
    d.rounded_rectangle([40, y0, 40 + block_w, y0 + block_h], radius=20, fill=(15, 23, 42, 210))
    # brand accent bar
    d.rectangle([40, y0, 48, y0 + block_h], fill=(56, 189, 248, 255))
    yy = y0 + pad
    for ln, f, h in zip(lines, fonts, heights):
        color = (56, 189, 248, 255) if f is title_f else (226, 232, 240, 255)
        d.text((x, yy), ln, font=f, fill=color)
        yy += h
    img.save(png_path)


def overlay_text(in_path: str, out_path: str, lines: list[str]) -> str:
    """Composite the candidate explanation caption onto a clip (Pillow + overlay)."""
    png = tempfile.mktemp(suffix=".png")
    _caption_png(lines, png)
    # Explicit format chain — generated clips can report unknown color_range/space, which
    # makes a bare `overlay` drop the PNG alpha (no-op). Convert to rgba first.
    subprocess.run(
        [FFMPEG, "-y", "-i", in_path, "-i", png,
         "-filter_complex", "[0:v]format=rgba[b];[b][1:v]overlay=0:0,format=yuv420p",
         "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path],
        check=True, capture_output=True,
    )
    os.remove(png)
    return out_path


def narrate(text: str, out_path: str, voice: str | None = None) -> str:
    """macOS `say` -> aac audio (one consistent narrator voice for the whole video)."""
    voice = voice or NARRATOR_VOICE
    aiff = tempfile.mktemp(suffix=".aiff")
    subprocess.run(["say", "-v", voice, "-o", aiff, text], check=True)
    subprocess.run([FFMPEG, "-y", "-i", aiff, "-c:a", "aac", "-b:a", "160k", out_path],
                   check=True, capture_output=True)
    os.remove(aiff)
    return out_path


def audio_duration(path: str) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 5.0


def compose_scene(broll: str, lines: list[str], audio: str, out_path: str) -> str:
    """Caption a b-roll clip, loop it to the narration length, and mux the voice."""
    capped = tempfile.mktemp(suffix=".mp4")
    overlay_text(broll, capped, lines)
    dur = audio_duration(audio)
    subprocess.run(
        [FFMPEG, "-y", "-stream_loop", "-1", "-i", capped, "-i", audio,
         "-map", "0:v:0", "-map", "1:a:0", "-t", f"{dur:.2f}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24", "-c:a", "aac", out_path],
        check=True, capture_output=True,
    )
    os.remove(capped)
    return out_path


def stitch_av(paths: list[str], out_path: str) -> str:
    """Concat scenes that each carry video + narration audio."""
    lst = tempfile.mktemp(suffix=".txt")
    open(lst, "w").write("\n".join(f"file '{p}'" for p in paths))
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24", "-c:a", "aac", "-b:a", "160k", out_path],
        check=True, capture_output=True,
    )
    os.remove(lst)
    return out_path


def stitch(paths: list[str], out_path: str) -> str:
    lst = tempfile.mktemp(suffix=".txt")
    open(lst, "w").write("\n".join(f"file '{p}'" for p in paths))
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24", "-an", out_path],
        check=True, capture_output=True,
    )
    os.remove(lst)
    return out_path
