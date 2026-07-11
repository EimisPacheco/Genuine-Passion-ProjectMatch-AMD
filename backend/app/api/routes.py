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

from backend.app import analyses, progress, race, store
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


# ----------------------------- speed race -----------------------------
@router.get("/race/info")
def race_info() -> dict[str, Any]:
    """Provider availability, models, and the demo candidate pool for the race UI."""
    return race.race_info()


@router.get("/race/stream")
async def race_stream(max_tokens: int = 160) -> StreamingResponse:
    """SSE: Gemma on AMD vs the GPU baseline over the same Gemma task, one instant."""
    return StreamingResponse(
        (chunk async for chunk in race.stream_race(max_tokens=max_tokens)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/analyses/{analysis_id}/race/info")
def analysis_race_info(analysis_id: str) -> dict[str, Any]:
    """Race info scoped to a specific analysis's project + candidates."""
    project, pool = race.build_from_analysis(analysis_id)
    return race.race_info(project, pool)


@router.get("/analyses/{analysis_id}/race/stream")
async def analysis_race_stream(analysis_id: str, max_tokens: int = 160) -> StreamingResponse:
    """SSE: Gemma on AMD vs GPU baseline over THIS analysis's candidates."""
    project, pool = race.build_from_analysis(analysis_id)
    return StreamingResponse(
        (chunk async for chunk in race.stream_race(max_tokens, project, pool)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


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
        sources = github_api.search_candidates(company, limit=pool_size)
        if not sources:
            raise HTTPException(
                422, "No candidates found for this mission. Add more specific "
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
    out = []
    for r in ranking:
        cid = r["candidate_id"]
        out.append({
            **r,
            "name": names.get(cid, {}).get("name", cid),
            "headline": names.get(cid, {}).get("headline", ""),
            "location": names.get(cid, {}).get("location", ""),
            "selected": r["rank"] <= top_n,
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
def video_subtitles(analysis_id: str):
    """Serve WebVTT (converted from the .srt) so the HTML <track> renders captions."""
    vid = _result(analysis_id).get("video_report", {})
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
