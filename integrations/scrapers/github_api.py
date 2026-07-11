"""Real GitHub evidence via the public REST API.

Used only in LIVE_MODE. Works unauthenticated (low rate limit); a GITHUB_TOKEN
raises limits. Returns evidence dicts in the same shape as the demo loader, so
the discovery agent treats live and seeded evidence identically. Any failure
returns [] so the caller can fall back to seeded data.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import httpx

from backend.app.config import settings

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

# README images worth reading with vision (architecture diagrams, screenshots,
# demos) vs. noise (badges, shields, icons).
_IMG_SKIP = ("shields.io", "badge", "badgen", "/badges/", "favicon", "icon",
             "logo", ".svg", "avatars.githubusercontent", "travis-ci", "circleci")


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "projectmatch-ai"}
    if settings.github_token:
        h["Authorization"] = f"Bearer {settings.github_token}"
    return h


def fetch_repo_readme_images(owner: str, repo: str, default_branch: str = "HEAD",
                             limit: int = 3) -> list[dict[str, str]]:
    """Extract architecture-diagram / screenshot image URLs embedded in a repo's
    README (markdown `![alt](src)` and `<img src>`), resolved to absolute URLs."""
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(f"{API}/repos/{owner}/{repo}/readme",
                           headers={**_headers(), "Accept": "application/vnd.github.raw"})
            if r.status_code != 200:
                return []
            md = r.text
    except Exception:
        return []
    base = f"{RAW}/{owner}/{repo}/{default_branch}/"
    pairs = re.findall(r"!\[([^\]]*)\]\(([^)\s]+)", md)  # ![alt](src)
    pairs += [("", m) for m in re.findall(r'<img[^>]+src=["\']([^"\']+)', md)]  # <img src>
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for alt, src in pairs:
        src = src.strip()
        if src.startswith("http"):
            url = src
        else:
            url = urljoin(base, src.lstrip("./"))
        low = url.lower()
        if any(s in low for s in _IMG_SKIP) or url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "alt": (alt or "").strip()[:140]})
        if len(out) >= limit:
            break
    return out


# Hosts we know how to route as evidence sources, found in a GitHub profile's
# blog/bio. Keep in sync with dispatch.SOURCE_HOSTS.
_PROFILE_HOSTS = (
    "devpost.com", "kaggle.com", "medium.com", "linkedin.com", "substack.com",
    "dev.to", "lablab.ai", "youtube.com", "youtu.be", "gitlab.com",
)
_URL_RE = re.compile(r"https?://[^\s)>\"']+", re.I)


# Terms too generic to identify a domain expert on their own — dropped from the
# candidate-search query so results are about the mission, not the language.
_GENERIC_TERMS = {
    "python", "gpu", "api", "ml", "ai", "typescript", "javascript", "rust", "go",
    "golang", "java", "cpp", "c", "docker", "kubernetes", "sql", "web", "app",
    "framework", "library", "tool", "agents", "inference",
}


def _search_terms(project: dict[str, Any]) -> list[str]:
    """Pick the most domain-specific keywords to search GitHub with."""
    terms: list[str] = []
    for t in (project.get("expected_technologies") or []):
        tl = (t or "").lower().strip()
        if tl and tl not in _GENERIC_TERMS and tl not in terms:
            terms.append(tl)
    if not terms:  # fall back to distinctive words in the title
        for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", project.get("title", "")):
            wl = w.lower()
            if wl not in _GENERIC_TERMS and wl not in terms:
                terms.append(wl)
    return terms[:5]


def search_candidates(project: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    """Free Discovery: find real people whose public GitHub work matches the
    mission — no recruiter-supplied list. Searches repositories by the project's
    domain keywords (highest-starred first) and returns their (individual) owners
    as candidate dicts ready for the pipeline. Empty on any failure.
    """
    terms = _search_terms(project)
    if not terms:
        return []
    # GitHub free-text search ANDs every word, so a long query returns nothing.
    # Broaden progressively (3 → 2 → 1 terms) until a query actually returns repos.
    items: list[dict[str, Any]] = []
    for k in sorted({min(3, len(terms)), min(2, len(terms)), 1}, reverse=True):
        query = " ".join(terms[:k])
        try:
            with httpx.Client(timeout=20) as client:
                r = client.get(
                    f"{API}/search/repositories",
                    params={"q": query, "sort": "stars", "order": "desc", "per_page": 60},
                    headers=_headers(),
                )
                r.raise_for_status()
                items = r.json().get("items", []) or []
        except Exception as exc:
            print(f"[github_api] candidate search failed for '{query}' ({exc})")
            items = []
        if items:
            break

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for repo in items:
        owner = repo.get("owner") or {}
        if owner.get("type") != "User":  # skip orgs — we want people
            continue
        login = owner.get("login") or ""
        key = login.lower()
        if not login or key in seen:
            continue
        seen.add(key)
        desc = (repo.get("description") or "").strip()
        name = repo.get("name") or ""
        headline = (f"{name} — {desc}" if desc else name)[:120]
        out.append({
            "id": f"gh_{key}",
            "name": login,
            "github_handle": login,
            "headline": headline,
            "sources": [f"https://github.com/{login}"],
        })
        if len(out) >= limit:
            break
    return out


def fetch_user_profile(handle: str) -> dict[str, Any]:
    """The candidate's public GitHub profile — used to auto-derive *other*
    sources (personal site, Medium, Devpost, LinkedIn…) from just the handle,
    so the recruiter never has to hunt down usernames.

    Returns {name, bio, blog, twitter, company, extra_urls}. `extra_urls` are
    real links found on the profile (the `blog` field plus any URLs the person
    put in their bio) that map to a source we can scrape. Failure → {}.
    """
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(f"{API}/users/{handle}", headers=_headers())
            r.raise_for_status()
            u = r.json()
    except Exception as exc:
        print(f"[github_api] profile fetch failed for {handle} ({exc})")
        return {}

    bio = (u.get("bio") or "")
    blog = (u.get("blog") or "").strip()
    twitter = (u.get("twitter_username") or "").strip().lstrip("@")

    found: list[str] = []
    if blog:
        found.append(blog if blog.startswith("http") else f"https://{blog}")
    found += _URL_RE.findall(bio)

    extra: list[str] = []
    seen: set[str] = set()
    for url in found:
        url = url.rstrip(".,);]")
        low = url.lower()
        # Keep links that map to a known source; skip the person's own github.
        if "github.com" in low or "github.io" in low:
            continue
        keep = any(h in low for h in _PROFILE_HOSTS) or (url == (blog if blog.startswith("http") else f"https://{blog}"))
        if keep and url not in seen:
            seen.add(url)
            extra.append(url)

    return {
        "name": u.get("name") or "",
        "bio": bio[:280],
        "blog": blog,
        "twitter": twitter,
        "company": u.get("company") or "",
        "extra_urls": extra,
    }


def fetch_user_repos(handle: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{API}/users/{handle}/repos",
                params={"sort": "pushed", "per_page": limit},
                headers=_headers(),
            )
            resp.raise_for_status()
            repos = resp.json()
    except Exception as exc:
        print(f"[github_api] live fetch failed for {handle} ({exc}); falling back")
        return []

    evidence: list[dict[str, Any]] = []
    non_fork = [r for r in repos if not r.get("fork")]
    # Read README images (diagrams/screenshots) for the top repos by stars, so the
    # Visual Portfolio agent has real visuals without hammering the API for all.
    readme_ranked = sorted(non_fork, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:3]
    readme_ids = {r.get("id") for r in readme_ranked}
    for r in non_fork:
        owner = (r.get("owner") or {}).get("login") or handle
        name = r.get("name", "")
        images = [{
            "url": f"https://opengraph.githubassets.com/1/{owner}/{name}",
            "alt": f"{name} social preview",
        }] if name else []
        if r.get("id") in readme_ids and name:
            images += fetch_repo_readme_images(owner, name, r.get("default_branch") or "HEAD")
        evidence.append(
            {
                "source": "github",
                "title": f"{name} — {r.get('description') or 'GitHub repository'}",
                "url": r.get("html_url", ""),
                "description": (r.get("description") or "")[:500],
                "technologies": [r["language"]] if r.get("language") else [],
                "domain_tags": (r.get("topics") or [])[:6],
                "feature_tags": [],
                "evidence_date": (r.get("pushed_at") or "")[:10],
                "confidence": 0.85,
                "_stars": r.get("stargazers_count", 0),
                "_forks": r.get("forks_count", 0),
                "images": images,  # social preview + README diagrams/screenshots
            }
        )
    return evidence
