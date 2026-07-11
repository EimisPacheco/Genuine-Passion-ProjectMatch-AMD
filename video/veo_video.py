"""Veo 3 (Google DeepMind) text-to-video — drop-in replacement for the Fal path.

Generates b-roll with the Gemini API's **Veo 3.1** model (`predictLongRunning`),
then reuses the provider-agnostic ffmpeg/PIL/TTS helpers from `media`
(overlay_text, narrate, compose_scene, stitch, ...) — only the video-generation
backend changes. Requires GEMINI_API_KEY.

The two video scripts import this module instead of a Fal client, so the same
submit_scene/wait_and_download interface is preserved.
"""
from __future__ import annotations

import base64
import os
import time

import requests

# Reuse the provider-agnostic helpers (ffmpeg / PIL captions / macOS TTS).
from video.media import (  # noqa: F401
    audio_duration,
    compose_scene,
    narrate,
    overlay_text,
    stitch,
    stitch_av,
    _caption_png,
    _font,
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
VEO_MODEL = os.environ.get("VEO_MODEL", "veo-3.1-generate-preview")
API = "https://generativelanguage.googleapis.com/v1beta"


def submit_scene(prompt: str, duration: int = 8, aspect_ratio: str = "16:9",
                 resolution: str = "720p", retries: int = 6, backoff: float = 8.0):
    """Submit a Veo 3 text-to-video job; returns (operation_name, "") to match
    the Fal (status_url, response_url) signature. `response_url` is unused."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set (needed for Veo 3)")
    url = f"{API}/models/{VEO_MODEL}:predictLongRunning?key={GEMINI_API_KEY}"
    body = {"instances": [{"prompt": prompt}],
            "parameters": {"aspectRatio": aspect_ratio}}
    last = None
    for _ in range(retries):
        r = requests.post(url, json=body, timeout=60)
        if r.status_code == 200:
            return r.json()["name"], ""
        last = f"{r.status_code}: {r.text[:180]}"
        if r.status_code in (429, 500, 502, 503):
            time.sleep(backoff)
            continue
        r.raise_for_status()
    raise RuntimeError(f"Veo submit failed after {retries} retries ({last})")


def _find_video(obj):
    """Recursively locate a Veo video payload: (uri, base64) — either may be None."""
    if isinstance(obj, dict):
        if "video" in obj and isinstance(obj["video"], dict):
            v = obj["video"]
            if v.get("uri") or v.get("videoUri"):
                return v.get("uri") or v.get("videoUri"), None
            if v.get("bytesBase64Encoded"):
                return None, v["bytesBase64Encoded"]
        if obj.get("bytesBase64Encoded"):
            return None, obj["bytesBase64Encoded"]
        if obj.get("uri") and str(obj.get("uri")).startswith("http"):
            return obj["uri"], None
        for val in obj.values():
            got = _find_video(val)
            if got != (None, None):
                return got
    elif isinstance(obj, list):
        for item in obj:
            got = _find_video(item)
            if got != (None, None):
                return got
    return None, None


def wait_and_download(operation_name: str, _response_url: str, out_path: str,
                      max_seconds: int = 600) -> str:
    """Poll the Veo long-running operation, then download the generated clip."""
    deadline = time.time() + max_seconds
    op = None
    while time.time() < deadline:
        op = requests.get(f"{API}/{operation_name}?key={GEMINI_API_KEY}", timeout=30).json()
        if op.get("done"):
            break
        if op.get("error"):
            raise RuntimeError(f"Veo op error: {op['error']}")
        time.sleep(8)
    else:
        raise TimeoutError(f"Veo job timed out after {max_seconds}s")
    if op.get("error"):
        raise RuntimeError(f"Veo op error: {op['error']}")
    uri, b64 = _find_video(op.get("response", op))
    if b64:
        open(out_path, "wb").write(base64.b64decode(b64))
        return out_path
    if uri:
        dl = uri + (("&" if "?" in uri else "?") + f"key={GEMINI_API_KEY}")
        open(out_path, "wb").write(requests.get(dl, timeout=600).content)
        return out_path
    raise RuntimeError(f"Veo result missing video payload: {str(op)[:240]}")
