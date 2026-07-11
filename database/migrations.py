"""Run database migrations (GCP Cloud SQL for PostgreSQL + pgvector).

Importable and runnable as a module: `python -m database.migrations`.
No-op when DATABASE_URL is unset (the store runs in-memory).
"""
from backend.app import store


def main() -> None:
    store.run_migrations()
    print("Database migrations applied (GCP Cloud SQL pgvector) if DATABASE_URL is set.")


if __name__ == "__main__":
    main()
