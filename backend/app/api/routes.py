"""All HTTP routes for the recruiter API.

Endpoints cover the full product workflow: project intake, candidate input,
async analysis with live SSE progress, ranked candidates, evidence explorer,
agent traces and video viewing. The pipeline is synchronous
(LangGraph + LLM); we run it in a thread executor so SSE stays responsive.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse

from backend.app import analyses, progress, store
from backend.app.api.schemas import AnalysisIn, ProjectIn
from backend.app.config import settings
from integrations.scrapers import demo_loader

router = APIRouter(prefix="/api")


# ----------------------------- demo / projects -----------------------------
@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "db_backend": settings.db_backend,
        "db_connected": store.available(),
        "llm_provider": settings.active_provider,
        "amd": settings.amd_llm_enabled,
        "gemini": settings.gemini_enabled,
        "gemma_model": settings.amd_llm_model,
        "langfuse": settings.langfuse_enabled,
        "brightdata": settings.brightdata_enabled,
        "live_mode": settings.live_mode,
    }


@router.get("/config")
def public_config() -> dict[str, Any]:
    """Client-safe config for the frontend. The Maps key is a referrer-restricted
    browser key, so serving it here is expected (not a server secret)."""
    return {"google_maps_api_key": settings.google_maps_api_key}


@router.get("/candidates")
def talent_pool() -> dict[str, Any]:
    """Every candidate ever discovered, across all analyses — the persistent talent
    pool. Lets a recruiter browse who's already been found instead of re-searching."""
    return {"candidates": store.talent_pool()}


@router.get("/demo/defaults")
def demo_defaults() -> dict[str, Any]:
    return {
        "company_project": demo_loader.load_company_project(),
        "candidate_sources": demo_loader.list_candidates(),
    }


@router.post("/projects")
def create_project(payload: ProjectIn) -> dict[str, Any]:
    project = payload.model_dump()
    pid = analyses.register_project(project)
    return {"project_id": pid, "project": project}


# ----------------------------- analyses -----------------------------
@router.post("/analyses")
async def create_analysis(payload: AnalysisIn) -> dict[str, Any]:
    if payload.use_demo or (payload.company_project is None and payload.project_id is None):
        company = analyses.default_company_project()
    elif payload.project_id:
        company = analyses.get_project(payload.project_id)
        if not company:
            raise HTTPException(404, "project_id not found")
    else:
        company = payload.company_project.model_dump()

    live_mode = payload.live_mode
    if payload.discover_candidates and not payload.use_demo:
        # Free Discovery: the recruiter supplies no people — find them from the
        # mission by searching GitHub, then investigate the discovered pool live.
        from integrations.scrapers import github_api

        pool_size = min(max(payload.top_n * 2, 6), 18)
        # Over-fetch, then drop anyone already in the pool so discovery surfaces
        # *new* people rather than re-listing candidates we've already saved.
        found = github_api.search_candidates(company, limit=pool_size + 15)
        known = store.known_handles()
        fresh = [s for s in found if (s.get("github_handle", "").lower() not in known)]
        sources = fresh[:pool_size]
        if not sources:
            already = bool(found) and not fresh
            raise HTTPException(
                422,
                "Everyone we found for this mission is already in your talent pool — "
                "browse it directly." if already else
                "No candidates found for this mission. Add more specific "
                "technologies to the project, or use the Applicants tab.",
            )
        live_mode = True  # discovered people have no seeded evidence
    elif payload.use_demo or not payload.candidate_sources:
        sources = analyses.default_candidate_sources()
    else:
        sources = []
        for c in payload.candidate_sources:
            d = c.model_dump()
            d["id"] = d.get("id") or f"cand_{uuid.uuid4().hex[:8]}"
            sources.append(d)

    analysis_id = analyses.create_analysis(company, sources, payload.top_n, live_mode=live_mode)
    analyses.set_sources(analysis_id, sources)

    # run the synchronous pipeline off the event loop
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, analyses.run, analysis_id)

    return {"analysis_id": analysis_id, "status": "running"}


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> dict[str, Any]:
    rec = analyses.get(analysis_id)
    if not rec:
        raise HTTPException(404, "analysis not found")
    return {
        "id": analysis_id,
        "status": rec.get("status"),
        "top_n": rec.get("top_n"),
        "company_project": _project_summary(rec.get("company_project", {})),
        "error": rec.get("error"),
    }


@router.get("/analyses/{analysis_id}/stream")
async def stream_analysis(analysis_id: str) -> StreamingResponse:
    async def event_gen():
        q = await progress.subscribe(analysis_id)
        try:
            while True:
                event = await q.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("status") in ("done", "error") and event.get("step", 0) >= progress.TOTAL_STEPS:
                    break
        finally:
            progress.unsubscribe(analysis_id, q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy/nginx buffering of the stream
        },
    )


@router.get("/analyses/{analysis_id}/candidates")
def ranked_candidates(analysis_id: str) -> dict[str, Any]:
    result = _result(analysis_id)
    ranking = result.get("ranking", [])
    narratives = result.get("narratives", {})
    names = {c["id"]: c for c in result.get("candidates", [])}
    top_n = result.get("top_n", len(ranking))
    # LinkedIn is required to be "selected" (successfully considered): fill the
    # Top-N from the highest-ranked candidates that actually have a LinkedIn URL.
    selected_ids: set[str] = set()
    for r in sorted(ranking, key=lambda x: x.get("rank", 10_000)):
        prof = names.get(r["candidate_id"], {})
        if prof.get("linkedin_url") and len(selected_ids) < top_n:
            selected_ids.add(r["candidate_id"])
    out = []
    for r in ranking:
        cid = r["candidate_id"]
        prof = names.get(cid, {})
        out.append({
            **r,
            "name": prof.get("name", cid),
            "headline": prof.get("headline", ""),
            "location": prof.get("location", ""),
            "city": prof.get("city", ""),
            "state": prof.get("state", ""),
            "country": prof.get("country", ""),
            "email": prof.get("email", ""),
            "linkedin_url": prof.get("linkedin_url", ""),
            "contactable": bool(prof.get("linkedin_url")),
            "selected": cid in selected_ids,
            "narrative": narratives.get(cid, {}),
        })
    return {"analysis_id": analysis_id, "top_n": top_n, "candidates": out}


