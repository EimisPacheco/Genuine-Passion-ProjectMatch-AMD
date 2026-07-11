"""Integration tests: the full LangGraph pipeline on seeded demo data."""
from __future__ import annotations


def test_pipeline_produces_ranking(pipeline_result):
    ranking = pipeline_result["ranking"]
    assert len(ranking) == 3
    # scores are sorted descending and ranks are 1..N
    scores = [r["overall_score"] for r in ranking]
    assert scores == sorted(scores, reverse=True)
    assert [r["rank"] for r in ranking] == [1, 2, 3]


def test_top_candidate_is_the_clear_match(pipeline_result):
    # Ava's projects (agent-recruiter, passion-signals, TalentScout) match best.
    top = pipeline_result["ranking"][0]
    assert top["candidate_id"] == "cand_ava_nguyen"
    assert top["project_similarity"] >= pipeline_result["ranking"][1]["project_similarity"]


def test_all_sub_scores_in_unit_range(pipeline_result):
    keys = ["overall_score", "project_similarity", "genuine_passion", "domain_similarity",
            "technology_similarity", "innovation", "evidence_quality", "confidence"]
    for r in pipeline_result["ranking"]:
        for k in keys:
            assert 0.0 <= r[k] <= 1.0, f"{k}={r[k]} out of range"


def test_narratives_for_selected(pipeline_result):
    narratives = pipeline_result["narratives"]
    selected = pipeline_result["ranking"][:3]
    for r in selected:
        assert r["candidate_id"] in narratives
        assert narratives[r["candidate_id"]]["explanation"]


def test_single_video_report(pipeline_result):
    vid = pipeline_result["video_report"]
    assert vid["analysis_id"] == "an_test"
    # one video for all selected candidates, not one per candidate
    assert len(vid["candidate_ids"]) == 3
    assert vid["srt_path"].endswith(".srt")
    assert vid["duration_seconds"] > 0
