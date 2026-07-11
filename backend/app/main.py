"""FastAPI application entry point (runs locally or in a container).

On startup we attempt database migrations (best-effort: the app still serves
with the in-memory fallback if the DB is down). CORS is open for the Next.js
dev frontend.
"""
from __future__ import annotations

import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router

app = FastAPI(
    title="Genuine Passion ProjectMatch AI",
    description="Find the people who were already building your future project.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def _startup() -> None:
    # Run migrations on the active backend (Cloud SQL for PostgreSQL when DATABASE_URL
    # is set). Best-effort: the app serves with the in-memory
    # fallback if the database is unreachable.
    with contextlib.suppress(Exception):
        from backend.app import store
        from backend.app.config import settings

        store.run_migrations()
        print(f"[startup] {settings.db_backend} migrations applied.")


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "projectmatch-ai", "docs": "/docs", "health": "/api/health"}
