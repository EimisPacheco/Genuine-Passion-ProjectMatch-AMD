"""Provider registry. `get_provider(name)` returns a cached provider instance.

Providers:
  amd    — Gemma on the AMD MI300X (primary; Ollama, OpenAI-compatible)
  gemini    — same Gemma 4 31B served by Google (race baseline)
"""
from __future__ import annotations

from backend.app.config import settings
from backend.app.llm.providers.base import LLMResult
from backend.app.llm.providers.openai_compat import OpenAICompatProvider

_cache: dict[str, object] = {}


def get_provider(name: str | None = None):
    name = (name or settings.active_provider or "").lower()
    if name in _cache:
        return _cache[name]

    if name == "amd":
        prov = OpenAICompatProvider(
            name="amd",
            api_key=settings.amd_llm_api_key or "EMPTY",
            base_url=settings.amd_llm_base_url,
            default_model=settings.amd_llm_model,
        )
    elif name == "gemini":
        prov = OpenAICompatProvider(
            name="gemini",
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
            default_model=settings.gemini_model,
        )
    else:
        raise RuntimeError(f"Unknown or unconfigured LLM provider: {name!r}")

    _cache[name] = prov
    return prov


__all__ = ["get_provider", "LLMResult"]
