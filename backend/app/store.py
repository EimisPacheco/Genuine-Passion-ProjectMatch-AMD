"""Best-effort persistence facade over the configured database backend.

Backend is chosen by `settings.db_backend`: **Google Cloud SQL for PostgreSQL +
pgvector** when `DATABASE_URL` is set, otherwise in-memory only. The pipeline keeps
the full working set in `ProjectMatchState`, so storage is a best-effort
side-effect used by the API/UI and by vector search. `available()` reports
connectivity so callers can choose DB vector search vs. an in-process cosine fallback.
"""
from __future__ import annotations

import contextlib
from typing import Any

from backend.app.config import settings

_available: bool | None = None


def _backend():
    if settings.db_backend == "postgres":
        from database import postgres_client as m
        return m
    return None  # in-memory only


def available() -> bool:
    global _available
    if _available is not None:
        return _available
    m = _backend()
    if m is None:
        _available = False
        return _available
    try:
        _available = bool(m.available())
    except Exception as exc:
        print(f"[store] {settings.db_backend} unavailable, running in-memory only ({exc})")
        _available = False
    return _available


def run_migrations() -> None:
    with contextlib.suppress(Exception):
        _backend().run_migrations()


def save(table: str, row: dict[str, Any]) -> None:
    if not available():
        return
    with contextlib.suppress(Exception):
        _backend().insert_row(table, row)


def save_many(table: str, rows: list[dict[str, Any]]) -> None:
    if not available() or not rows:
        return
    with contextlib.suppress(Exception):
        _backend().insert_rows(table, rows)


def vector_search(
    query_embedding: list[float],
    candidate_id: str | None = None,
    owner_type: str = "candidate_project",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Nearest embeddings via the backend's vector search (pgvector / cosineDistance)."""
    if not available():
        return []
    try:
        return _backend().vector_search(
            query_embedding, owner_type=owner_type, candidate_id=candidate_id, limit=limit
        )
    except Exception:
        return []


def agent_runs(analysis_id: str) -> list[dict[str, Any]]:
    if not available():
        return []
    try:
        return _backend().agent_runs(analysis_id)
    except Exception:
        return []


def fetch(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Raw query passthrough (best-effort; returns [] if the backend has no query())."""
    if not available():
        return []
    try:
        return _backend().query(sql, params)
    except Exception:
        return []


def reset_availability() -> None:
    """For tests: force re-probe."""
    global _available
    _available = None
