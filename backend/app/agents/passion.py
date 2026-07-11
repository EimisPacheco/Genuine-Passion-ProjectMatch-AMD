"""Agent 5 — Passion Detection.

Measures genuine passion from public-artifact patterns. Scores are computed with
a transparent, deterministic heuristic (so they are reproducible and traceable),
and Claude writes a human explanation that must reference the actual evidence.

Sub-scores (0-1): genuine_passion, domain_passion, technology_passion,
builder_consistency, innovation, voluntary_effort.
"""
from __future__ import annotations

from typing import Any

from backend.app.agents.base import agent_step
from backend.app.agents.common import jaccard
from backend.app.config import settings
from backend.app.graph.state import ProjectMatchState
from backend.app.llm import engine

VOLUNTARY_SOURCES = {"github", "devpost", "lablab", "portfolio", "kaggle", "blog", "youtube"}


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    company = state["company_project"]
    evidence = state["evidence"]
    company_domains = company.get("domain_tags", [])
    company_techs = company.get("technologies", [])

    scores: dict[str, dict[str, Any]] = {}
    with agent_step("passion_detection", analysis_id) as h:
        for cid, items in evidence.items():
            scores[cid] = _score_candidate(
                cid, items, company_domains, company_techs, h["trace_handle"]
            )
        h["summary"] = ", ".join(
            f"{cid}:{s['genuine_passion']:.2f}" for cid, s in scores.items()
        )
    return {"passion_scores": scores}


def _score_candidate(cid, items, company_domains, company_techs, trace_handle):
    if not items:
        return _empty()

    # domain passion: confidence-weighted share of evidence overlapping company domains
    dom_hits = [
        float(e.get("confidence", 0.6))
        for e in items
        if set(map(str.lower, e.get("domain_tags", []))) & set(map(str.lower, company_domains))
    ]
    domain_passion = _clip(sum(dom_hits) / max(len(items), 1) + 0.1 * (len(dom_hits) >= 3))

    # technology passion: jaccard of candidate techs vs company techs
    cand_techs = sorted({t for e in items for t in e.get("technologies", [])})
    technology_passion = _clip(jaccard(cand_techs, company_techs) * 1.5)

    # builder consistency: count + temporal spread of dated evidence
    dates = sorted(e.get("evidence_date", "") for e in items if e.get("evidence_date"))
    span_months = _month_span(dates)
    builder_consistency = _clip(min(len(items) / 6.0, 1.0) * 0.6 + min(span_months / 12.0, 1.0) * 0.4)

    # voluntary effort: number of self-initiated artifacts
    voluntary = sum(1 for e in items if e.get("source") in VOLUNTARY_SOURCES)
    voluntary_effort = _clip(min(voluntary / 5.0, 1.0))

    # innovation: awards / winner / novel signals
    innovation = _clip(
        sum(
            0.25
            for e in items
            if any(k in (e.get("description") or "").lower() for k in ["win", "winner", "medal", "novel", "first"])
        )
        + 0.4 * (domain_passion > 0.5)
    )

    genuine_passion = _clip(
        0.40 * domain_passion
        + 0.20 * builder_consistency
        + 0.20 * voluntary_effort
        + 0.10 * technology_passion
        + 0.10 * innovation
    )

    explanation = _explain(
        cid, items, genuine_passion, domain_passion, builder_consistency, trace_handle
    )

    return {
        "genuine_passion": round(genuine_passion, 3),
        "domain_passion": round(domain_passion, 3),
        "technology_passion": round(technology_passion, 3),
        "builder_consistency": round(builder_consistency, 3),
        "innovation": round(innovation, 3),
        "voluntary_effort": round(voluntary_effort, 3),
        "evidence_ids": [e["id"] for e in items],
        "explanation": explanation,
    }


def _explain(cid, items, genuine, domain, consistency, trace_handle) -> str:
    if not settings.llm_enabled:
        top = sorted(items, key=lambda e: e.get("confidence", 0), reverse=True)[:2]
        titles = "; ".join(e.get("title", "") for e in top)
        return (
            f"Genuine passion {genuine:.0%} driven by domain alignment ({domain:.0%}) "
            f"and consistent building ({consistency:.0%}). Key evidence: {titles}."
        )
    titles = "\n".join(f"- [{e['id']}] {e.get('title')} ({e.get('url')})" for e in items)
    try:
        return engine.complete_text(
            f"""Write 2-3 sentences explaining this candidate's genuine passion based ONLY
on the evidence below. Reference specific evidence by its [id]. Do not invent anything.
Scores: genuine={genuine:.2f}, domain_alignment={domain:.2f}, consistency={consistency:.2f}.
Evidence:
{titles}""",
            trace_handle=trace_handle,
            name="passion_explanation",
            max_tokens=300,
        ).strip()
    except Exception:
        return f"Genuine passion {genuine:.0%} based on {len(items)} public artifacts."


def _empty() -> dict[str, Any]:
    return {
        "genuine_passion": 0.0,
        "domain_passion": 0.0,
        "technology_passion": 0.0,
        "builder_consistency": 0.0,
        "innovation": 0.0,
        "voluntary_effort": 0.0,
        "evidence_ids": [],
        "explanation": "No public evidence discovered.",
    }


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def _month_span(dates: list[str]) -> int:
    dates = [d for d in dates if len(d) >= 7]
    if len(dates) < 2:
        return 0
    def ym(d: str) -> int:
        y, m = int(d[:4]), int(d[5:7])
        return y * 12 + m
    return ym(dates[-1]) - ym(dates[0])
