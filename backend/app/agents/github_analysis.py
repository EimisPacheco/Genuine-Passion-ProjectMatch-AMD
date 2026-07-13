"""Agent 3 — GitHub Analysis.

Deep-analyzes each GitHub evidence item into a repository profile: quality score,
architecture profile, feature profile, and maturity. Claude judges quality and
architecture from the README/description signals; a heuristic fallback derives
scores from evidence confidence and keyword signals.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from backend.app import store
from backend.app.agents.base import agent_step, new_id
from backend.app.config import settings
from backend.app.graph.state import ProjectMatchState
from backend.app.llm import engine

MATURITY_SIGNALS = ["test", "pytest", "ci", "architecture", "readme", "diagram", "docs"]


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    evidence = state["evidence"]
    out: dict[str, list[dict[str, Any]]] = {}

    with agent_step("github_analysis", analysis_id) as h:
        n = 0
        for cid, items in evidence.items():
            repos = [e for e in items if e.get("source") == "github"]
            # One Gemma call per repo; they're independent, so run them concurrently
            # instead of one-at-a-time (a prolific candidate can have dozens of repos,
            # and this loop dominates the run's wall-clock). All repos are analyzed.
            if len(repos) > 1 and settings.github_concurrency > 1:
                with ThreadPoolExecutor(max_workers=settings.github_concurrency) as pool:
                    profiles = list(pool.map(lambda e: _analyze(cid, e, h["trace_handle"]), repos))
            else:
                profiles = [_analyze(cid, e, h["trace_handle"]) for e in repos]
            out[cid] = profiles
            n += len(profiles)
            store.save_many(
                "github_projects",
                [
                    {
                        "id": p["id"],
                        "candidate_id": cid,
                        "repo_full_name": p["repo_full_name"],
                        "url": p["url"],
                        "description": p["description"],
                        "languages": p["languages"],
                        "dependencies": p.get("dependencies", []),
                        "stars": int(p.get("stars", 0)),
                        "forks": int(p.get("forks", 0)),
                        "quality_score": float(p["quality_score"]),
                        "architecture_profile": p["architecture_profile"],
                        "feature_profile": p["feature_profile"],
                        "maturity": p["maturity"],
                        "last_activity": p.get("last_activity", ""),
                    }
                    for p in profiles
                ],
            )
        h["summary"] = f"analyzed {n} repositories"
    return {"github_analyses": out}


def _analyze(cid: str, ev: dict[str, Any], trace_handle) -> dict[str, Any]:
    base = {
        "id": new_id("gh_"),
        "evidence_id": ev.get("id"),
        "repo_full_name": ev.get("title", "").split(" — ")[0],
        "url": ev.get("url", ""),
        "description": ev.get("description", ""),
        "languages": ev.get("technologies", []),
        "stars": ev.get("_stars", 0),
        "forks": ev.get("_forks", 0),
        "last_activity": ev.get("evidence_date", ""),
        "feature_profile": ev.get("feature_tags", []),
    }
    if settings.llm_enabled:
        try:
            llm = engine.complete_json(
                f"""Assess this GitHub repository for engineering quality and architecture.
Return JSON: quality_score (0-1 float), maturity (prototype|developing|mature),
architecture_profile (one sentence), feature_profile (array of strings).

Repo: {ev.get('title')}
Description: {ev.get('description')}
Technologies: {ev.get('technologies')}""",
                trace_handle=trace_handle,
                name="github_analysis",
            )
            base["quality_score"] = float(llm.get("quality_score", _heuristic_quality(ev)))
            base["maturity"] = llm.get("maturity", "developing")
            base["architecture_profile"] = llm.get("architecture_profile", "")
            base["feature_profile"] = llm.get("feature_profile") or base["feature_profile"]
            return base
        except Exception:
            pass
    base["quality_score"] = _heuristic_quality(ev)
    base["maturity"] = "mature" if base["quality_score"] > 0.75 else "developing"
    base["architecture_profile"] = ev.get("description", "")[:160]
    return base


def _heuristic_quality(ev: dict[str, Any]) -> float:
    desc = (ev.get("description") or "").lower()
    signals = sum(1 for s in MATURITY_SIGNALS if s in desc)
    stars = ev.get("_stars", 0)
    score = 0.5 * float(ev.get("confidence", 0.6))
    score += min(signals * 0.08, 0.32)
    score += min(stars / 1000.0, 0.18)
    return round(min(score, 1.0), 3)
