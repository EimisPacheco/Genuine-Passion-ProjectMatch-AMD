"""Agent 9 — Executive Video.

Generates ONE executive summary video for all selected candidates (never one per
candidate). Builds scenes (company overview -> ranking overview -> per-candidate
-> recommendation), narrates them, and renders an MP4 + .srt + script via the
ffmpeg renderer. Narration is templated from real scores/evidence so it is fast
and never fabricates; explanations come from the storytelling agent.
"""
from __future__ import annotations

from typing import Any

from backend.app import store
from backend.app.agents.base import agent_step, new_id
from backend.app.config import settings
from backend.app.graph.state import ProjectMatchState
from video import renderer
from video.renderer import Scene


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    company = state["company_project"]
    ranking = state["ranking"]
    narratives = state.get("narratives", {})
    candidates = {c["id"]: c for c in state.get("candidates", [])}
    top_n = state.get("top_n", 3)
    selected = ranking[:top_n]

    with agent_step("executive_video", analysis_id, f"{len(selected)} candidates") as h:
        scenes = _build_scenes(company, selected, narratives, candidates)
        result = renderer.render(scenes, settings.video_out_path, basename=f"exec_{analysis_id[:8]}")

        report = {
            "id": new_id("vid_"),
            "analysis_id": analysis_id,
            "title": f"ProjectMatch Executive Summary — {company.get('title')}",
            "mp4_path": str(result.mp4_path) if result.mp4_path else "",
            "srt_path": str(result.srt_path),
            "narration_script": result.narration,
            "duration_seconds": float(result.duration),
            "candidate_ids": [r["candidate_id"] for r in selected],
        }
        store.save("video_reports", report)
        h["summary"] = f"video {result.duration:.0f}s, mp4={'yes' if result.mp4_path else 'no'}"

    return {"video_report": report}


def _build_scenes(company, selected, narratives, candidates) -> list[Scene]:
    title = company.get("title", "Company Project")
    scenes: list[Scene] = []

    # Scene 1 — company overview
    scenes.append(Scene(
        title=title,
        bullets=[
            f"Problem: {company.get('business_problem', '')[:120]}",
            f"Mission: {company.get('mission', '')[:120]}",
            f"Domains: {', '.join(company.get('domain_tags', [])[:5])}",
        ],
        narration=(
            f"Here is the executive summary for {title}. "
            f"The company wants to solve this problem: {company.get('business_problem','')}. "
            f"We searched public technical work to find people who were already building "
            f"toward this exact mission."
        ),
        subtitle_label=f"Company project: {title}",
    ))

    # Scene 2 — ranking overview
    ranking_bullets = [
        f"#{r['rank']} {_name(candidates, r['candidate_id'])} — match {r['overall_score']:.0%}"
        for r in selected
    ]
    scenes.append(Scene(
        title=f"Top {len(selected)} Candidates",
        bullets=ranking_bullets,
        narration=(
            "Across all candidates, these are the strongest matches, ranked by overall "
            "ProjectMatch score combining project similarity, genuine passion, and evidence quality. "
            + " ".join(
                f"Number {r['rank']}, {_name(candidates, r['candidate_id'])}, at {r['overall_score']:.0%}."
                for r in selected
            )
        ),
        subtitle_label="Candidate ranking overview",
    ))

    # Scene 3+ — per candidate
    for r in selected:
        cid = r["candidate_id"]
        nar = narratives.get(cid, {})
        projects = nar.get("supporting_projects", [])[:3]
        bullets = [
            f"Project similarity {r['project_similarity']:.0%} · passion {r['genuine_passion']:.0%}",
            *[f"Evidence: {p['title'][:80]}" for p in projects],
        ]
        scenes.append(Scene(
            title=f"#{r['rank']}  {_name(candidates, cid)}",
            bullets=bullets,
            narration=(
                f"Number {r['rank']}, {_name(candidates, cid)}. "
                f"{nar.get('explanation', '')} "
                f"Project similarity is {r['project_similarity']:.0%} and genuine passion is "
                f"{r['genuine_passion']:.0%}. {r['recommendation']}."
            ),
            subtitle_label=f"#{r['rank']} {_name(candidates, cid)}",
        ))

    # Final scene — recommendation
    names = ", ".join(_name(candidates, r["candidate_id"]) for r in selected)
    scenes.append(Scene(
        title="Recommendation",
        bullets=[f"Prioritize: {names}", "Every claim is backed by public evidence and source URLs."],
        narration=(
            f"In summary, we recommend prioritizing {names}. "
            "Each was already building toward this project before the company decided to build it, "
            "and every recommendation is backed by verifiable public evidence."
        ),
        subtitle_label="Recommendation summary",
    ))
    return scenes


def _name(candidates: dict, cid: str) -> str:
    return candidates.get(cid, {}).get("name", cid)
