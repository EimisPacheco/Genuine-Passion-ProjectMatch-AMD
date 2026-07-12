"""Offline text-to-speech for video narration.

Strategy (no paid API): macOS `say` first (reliable on the dev machine), then
pyttsx3 (cross-platform via espeak), then a silent fallback. Returns a path to a
WAV file or None when narration is silent. Duration is measured via ffprobe with
a words-per-second estimate as fallback.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.app.config import settings

WORDS_PER_SECOND = 2.6


def estimate_duration(text: str) -> float:
    words = max(len(text.split()), 1)
    return max(2.0, round(words / WORDS_PER_SECOND, 2))


def synthesize(text: str, out_path: Path) -> tuple[Path | None, float]:
    """Render `text` to a WAV at out_path. Returns (path|None, duration_seconds)."""
    text = text.strip()
    if not text or not settings.tts_enabled:
        return None, estimate_duration(text)

    audio = _macos_say(text, out_path) or _pyttsx3(text, out_path)
    if audio is None:
        return None, estimate_duration(text)
    return audio, _probe_duration(audio) or estimate_duration(text)


def _macos_say(text: str, out_path: Path) -> Path | None:
    if platform.system() != "Darwin" or not shutil.which("say"):
        return None
    if not shutil.which("ffmpeg"):
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
            aiff = Path(tmp.name)
        opts: list[str] = []
        if settings.tts_voice:
            opts += ["-v", settings.tts_voice]
        if settings.tts_rate:
            opts += ["-r", str(settings.tts_rate)]
        try:  # configured voice; fall back to the default if it isn't installed
            subprocess.run(["say", *opts, "-o", str(aiff), text], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            subprocess.run(["say", "-o", str(aiff), text], check=True, capture_output=True)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(aiff), str(out_path)],
            check=True, capture_output=True,
        )
        aiff.unlink(missing_ok=True)
        return out_path
    except Exception as exc:
        print(f"[tts] macOS say failed ({exc})")
        return None


def _pyttsx3(text: str, out_path: Path) -> Path | None:
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.save_to_file(text, str(out_path))
        engine.runAndWait()
        return out_path if out_path.exists() and out_path.stat().st_size > 0 else None
    except Exception as exc:
        print(f"[tts] pyttsx3 failed ({exc})")
        return None


def _probe_duration(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, text=True,
        )
        return round(float(out.stdout.strip()), 2)
    except Exception:
        return None
