"""Loads seeded candidate evidence from demo_data/.

This is the deterministic, demo-safe source of evidence. Each candidate lives in
demo_data/<dir>/candidate.json. We map by candidate id so LIVE_MODE scrapers can
fall back here per-source when a live fetch fails.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from backend.app.config import settings

CANDIDATE_DIRS = ["candidate_a", "candidate_b", "candidate_c"]


@lru_cache
def _all() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for d in CANDIDATE_DIRS:
        path = settings.demo_data_dir / d / "candidate.json"
        if path.exists():
            data = json.loads(path.read_text())
            out[data["id"]] = data
    return out


def list_candidates() -> list[dict[str, Any]]:
    """Profiles only (no evidence) for the default demo roster."""
    return [
        {k: v for k, v in c.items() if k != "evidence"} for c in _all().values()
    ]


def load_company_project() -> dict[str, Any]:
    path = settings.demo_data_dir / "company_project.json"
    return json.loads(path.read_text())


def evidence_for(candidate_id: str, source: str | None = None) -> list[dict[str, Any]]:
    cand = _all().get(candidate_id)
    if not cand:
        return []
    ev = cand.get("evidence", [])
    if source:
        ev = [e for e in ev if e.get("source") == source]
    return [dict(e) for e in ev]


def profile_for(candidate_id: str) -> dict[str, Any] | None:
    cand = _all().get(candidate_id)
    if not cand:
        return None
    return {k: v for k, v in cand.items() if k != "evidence"}


@lru_cache
def _dirs() -> dict[str, str]:
    """candidate_id -> demo_data subdirectory (for resolving image files)."""
    out: dict[str, str] = {}
    for d in CANDIDATE_DIRS:
        path = settings.demo_data_dir / d / "candidate.json"
        if path.exists():
            out[json.loads(path.read_text())["id"]] = d
    return out


def portfolio_images_for(candidate_id: str) -> list[dict[str, Any]]:
    """Seeded portfolio images with resolved absolute file paths.

    Each item: {title, source_url, path (local file or ""), file}. The Visual
    Portfolio Agent base64-encodes `path` for the vision model and cites
    `source_url` in its output (anti-hallucination).
    """
    cand = _all().get(candidate_id)
    sub = _dirs().get(candidate_id)
    if not cand or not sub:
        return []
    base = settings.demo_data_dir / sub
    out: list[dict[str, Any]] = []
    for im in cand.get("portfolio_images", []):
        path = base / im.get("file", "") if im.get("file") else None
        out.append({
            "title": im.get("title", ""),
            "source_url": im.get("source_url", ""),
            "file": im.get("file", ""),
            "path": str(path) if path and path.exists() else "",
        })
    return out
