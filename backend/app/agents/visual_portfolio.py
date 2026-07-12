"""Agent 5 — Visual Portfolio (Gemma 4 31B multimodal).

Feeds a candidate's real portfolio images — architecture diagrams, app
screenshots, demo stills — to Gemma's vision capability on the AMD MI300X and
extracts what the work *visually* demonstrates: system design, polish/effort,
and domain cues. This is the multimodal pillar: side projects reveal what people
can't stop building, and a lot of that signal lives in pictures, not prose.

Anti-hallucination: every caption cites the real `source_url` of the image. With
no vision-capable provider configured the agent degrades to a deterministic
caption so the pipeline and UI still render (offline-safe).
"""
from __future__ import annotations

import base64
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from backend.app.agents.base import agent_step
from backend.app.config import settings
from backend.app.graph.state import ProjectMatchState
from backend.app.llm import engine
from integrations.scrapers import demo_loader

SYSTEM = (
    "You are a senior engineer reviewing a developer's portfolio image. Judge "
    "what it demonstrates about their work — system design, build quality, and "
    "the problem domain. Be specific and grounded in what is actually visible."
)

PROMPT = (
    "Look at this portfolio image and return JSON with keys: "
    "caption (one specific sentence describing what the image shows), "
    "signals (array of 2-5 short lowercase-hyphenated tags, e.g. "
    "'multi-agent-architecture', 'polished-ui', 'evaluation-rigor'), "
    "polish (float 0-1 estimating engineering effort/polish visible), "
    "domain (2-4 word domain guess), "
    "has_people (true ONLY if the image is primarily a photograph of one or more "
    "real people — a team photo, group photo, or portrait; false for diagrams, "
    "screenshots, UIs, charts, code, logos, or repository preview cards)."
)


def run(state: ProjectMatchState) -> dict[str, Any]:
    analysis_id = state["analysis_id"]
    evidence = state.get("evidence", {})
    live_mode = state.get("live_mode")
    out: dict[str, list[dict[str, Any]]] = {}

    with agent_step("visual_portfolio", analysis_id) as h:
        total = 0
        for cid in evidence.keys():
            images = _collect_images(cid, evidence.get(cid, []), live_mode)
            # Vision calls are independent HTTP requests — run them concurrently
            # instead of one-at-a-time (this agent dominates the run's wall-clock).
            if len(images) > 1 and settings.visual_concurrency > 1:
                with ThreadPoolExecutor(max_workers=settings.visual_concurrency) as pool:
                    analyses = list(pool.map(
                        lambda im: _analyze_image(cid, im, h["trace_handle"]), images))
            else:
                analyses = [_analyze_image(cid, im, h["trace_handle"]) for im in images]
            # Drop photos of people (team/group shots) — but never blank the whole
            # portfolio: if that would remove everything, keep what we have.
            kept = [a for a in analyses if not a.get("has_people")]
            out[cid] = kept if kept else analyses
            total += len(out[cid])
        target = _vision_target()
        how = f"via {target[0]}" if target else "heuristically (no vision provider)"
        h["summary"] = f"analyzed {total} portfolio images {how}"
    return {"visual_analyses": out}


def _vision_target() -> tuple[str, str] | None:
    """(provider, model) for the vision call — follow the active provider, then
    fall back to any vision-capable Gemma provider that has a key."""
    candidates = {
        "amd": (settings.amd_llm_enabled, settings.amd_llm_vision_model),
        "gemini": (settings.gemini_enabled, settings.gemini_vision_model),
    }
    active = settings.active_provider
    if active in candidates and candidates[active][0]:
        return (active, candidates[active][1])
    for name, (ok, model) in candidates.items():  # amd → gemini
        if ok:
            return (name, model)
    return None


