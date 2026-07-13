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
from backend.app.agents.common import TECH_VOCAB, heuristic_tags
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
    company = state.get("company_project", {})  # needed to explain the tag-overlap scores

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

            reasons = _reasons(
                company, items, p, s, github.get(cid, []), visual.get(cid, []),
                hackathon.get(cid, []), evidence_quality,
            )
            technologies = _technologies(items)

            rows.append(
                {
                    "candidate_id": cid,
                    "overall_score": round(overall, 3),
                    "confidence": round(confidence, 3),
                    "code_score": round(code_score, 3),
                    "design_score": round(design_score, 3),
                    "evidence_quality": round(evidence_quality, 3),
                    "evidence_ids": evidence_ids,
                    "reasons": reasons,
                    "technologies": technologies,
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


# Reuse the exact sets the scores are computed from — a duplicated copy would drift
# and the explanation would contradict the number it explains.
from backend.app.agents.passion import VOLUNTARY_SOURCES

NOVELTY_WORDS = ("win", "winner", "medal", "novel", "first")


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _overlap(a: list[str], b: list[str]) -> list[str]:
    lower = {x.lower() for x in b}
    return sorted({x for x in a if x.lower() in lower})


def _technologies(items: list[dict[str, Any]], limit: int = 24) -> list[str]:
    """Every technology the candidate has actually used, from ALL their evidence:
    the languages/topics GitHub reports on each repo, PLUS anything from the shared
    tech vocabulary that shows up in the titles and descriptions (a repo's real
    stack is often only named in its README, not its `language` field). Ordered by
    how often it recurs, so the stack they lean on rises to the top."""
    from collections import Counter

    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for e in items:
        text = f"{e.get('title', '')} {e.get('description', '')}"
        tags = (
            list(e.get("technologies", []))
            + list(e.get("domain_tags", []))
            + heuristic_tags(text, TECH_VOCAB)
        )
        for t in tags:
            t = (t or "").strip()
            if not t:
                continue
            key = t.lower()
            counts[key] += 1
            display.setdefault(key, t)
    ranked = sorted(counts, key=lambda k: (-counts[k], k))
    return [display[k] for k in ranked[:limit]]


def _reasons(
    company: dict[str, Any], items: list[dict[str, Any]], p: dict[str, Any], s: dict[str, Any],
    gh: list[dict[str, Any]], visual: list[dict[str, Any]], hack: list[dict[str, Any]],
    evidence_quality: float,
) -> dict[str, str]:
    """One short, data-backed sentence per score — why THIS candidate got THIS number.

    Everything here is read off the same inputs the scores were computed from, so the
    explanation can never disagree with the number it explains.
    """
    n = len(items)
    sources = sorted({e.get("source", "") for e in items if e.get("source")})
    cand_domains = sorted({d for e in items for d in e.get("domain_tags", [])})
    cand_techs = sorted({t for e in items for t in e.get("technologies", [])})
    proj_domains = company.get("domain_tags", []) or []
    proj_techs = company.get("technologies", []) or company.get("expected_technologies", []) or []

    dom_hit = _overlap(proj_domains, cand_domains)
    tech_hit = _overlap(proj_techs, cand_techs)
    voluntary = sum(1 for e in items if e.get("source") in VOLUNTARY_SOURCES)
    novel = [e for e in items
             if any(k in (e.get("description") or "").lower() for k in NOVELTY_WORDS)]
    dated = sorted(e.get("evidence_date", "") for e in items if e.get("evidence_date"))
    span = _month_span_safe(dated)
    qs = [g.get("quality_score") for g in gh if g.get("quality_score") is not None]
    pol = [v.get("polish") for v in visual if v.get("polish") is not None]
    ex = [h.get("execution_quality") for h in hack if h.get("execution_quality") is not None]
    avg_conf = sum(float(e.get("confidence", 0.6)) for e in items) / n if n else 0.0

    # --- extra signals so Code and Project-similarity can say WHY, not just "average of N" ---
    from collections import Counter
    mats = Counter((g.get("maturity") or "").lower() for g in gh if g.get("maturity"))
    stars = sum(int(g.get("stars", 0) or 0) for g in gh)
    best = max(gh, key=lambda g: float(g.get("quality_score") or 0.0), default=None) if gh else None
    best_name = (best.get("repo_full_name") or "").strip() if best else ""
    best_arch = (best.get("architecture_profile") or "").strip().rstrip(". ") if best else ""
    emb = float(s.get("embedding_similarity", s.get("mission_similarity", 0.0)) or 0.0)
    dsim = float(s.get("domain_similarity", 0.0) or 0.0)
    tsim = float(s.get("technology_similarity", 0.0) or 0.0)
    fsim = float(s.get("feature_similarity", 0.0) or 0.0)

    def lst(xs: list[str], k: int = 4) -> str:
        return ", ".join(xs[:k]) + ("…" if len(xs) > k else "")

    # Code score — what the number actually reflects, per repo.
    if qs:
        mat_desc = ", ".join(f"{c} {name}" for name, c in mats.most_common()) if mats else ""
        code_reason = (
            f"Gemma read {_plural(len(qs), 'repository', 'repositories')} and scored each for "
            "engineering quality — code structure, docs, tests and architecture; this is the average"
            + (f" ({mat_desc} by maturity)" if mat_desc else "") + "."
        )
        if best_name:
            code_reason += f" Strongest is {best_name}" + (f" — {best_arch[:140]}" if best_arch else "") + "."
        if stars > 0:
            code_reason += f" {stars:,} GitHub stars across these repos."
    else:
        code_reason = (
            "No repositories were deep-analysed here, so this is estimated from their technology "
            "depth and how consistently they build — treat it as a floor, not a measured value."
        )

    # Project similarity — the exact recipe behind the percentage.
    proj_reason = (
        "How close their public work sits to your mission. The largest input (55% of the score) is "
        f"semantic — the embedding of their strongest evidence is {emb:.0%} similar to the project "
        f"description. Tag overlap supplies the rest: domain {dsim:.0%}, technology {tsim:.0%}, "
        f"features {fsim:.0%}. "
        + (f"Shared ground: {lst(dom_hit)}" + (f"; {lst(tech_hit)}" if tech_hit else "") + "."
           if (dom_hit or tech_hit) else
           "Barely any tag overlap — the match is almost entirely semantic, so open the evidence to judge fit yourself.")
    )

    return {
        "overall_score":
            "Weighted blend: project fit 40%, genuine passion 25%, domain 15%, "
            "technology 10%, innovation 5%, evidence quality 5%.",
        "project_similarity": proj_reason,
        "genuine_passion":
            "Do they keep choosing this problem? Blends how much of their work touches the "
            f"project's domains, how consistently they build, and how much is self-initiated "
            f"({voluntary} of {n} items).",
        "domain_similarity":
            (f"{len(dom_hit)} of {len(proj_domains)} project domains appear in their work: {lst(dom_hit)}."
             if dom_hit else
             f"None of the project's {len(proj_domains)} domains appear in their evidence."),
        "technology_similarity":
            (f"{len(tech_hit)} of {len(proj_techs)} project technologies appear in their work: {lst(tech_hit)}."
             if tech_hit else
             f"None of the project's {len(proj_techs)} technologies appear in their evidence."),
        "code_score": code_reason,
        "design_score":
            (f"Gemma's vision model looked at {_plural(len(pol), 'portfolio image', 'portfolio images')} "
             "(architecture diagrams, product screenshots) and rated their visual polish and rigor"
             + (f", averaged with execution quality from {_plural(len(ex), 'hackathon project', 'hackathon projects')}." if ex else ".")
             if pol else
             "No portfolio images were readable, so this is estimated from innovation and voluntary effort."),
        "builder_consistency":
            f"{_plural(n, 'piece', 'pieces')} of public work spanning "
            f"{_plural(span, 'month', 'months')}. Full marks needs ~6 items across a year or more.",
        "voluntary_effort":
            f"{_plural(voluntary, 'self-initiated artifact', 'self-initiated artifacts')} "
            f"(repos, hackathons, notebooks, writing). Full marks at 5 or more.",
        "innovation":
            (f"{_plural(len(novel), 'item mentions', 'items mention')} an award, a win or a novel "
             f"result: {lst([e.get('title', '') for e in novel], 2)}."
             if novel else
             "Nothing in their evidence mentions an award, a win, or a novel result — this "
             "measures recognised novelty, not skill."),
        "evidence_quality":
            f"{n} evidence items across {len(sources)} distinct sources "
            f"({lst(sources, 5)}), average source confidence {avg_conf:.0%}.",
        "confidence":
            f"How much we trust this verdict: driven by evidence quality and how much we "
            f"found ({n} items; 5+ is a full signal).",
    }


def _month_span_safe(dates: list[str]) -> int:
    if len(dates) < 2:
        return 0
    try:
        y0, m0 = int(dates[0][:4]), int(dates[0][5:7])
        y1, m1 = int(dates[-1][:4]), int(dates[-1][5:7])
        return max(0, (y1 - y0) * 12 + (m1 - m0))
    except Exception:
        return 0


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
