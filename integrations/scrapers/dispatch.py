"""Evidence discovery dispatch.

`discover(candidate)` returns a flat list of evidence dicts for one candidate.
- LIVE_MODE=false -> seeded demo evidence (deterministic, demo-safe).
- LIVE_MODE=true  -> query EVERY source for the candidate (not a hand-picked
  subset). Free sources (GitHub, Dev.to, Hacker News, Devpost, Kaggle) are
  derived automatically from the candidate's handle; any explicit URLs the
  candidate provides (e.g. a LinkedIn profile) are queried too. A source that
  has nothing for the candidate simply contributes nothing — no fallback.

The bot-blocked sources (LinkedIn, Medium, lablab) are unblocked via Bright Data
Web Unlocker — only hit when an explicit URL is provided, OR when
LIVE_TRY_PAID_SOURCES=true also derives Medium/lablab from the handle.
"""
from __future__ import annotations

from typing import Any

from backend.app.config import settings
from integrations.scrapers import apis, brightdata_client, demo_loader, github_api, web

SOURCE_HOSTS = {
    "github.com": "github",
    "devpost.com": "devpost",
    "lablab.ai": "lablab",
    "kaggle.com": "kaggle",
    "linkedin.com": "linkedin",
    "medium.com": "medium",
    "substack.com": "blog",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "dev.to": "devto",
    "news.ycombinator.com": "hackernews",
}

# Free sources we can derive from a handle and query for every candidate.
FREE_DERIVED = [
    "https://github.com/{h}",
    "https://dev.to/{h}",
    "https://news.ycombinator.com/user?id={h}",
    "https://devpost.com/{h}",
    "https://www.kaggle.com/{h}",
]
# Bright Data (paid) sources — only derived when explicitly enabled, to protect the budget.
PAID_DERIVED = [
    "https://medium.com/@{h}",
    "https://lablab.ai/u/@{h}",
]


def _source_of(url: str) -> str:
    for host, src in SOURCE_HOSTS.items():
        if host in url:
            return src
    return "portfolio"


def _handle(candidate: dict[str, Any], urls: list[str]) -> str:
    h = (candidate.get("github_handle") or "").strip().lstrip("@")
    if h:
        return h
    for u in urls:  # fall back to a handle embedded in an explicit github URL
        if "github.com/" in u:
            return u.rstrip("/").split("/")[-1]
    return ""


def _all_urls(candidate: dict[str, Any]) -> list[str]:
    """Explicit URLs + every derivable source URL for this candidate.

    From just the GitHub handle we (1) probe the handle-based free sources and
    (2) read the candidate's public GitHub profile and follow the *real* links
    on it (personal site, Medium, Devpost, LinkedIn…), so the recruiter doesn't
    have to supply those usernames. Bright-data-gated hosts still only run when
    Bright Data is enabled (handled downstream in discover()).
    """
    urls = [u for u in candidate.get("sources", []) if u]
    h = _handle(candidate, urls)
    if h:
        urls += [t.format(h=h) for t in FREE_DERIVED]
        if settings.live_try_paid_sources:
            urls += [t.format(h=h) for t in PAID_DERIVED]
        urls += _profile_sources(h)  # real links read off the GitHub profile
    seen: set[str] = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


def _profile_sources(handle: str) -> list[str]:
    """Extra source URLs auto-discovered from the candidate's GitHub profile
    (blog + bio links). Empty on any failure — never blocks discovery."""
    try:
        profile = github_api.fetch_user_profile(handle)
    except Exception:
        return []
    return list(profile.get("extra_urls") or [])


def discover(candidate: dict[str, Any], live_mode: bool | None = None) -> list[dict[str, Any]]:
    """Discover a candidate's evidence across all sources (live) or seeded data."""
    live = settings.live_mode if live_mode is None else live_mode
    candidate_id = candidate["id"]
    if not live:
        return demo_loader.evidence_for(candidate_id)

    collected: list[dict[str, Any]] = []
    github_done = False
    for url in _all_urls(candidate):
        source = _source_of(url)
        if source == "github":
            if github_done:  # one GitHub fetch per candidate covers all their repos
                continue
            github_done = True
            handle = candidate.get("github_handle") or url.rstrip("/").split("/")[-1]
            items = github_api.fetch_user_repos(handle)
        elif source == "devto":
            items = apis.fetch_devto(url)  # free Dev.to API
        elif source == "hackernews":
            items = apis.fetch_hackernews(url)  # free HN Algolia API
        elif source in ("linkedin", "medium", "lablab") and settings.brightdata_enabled:
            # Bot-blocked sources unblocked via Bright Data Web Unlocker.
            items = brightdata_client.scrape(url, source)
        else:
            items = web.scrape_url(url, source)  # devpost / kaggle / blog / portfolio
        if items:  # empty source contributes nothing — no fallback
            collected.extend(items)
    return collected
