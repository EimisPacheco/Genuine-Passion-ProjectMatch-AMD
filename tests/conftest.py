"""Shared fixtures. Runs the full pipeline once on seeded demo data in heuristic
mode (no API keys, no external DB) so tests are deterministic and offline."""
from __future__ import annotations

import pytest

from backend.app.graph.pipeline import run_pipeline
from integrations.scrapers import demo_loader


@pytest.fixture(scope="session")
def pipeline_result():
    company = demo_loader.load_company_project()
    candidates = demo_loader.list_candidates()
    return run_pipeline(company, candidates, top_n=3, analysis_id="an_test")


@pytest.fixture(scope="session")
def evidence_ids(pipeline_result):
    ids = set()
    for items in pipeline_result["evidence"].values():
        ids.update(e["id"] for e in items)
    return ids
