"""Pydantic request/response models for the API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectIn(BaseModel):
    title: str
    description: str = ""
    business_problem: str = ""
    target_users: str = ""
    expected_features: list[str] = Field(default_factory=list)
    expected_technologies: list[str] = Field(default_factory=list)
    success_criteria: str = ""
    desired_candidates: int = 3


class CandidateSourceIn(BaseModel):
    id: str | None = None
    name: str
    headline: str = ""
    github_handle: str = ""
    location: str = ""
    sources: list[str] = Field(default_factory=list)


class VideoCaptionIn(BaseModel):
    """Audience for the on-demand Gemma caption of the recommendation video."""
    style: str = "tech"  # tech (hiring manager) | non_tech (HR)


class AnalysisIn(BaseModel):
    project_id: str | None = None
    company_project: ProjectIn | None = None
    candidate_sources: list[CandidateSourceIn] | None = None
    top_n: int = 3
    use_demo: bool = False
    live_mode: bool = False
    # Free Discovery: find candidates from the project itself (GitHub search) when
    # no candidate_sources are supplied. Forces live discovery.
    discover_candidates: bool = False
