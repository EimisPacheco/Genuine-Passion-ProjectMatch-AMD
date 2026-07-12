"""Agent 11 — Clip Captioning (Gemma vision, four styles).

Captions a fixed set of short video clips (demo_data/clips/). For each clip we
sample frames (start/middle/end) with ffmpeg and ask Gemma vision on the AMD
MI300X for a caption/summary in four distinct styles — formal, sarcastic,
humorous-tech, humorous-non-tech — in a single JSON response. Grounded in the
sampled frames and the clip's citable source URL; degrades to a deterministic
caption when no vision provider (or ffmpeg) is available, so it never hard-fails.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.agents.base import agent_step
from backend.app.agents.visual_portfolio import _vision_target
from backend.app.config import settings
from backend.app.graph.state import ProjectMatchState
from backend.app.llm import engine
from video import captioning

STYLES = ["formal", "sarcastic", "humorous_tech", "humorous_non_tech"]

SYSTEM = (
    "You are captioning a short video clip. You are shown up to three still frames "
    "sampled from the clip (start, middle, end). Base every caption ONLY on what is "
    "actually visible across those frames — do not invent details."
)

PROMPT = (
    "Return JSON with these exact keys, each a 1-2 sentence caption/summary of the "
    "clip written in that style:\n"
    "- formal: professional, precise, neutral.\n"
    "- sarcastic: dry, ironic, deadpan.\n"
    "- humorous_tech: funny with software-engineering in-jokes.\n"
    "- humorous_non_tech: funny for a general audience, no technical jargon.\n"
    'Keys exactly: "formal", "sarcastic", "humorous_tech", "humorous_non_tech".'
)


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    clips_dir = settings.demo_data_dir / "clips"
    clips = captioning.list_clips(clips_dir)
    out: list[dict[str, Any]] = []

    with agent_step("clip_captioning", analysis_id, f"{len(clips)} clips") as h:
        target = _vision_target()
        for clip in clips:
            out.append(_caption(clip, target, h["trace_handle"]))
        how = f"via {target[0]}" if target and out else "heuristically" if out else "no clips"
        h["summary"] = f"captioned {len(out)} clips in 4 styles {how}"

    return {"clip_captions": out}


def _caption(clip: dict[str, Any], target, trace_handle) -> dict[str, Any]:
    frames = captioning.extract_frames(Path(clip["path"]), n=3)
    base = {
        "id": clip["id"],
        "title": clip["title"],
        "source_url": clip.get("source_url", ""),
        "thumb": frames[0] if frames else "",
        "provider": "heuristic",
        "model": "none",
    }
    if not target or not frames:
        base["captions"] = _heuristic(clip["title"])
        return base

    provider, model = target
    try:
        res = engine.complete_json(
            PROMPT, system=SYSTEM, images=frames,
            provider=provider, model=model, trace_handle=trace_handle,
            name="clip_captioning", max_tokens=500,
        )
        caps = {s: str(res.get(s, ""))[:300] for s in STYLES}
        if not any(caps.values()):
            raise ValueError("empty caption set")
        base.update({"captions": caps, "provider": provider, "model": model})
    except Exception:
        base["captions"] = _heuristic(clip["title"])
    return base


def _heuristic(title: str) -> dict[str, str]:
    return {
        "formal": f"A short video clip titled “{title}”.",
        "sarcastic": f"Oh good, “{title}”. Truly the content we were all waiting for.",
        "humorous_tech": f"“{title}”: passes on my machine, ships to prod, prays. 🚀",
        "humorous_non_tech": f"“{title}” — basically a highlight reel your friends will pretend to watch.",
    }
