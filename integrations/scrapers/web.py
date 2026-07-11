"""Generic best-effort web scraper for non-GitHub sources.

Devpost, lablab.ai, Kaggle, portfolios, blogs, and YouTube all expose useful
metadata in <title> and og/meta tags. In LIVE_MODE we fetch a source URL and
extract one evidence item from its metadata — including any **images** (og:image
plus in-page screenshots / architecture diagrams / demo stills), so the Visual
Portfolio agent can read them with Gemma vision. Any failure returns [] so the
discovery agent degrades gracefully.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (compatible; projectmatch-ai/1.0)"}

# Skip obvious non-evidence images (icons, avatars, badges, tracking pixels).
_IMG_SKIP = (
    "avatar", "icon", "favicon", "logo", "badge", "sprite", "emoji", "spinner",
    "placeholder", ".svg", "gravatar", "shields.io", "pixel", "1x1", "spacer",
)


def scrape_url(url: str, source: str) -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers=UA)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
    except Exception as exc:
        print(f"[web] live scrape failed for {url} ({exc}); falling back")
        return []

    title = _meta(soup, "og:title") or (soup.title.string if soup.title else url)
    desc = _meta(soup, "og:description") or _meta(soup, "description") or ""
    images = _extract_images(soup, url, source)
    return [
        {
            "source": source,
            "title": (title or url).strip()[:200],
            "url": url,
            "description": desc.strip()[:500],
            "technologies": [],
            "domain_tags": [],
            "feature_tags": [],
            "evidence_date": "",
            "confidence": 0.6,
            "images": images,  # [{"url", "alt"}] — screenshots/diagrams for Gemma vision
        }
    ]


def _extract_images(soup: BeautifulSoup, page_url: str, source: str) -> list[dict[str, str]]:
    """Collect real content images: the social preview + in-page screenshots.

    Devpost software pages put screenshots in the gallery (`#gallery img`, and
    `img.software_photo`); lablab and blogs use `<article> img` / `figure img`.
    We de-dup, skip icons/avatars/badges, and keep the first few."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(src: str | None, alt: str = ""):
        if not src:
            return
        src = urljoin(page_url, src.strip())
        if not src.startswith("http"):
            return
        low = src.lower()
        if any(s in low for s in _IMG_SKIP):
            return
        if src in seen:
            return
        seen.add(src)
        out.append({"url": src, "alt": (alt or "").strip()[:140]})

    # 1) social preview (usually the app's hero screenshot)
    add(_meta(soup, "og:image"))
    add(_meta(soup, "twitter:image"))

    # 2) source-specific galleries, then a generic content-image pass
    selectors = {
        "devpost": ["#gallery img", "img.software_photo", ".software-gallery img", "figure img"],
        "lablab": [".prose img", "article img", "figure img", "main img"],
        "kaggle": ["img"],
    }.get(source, ["article img", "figure img", ".prose img", "main img", "img"])
    for sel in selectors:
        for tag in soup.select(sel):
            add(tag.get("src") or tag.get("data-src") or tag.get("data-original"),
                tag.get("alt", ""))
            if len(out) >= 6:
                return out
    return out[:6]


def _meta(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return tag["content"]
    return None