def _collect_images(cid: str, items: list[dict], live_mode: bool | None) -> list[dict[str, Any]]:
    """Gather portfolio visuals from discovered sources — GitHub README diagrams +
    social previews, Devpost/lablab screenshots, Dev.to covers. To avoid the same
    repo showing several near-identical cards, we keep only ONE image per repo,
    preferring a real README image over the generic GitHub social-preview card."""
    imgs = list(demo_loader.portfolio_images_for(cid))
    if live_mode:
        by_repo: dict[str, list[dict[str, Any]]] = {}
        for e in items:
            ev_title = e.get("title", "")
            ev_url = e.get("url", "")
            src = e.get("source", "")
            for im in (e.get("images") or []):
                u = im.get("url")
                if not u:
                    continue
                by_repo.setdefault(ev_url or u, []).append({
                    "title": (im.get("alt") or ev_title)[:140],
                    "source_url": ev_url or u,
                    "url": u,
                    "file": "",
                    "path": "",
                    "source": src,
                })
        for group in by_repo.values():
            # Sort generic social-preview cards last, keep one real image per repo.
            group.sort(key=lambda im: "opengraph.githubassets" in (im.get("url") or ""))
            imgs.append(group[0])
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for im in imgs:
        key = im.get("url") or im.get("source_url") or im.get("path")
        if key and key not in seen:
            seen.add(key)
            uniq.append(im)
    return uniq[:settings.visual_max_images]  # each image = one Gemma vision call


def _analyze_image(cid: str, im: dict[str, Any], trace_handle) -> dict[str, Any]:
    base = {
        "candidate_id": cid,
        "image_title": im.get("title", ""),
        "source": im.get("source", "portfolio"),
        "source_url": im.get("source_url") or im.get("url", ""),
        "thumb_url": _thumb_url(cid, im),
    }
    target = _vision_target()
    # Ollama (AMD) needs base64 image data, not a URL — download + encode live
    # images; local demo assets are already read from disk. Falls back to the raw
    # URL (for URL-accepting providers) and then to a heuristic caption.
    if im.get("path"):
        img_ref = _data_uri(im["path"])
    elif im.get("url"):
        img_ref = _url_to_data_uri(im["url"]) or im["url"]
    else:
        img_ref = ""
    if not target or not img_ref:
        base.update(_heuristic(im))
        return base

    provider, model = target
    try:
        res = engine.complete_json(
            PROMPT,
            system=SYSTEM,
            images=[img_ref],
            provider=provider,
            model=model,
            trace_handle=trace_handle,
            name="visual_portfolio",
            max_tokens=400,
        )
        base.update({
            "caption": str(res.get("caption", ""))[:300],
            "signals": [str(s)[:40] for s in (res.get("signals") or [])][:6],
            "polish": _clip(float(res.get("polish", 0.6))),
            "domain": str(res.get("domain", ""))[:60],
            "has_people": bool(res.get("has_people", False)),
            "provider": provider,
            "model": model,
        })
    except Exception:
        base.update(_heuristic(im))
    return base


def _thumb_url(cid: str, im: dict[str, Any]) -> str:
    if im.get("file"):
        return f"/api/assets/portfolio/{cid}/{Path(im['file']).name}"
    return im.get("url", "")


def _data_uri(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _url_to_data_uri(url: str) -> str:
    """Download an image URL and return a base64 data URI (Ollama/Gemma vision
    requires inline image data, not URLs). Skips oversized/non-image responses."""
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True,
                      headers={"User-Agent": "projectmatch-ai/1.0"})
        r.raise_for_status()
        if len(r.content) > 6_000_000:  # ~6 MB cap
            return ""
        ct = (r.headers.get("content-type") or "").split(";")[0].strip()
        if not ct.startswith("image/"):
            ct = mimetypes.guess_type(url)[0] or "image/png"
        return f"data:{ct};base64," + base64.b64encode(r.content).decode("ascii")
    except Exception:
        return ""


_PEOPLE_HINTS = ("team", "group photo", "group picture", "selfie",
                 "portrait", "our team", "headshot")


def _heuristic(im: dict[str, Any]) -> dict[str, Any]:
    title = im.get("title", "portfolio image")
    low = title.lower()
    is_arch = any(k in low for k in ("architecture", "diagram", "pipeline"))
    return {
        "caption": (
            f"{title}: a {'system architecture diagram' if is_arch else 'product screenshot'} "
            "from the candidate's public work."
        ),
        "signals": (
            ["architecture-diagram", "documented", "self-initiated"]
            if is_arch else ["polished-ui", "shipped-product", "self-initiated"]
        ),
        "polish": 0.7 if is_arch else 0.65,
        "domain": "",
        # Heuristic can only catch obvious people-photo titles; real Gemma vision
        # classifies the rest.
        "has_people": any(k in low for k in _PEOPLE_HINTS),
        "provider": "heuristic",
        "model": "none",
    }


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))
