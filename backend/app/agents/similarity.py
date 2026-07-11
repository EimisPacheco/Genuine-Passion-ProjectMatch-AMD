"""Agent 6 — Similarity.

Compares the company project to each candidate's projects using both structured
tag overlap and embedding similarity. Embedding similarity uses the Cloud SQL
pgvector search; if the DB is unavailable it falls back
to in-process cosine over locally computed embeddings.

Outputs per candidate: project/feature/domain/technology/mission similarity plus
the most-relevant evidence ids.
"""
from __future__ import annotations

from typing import Any

from backend.app import store
from backend.app.agents.base import agent_step
from backend.app.agents.common import evidence_text, jaccard, project_text
from backend.app.graph.state import ProjectMatchState
from backend.app.llm import embeddings


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    company = state["company_project"]
    evidence = state["evidence"]

    company_vec = company.get("_embedding") or embeddings.embed(project_text(company))
    company_domains = company.get("domain_tags", [])
    company_techs = company.get("technologies", [])
    company_features = company.get("feature_tags", []) or company.get("expected_features", [])

    used_vector_db = store.available()
    results: dict[str, dict[str, Any]] = {}

    with agent_step("similarity", analysis_id,
                    f"vector_db={'pgvector' if used_vector_db else 'in-process'}") as h:
        for cid, items in evidence.items():
            results[cid] = _compare(
                cid, items, company_vec, company_domains, company_techs,
                company_features, used_vector_db,
            )
        h["summary"] = ", ".join(
            f"{cid}:{r['project_similarity']:.2f}" for cid, r in results.items()
        )
    return {"similarity_scores": results}


def _compare(cid, items, company_vec, c_domains, c_techs, c_features, use_db):
    if not items:
        return _empty()

    # --- embedding similarity (Cloud SQL pgvector or in-process) ---
    emb_sim, top_ids = _embedding_similarity(cid, items, company_vec, use_db)

    # --- structured tag overlap ---
    cand_domains = sorted({d for e in items for d in e.get("domain_tags", [])})
    cand_techs = sorted({t for e in items for t in e.get("technologies", [])})
    cand_features = sorted({f for e in items for f in e.get("feature_tags", [])})

    domain_similarity = jaccard(c_domains, cand_domains)
    technology_similarity = jaccard(c_techs, cand_techs)
    feature_similarity = jaccard(c_features, cand_features)
    mission_similarity = emb_sim  # mission captured by the embedding of full project text

    project_similarity = _clip(
        0.55 * emb_sim
        + 0.20 * domain_similarity
        + 0.15 * technology_similarity
        + 0.10 * feature_similarity
    )

    return {
        "project_similarity": round(project_similarity, 3),
        "feature_similarity": round(feature_similarity, 3),
        "domain_similarity": round(domain_similarity, 3),
        "technology_similarity": round(technology_similarity, 3),
        "mission_similarity": round(mission_similarity, 3),
        "embedding_similarity": round(emb_sim, 3),
        "top_evidence_ids": top_ids,
    }


def _embedding_similarity(cid, items, company_vec, use_db) -> tuple[float, list[str]]:
    if use_db:
        # Vector search in the active DB backend (Cloud SQL pgvector).
        rows = store.vector_search(company_vec, candidate_id=cid, owner_type="candidate_project", limit=5)
        if rows:
            top_ids = [r["owner_id"] for r in rows[:3]]
            return float(rows[0]["sim"]), top_ids

    # in-process fallback
    scored = sorted(
        ((embeddings.cosine(company_vec, embeddings.embed(evidence_text(e))), e["id"]) for e in items),
        reverse=True,
    )
    top_ids = [eid for _, eid in scored[:3]]
    return (scored[0][0] if scored else 0.0), top_ids


def _empty() -> dict[str, Any]:
    return {
        "project_similarity": 0.0,
        "feature_similarity": 0.0,
        "domain_similarity": 0.0,
        "technology_similarity": 0.0,
        "mission_similarity": 0.0,
        "embedding_similarity": 0.0,
        "top_evidence_ids": [],
    }


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))
