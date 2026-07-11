"""Google Cloud SQL for PostgreSQL (+ pgvector) client.

The store's PostgreSQL backend for the H0 "Hack the Zero Stack"
hackathon (AWS Database requirement). Same surface the `store` facade needs:
`available / run_migrations / insert_row / insert_rows / vector_search /
agent_runs`. Vector search uses **pgvector** (`<=>` cosine distance) so the
candidate-matching similarity runs inside Cloud SQL.

Activated when `DATABASE_URL` (the Cloud SQL endpoint) is set — see config.db_backend.
Cloud SQL is Postgres-wire-compatible, so this also works against any
plain Postgres for local testing.
"""
from __future__ import annotations

from typing import Any, Iterable

from backend.app.config import settings

_conn = None


def _connection():
    global _conn
    if _conn is None or getattr(_conn, "closed", True):
        import psycopg

        _conn = psycopg.connect(settings.database_url, autocommit=True)
    return _conn


def available() -> bool:
    try:
        with _connection().cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception as exc:  # pragma: no cover - network/credential errors
        print(f"[postgres] unavailable ({exc})")
        return False


# --- schema (Postgres + pgvector) ---
_TABLES: dict[str, str] = {
    "company_projects": "id text, title text, description text, business_problem text, target_users text, mission text, goals text[], domain_tags text[], feature_tags text[], technologies text[], complexity text, innovation_indicators text[], success_criteria text, desired_candidates int, created_at timestamptz default now()",
    "candidate_profiles": "id text, name text, headline text, sources text[], github_handle text, location text, created_at timestamptz default now()",
    "candidate_projects": "id text, candidate_id text, source text, title text, url text, description text, technologies text[], domain_tags text[], feature_tags text[], mission text, created_at timestamptz default now()",
    "github_projects": "id text, candidate_id text, repo_full_name text, url text, description text, languages text[], dependencies text[], stars bigint, forks bigint, quality_score real, architecture_profile text, feature_profile text[], maturity text, last_activity text, created_at timestamptz default now()",
    "hackathon_projects": "id text, candidate_id text, platform text, title text, url text, problem_solved text, features text[], technologies text[], innovation text, execution_quality real, domain_tags text[], awards text[], created_at timestamptz default now()",
    "candidate_evidence": "id text, candidate_id text, source text, title text, url text, description text, technologies text[], domain_tags text[], feature_tags text[], evidence_date text, confidence real, created_at timestamptz default now()",
    "candidate_scores": "id text, analysis_id text, candidate_id text, overall_score real, project_similarity real, feature_similarity real, domain_similarity real, technology_similarity real, mission_similarity real, genuine_passion real, domain_passion real, technology_passion real, builder_consistency real, innovation real, voluntary_effort real, evidence_quality real, confidence real, rank int, recommendation text, explanation text, evidence_ids text[], created_at timestamptz default now()",
    "agent_runs": "id text, analysis_id text, agent_name text, status text, input_summary text, output_summary text, latency_ms bigint, langfuse_trace_id text, created_at timestamptz default now()",
    "video_reports": "id text, analysis_id text, title text, mp4_path text, srt_path text, narration_script text, duration_seconds real, candidate_ids text[], created_at timestamptz default now()",
}


def run_migrations() -> None:
    dim = settings.embedding_dim
    with _connection().cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        for name, cols in _TABLES.items():
            cur.execute(f"CREATE TABLE IF NOT EXISTS {name} ({cols})")
        # embeddings table uses the pgvector type for similarity search
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS project_embeddings ("
            f"id text, owner_type text, owner_id text, candidate_id text, "
            f"text text, embedding vector({dim}), created_at timestamptz default now())"
        )
    print("[postgres] migrations applied (pgvector enabled).")


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in v) + "]"


def insert_row(table: str, row: dict[str, Any]) -> None:
    insert_rows(table, [row])


def insert_rows(table: str, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ", ".join("%s::vector" if c == "embedding" else "%s" for c in cols)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    with _connection().cursor() as cur:
        for r in rows:
            vals = [
                _vec_literal(r[c]) if c == "embedding" and isinstance(r.get(c), list) else r.get(c)
                for c in cols
            ]
            cur.execute(sql, vals)


def vector_search(
    query_embedding: list[float],
    owner_type: str = "candidate_project",
    candidate_id: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Nearest project_embeddings rows by pgvector cosine similarity (1 - distance)."""
    from psycopg.rows import dict_row

    vec = _vec_literal(query_embedding)
    where = ["owner_type = %s"]
    args: list[Any] = [vec, owner_type]
    if candidate_id:
        where.append("candidate_id = %s")
        args.append(candidate_id)
    args += [vec, limit]
    sql = (
        f"SELECT owner_id, candidate_id, text, "
        f"1 - (embedding <=> %s::vector) AS sim "
        f"FROM project_embeddings WHERE {' AND '.join(where)} "
        f"ORDER BY embedding <=> %s::vector LIMIT %s"
    )
    with _connection().cursor(row_factory=dict_row) as cur:
        cur.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]


def agent_runs(analysis_id: str) -> list[dict[str, Any]]:
    from psycopg.rows import dict_row

    sql = (
        "SELECT agent_name, status, input_summary, output_summary, latency_ms, "
        "langfuse_trace_id, created_at FROM agent_runs WHERE analysis_id = %s "
        "ORDER BY created_at"
    )
    with _connection().cursor(row_factory=dict_row) as cur:
        cur.execute(sql, [analysis_id])
        return [dict(r) for r in cur.fetchall()]
