"""Provider-agnostic result type and message builder.

Every provider returns an `LLMResult` carrying both the text and the speed
metrics the hackathon cares about (tokens/sec, time-to-first-token, wall-clock).
Those metrics power the live Gemma-on-AMD vs GPU race and the per-agent trace view.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    ttft_ms: float = 0.0       # time to first token (streaming) or full latency
    total_ms: float = 0.0      # wall-clock for the whole call
    tokens_per_sec: float = 0.0


def build_messages(
    prompt: str, system: str = "", images: list[str] | None = None
) -> list[dict[str, Any]]:
    """OpenAI-style chat messages. `images` may be https URLs or data: URIs."""
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if images:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for url in images:
            content.append({"type": "image_url", "image_url": {"url": url}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})
    return messages
