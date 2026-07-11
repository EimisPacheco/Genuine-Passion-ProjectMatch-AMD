"""End-to-end API tests via FastAPI TestClient.

Runs the analysis synchronously through the analyses runner, then exercises the
read endpoints the frontend uses.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import analyses
from backend.app.main import app

client = TestClient(app)


def _completed_analysis() -> str:
    company = analyses.default_company_project()
    sources = analyses.default_candidate_sources()
    aid = analyses.create_analysis(company, sources, top_n=3)
    analyses.set_sources(aid, sources)
    analyses.run(aid)  # synchronous
    return aid


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_demo_defaults():
    r = client.get("/api/demo/defaults")
    body = r.json()
    assert body["company_project"]["title"]
    assert len(body["candidate_sources"]) == 3


def test_full_read_flow():
    aid = _completed_analysis()

    status = client.get(f"/api/analyses/{aid}").json()
    assert status["status"] == "done"

    cands = client.get(f"/api/analyses/{aid}/candidates").json()
    assert cands["candidates"][0]["rank"] == 1
    assert cands["candidates"][0]["name"]

    cid = cands["candidates"][0]["candidate_id"]
    ev = client.get(f"/api/analyses/{aid}/candidates/{cid}/evidence").json()
    assert len(ev["evidence"]) > 0
    assert all(e["url"].startswith("http") for e in ev["evidence"])

    vid = client.get(f"/api/analyses/{aid}/video").json()
    assert vid["title"]
    assert vid["duration_seconds"] > 0

    traces = client.get(f"/api/analyses/{aid}/traces").json()
    assert len(traces["timeline"]) > 0
