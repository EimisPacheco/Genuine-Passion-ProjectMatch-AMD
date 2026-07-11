"""Provider-agnostic LLM entrypoint used by every agent.

Drop-in replacement for the old `llm.claude` module: same `complete_text` /
`complete_json` signatures, but routes to the configured provider (Gemma on the
AMD MI300X by default) and records speed metrics (tokens/sec) into the Langfuse
trace.
"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.app.config import settings
from backend.app.llm.observability import log_generation
from backend.app.llm.providers import get_provider

DEFAULT_SYSTEM = "You are a precise technical analyst. Be concise and factual."


def _parse_json(raw: str) -> Any:
    """Robust JSON extraction: strip code fences, else grab the outermost object."""
    raw = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise


def complete_text(
    prompt: str,
    *,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 2048,
    trace_handle: dict | None = None,
    name: str = "completion",
    provider: str | None = None,
    images: list[str] | None = None,
) -> str:
    if not settings.llm_enabled:
        raise RuntimeError("No LLM provider configured (set AMD_LLM_BASE_URL for LLM_PROVIDER=amd).")
    prov = get_provider(provider or settings.active_provider)
    result = prov.complete(
        prompt,
        system=system or DEFAULT_SYSTEM,
        model=model,
        max_tokens=max_tokens,
        images=images,
    )
    log_generation(
        trace_handle,
        name=name,
        model=result.model,
        prompt=prompt,
        completion=result.text,
        usage={
            "input": result.input_tokens,
            "output": result.output_tokens,
            "tokens_per_sec": round(result.tokens_per_sec, 1),
        },
    )
    return result.text


def complete_json(
    prompt: str,
    *,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 2048,
    trace_handle: dict | None = None,
    name: str = "completion_json",
    provider: str | None = None,
    images: list[str] | None = None,
) -> Any:
    sys = (system + "\n\n" if system else "") + (
        "Respond with ONLY valid minified JSON. No markdown, no prose, no code fences."
    )
    raw = complete_text(
        prompt,
        system=sys,
        model=model,
        max_tokens=max_tokens,
        trace_handle=trace_handle,
        name=name,
        provider=provider,
        images=images,
    )
    return _parse_json(raw)
