"""Shared agent plumbing: the `agent_step` context manager.

Every pipeline node wraps its work in `agent_step(...)`. That single context
manager handles: Langfuse trace span, progress-bus emit (running/ok/error),
latency timing, and an `agent_runs` row in the DB for the trace viewer.
Storage failures never break the pipeline (best-effort logging).
"""
from __future__ import annotations

import contextlib
import time
import uuid
from typing import Iterator

from backend.app import progress
from backend.app.llm.observability import trace

# step number per agent for the progress bar
STEP = {
    "project_understanding": 1,
    "evidence_discovery": 2,
    "github_analysis": 3,
    "hackathon_analysis": 4,
    "visual_portfolio": 5,
    "passion_detection": 6,
    "similarity": 7,
    "ranking": 8,
    "storytelling": 9,
    "executive_video": 10,
}


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


@contextlib.contextmanager
def agent_step(agent_name: str, analysis_id: str, detail: str = "") -> Iterator[dict]:
    """Yield a handle dict with `trace_handle` and `trace_id`."""
    step = STEP.get(agent_name, 0)
    progress.emit(analysis_id, agent_name, "running", step, detail)
    started = time.time()
    handle: dict = {}
    with trace(f"agent:{agent_name}", {"analysis_id": analysis_id}) as t:
        handle["trace_handle"] = t
        handle["trace_id"] = t.get("trace_id", "")
        status = "ok"
        output_summary = ""
        try:
            yield handle
            output_summary = str(handle.get("summary", ""))[:500]
        except Exception as exc:  # log + re-raise so the run records the failure
            status = "error"
            output_summary = f"ERROR: {exc}"[:500]
            _record(agent_name, analysis_id, status, detail, output_summary,
                    started, handle["trace_id"])
            progress.emit(analysis_id, agent_name, "error", step, str(exc))
            raise
    latency = int((time.time() - started) * 1000)
    _record(agent_name, analysis_id, status, detail, output_summary, started,
            handle["trace_id"])
    progress.emit(analysis_id, agent_name, "ok", step, output_summary[:120])


def _record(agent_name, analysis_id, status, detail, output_summary, started, trace_id):
    with contextlib.suppress(Exception):
        from backend.app import store

        store.save(
            "agent_runs",
            {
                "id": new_id("run_"),
                "analysis_id": analysis_id,
                "agent_name": agent_name,
                "status": status,
                "input_summary": detail[:500],
                "output_summary": output_summary,
                "latency_ms": int((time.time() - started) * 1000),
                "langfuse_trace_id": trace_id,
            },
        )
