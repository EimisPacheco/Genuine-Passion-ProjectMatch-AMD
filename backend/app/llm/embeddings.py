"""Pluggable embedding provider.

Order of preference:
1. **Ollama GPU endpoint** (when OLLAMA_EMBEDDINGS_URL is set) — `all-minilm`
   served by Ollama on the AMD MI300X (384-dim).
2. Local sentence-transformers (if installed).
3. Deterministic hashing embedding so the pipeline + vector search never break.
"""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache

import httpx

from backend.app.config import settings

_model = None


def _ollama_embed(texts: list[str]) -> list[list[float]] | None:
    """Call an Ollama embeddings endpoint (e.g. all-minilm on the AMD MI300X)."""
    if not settings.ollama_embeddings_enabled:
        return None
    url = settings.ollama_embeddings_url.rstrip("/") + "/api/embed"
    try:
        resp = httpx.post(
            url,
            json={"model": settings.ollama_embeddings_model, "input": texts},
            timeout=60,
        )
        resp.raise_for_status()
        embs = (resp.json() or {}).get("embeddings")
        if embs and len(embs) == len(texts):
            return embs
    except Exception as exc:
        print(f"[embeddings] Ollama endpoint failed ({exc}); falling back")
    return None


@lru_cache
def _load_model():
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.embedding_model)
    except Exception as exc:  # pragma: no cover - fallback path
        print(f"[embeddings] sentence-transformers unavailable, using hash fallback ({exc})")
        _model = "hash"
    return _model


def _hash_embedding(text: str, dim: int) -> list[float]:
    """Deterministic bag-of-words hashing embedding, L2-normalized."""
    vec = [0.0] * dim
    for token in text.lower().split():
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text: str) -> list[float]:
    return embed_batch([text])[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    texts = [t or " " for t in texts]
    # 0) Ollama GPU endpoint (e.g. all-minilm on the AMD MI300X) when configured.
    gpu = _ollama_embed(texts)
    if gpu is not None:
        return gpu
    # 1) local sentence-transformers, else 2) hash fallback.
    model = _load_model()
    if model == "hash":
        return [_hash_embedding(t, settings.embedding_dim) for t in texts]
    vecs = model.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
