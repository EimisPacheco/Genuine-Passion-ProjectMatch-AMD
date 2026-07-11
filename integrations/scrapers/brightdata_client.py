"""Bright Data Web Unlocker — unblock layer for bot-protected sources.

LinkedIn, Medium, and lablab.ai block plain scraping (403 / auth wall / Cloudflare).
Bright Data's Web Unlocker returns the rendered HTML past those blocks via a single
API. We extract evidence (title + description) from the page's metadata, mirroring
the generic scraper. Any failure returns [] so discovery falls back gracefully.

POST https://api.brightdata.com/request
  Authorization: Bearer <BRIGHTDATA_API_TOKEN>
  { "zone": "<zone>", "url": "<target>", "format": "raw" }   -> rendered HTML
"""
from __future__ import annotations

from typing import Any

import httpx
from bs4 import BeautifulSoup

from backend.app.config import settings


def unlock(url: str, timeout: int = 60) -> str:
    """Fetch a URL's rendered HTML through Bright Data Web Unlocker."""
    if not settings.brightdata_enabled:
        return ""
    try:
        resp = httpx.post(
            settings.brightdata_url,
            headers={"Authorization": f"Bearer {settings.brightdata_api_token}"},
            json={"zone": settings.brightdata_zone, "url": url, "format": "raw"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        print(f"[brightdata] unlock failed for {url} ({exc})")
        return ""


def _meta(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
    return tag["content"] if tag and tag.get("content") else None


def scrape(url: str, source: str) -> list[dict[str, Any]]:
    """Return one evidence item for a bot-blocked page via Bright Data."""
    html = unlock(url)
    if not html or "just a moment" in html.lower():
        return []
    soup = BeautifulSoup(html, "lxml")
    title = _meta(soup, "og:title") or (soup.title.string if soup.title else url)
    desc = _meta(soup, "og:description") or _meta(soup, "description") or ""
    feature = {
        "linkedin": ["professional-experience", "voluntary-effort"],
        "medium": ["writing", "thought-leadership", "voluntary-effort"],
        "lablab": ["hackathon", "demo"],
    }.get(source, [])
    return [
        {
            "source": source,
            "title": (title or url).strip()[:200],
            "url": url,
            "description": desc.strip()[:500],
            "technologies": [],
            "domain_tags": [],
            "feature_tags": feature,
            "evidence_date": "",
            "confidence": 0.7,
        }
    ]
