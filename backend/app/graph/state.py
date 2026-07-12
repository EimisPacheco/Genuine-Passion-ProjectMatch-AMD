"""Typed shared state for the LangGraph pipeline.

We use a TypedDict for LangGraph compatibility. Nested values are plain dicts so
nodes can be tested in isolation and the whole state serializes to JSON for the
trace viewer.
"""
from __future__ import annotations

from typing import Any, TypedDict


class ProjectMatchState(TypedDict, total=False):
    analysis_id: str
    top_n: int
    live_mode: bool

    # Agent 1
    company_project: dict[str, Any]

    # Input + Agent 2
    candidate_sources: list[dict[str, Any]]   # [{candidate_id, name, sources:[...]}]
    candidates: list[dict[str, Any]]          # normalized candidate profiles
    evidence: dict[str, list[dict[str, Any]]] # candidate_id -> [evidence]

    # Agents 3 & 4
    github_analyses: dict[str, list[dict[str, Any]]]
    hackathon_analyses: dict[str, list[dict[str, Any]]]

    # Agent 5 — Visual Portfolio (Gemma 4 31B multimodal)
    visual_analyses: dict[str, list[dict[str, Any]]]

    # Agents 5 & 6
    passion_scores: dict[str, dict[str, Any]]
    similarity_scores: dict[str, dict[str, Any]]

    # Agent 7
    ranking: list[dict[str, Any]]

    # Agent 8
    narratives: dict[str, dict[str, Any]]

    # Agent 9
    video_report: dict[str, Any]

    # Agent 11 — fixed clip set → 4-style Gemma captions
    clip_captions: list[dict[str, Any]]

    # Cross-cutting
    trace_ids: dict[str, str]
