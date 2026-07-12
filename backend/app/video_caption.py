"""Timed captions for the recommendation video — the WHOLE video, two audiences.

Generated once, right after the video is rendered (not on click), so the Video tab
is instant. For each audience we make a single Gemma vision call: it sees frames
sampled from the video plus the scene-by-scene narration, and returns one caption
per scene. Each caption carries the scene's start/end, so the UI can keep the
caption, the narration script and the playhead in sync — and so the captions can
be served as the video's own subtitle track.

The same video is read by two very different people:
  * a technical hiring manager — wants the engineering substance
  * an HR recruiter — wants plain language and fit
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.app.agents.visual_portfolio import _vision_target
from backend.app.llm import engine
from video import captioning

STYLES: dict[str, str] = {
    "tech": (
        "a technical hiring manager. Be concrete about the engineering: the stack, the "
        "architecture, and what the candidates' work actually demonstrates. Technical "
        "vocabulary is expected"
    ),
    "non_tech": (
        "an HR recruiter with no engineering background. Use plain language and NO "
        "technical jargon: who these people are, what they have built, and why they fit "
        "the role"
    ),
}

SYSTEM = (
    "You caption a candidate-recommendation video scene by scene. You are given frames "
    "sampled from the video and the narration of every scene, in order. Ground every "
    "caption in what that scene actually says — never invent people, names or numbers."
)


def caption_scenes(video_path: str, scenes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Timed captions covering the whole video, for every audience.

    Returns {audience: [{start, end, text}, ...]} — one entry per scene. Falls back
    to the scene's own narration if the model is unavailable, so the UI always has a
    complete, in-sync track.
    """
    if not scenes:
        return {k: [] for k in STYLES}

    frames = captioning.extract_frames(Path(video_path), n=3) if video_path else []
    target = _vision_target()

    out: dict[str, list[dict[str, Any]]] = {}
    for audience in STYLES:
        try:
            texts = _gemma_captions(frames, scenes, audience, target)
        except Exception as exc:
            print(f"[video_caption] {audience} captions fell back to narration ({str(exc)[:90]})")
            texts = [_fallback(s) for s in scenes]
        out[audience] = [
            {"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": t}
            for s, t in zip(scenes, texts)
        ]
    return out


def _gemma_captions(frames, scenes, audience: str, target) -> list[str]:
    if not target:
        raise RuntimeError("no vision provider configured")
    provider, model = target

    listing = "\n".join(
        f"{i + 1}. [{s.get('title', '')}] {(s.get('narration') or '')[:300]}"
        for i, s in enumerate(scenes)
    )
    prompt = (
        f"This video has {len(scenes)} scenes, in order:\n\n{listing}\n\n"
        f"Write ONE caption for EACH scene, in the same order, for {STYLES[audience]}. "
        f"Each caption is 1-2 sentences describing that scene. "
        f'Return JSON: {{"captions": [ ... exactly {len(scenes)} strings ... ]}}'
    )
    res = engine.complete_json(
        prompt, system=SYSTEM, images=frames or None,
        provider=provider, model=model, name=f"video_caption:{audience}",
        max_tokens=2400,
    )
    texts = [str(t).strip() for t in (res.get("captions") or []) if str(t).strip()]
    if not texts:
        raise RuntimeError("model returned no captions")
    # Align strictly to the scene count: pad short replies from the narration.
    if len(texts) < len(scenes):
        texts += [_fallback(s) for s in scenes[len(texts):]]
    return texts[:len(scenes)]


def _fallback(scene: dict[str, Any]) -> str:
    """A caption built from the scene's own narration — always accurate, never empty."""
    text = " ".join((scene.get("narration") or scene.get("title") or "").split())
    if len(text) <= 220:
        return text or scene.get("title", "")
    cut = text[:220]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[: end + 1] if end > 80 else cut.rstrip(",;: ") + "…")


def _ts(seconds: float) -> str:
    s = max(0.0, float(seconds))
    ms = int((s - int(s)) * 1000)
    i = int(s)
    return f"{i // 3600:02d}:{(i % 3600) // 60:02d}:{i % 60:02d}.{ms:03d}"


def to_vtt(cues: list[dict[str, Any]]) -> str:
    """WebVTT so the captions are the video's real subtitle track (fullscreen too)."""
    blocks = ["WEBVTT", ""]
    for i, c in enumerate(cues, 1):
        text = re.sub(r"\s+", " ", str(c.get("text", ""))).strip()
        if not text:
            continue
        blocks.append(str(i))
        blocks.append(f"{_ts(c.get('start', 0))} --> {_ts(c.get('end', 0))}")
        blocks.append(text)
        blocks.append("")
    return "\n".join(blocks)
