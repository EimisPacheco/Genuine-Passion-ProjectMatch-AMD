"""Live Gemma-on-AMD vs GPU-baseline speed race.

Runs the SAME Gemma match/passion task over the SAME candidate pool on two
providers at the same instant — Gemma on the AMD MI300X on the left, and the GPU
baseline on the right (`RACE_BASELINE=gemini`: the SAME Gemma served by Google's
GPU) — and streams per-side
metrics (tokens, tokens/sec, elapsed, per-candidate cards) over SSE. Candidates
run sequentially per side so the latency gap compounds visibly with each card:
it is a swarm of inferences, not a single call.

Honesty: nothing is simulated. A side whose provider key is missing emits an
`error` event and the other side still races. tokens/sec during streaming is an
estimate (chars/4 over wall-clock); the authoritative per-card number comes from
the provider's reported output tokens.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator

from backend.app.config import settings
from backend.app.llm.providers import get_provider
from integrations.scrapers import demo_loader

RACE_SYSTEM = (
    "You are a passion-match analyst. Given a company project and a candidate's "
    "public work, judge in 2-3 sentences whether the candidate is genuinely "
    "passionate about this project's domain, then give a match score 0-100. "
    "Reference the candidate's actual projects. Be concise."
)

_EMIT_INTERVAL_S = 0.12  # throttle live progress events


def _baseline() -> tuple[str, str, str, bool]:
    """(provider, label, model, available) for the GPU baseline side."""
    pref = (settings.race_baseline or "auto").lower()
    if pref == "auto":
        provider = "gemini"
    else:
        provider = pref
    if provider == "amd":
        return ("amd", "Gemma on AMD · Ollama", settings.amd_llm_model, settings.amd_llm_enabled)
    if provider == "gemini":
        label = "Gemma 4 31B · Google" if "gemma" in settings.gemini_model.lower() else "Gemini (GPU baseline)"
        return ("gemini", label, settings.gemini_model, settings.gemini_enabled)
    return (provider, provider, "", False)


def _primary() -> tuple[str, str, str, bool]:
    """(provider, label, model, available) for the primary side — follows the
    active provider so the race reflects however the app is actually configured."""
    p = settings.active_provider
    if p == "amd":
        return ("amd", "Gemma on AMD · MI300X", settings.amd_llm_model, settings.amd_llm_enabled)
    if p == "gemini":
        return ("gemini", "Gemma · Google", settings.gemini_model, settings.gemini_enabled)
    return (p, p, "", False)


def _sides() -> list[dict[str, Any]]:
    pp, plabel, pmodel, pavail = _primary()
    bp, blabel, bmodel, bavail = _baseline()
    return [
        {"id": "primary", "provider": pp, "label": plabel, "model": pmodel, "available": pavail},
        {"id": "baseline", "provider": bp, "label": blabel, "model": bmodel, "available": bavail},
    ]


def race_info(
    project: dict[str, Any] | None = None, pool: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    if project is None:
        project = demo_loader.load_company_project()
    if pool is None:
        pool = [_brief(c) for c in demo_loader.list_candidates()]
    return {
        "project": {"title": project.get("title"), "description": project.get("description", "")[:240]},
        "total_cards": len(pool),
        "candidates": [{"name": b["name"], "headline": b["headline"]} for b in pool],
        "sides": _sides(),
    }


def build_from_analysis(analysis_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Project + candidate briefs for a specific analysis (so the race runs on
    the same project/candidates the user is investigating, not the demo pool)."""
    from backend.app import analyses

    rec = analyses.get(analysis_id) or {}
    project = rec.get("company_project") or demo_loader.load_company_project()
    sources = rec.get("candidate_sources") or demo_loader.list_candidates()
    evidence = (rec.get("result") or {}).get("evidence") or {}
    pool = [_brief(c, evidence.get(c.get("id", ""))) for c in sources]
    return project, pool


