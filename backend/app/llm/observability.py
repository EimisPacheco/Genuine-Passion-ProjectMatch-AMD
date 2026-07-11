"""Langfuse observability wrapper (spec Agent 11).

Provides a thin, dependency-optional tracing layer. When Langfuse keys are
absent (or the SDK isn't installed) every function becomes a safe no-op so the
pipeline still runs. Trace ids are returned so the UI can deep-link.
"""
from __future__ import annotations

import contextlib
from typing import Any, Iterator

from backend.app.config import settings

_lf = None


def _client():
    global _lf
    if _lf is not None:
        return _lf
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse import Langfuse

        _lf = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[langfuse] disabled ({exc})")
        _lf = None
    return _lf


@contextlib.contextmanager
def trace(name: str, metadata: dict[str, Any] | None = None) -> Iterator[dict]:
    """Context manager yielding a handle dict with `trace_id`.

    Usage:
        with trace("agent:ranking") as t:
            ... ; t["trace_id"]
    """
    client = _client()
    handle: dict[str, Any] = {"trace_id": "", "_span": None}
    if client is None:
        yield handle
        return
    try:
        span = client.trace(name=name, metadata=metadata or {})
        handle["trace_id"] = getattr(span, "id", "") or ""
        handle["_span"] = span
    except Exception:
        yield handle
        return
    try:
        yield handle
    finally:
        with contextlib.suppress(Exception):
            client.flush()


def log_generation(
    handle: dict | None,
    *,
    name: str,
    model: str,
    prompt: str,
    completion: str,
    usage: dict | None = None,
) -> None:
    """Attach an LLM generation to an active trace (no-op if disabled)."""
    if not handle or handle.get("_span") is None:
        return
    with contextlib.suppress(Exception):
        handle["_span"].generation(
            name=name,
            model=model,
            input=prompt,
            output=completion,
            usage=usage or {},
        )
