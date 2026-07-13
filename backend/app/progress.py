"""In-memory progress bus for live analysis updates (SSE).

The pipeline runs in a background task and emits step events; the SSE endpoint
subscribes per analysis_id. Bounded history lets a late subscriber catch up.
This is intentionally simple (single-process) — adequate for the MVP/demo.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

TOTAL_STEPS = 10  # agents 1..10 drive the progress bar

_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
_subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
_status: dict[str, str] = {}


def emit(analysis_id: str, agent: str, status: str, step: int, detail: str = "") -> None:
    # Percent tracks *completed* steps, not the one in flight. A step that is only
    # "running" (e.g. the 10th agent rendering the video, which takes minutes) counts
    # as step-1 done — so the bar never reads 100% while work is still happening. It
    # reaches 100% only on an "ok"/"done" for the final step.
    completed = step if status in ("ok", "done") else max(step - 1, 0)
    event = {
        "analysis_id": analysis_id,
        "agent": agent,
        "status": status,            # running | ok | error | done
        "step": step,
        "total": TOTAL_STEPS,
        "percent": round(min(completed, TOTAL_STEPS) / TOTAL_STEPS * 100),
        "detail": detail,
        "ts": time.time(),
    }
    _history[analysis_id].append(event)
    if status in ("done", "error") and step >= TOTAL_STEPS:
        _status[analysis_id] = status
    for q in list(_subscribers.get(analysis_id, [])):
        with_nowait(q, event)


def with_nowait(q: asyncio.Queue, event: dict) -> None:
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:  # pragma: no cover
        pass


def history(analysis_id: str) -> list[dict[str, Any]]:
    return list(_history.get(analysis_id, []))


def status(analysis_id: str) -> str:
    return _status.get(analysis_id, "running" if analysis_id in _history else "unknown")


async def subscribe(analysis_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    # replay history so late subscribers see prior steps
    for event in history(analysis_id):
        with_nowait(q, event)
    _subscribers[analysis_id].append(q)
    return q


def unsubscribe(analysis_id: str, q: asyncio.Queue) -> None:
    if q in _subscribers.get(analysis_id, []):
        _subscribers[analysis_id].remove(q)