def _brief(c: dict[str, Any], items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cid = c.get("id", "")
    if items is None:
        items = demo_loader.evidence_for(cid)
    if not items:  # custom candidate with no discovered evidence yet
        items = demo_loader.evidence_for(cid)
    titles = [e.get("title", "") for e in (items or [])[:4]]
    return {
        "id": cid,
        "name": c.get("name", cid),
        "headline": c.get("headline", ""),
        "evidence": [t for t in titles if t],
    }


def _prompt(project: dict[str, Any], brief: dict[str, Any]) -> str:
    ev = "\n".join(f"- {t}" for t in brief["evidence"]) or "- (no public projects found)"
    return (
        f"Company project: {project.get('title')}\n"
        f"{project.get('description', '')[:400]}\n\n"
        f"Candidate: {brief['name']} — {brief['headline']}\n"
        f"Public work:\n{ev}\n\n"
        f"Verdict and match score:"
    )


def _short(text: str, limit: int = 220) -> str:
    text = " ".join((text or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj)}\n\n"


async def stream_race(
    max_tokens: int = 160,
    project: dict[str, Any] | None = None,
    pool: list[dict[str, Any]] | None = None,
) -> AsyncGenerator[str, None]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    if project is None:
        project = demo_loader.load_company_project()
    if pool is None:
        pool = [_brief(c) for c in demo_loader.list_candidates()]
    sides = _sides()

    yield _sse({"event": "init", "project": project.get("title"),
                "total_cards": len(pool), "sides": sides})

    tasks = [
        asyncio.create_task(
            _run_side(loop, queue, s, project, pool, max_tokens)
        )
        for s in sides
    ]

    finished = 0
    while finished < len(tasks):
        ev = await queue.get()
        if ev.get("event") in ("done", "error"):
            finished += 1
        yield _sse(ev)

    yield _sse({"event": "all_done"})
    for t in tasks:
        t.cancel()


async def _run_side(loop, queue, side_meta, project, pool, max_tokens) -> None:
    side = side_meta["id"]
    provider = side_meta["provider"]
    model = side_meta["model"]

    def push(ev: dict[str, Any]) -> None:
        ev.update({"side": side, "provider": provider, "model": model})
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    if not side_meta["available"]:
        push({"event": "error", "reason": "provider_not_configured",
              "note": f"Set {provider.upper()}_API_KEY to race this side."})
        return

    try:
        prov = get_provider(provider)
    except Exception as exc:  # pragma: no cover - defensive
        push({"event": "error", "reason": str(exc)[:200]})
        return

    started = time.time()
    cum_tokens = 0
    cards_done = 0
    push({"event": "start", "elapsed_ms": 0})

    try:
        for i, brief in enumerate(pool):
            prompt = _prompt(project, brief)
            live = {"chars": 0, "last": 0.0}

            def on_token(piece: str) -> None:
                live["chars"] += len(piece)
                now = time.time()
                if now - live["last"] < _EMIT_INTERVAL_S:
                    return
                live["last"] = now
                elapsed = now - started
                est = cum_tokens + live["chars"] // 4
                push({"event": "progress", "candidate": brief["name"], "card_index": i,
                      "tokens": est, "elapsed_ms": round(elapsed * 1000),
                      "tokens_per_sec": round(est / elapsed, 1) if elapsed > 0 else 0.0})

            result = await loop.run_in_executor(
                None,
                lambda p=prompt, oc=on_token: prov.complete(
                    p, system=RACE_SYSTEM, model=model, max_tokens=max_tokens,
                    stream=True, on_token=oc,
                ),
            )
            cum_tokens += result.output_tokens or (live["chars"] // 4)
            cards_done += 1
            elapsed = time.time() - started
            push({"event": "card", "candidate": brief["name"], "card_index": i,
                  "cards_done": cards_done, "verdict": _short(result.text),
                  "tokens": cum_tokens, "card_tokens_per_sec": round(result.tokens_per_sec, 1),
                  "elapsed_ms": round(elapsed * 1000),
                  "tokens_per_sec": round(cum_tokens / elapsed, 1) if elapsed > 0 else 0.0})

        total = time.time() - started
        push({"event": "done", "cards_done": cards_done, "tokens": cum_tokens,
              "total_ms": round(total * 1000),
              "tokens_per_sec": round(cum_tokens / total, 1) if total > 0 else 0.0})
    except Exception as exc:
        push({"event": "error", "reason": str(exc)[:200]})
