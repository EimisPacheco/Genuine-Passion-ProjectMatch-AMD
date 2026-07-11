"""LangGraph wiring of agents 1-9.

The graph is linear (each agent enriches shared state); GitHub and Hackathon
analysis fan out per candidate inside their own nodes. We expose `build_graph()`
and a convenience `run_pipeline()` used by the API and CLI.
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.app import progress
from backend.app.agents import (
    discovery,
    executive_video,
    github_analysis,
    hackathon_analysis,
    passion,
    ranking,
    similarity,
    storytelling,
    understanding,
    visual_portfolio,
)
from backend.app.agents.base import new_id
from backend.app.graph.state import ProjectMatchState

NODES = [
    ("project_understanding", understanding.run),
    ("evidence_discovery", discovery.run),
    ("github_analysis", github_analysis.run),
    ("hackathon_analysis", hackathon_analysis.run),
    ("visual_portfolio", visual_portfolio.run),
    ("passion_detection", passion.run),
    ("similarity", similarity.run),
    ("ranking", ranking.run),
    ("storytelling", storytelling.run),
    ("executive_video", executive_video.run),
]


def build_graph():
    # Graph node ids are suffixed so they never collide with state keys
    # (e.g. the `ranking` node vs the `ranking` state field).
    g = StateGraph(ProjectMatchState)
    ids = [f"{name}_node" for name, _ in NODES]
    for node_id, (_, fn) in zip(ids, NODES):
        g.add_node(node_id, fn)
    g.add_edge(START, ids[0])
    for prev, nxt in zip(ids, ids[1:]):
        g.add_edge(prev, nxt)
    g.add_edge(ids[-1], END)
    return g.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_pipeline(
    company_project: dict[str, Any],
    candidate_sources: list[dict[str, Any]],
    top_n: int = 3,
    analysis_id: str | None = None,
    live_mode: bool | None = None,
) -> ProjectMatchState:
    analysis_id = analysis_id or new_id("an_")
    initial: ProjectMatchState = {
        "analysis_id": analysis_id,
        "top_n": top_n,
        "company_project": company_project,
        "candidate_sources": candidate_sources,
        "live_mode": bool(live_mode),
    }
    try:
        final = get_graph().invoke(initial)
        progress.emit(analysis_id, "done", "done", progress.TOTAL_STEPS, "analysis complete")
        return final
    except Exception as exc:
        progress.emit(analysis_id, "pipeline", "error", progress.TOTAL_STEPS, str(exc))
        raise
