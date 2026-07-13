"""Best-effort persistence facade over the configured database backend.

Backend is chosen by `settings.db_backend`: **Google Cloud SQL for PostgreSQL +
pgvector** when `DATABASE_URL` is set, otherwise in-memory only. The pipeline keeps
the full working set in `ProjectMatchState`, so storage is a best-effort
side-effect used by the API/UI and by vector search. `available()` reports
connectivity so callers can choose DB vector search vs. an in-process cosine fallback.
"""
from __future__ import annotations

import contextlib
import json
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


def save_analysis(analysis_id: str, record: dict[str, Any]) -> None:
    """Persist a whole analysis so a shared link survives a backend restart."""
    if not available():
        return
    with contextlib.suppress(Exception):
        _backend().save_analysis(
            analysis_id, str(record.get("status", "")), json.dumps(record, default=str),
        )


def load_analysis(analysis_id: str) -> dict[str, Any] | None:
    """The persisted analysis, or None when absent / no DB."""
    if not available():
        return None
    try:
        raw = _backend().load_analysis(analysis_id)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def talent_pool(limit: int = 300) -> list[dict[str, Any]]:
    """Every distinct candidate ever discovered, newest first, with a summary of
    their evidence — the persistent talent graph across all analyses. Deduped by
    id (profiles are written once per analysis, so the same person recurs)."""
    if not available():
        return []
    # Dedup by GitHub handle (the stable identity — the same person can get a
    # different row id across analyses), preferring the row that has a LinkedIn.
    key = "COALESCE(NULLIF(github_handle, ''), id)"
    profiles = fetch(
        f"SELECT DISTINCT ON ({key}) id, name, github_handle, headline, location, city, "
        "state, country, email, linkedin_url, created_at "
        "FROM candidate_profiles WHERE id <> '' "
        f"ORDER BY {key}, (linkedin_url IS NOT NULL AND linkedin_url <> '') DESC, created_at DESC"
    )
    # Aggregate evidence by the SAME handle key, so a person split across ids merges.
    ekey = "COALESCE(NULLIF(p.github_handle, ''), p.id)"
    ev = fetch(
        f"SELECT {ekey} AS k, count(DISTINCT e.url) AS n, "
        "array_remove(array_agg(DISTINCT e.source), NULL) AS sources "
        "FROM candidate_evidence e JOIN candidate_profiles p ON p.id = e.candidate_id "
        f"GROUP BY {ekey}"
    )
    tech = fetch(
        f"SELECT {ekey} AS k, array_agg(DISTINCT t) AS techs "
        "FROM candidate_evidence e JOIN candidate_profiles p ON p.id = e.candidate_id, "
        f"unnest(e.technologies) AS t GROUP BY {ekey}"
    )
    ev_by = {r["k"]: r for r in ev}
    tech_by = {r["k"]: (r.get("techs") or []) for r in tech}
    for p in profiles:
        k = p.get("github_handle") or p["id"]
        e = ev_by.get(k, {})
        p["evidence_count"] = int(e.get("n", 0) or 0)
        p["sources"] = e.get("sources") or []
        p["technologies"] = tech_by.get(k, [])[:24]
        p["contactable"] = bool(p.get("linkedin_url"))
    profiles.sort(key=lambda p: str(p.get("created_at", "")), reverse=True)
    return profiles[:limit]


def known_handles() -> set[str]:
    """Lower-cased GitHub handles already saved in the pool. Free Discovery filters
    these out so it surfaces *new* people instead of re-listing the ones we already have."""
    if not available():
        return set()
    rows = fetch(
        "SELECT DISTINCT lower(github_handle) AS h FROM candidate_profiles "
        "WHERE github_handle IS NOT NULL AND github_handle <> ''"
    )
    return {r["h"] for r in rows if r.get("h")}


def recent_candidate(github_handle: str, days: int = 30) -> dict[str, Any] | None:
    """A previously-investigated candidate whose evidence is still fresh — so a new
    run can reuse it instead of re-scraping. Returns {profile, evidence} or None."""
    if not available() or not github_handle:
        return None
    prof = fetch(
        "SELECT DISTINCT ON (id) id, name, github_handle, headline, location, city, "
        "state, country, email, linkedin_url FROM candidate_profiles "
        "WHERE github_handle = %(h)s ORDER BY id, created_at DESC LIMIT 1",
        {"h": github_handle},
    )
    if not prof:
        return None
    ev = fetch(
        "SELECT id, source, title, url, description, technologies, domain_tags, "
        "feature_tags, evidence_date, confidence FROM candidate_evidence "
        "WHERE candidate_id = %(cid)s AND created_at > now() - make_interval(days => %(d)s) "
        "ORDER BY created_at DESC",
        {"cid": prof[0]["id"], "d": days},
    )
    if not ev:
        return None
    return {"profile": prof[0], "evidence": ev}


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
