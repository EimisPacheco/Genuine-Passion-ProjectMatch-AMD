"""Text-to-speech for video narration.

Strategy: **Google Cloud TTS** first (Studio/Neural2 voices — near-human, needs
the Text-to-Speech API enabled and a service-account key), then macOS `say`, then
pyttsx3, then a silent fallback. Returns a path to a WAV file or None when
narration is silent. Duration is measured via ffprobe with a words-per-second
estimate as fallback.
"""
from __future__ import annotations

import os
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

    audio = None
    if (settings.tts_provider or "").lower() == "gcloud":
        audio = _gcloud_tts(text, out_path)
    audio = audio or _macos_say(text, out_path) or _pyttsx3(text, out_path)
    if audio is None:
        return None, estimate_duration(text)
    return audio, _probe_duration(audio) or estimate_duration(text)


def _gcloud_tts(text: str, out_path: Path) -> Path | None:
    """Google Cloud Text-to-Speech (Studio / Neural2) — a natural, non-robotic
    narrator. Returns None on any failure so the caller falls back to `say`."""
    try:
        from google.cloud import texttospeech as tts

        cred = settings.google_credentials_file
        if cred and Path(cred).exists():
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(Path(cred).resolve()))
        client = tts.TextToSpeechClient()
        resp = client.synthesize_speech(
            input=tts.SynthesisInput(text=text),
            voice=tts.VoiceSelectionParams(
                language_code=settings.gcloud_tts_language,
                name=settings.gcloud_tts_voice,
            ),
            audio_config=tts.AudioConfig(
                audio_encoding=tts.AudioEncoding.LINEAR16,
                speaking_rate=settings.gcloud_tts_rate,
            ),
        )
        out_path.write_bytes(resp.audio_content)
        return out_path if out_path.stat().st_size > 0 else None
    except Exception as exc:
        print(f"[tts] Google Cloud TTS unavailable, falling back to `say` ({str(exc)[:120]})")
        return None


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
