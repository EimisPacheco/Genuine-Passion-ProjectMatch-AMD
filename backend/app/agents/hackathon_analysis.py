"""Agent 4 — Hackathon Analysis.

Analyzes Devpost / lablab.ai (and similar) evidence into structured project
profiles: problem solved, features, technologies, innovation, execution quality,
domain. Persists to `hackathon_projects`.
"""
from __future__ import annotations

from typing import Any

from backend.app import store
from backend.app.agents.base import agent_step, new_id
from backend.app.config import settings
from backend.app.graph.state import ProjectMatchState
from backend.app.llm import engine

HACKATHON_SOURCES = {"devpost", "lablab"}


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    evidence = state["evidence"]
    out: dict[str, list[dict[str, Any]]] = {}

    with agent_step("hackathon_analysis", analysis_id) as h:
        n = 0
        for cid, items in evidence.items():
            projects = [
                _analyze(cid, e, h["trace_handle"])
                for e in items
                if e.get("source") in HACKATHON_SOURCES
            ]
            out[cid] = projects
            n += len(projects)
            store.save_many(
                "hackathon_projects",
                [
                    {
                        "id": p["id"],
                        "candidate_id": cid,
                        "platform": p["platform"],
                        "title": p["title"],
                        "url": p["url"],
                        "problem_solved": p["problem_solved"],
                        "features": p["features"],
                        "technologies": p["technologies"],
                        "innovation": p["innovation"],
                        "execution_quality": float(p["execution_quality"]),
                        "domain_tags": p["domain_tags"],
                        "awards": p.get("awards", []),
                    }
                    for p in projects
                ],
            )
        h["summary"] = f"analyzed {n} hackathon projects"
    return {"hackathon_analyses": out}


def _analyze(cid: str, ev: dict[str, Any], trace_handle) -> dict[str, Any]:
    base = {
        "id": new_id("hk_"),
        "evidence_id": ev.get("id"),
        "platform": ev.get("source", ""),
        "title": ev.get("title", ""),
        "url": ev.get("url", ""),
        "technologies": ev.get("technologies", []),
        "domain_tags": ev.get("domain_tags", []),
        "features": ev.get("feature_tags", []),
        "awards": ["award" for kw in ["win", "winner", "medal"] if kw in (ev.get("description") or "").lower()][:1],
    }
    if settings.llm_enabled:
        try:
            llm = engine.complete_json(
                f"""Analyze this hackathon project. Return JSON:
problem_solved (str), features (array), innovation (one sentence),
execution_quality (0-1 float).

Title: {ev.get('title')}
Description: {ev.get('description')}
Technologies: {ev.get('technologies')}""",
                trace_handle=trace_handle,
                name="hackathon_analysis",
            )
            base["problem_solved"] = llm.get("problem_solved", ev.get("description", "")[:160])
            base["features"] = llm.get("features") or base["features"]
            base["innovation"] = llm.get("innovation", "")
            base["execution_quality"] = float(llm.get("execution_quality", ev.get("confidence", 0.6)))
            return base
        except Exception:
            pass
    base["problem_solved"] = ev.get("description", "")[:160]
    base["innovation"] = (ev.get("description") or "")[:120]
    base["execution_quality"] = float(ev.get("confidence", 0.6))
    return base
