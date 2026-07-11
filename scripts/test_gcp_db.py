"""Validate the GCP Cloud SQL for PostgreSQL + pgvector adapter end-to-end.

Run after setting DATABASE_URL to your Cloud SQL endpoint:
    pip install -r requirements.txt
    export DATABASE_URL="postgresql://postgres:PW@CLOUD_SQL_IP:5432/projectmatch"
    python scripts/test_gcp_db.py

Exercises: connect -> migrate (pgvector + tables) -> insert evidence/scores/embeddings
-> pgvector similarity search -> agent_runs read. Prints PASS/FAIL per step.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from backend.app.config import settings  # noqa: E402

if not settings.database_url:
    print("DATABASE_URL not set — point it at your Cloud SQL endpoint."); sys.exit(1)

from database import postgres_client as pg  # noqa: E402


def ok(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    return cond


print(f"db_backend = {settings.db_backend}  ({settings.database_url.split('@')[-1]})")
all_ok = True

all_ok &= ok("connect", pg.available())
pg.run_migrations()
all_ok &= ok("migrations (pgvector + tables)", True)

dim = settings.embedding_dim
pg.insert_rows("candidate_evidence", [{
    "id": "ev_test1", "candidate_id": "cand_test", "source": "github",
    "title": "test repo", "url": "https://github.com/x/y", "description": "d",
    "technologies": ["Python"], "domain_tags": ["ai"], "feature_tags": ["x"],
    "evidence_date": "2025-01-01", "confidence": 0.9,
}])
all_ok &= ok("insert candidate_evidence (text[] arrays)", True)

vec = [0.1] * dim
pg.insert_rows("project_embeddings", [{
    "id": "emb_test1", "owner_type": "candidate_project", "owner_id": "ev_test1",
    "candidate_id": "cand_test", "text": "test", "embedding": vec,
}])
all_ok &= ok("insert embedding (vector type)", True)

rows = pg.vector_search(vec, owner_type="candidate_project", candidate_id="cand_test", limit=5)
all_ok &= ok(f"pgvector search returned {len(rows)} row(s), sim={rows[0]['sim']:.3f}" if rows else "pgvector search", bool(rows))

pg.insert_rows("agent_runs", [{
    "id": "run_test1", "analysis_id": "an_test", "agent_name": "ranking",
    "status": "ok", "input_summary": "i", "output_summary": "o",
    "latency_ms": 12, "langfuse_trace_id": "",
}])
runs = pg.agent_runs("an_test")
all_ok &= ok(f"agent_runs read {len(runs)} row(s)", bool(runs))

print("\n" + ("ALL PASS ✅ — Cloud SQL + pgvector wired correctly." if all_ok else "SOME FAILURES ❌"))
sys.exit(0 if all_ok else 1)
