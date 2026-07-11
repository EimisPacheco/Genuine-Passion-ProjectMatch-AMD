"""Clean public-API sources (no scraping / no unblock layer needed).

Dev.to and Hacker News expose free JSON APIs, so we fetch directly instead of
scraping HTML. Both reveal *voluntary building/sharing* behavior — exactly the
genuine-passion signal this product is built on. Any failure returns [] so
discovery falls back to seeded evidence.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx


def fetch_devto(url: str) -> list[dict[str, Any]]:
    """Articles for a dev.to user → evidence items (voluntary technical writing)."""
    user = _devto_user(url)
    if not user:
        return []
    try:
        resp = httpx.get(
            "https://dev.to/api/articles",
            params={"username": user, "per_page": 5},
            timeout=20,
        )
        resp.raise_for_status()
        articles = resp.json()
    except Exception as exc:
        print(f"[devto] fetch failed for {url} ({exc})")
        return []

    out: list[dict[str, Any]] = []
    for a in (articles or [])[:5]:
        cover = a.get("cover_image") or a.get("social_image")
        images = [{"url": cover, "alt": a.get("title", "")[:140]}] if cover else []
        out.append(
            {
                "source": "devto",
                "title": (a.get("title") or "Dev.to article")[:200],
                "url": a.get("url") or url,
                "description": (a.get("description") or "")[:500],
                "technologies": [],
                "domain_tags": [str(t) for t in (a.get("tag_list") or [])][:6],
                "feature_tags": ["writing", "voluntary-effort", "thought-leadership"],
                "evidence_date": str(a.get("published_at") or "")[:10],
                "confidence": 0.72,
                "images": images,
            }
        )
    return out


def fetch_hackernews(url: str) -> list[dict[str, Any]]:
    """A user's HN stories (esp. Show HN) → evidence items (shipping signal)."""
    user = _hn_user(url)
    if not user:
        return []
    try:
        resp = httpx.get(
            "https://hn.algolia.com/api/v1/search",
            params={"tags": f"story,author_{user}", "hitsPerPage": 5},
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
    except Exception as exc:
        print(f"[hackernews] fetch failed for {url} ({exc})")
        return []

    out: list[dict[str, Any]] = []
    for h in hits[:5]:
        oid = h.get("objectID")
        hn_url = h.get("url") or f"https://news.ycombinator.com/item?id={oid}"
        out.append(
            {
                "source": "hackernews",
                "title": (h.get("title") or "Hacker News submission")[:200],
                "url": hn_url,
                "description": f"{h.get('points', 0)} points · {h.get('num_comments', 0)} comments on Hacker News",
                "technologies": [],
                "domain_tags": [],
                "feature_tags": ["shipping", "community", "voluntary-effort"],
                "evidence_date": str(h.get("created_at") or "")[:10],
                "confidence": 0.7,
            }
        )
    return out


def _devto_user(url: str) -> str:
    # https://dev.to/{username} or https://dev.to/{username}/{slug}
    path = urlparse(url).path.strip("/")
    return path.split("/")[0] if path else ""


def _hn_user(url: str) -> str:
    # https://news.ycombinator.com/user?id={username}
    q = parse_qs(urlparse(url).query)
    if "id" in q:
        return q["id"][0]
    path = urlparse(url).path.strip("/")
    return path.split("/")[-1] if path else ""
