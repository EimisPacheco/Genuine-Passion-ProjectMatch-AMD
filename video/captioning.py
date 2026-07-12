"""Clip frame extraction for Gemma video captioning.

Gemma 4 accepts image inputs; our stack serves it via Ollama (images, not native
video). So to caption a short clip we sample a few representative frames with
ffmpeg (start / middle / end) and hand them to Gemma vision — the practical
"video understanding" path on this serving stack. This module is media-only (no
LLM): it lists the fixed clip set and returns base64 frame data URIs.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

CLIP_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")


def list_clips(clips_dir: Path) -> list[dict[str, Any]]:
    """The fixed set of short clips to caption. Reads video files from
    `clips_dir`; an optional `clips.json` manifest ([{file,title,source_url}])
    adds titles + a citable source URL (anti-hallucination)."""
    d = Path(clips_dir)
    if not d.exists():
        return []
    manifest: dict[str, dict[str, Any]] = {}
    mf = d / "clips.json"
    if mf.exists():
        try:
            for item in json.loads(mf.read_text()):
                if item.get("file"):
                    manifest[item["file"]] = item
        except Exception:
            pass
    clips: list[dict[str, Any]] = []
    for p in sorted(d.iterdir()):
        if p.suffix.lower() not in CLIP_EXT:
            continue
        meta = manifest.get(p.name, {})
        clips.append({
            "id": p.stem,
            "file": p.name,
            "path": str(p),
            "title": meta.get("title") or p.stem.replace("_", " ").replace("-", " ").title(),
            "source_url": meta.get("source_url", ""),
        })
    return clips


def _duration(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return float(out)
    except Exception:
        return None


def extract_frames(clip_path: Path, n: int = 3) -> list[str]:
    """Sample up to `n` frames (start/middle/end) as downscaled PNG data URIs.
    Empty if ffmpeg is unavailable — the caller then falls back to heuristics."""
    if not shutil.which("ffmpeg"):
        return []
    dur = _duration(clip_path)
    fractions = [0.2, 0.5, 0.8][:max(1, n)]
    times = [round(dur * f, 2) for f in fractions] if dur and dur > 0.6 else [0.0]
    work = Path(tempfile.mkdtemp(prefix="pm_clip_"))
    uris: list[str] = []
    for i, t in enumerate(times):
        out = work / f"f{i}.png"
        cmd = ["ffmpeg", "-y", "-ss", str(t), "-i", str(clip_path),
               "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", str(out)]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except Exception:
            continue
        if out.exists():
            uris.append("data:image/png;base64," + base64.b64encode(out.read_bytes()).decode("ascii"))
    return uris
