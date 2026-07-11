"""Unit tests for scoring math: tag overlap, embeddings, ranking weights."""
from __future__ import annotations

from backend.app.agents.common import jaccard
from backend.app.agents.ranking import WEIGHTS, _evidence_quality, _recommendation
from backend.app.llm import embeddings


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_jaccard_bounds():
    assert jaccard([], ["a"]) == 0.0
    assert jaccard(["a", "b"], ["a", "b"]) == 1.0
    assert 0 < jaccard(["a", "b"], ["b", "c"]) < 1


def test_evidence_quality_range():
    items = [{"confidence": 0.9, "source": "github"}, {"confidence": 0.8, "source": "devpost"}]
    q = _evidence_quality(items)
    assert 0.0 <= q <= 1.0
    assert _evidence_quality([]) == 0.0


def test_recommendation_thresholds():
    assert "Strong" in _recommendation(0.8)
    assert "Weak" in _recommendation(0.1)


def test_embedding_cosine_self_is_one():
    v = embeddings.embed("autonomous ai recruiting investigator agents")
    assert abs(embeddings.cosine(v, v) - 1.0) < 1e-6


def test_embedding_related_more_similar_than_unrelated():
    base = embeddings.embed("autonomous ai recruiting agent investigator")
    related = embeddings.embed("ai agent that investigates candidates for recruiting")
    unrelated = embeddings.embed("baking sourdough bread at home")
    assert embeddings.cosine(base, related) > embeddings.cosine(base, unrelated)
