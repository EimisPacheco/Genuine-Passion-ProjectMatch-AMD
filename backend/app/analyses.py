"""In-memory registry of analyses + a runner the API/CLI share.

Keeps the latest pipeline result per analysis_id so API endpoints can serve
ranked candidates, narratives, and the video report without re-running. Results
are also persisted in Cloud SQL; this registry is the fast path for the live UI.
"""
from __future__ import annotations

from typing import Any

from backend.app import store
from backend.app.agents.base import new_id
from backend.app.graph.pipeline import run_pipeline
from integrations.scrapers import demo_loader

_analyses: dict[str, dict[str, Any]] = {}
_projects: dict[str, dict[str, Any]] = {}


def register_project(project: dict[str, Any]) -> str:
    pid = project.get("id") or new_id("proj_")
    project["id"] = pid
    _projects[pid] = project
    return pid


def get_project(pid: str) -> dict[str, Any] | None:
    return _projects.get(pid)


def default_company_project() -> dict[str, Any]:
    return demo_loader.load_company_project()


def default_candidate_sources() -> list[dict[str, Any]]:
    return demo_loader.list_candidates()


def create_analysis(
    company_project: dict[str, Any],
    candidate_sources: list[dict[str, Any]],
    top_n: int,
    live_mode: bool = False,
) -> str:
    analysis_id = new_id("an_")
    _analyses[analysis_id] = {
        "id": analysis_id,
        "status": "running",
        "top_n": top_n,
        "company_project": company_project,
        "live_mode": live_mode,
    }
    return analysis_id


def run(analysis_id: str) -> dict[str, Any]:
    record = _analyses[analysis_id]
    try:
        final = run_pipeline(
            record["company_project"],
            record.get("candidate_sources") or default_candidate_sources(),
            top_n=record["top_n"],
            analysis_id=analysis_id,
            live_mode=record.get("live_mode", False),
        )
        record.update({"status": "done", "result": final})
    except Exception as exc:  # surface failure to the API
        record.update({"status": "error", "error": str(exc)})
        store.save_analysis(analysis_id, record)
        raise
    # Persist the finished analysis so its link still resolves after a restart.
    store.save_analysis(analysis_id, record)
    return record


def set_sources(analysis_id: str, sources: list[dict[str, Any]]) -> None:
    _analyses[analysis_id]["candidate_sources"] = sources


def get(analysis_id: str) -> dict[str, Any] | None:
    """Memory first (live runs), then the database — so a shared analysis link
    still works after the backend restarts or redeploys."""
    record = _analyses.get(analysis_id)
    if record is not None:
        return record
    record = store.load_analysis(analysis_id)
    if record is not None:
        _analyses[analysis_id] = record  # warm the fast path
    return record
