"""QA Agent (spec Agent 12) — anti-hallucination invariants.

Guarantees that every recommendation is backed by real, discovered evidence and
that nothing is invented:
  * every ranked candidate has non-empty evidence_ids
  * every referenced evidence id exists in the discovered evidence set
  * every supporting project in a narrative maps to a real evidence id + URL
  * no evidence URL is fabricated relative to what discovery returned
"""
from __future__ import annotations

import re


def test_every_score_has_evidence(pipeline_result, evidence_ids):
    for r in pipeline_result["ranking"]:
        assert r["evidence_ids"], f"{r['candidate_id']} has no evidence_ids"
        for eid in r["evidence_ids"]:
            assert eid in evidence_ids, f"score references unknown evidence {eid}"


def test_narrative_projects_are_real(pipeline_result, evidence_ids):
    all_urls = {
        e["url"] for items in pipeline_result["evidence"].values() for e in items
    }
    for cid, nar in pipeline_result["narratives"].items():
        for proj in nar.get("supporting_projects", []):
            assert proj["id"] in evidence_ids, f"invented evidence id {proj['id']}"
            assert proj["url"] in all_urls, f"invented URL {proj['url']}"


def test_no_evidence_without_source_url(pipeline_result):
    for items in pipeline_result["evidence"].values():
        for e in items:
            assert e.get("url"), f"evidence {e.get('id')} missing source URL"
            assert re.match(r"^https?://", e["url"]), f"bad URL {e['url']}"


def test_similarity_top_evidence_are_real(pipeline_result, evidence_ids):
    for cid, sim in pipeline_result["similarity_scores"].items():
        for eid in sim.get("top_evidence_ids", []):
            assert eid in evidence_ids
