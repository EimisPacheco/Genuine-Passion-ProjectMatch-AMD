"""Agent 2 — Evidence Discovery.

For each candidate, discover public evidence via the scraper dispatch (live or
seeded), assign stable evidence ids, persist to `candidate_evidence` +
`candidate_profiles`, and embed each evidence item for later vector search.
All evidence retains its source URL — the anti-hallucination foundation.
"""
from __future__ import annotations

from typing import Any

from backend.app import store
from backend.app.agents.base import agent_step, new_id
from backend.app.config import settings
from backend.app.agents.common import DOMAIN_VOCAB, TECH_VOCAB, evidence_text, heuristic_tags
from backend.app.graph.state import ProjectMatchState
from backend.app.llm import embeddings
from integrations.scrapers import dispatch, geocode, github_api, linkedin_finder


def _resolve_display_name(cand: dict[str, Any], live_mode: bool | None,
                          prof: dict[str, Any] | None = None) -> None:
    """Show the person's real name, not their GitHub login. Free Discovery seeds
    `name` with the handle (it's all the search API gives us); replace it with the
    real name off their GitHub profile as soon as we know it. If we already have a
    real name (Applicants, or an earlier resolve), leave it alone."""
    handle = (cand.get("github_handle") or "").strip()
    current = (cand.get("name") or "").strip()
    if current and current.lower() != handle.lower():
        return  # already a real name — don't clobber it
    real = (prof.get("name") or "").strip() if prof else ""
    if not real and live_mode and handle:
        try:
            real = (github_api.fetch_user_profile(handle).get("name") or "").strip()
        except Exception:
            real = ""
    if real:
        cand["name"] = real


def _enrich_contact(cand: dict[str, Any], live_mode: bool | None) -> None:
    """Best-effort contact info for the Rankings view. Live candidates get their
    public GitHub profile read (real name, location, email, LinkedIn if linked);
    every candidate with a location is geocoded into city / state / country. All
    fields are optional — missing data simply stays blank (never fabricated)."""
    prof: dict[str, Any] = {}
    if live_mode and cand.get("github_handle"):
        try:
            prof = github_api.fetch_user_profile(cand["github_handle"]) or {}
            cand["location"] = cand.get("location") or prof.get("location", "")
            cand["email"] = cand.get("email") or prof.get("email", "")
            cand["linkedin_url"] = cand.get("linkedin_url") or prof.get("linkedin", "")
        except Exception:
            prof = {}
    # Reuse the profile we just fetched, so this doesn't cost a second API call.
    _resolve_display_name(cand, live_mode, prof)
    # LinkedIn a recruiter pasted (Applicants tab) — pick it out of the sources.
    if not cand.get("linkedin_url"):
        cand["linkedin_url"] = next(
            (u for u in cand.get("sources", []) if "linkedin.com" in (u or "").lower()), "")
    if cand.get("location"):
        p = geocode.parts(cand["location"])
        cand["city"] = cand.get("city") or p.get("city", "")
        cand["state"] = cand.get("state") or p.get("state", "")
        cand["country"] = cand.get("country") or p.get("country", "")


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    candidates = state["candidate_sources"]
    evidence_map: dict[str, list[dict[str, Any]]] = {}
    profiles: list[dict[str, Any]] = []

    with agent_step("evidence_discovery", analysis_id, f"{len(candidates)} candidates") as h:
        emb_rows: list[dict[str, Any]] = []
        live_mode = state.get("live_mode")
        reused_count = 0
        for cand in candidates:
            cid = cand["id"]
            handle = cand.get("github_handle", "")
            # Reuse: if we already investigated this person recently, load the saved
            # evidence instead of re-scraping GitHub and re-running the LinkedIn search.
            reused = store.recent_candidate(handle, days=30) if (live_mode and handle) else None
            if reused:
                reused_count += 1
                items = [dict(e) for e in reused["evidence"]]
                prof = reused["profile"]
                for k in ("linkedin_url", "location", "city", "state", "country", "email"):
                    cand[k] = cand.get(k) or prof.get(k, "")
                # Use the stored real name; if that row was saved before we resolved
                # names (handle only), fall back to a fresh GitHub profile lookup.
                _resolve_display_name(cand, live_mode, prof)
            else:
                _enrich_contact(cand, live_mode)
                items = dispatch.discover(cand, live_mode=live_mode)
                # Fallback: if the GitHub profile gave no LinkedIn, find it by web search
                # (Bright Data SERP + Gemma verify) — motivated builders link their repos
                # on LinkedIn, so their profile is the top result for name + stack.
                if live_mode and not cand.get("linkedin_url") and settings.brightdata_enabled and cand.get("name"):
                    tech = [t for e in items for t in e.get("technologies", []) if t][:5]
                    found = linkedin_finder.find(cand["name"], tech, handle)
                    if found:
                        cand["linkedin_url"] = found
            for ev in items:
                # Tag live evidence from the shared vocab (seeded evidence already
                # carries hand-authored tags) so domain/technology relevance flows
                # into similarity + passion instead of raw evidence volume.
                _etext = f"{ev.get('title', '')} {ev.get('description', '')}"
                if not ev.get("technologies"):
                    ev["technologies"] = heuristic_tags(_etext, TECH_VOCAB)
                if not ev.get("domain_tags"):
                    ev["domain_tags"] = heuristic_tags(_etext, DOMAIN_VOCAB)
            for ev in items:
                ev["id"] = ev.get("id") or new_id("ev_")
                ev["candidate_id"] = cid
                emb_rows.append(
                    {
                        "id": new_id("emb_"),
                        "owner_type": "candidate_project",
                        "owner_id": ev["id"],
                        "candidate_id": cid,
                        "text": evidence_text(ev)[:2000],
                        "embedding": embeddings.embed(evidence_text(ev)),
                    }
                )
            evidence_map[cid] = items

            # Persist the whole person, contact trail included — a candidate found by
            # Free Discovery is only useful later if we kept how to reach them. Skip
            # when reused: it is already in the pool, and re-writing would duplicate.
            if not reused:
                store.save(
                    "candidate_profiles",
                    {
                        "id": cid,
                        "name": cand.get("name", cid),
                        "headline": cand.get("headline", ""),
                        "sources": cand.get("sources", []),
                        "github_handle": handle,
                        "location": cand.get("location", ""),
                        "city": cand.get("city", ""),
                        "state": cand.get("state", ""),
                        "country": cand.get("country", ""),
                        "email": cand.get("email", ""),
                        "linkedin_url": cand.get("linkedin_url", ""),
                    },
                )
                store.save_many(
                    "candidate_evidence",
                    [
                        {
                            "id": ev["id"],
                            "candidate_id": cid,
                            "source": ev.get("source", ""),
                            "title": ev.get("title", ""),
                            "url": ev.get("url", ""),
                            "description": ev.get("description", ""),
                            "technologies": ev.get("technologies", []),
                            "domain_tags": ev.get("domain_tags", []),
                            "feature_tags": ev.get("feature_tags", []),
                            "evidence_date": ev.get("evidence_date", ""),
                            "confidence": float(ev.get("confidence", 0.6)),
                        }
                        for ev in items
                    ],
                )
            profiles.append({k: v for k, v in cand.items()})

        store.save_many("project_embeddings", emb_rows)
        total = sum(len(v) for v in evidence_map.values())
        reuse = f" ({reused_count} reused from the pool)" if reused_count else ""
        h["summary"] = f"discovered {total} evidence items across {len(candidates)} candidates{reuse}"

    return {"evidence": evidence_map, "candidates": profiles}
