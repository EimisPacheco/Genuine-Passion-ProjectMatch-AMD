"""On-demand caption for a recommendation video (Gemma vision, one chosen style).

The user picks a tone under the video player and clicks "Generate caption". We
sample frames from *that analysis's* rendered MP4 with ffmpeg, hand them to Gemma
vision on the AMD MI300X along with the narration script, and get back a single
caption written in the requested style. Nothing runs during the pipeline — this is
purely on demand, so it costs nothing until asked for.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.agents.visual_portfolio import _vision_target
from backend.app.llm import engine
from video import captioning

STYLES: dict[str, str] = {
    "formal": "professional, precise and neutral — suitable for an executive audience",
    "sarcastic": "dry, ironic and deadpan",
    "humorous_tech": "funny, with software-engineering in-jokes",
    "humorous_non_tech": "funny for a general audience, with no technical jargon",
}

SYSTEM = (
    "You are writing a caption for a short recommendation video. You are shown frames "
    "sampled from the video and given its narration script. Ground the caption in what "
    "the video actually shows and says — never invent people, names or numbers."
)


def caption_video(video_path: str, narration: str, style: str) -> dict[str, Any]:
    """Caption the video in one style. Returns {style, caption, provider, model}."""
    key = (style or "formal").lower()
    if key not in STYLES:
        raise ValueError(f"unknown style '{style}' (expected one of {list(STYLES)})")

    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError("video not available for this analysis")

    frames = captioning.extract_frames(path, n=3)
    target = _vision_target()
    if not target or not frames:
        raise RuntimeError("no vision provider or no frames could be read from the video")

    provider, model = target
    prompt = (
        f"Write ONE caption (2-3 sentences) for this recommendation video, in a style that is "
        f"{STYLES[key]}.\n\n"
        f"Narration script (for context):\n{(narration or '')[:1200]}\n\n"
        'Return JSON with a single key "caption".'
    )
    res = engine.complete_json(
        prompt, system=SYSTEM, images=frames,
        provider=provider, model=model, name="video_caption", max_tokens=400,
    )
    caption = str(res.get("caption", "")).strip()[:600]
    if not caption:
        raise RuntimeError("the vision model returned an empty caption")
    return {"style": key, "caption": caption, "provider": provider, "model": model}
