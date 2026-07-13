"""Shared helpers for agents: text building and heuristic tagging fallback.

Heuristics let the pipeline run (and tests pass) with no LLM reachable, while
Gemma on the AMD MI300X does the richer extraction when available.
"""
from __future__ import annotations

from typing import Any

TECH_VOCAB = [
    "python", "typescript", "javascript", "react", "next.js", "fastapi", "node.js",
    "langgraph", "langchain", "claude", "anthropic", "openai", "llm", "llms",
    "embeddings", "vector", "agents", "multi-agent", "transformers", "pytorch",
    "scikit-learn", "xgboost", "tailwind", "streamlit",
    # LLM inference / GPU serving
    "vllm", "cuda", "rocm", "quantization", "gptq", "awq", "gguf", "ollama",
    "llama.cpp", "modal", "docker", "kubernetes", "tensorrt", "triton",
    "inference", "serverless", "gpu",
    # local-first / CRDT
    "rust", "wasm", "crdt", "yjs", "automerge", "sqlite", "electric", "replicache",
    # geospatial / ML
    "tensorflow", "numpy", "rasterio", "geopandas", "sentinel", "landsat",
    "satellite", "segmentation", "cnn",
]
DOMAIN_VOCAB = [
    "recruiting", "ai-agents", "developer-tools", "research-automation", "nlp",
    "ml", "frontend", "evaluation", "developer-analytics", "ai-apps", "web",
    "tabular", "ml-tooling",
    # single-word domain tokens that substring-match real text
    "inference", "serverless", "gpu", "quantization", "infrastructure",
    "optimization", "deployment", "collaboration", "offline", "geospatial",
    "climate", "satellite", "wildfire", "remote-sensing", "local-first",
]


def evidence_text(ev: dict[str, Any]) -> str:
    parts = [
        ev.get("title", ""),
        ev.get("description", ""),
        " ".join(ev.get("technologies", [])),
        " ".join(ev.get("domain_tags", [])),
        " ".join(ev.get("feature_tags", [])),
    ]
    return " ".join(p for p in parts if p).strip()


def project_text(project: dict[str, Any]) -> str:
    parts = [
        project.get("title", ""),
        project.get("description", ""),
        project.get("business_problem", ""),
        project.get("mission", ""),
        " ".join(project.get("goals", []) or []),
        " ".join(project.get("expected_features", []) or project.get("feature_tags", []) or []),
        " ".join(project.get("expected_technologies", []) or project.get("technologies", []) or []),
        " ".join(project.get("domain_tags", []) or []),
    ]
    return " ".join(p for p in parts if p).strip()


def heuristic_tags(text: str, vocab: list[str]) -> list[str]:
    low = text.lower()
    return [v for v in vocab if v in low]


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = {x.lower() for x in a}, {x.lower() for x in b}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
