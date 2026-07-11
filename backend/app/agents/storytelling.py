"""Agent 8 — Storytelling.

Generates recruiter-friendly, evidence-grounded explanations for each selected
candidate: why selected, which projects support it, which passion signals fired,
and mission alignment. Every explanation references real evidence ids/URLs.
"""
from __future__ import annotations

from typing import Any

from backend.app.agents.base import agent_step
from backend.app.config import settings
from backend.app.graph.state import ProjectMatchState
from backend.app.llm import engine


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    company = state["company_project"]
    evidence = state["evidence"]
    ranking = state["ranking"]
    top_n = state.get("top_n", 3)
    selected = ranking[:top_n]

    narratives: dict[str, dict[str, Any]] = {}
    with agent_step("storytelling", analysis_id, f"{len(selected)} candidates") as h:
        for r in selected:
            cid = r["candidate_id"]
            items = evidence.get(cid, [])
            ev_by_id = {e["id"]: e for e in items}
            relevant = [ev_by_id[i] for i in r["evidence_ids"] if i in ev_by_id][:4]
            narratives[cid] = {
                "candidate_id": cid,
                "headline": _headline(r),
                "explanation": _explain(company, r, relevant, h["trace_handle"]),
                "supporting_projects": [
                    {"title": e.get("title"), "url": e.get("url"), "id": e["id"]}
                    for e in relevant
                ],
                "passion_signals": r.get("passion_explanation", ""),
            }
        h["summary"] = f"wrote {len(narratives)} narratives"
    return {"narratives": narratives}


def _headline(r: dict[str, Any]) -> str:
    return (
        f"Overall {r['overall_score']:.0%} · similarity {r['project_similarity']:.0%} · "
        f"passion {r['genuine_passion']:.0%} — {r['recommendation']}"
    )


def _explain(company, r, relevant, trace_handle) -> str:
    titles = "\n".join(f"- [{e['id']}] {e.get('title')} ({e.get('url')})" for e in relevant)
    if not settings.llm_enabled or not relevant:
        names = "; ".join(e.get("title", "") for e in relevant) or "their public work"
        return (
            f"Selected because their projects align with '{company.get('title')}'. "
            f"Project similarity {r['project_similarity']:.0%} and genuine passion "
            f"{r['genuine_passion']:.0%}. Most relevant: {names}."
        )
    try:
        return engine.complete_text(
            f"""You are briefing a recruiter. In 3-4 sentences explain why this candidate
matches the company project. Reference specific evidence by [id]. Use ONLY the evidence
listed — never invent projects, repos, or facts.

Company project: {company.get('title')} — {company.get('description')[:300]}
Scores: overall={r['overall_score']:.2f}, project_similarity={r['project_similarity']:.2f},
genuine_passion={r['genuine_passion']:.2f}, domain={r['domain_similarity']:.2f}.
Evidence:
{titles}""",
            trace_handle=trace_handle,
            name="storytelling",
            max_tokens=400,
        ).strip()
    except Exception:
        names = "; ".join(e.get("title", "") for e in relevant)
        return f"Strong match for {company.get('title')}. Key evidence: {names}."