@router.get("/analyses/{analysis_id}/candidates/{candidate_id}/evidence")
def candidate_evidence(analysis_id: str, candidate_id: str) -> dict[str, Any]:
    result = _result(analysis_id)
    evidence = result.get("evidence", {}).get(candidate_id, [])
    return {"candidate_id": candidate_id, "evidence": evidence}


@router.get("/analyses/{analysis_id}/candidates/{candidate_id}/visual")
def candidate_visual(analysis_id: str, candidate_id: str) -> dict[str, Any]:
    """Gemma 4 vision analyses of the candidate's portfolio images."""
    result = _result(analysis_id)
    visual = result.get("visual_analyses", {}).get(candidate_id, [])
    return {"candidate_id": candidate_id, "visual": visual}


@router.get("/assets/portfolio/{candidate_id}/{filename}")
def portfolio_asset(candidate_id: str, filename: str) -> FileResponse:
    """Serve a seeded portfolio image (matched against the candidate's manifest)."""
    for im in demo_loader.portfolio_images_for(candidate_id):
        if im.get("path") and Path(im["path"]).name == filename:
            return FileResponse(im["path"])
    raise HTTPException(404, "portfolio image not found")


@router.get("/analyses/{analysis_id}/traces")
def traces(analysis_id: str) -> dict[str, Any]:
    timeline = progress.history(analysis_id)
    runs = store.agent_runs(analysis_id)
    return {"analysis_id": analysis_id, "timeline": timeline, "agent_runs": runs,
            "langfuse_host": settings.langfuse_host if settings.langfuse_enabled else None}


@router.get("/analyses/{analysis_id}/video")
def video_meta(analysis_id: str) -> dict[str, Any]:
    result = _result(analysis_id)
    vid = result.get("video_report", {})
    # Featured video: serve the pre-generated briefing everywhere so we never
    # pay to re-render. Falls back to the per-analysis video when unset/missing.
    if settings.featured_video_enabled:
        return {
            "title": vid.get("title") or "Candidate Briefing — Gemma 4 on AMD",
            "duration_seconds": vid.get("duration_seconds"),
            "narration_script": vid.get("narration_script", ""),
            "has_mp4": True,
            "mp4_url": f"/api/analyses/{analysis_id}/video/file",
            "srt_url": f"/api/analyses/{analysis_id}/video/subtitles",
            "candidate_ids": vid.get("candidate_ids", []),
            "featured": True,
        }
    if not vid:
        raise HTTPException(404, "video not ready")
    return {
        "title": vid.get("title"),
        "duration_seconds": vid.get("duration_seconds"),
        "narration_script": vid.get("narration_script"),
        "has_mp4": bool(vid.get("mp4_path")),
        "mp4_url": f"/api/analyses/{analysis_id}/video/file" if vid.get("mp4_path") else None,
        "srt_url": f"/api/analyses/{analysis_id}/video/subtitles",
        "candidate_ids": vid.get("candidate_ids", []),
        # Pre-generated: the whole video captioned per audience, plus the timed
        # narration — everything the UI needs to follow the playhead.
        "scenes": vid.get("scenes", []),
        "captions": vid.get("captions", {}),
    }


@router.get("/analyses/{analysis_id}/video/file")
def video_file(analysis_id: str):
    if settings.featured_video_enabled:
        return FileResponse(str(settings.featured_video_path), media_type="video/mp4", filename="briefing.mp4")
    vid = _result(analysis_id).get("video_report", {})
    path = vid.get("mp4_path")
    if not path or not Path(path).exists():
        raise HTTPException(404, "mp4 not available")
    return FileResponse(path, media_type="video/mp4", filename=Path(path).name)


@router.get("/analyses/{analysis_id}/video/subtitles")
def video_subtitles(analysis_id: str, style: str = "tech"):
    """WebVTT for the HTML <track>. Serves the pre-generated captions for the chosen
    audience (so fullscreen viewers see them too); falls back to the rendered .srt."""
    from backend.app import video_caption

    vid = _result(analysis_id).get("video_report", {})
    cues = (vid.get("captions") or {}).get(style)
    if cues:
        return Response(content=video_caption.to_vtt(cues), media_type="text/vtt")
    path = vid.get("srt_path")
    if not path or not Path(path).exists():
        raise HTTPException(404, "subtitles not available")
    vtt = "WEBVTT\n\n" + Path(path).read_text().replace(",", ".")
    return Response(content=vtt, media_type="text/vtt")


# ----------------------------- helpers -----------------------------
def _result(analysis_id: str) -> dict[str, Any]:
    rec = analyses.get(analysis_id)
    if not rec:
        raise HTTPException(404, "analysis not found")
    if rec.get("status") == "error":
        raise HTTPException(500, rec.get("error", "analysis failed"))
    result = rec.get("result")
    if not result:
        raise HTTPException(409, "analysis still running")
    return result


def _project_summary(p: dict[str, Any]) -> dict[str, Any]:
    return {k: p.get(k) for k in ("id", "title", "description", "business_problem",
                                  "domain_tags", "technologies", "mission")}
