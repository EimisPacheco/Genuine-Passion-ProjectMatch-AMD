"""Agent 1 — Project Understanding.

Extracts a structured profile of the company project (mission, goals, domain &
feature tags, technologies, complexity, innovation indicators), embeds it, and
persists to `company_projects` + `project_embeddings`. Claude does the
extraction; a heuristic fallback keeps it running without an API key.
"""
from __future__ import annotations

from typing import Any

from backend.app import store
from backend.app.agents.base import agent_step, new_id
from backend.app.agents.common import (
    DOMAIN_VOCAB,
    TECH_VOCAB,
    heuristic_tags,
    project_text,
)
from backend.app.config import settings
from backend.app.graph.state import ProjectMatchState
from backend.app.llm import embeddings, engine

SYSTEM = (
    "You analyze a company's target software project and extract a structured "
    "profile for matching it against candidate work."
)


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    project = dict(state["company_project"])
    with agent_step("project_understanding", analysis_id, project.get("title", "")) as h:
        profile = _extract(project, h["trace_handle"])
        profile["id"] = project.get("id") or new_id("proj_")

        # In LIVE mode, merge heuristic tags from the SHARED vocab so the project
        # and live evidence (tagged from the same vocab in discovery) actually
        # overlap — this drives domain/technology similarity + passion instead of
        # volume. Seeded demos keep their curated tags untouched (deterministic).
        if state.get("live_mode"):
            _ptext = project_text(profile)
            profile["domain_tags"] = sorted(
                set(profile.get("domain_tags", [])) | set(heuristic_tags(_ptext, DOMAIN_VOCAB))
            )
            profile["technologies"] = sorted(
                set(profile.get("technologies", [])) | set(heuristic_tags(_ptext, TECH_VOCAB))
            )

        text = project_text(profile)
        vec = embeddings.embed(text)

        store.save(
            "company_projects",
            {
                "id": profile["id"],
                "title": profile.get("title", ""),
                "description": profile.get("description", ""),
                "business_problem": profile.get("business_problem", ""),
                "target_users": profile.get("target_users", ""),
                "mission": profile.get("mission", ""),
                "goals": profile.get("goals", []),
                "domain_tags": profile.get("domain_tags", []),
                "feature_tags": profile.get("feature_tags", []),
                "technologies": profile.get("technologies", []),
                "complexity": profile.get("complexity", ""),
                "innovation_indicators": profile.get("innovation_indicators", []),
                "success_criteria": profile.get("success_criteria", ""),
                "desired_candidates": int(profile.get("desired_candidates", state.get("top_n", 3))),
            },
        )
        store.save(
            "project_embeddings",
            {
                "id": new_id("emb_"),
                "owner_type": "company_project",
                "owner_id": profile["id"],
                "candidate_id": "",
                "text": text[:2000],
                "embedding": vec,
            },
        )
        profile["_embedding"] = vec
        h["summary"] = f"domain={profile.get('domain_tags')} tech={profile.get('technologies')[:5]}"
        return {"company_project": profile}


def _extract(project: dict[str, Any], trace_handle) -> dict[str, Any]:
    if not settings.llm_enabled:
        return _heuristic(project)
    prompt = f"""Analyze this company project and return JSON with keys:
mission (str), goals (string array), domain_tags (lowercase-hyphenated array),
feature_tags (array), technologies (array), complexity (one of low|medium|high),
innovation_indicators (array).

Project title: {project.get('title')}
Description: {project.get('description')}
Business problem: {project.get('business_problem')}
Target users: {project.get('target_users')}
Expected features: {project.get('expected_features')}
Expected technologies: {project.get('expected_technologies')}
Success criteria: {project.get('success_criteria')}"""
    try:
        extracted = engine.complete_json(
            prompt, system=SYSTEM, trace_handle=trace_handle, name="project_understanding"
        )
    except Exception:
        return _heuristic(project)
    merged = dict(project)
    merged.update({k: v for k, v in extracted.items() if v})
    merged.setdefault("technologies", project.get("expected_technologies", []))
    merged.setdefault("feature_tags", project.get("expected_features", []))
    return merged


def _heuristic(project: dict[str, Any]) -> dict[str, Any]:
    text = project_text(project)
    merged = dict(project)
    merged["mission"] = project.get("mission") or project.get("business_problem", "")
    merged["goals"] = project.get("goals") or [project.get("success_criteria", "")]
    merged["domain_tags"] = project.get("domain_tags") or heuristic_tags(text, DOMAIN_VOCAB)
    merged["feature_tags"] = project.get("feature_tags") or project.get("expected_features", [])
    merged["technologies"] = project.get("technologies") or project.get(
        "expected_technologies", []
    ) or heuristic_tags(text, TECH_VOCAB)
    merged["complexity"] = project.get("complexity") or "high"
    merged["innovation_indicators"] = project.get("innovation_indicators") or [
        "autonomous multi-agent orchestration"
    ]
    return merged
