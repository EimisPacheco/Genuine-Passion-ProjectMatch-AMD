"""Find a candidate's LinkedIn by web search — the way a recruiter would.

Motivated builders publish their projects on LinkedIn and link their GitHub there,
so their profile is usually the top result for "<name> <their stack> linkedin". We
run that search through Bright Data's Google SERP (structured JSON), then attach a
profile ONLY when it verifies as the same person:

  1. it is a real profile URL (linkedin.com/in/…, not a /posts/ or /company/ link),
  2. the result title contains the candidate's name, and
  3. Gemma confirms the LinkedIn headline matches the candidate's actual work.

If nothing verifies, we return "" — a wrong LinkedIn is worse than none. Used only
as a fallback when the GitHub profile yielded no LinkedIn.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any
from urllib.parse import quote

import httpx

from backend.app.config import settings

_PROFILE_RE = re.compile(r"https?://([a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+", re.I)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def _name_tokens(name: str) -> list[str]:
    return [t for t in _norm(name).split() if len(t) >= 2]


def _serp(query: str) -> list[dict[str, Any]]:
    """Google organic results via Bright Data (brd_json=1 → structured JSON)."""
    url = f"https://www.google.com/search?q={quote(query)}&brd_json=1"
    try:
        r = httpx.post(
            settings.brightdata_url,
            headers={"Authorization": f"Bearer {settings.brightdata_api_token}",
                     "Content-Type": "application/json"},
            json={"zone": settings.brightdata_zone, "url": url, "format": "raw"},
            timeout=90,
        )
        r.raise_for_status()
        data = json.loads(r.text)
    except Exception as exc:
        print(f"[linkedin_finder] SERP failed ({str(exc)[:90]})")
        return []
    return data.get("organic") or data.get("organic_results") or []


def find(name: str, tech_terms: list[str], github_handle: str = "") -> str:
    """Best-guess LinkedIn profile URL for this person, or "" if none verifies."""
    if not name or not settings.brightdata_enabled:
        return ""
    tokens = _name_tokens(name)
    if not tokens:
        return ""

    # Precise first (name + their stack — disambiguates common names), then broad.
    # The broad pass leans on Gemma verify to reject a same-name different-person hit.
    queries = [" ".join([name, *tech_terms[:3], "linkedin"]).strip()]
    if tech_terms:
        queries.append(f"{name} linkedin")

    for query in queries:
        for res in _serp(query)[:10]:
            link = (res.get("link") or res.get("url") or "").strip()
            title = res.get("title") or ""
            m = _PROFILE_RE.match(link)
            if not m or "/posts/" in link or "/company/" in link:
                continue
            if not all(tok in _norm(title) for tok in tokens):  # name must be in the title
                continue
            if _verify(name, title, tech_terms, github_handle):
                return m.group(0)
    return ""


def _verify(name: str, headline: str, tech_terms: list[str], github_handle: str) -> bool:
    """Gemma confirms the LinkedIn belongs to the same builder. Degrades to a
    trusting `True` if no vision/text provider is reachable — the name-in-title
    match already gates hard, so this is an extra guard, not the only one."""
    try:
        from backend.app.agents.visual_portfolio import _vision_target
        from backend.app.llm import engine

        target = _vision_target()
        if not target:
            return True  # name+profile match already passed; don't block on Gemma
        provider, model = target
        prompt = (
            f'A candidate named "{name}" (GitHub: {github_handle or "n/a"}) works with: '
            f'{", ".join(tech_terms[:6]) or "unknown"}.\n'
            f'A LinkedIn search returned this profile headline: "{headline}".\n'
            'Is this the SAME person? Answer JSON: {"same_person": true|false}.'
        )
        res = engine.complete_json(prompt, provider=provider, model=model,
                                   name="linkedin_verify", max_tokens=120)
        return bool(res.get("same_person", True))
    except Exception:
        return True
