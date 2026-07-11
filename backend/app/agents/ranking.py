"""Agent 7 — Candidate Ranking.

Combines similarity, passion, alignment, innovation, and evidence quality into an
overall ProjectMatch score using the spec weights, then ranks and selects Top N.

    40% Project Similarity
    25% Genuine Passion
    15% Domain Alignment
    10% Technology Alignment
     5% Innovation
     5% Evidence Quality

INVARIANT: every persisted score carries a non-empty `evidence_ids` list whose
ids all exist in candidate_evidence (enforced by the QA tests).
"""
from __future__ import annotations

from typing import Any

from backend.app import store
from backend.app.agents.base import agent_step, new_id
from backend.app.graph.state import ProjectMatchState

WEIGHTS = {
    "project_similarity": 0.40,
    "genuine_passion": 0.25,
    "domain_similarity": 0.15,
    "technology_similarity": 0.10,
    "innovation": 0.05,
    "evidence_quality": 0.05,
}


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    top_n = state.get("top_n", 3)
    evidence = state["evidence"]
    passion = state["passion_scores"]
    similarity = state["similarity_scores"]

    github = state.get("github_analyses", {})
    visual = state.get("visual_analyses", {})
    hackathon = state.get("hackathon_analyses", {})

    rows: list[dict[str, Any]] = []
    with agent_step("ranking", analysis_id, f"top_n={top_n}") as h:
        for cid, items in evidence.items():
            p = passion.get(cid, {})
            s = similarity.get(cid, {})
            evidence_quality = _evidence_quality(items, visual.get(cid, []))
            code_score = _code_score(github.get(cid, []), p)
            design_score = _design_score(visual.get(cid, []), hackathon.get(cid, []), p)

            components = {
                "project_similarity": s.get("project_similarity", 0.0),
                "genuine_passion": p.get("genuine_passion", 0.0),
                "domain_similarity": s.get("domain_similarity", 0.0),
                "technology_similarity": s.get("technology_similarity", 0.0),
                "innovation": p.get("innovation", 0.0),
                "evidence_quality": evidence_quality,
            }
            overall = sum(WEIGHTS[k] * components[k] for k in WEIGHTS)
            confidence = _confidence(items, evidence_quality)
            evidence_ids = _evidence_ids(items, p, s)

            rows.append(
                {
                    "candidate_id": cid,
                    "overall_score": round(overall, 3),
                    "confidence": round(confidence, 3),
                    "code_score": round(code_score, 3),
                    "design_score": round(design_score, 3),
                    "evidence_quality": round(evidence_quality, 3),
                    "evidence_ids": evidence_ids,
                    **{k: round(v, 3) for k, v in components.items()},
                    "feature_similarity": s.get("feature_similarity", 0.0),
                    "mission_similarity": s.get("mission_similarity", 0.0),
                    "domain_passion": p.get("domain_passion", 0.0),
                    "technology_passion": p.get("technology_passion", 0.0),
                    "builder_consistency": p.get("builder_consistency", 0.0),
                    "voluntary_effort": p.get("voluntary_effort", 0.0),
                    "passion_explanation": p.get("explanation", ""),
                }
            )

        rows.sort(key=lambda r: r["overall_score"], reverse=True)
        for i, r in enumerate(rows, start=1):
            r["rank"] = i
            r["recommendation"] = _recommendation(r["overall_score"])

        _persist(analysis_id, rows)
        ranked = rows[:top_n]
        h["summary"] = " > ".join(f"{r['candidate_id']}({r['overall_score']:.2f})" for r in ranked)

    return {"ranking": rows, "top_n": top_n}


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def _code_score(gh_analyses: list[dict[str, Any]], passion: dict[str, Any]) -> float:
    """Engineering quality from GitHub repo analyses; fallback to passion signals."""
    qs = [float(g.get("quality_score")) for g in gh_analyses if g.get("quality_score") is not None]
    if qs:
        return _clip(sum(qs) / len(qs))
    return _clip(0.6 * passion.get("technology_passion", 0.0) + 0.4 * passion.get("builder_consistency", 0.0))


def _design_score(
    visual: list[dict[str, Any]], hackathon: list[dict[str, Any]], passion: dict[str, Any]
) -> float:
    """Design/polish from the Visual Portfolio agent + hackathon execution quality."""
    vals = [float(v.get("polish")) for v in visual if v.get("polish") is not None]
    vals += [float(h.get("execution_quality")) for h in hackathon if h.get("execution_quality") is not None]
    if vals:
        return _clip(sum(vals) / len(vals))
    return _clip(0.5 * passion.get("innovation", 0.0) + 0.5 * passion.get("voluntary_effort", 0.0))


def _evidence_quality(items: list[dict[str, Any]], visual: list[dict[str, Any]] | None = None) -> float:
    if not items:
        return 0.0
    avg_conf = sum(float(e.get("confidence", 0.6)) for e in items) / len(items)
    breadth = len({e.get("source") for e in items}) / 6.0  # multi-source discovery pays off
    base = 0.7 * avg_conf + 0.3 * min(breadth, 1.0)
    # Blend a small signal from Gemma-analyzed portfolio images (architecture
    # diagrams / app screenshots) so real visual evidence counts toward the match.
    pol = [float(v.get("polish")) for v in (visual or []) if v.get("polish") is not None]
    vq = sum(pol) / len(pol) if pol else 0.0
    return max(0.0, min(1.0, base * 0.9 + vq * 0.1))


def _confidence(items, evidence_quality) -> float:
    return max(0.0, min(1.0, 0.5 * evidence_quality + 0.5 * min(len(items) / 5.0, 1.0)))


def _evidence_ids(items, passion, similarity) -> list[str]:
    ids = list(dict.fromkeys(
        (similarity.get("top_evidence_ids", []) or [])
        + (passion.get("evidence_ids", []) or [])
        + [e["id"] for e in items]
    ))
    return ids


def _recommendation(score: float) -> str:
    # Calibrated to the realistic overall-score distribution: project_similarity
    # (embedding cosine of concise evidence text + tag overlap) compresses even
    # excellent matches to ~0.30-0.35, so a domain specialist reads as "Strong".
    if score >= 0.30:
        return "Strong match — prioritize outreach"
    if score >= 0.25:
        return "Promising match — worth a conversation"
    if score >= 0.15:
        return "Adjacent — consider for related roles"
    return "Weak match"


def _persist(analysis_id: str, rows: list[dict[str, Any]]) -> None:
    store.save_many(
        "candidate_scores",
        [
            {
                "id": new_id("score_"),
                "analysis_id": analysis_id,
                "candidate_id": r["candidate_id"],
                "overall_score": float(r["overall_score"]),
                "project_similarity": float(r["project_similarity"]),
                "feature_similarity": float(r["feature_similarity"]),
                "domain_similarity": float(r["domain_similarity"]),
                "technology_similarity": float(r["technology_similarity"]),
                "mission_similarity": float(r["mission_similarity"]),
                "genuine_passion": float(r["genuine_passion"]),
                "domain_passion": float(r["domain_passion"]),
                "technology_passion": float(r["technology_passion"]),
                "builder_consistency": float(r["builder_consistency"]),
                "innovation": float(r["innovation"]),
                "voluntary_effort": float(r["voluntary_effort"]),
                "evidence_quality": float(r["evidence_quality"]),
                "confidence": float(r["confidence"]),
                "rank": int(r["rank"]),
                "recommendation": r["recommendation"],
                "explanation": r.get("passion_explanation", ""),
                "evidence_ids": r["evidence_ids"],
            }
            for r in rows
        ],
    )
