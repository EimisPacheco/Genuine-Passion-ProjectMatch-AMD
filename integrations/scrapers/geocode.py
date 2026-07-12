"""Turn a free-text location ("San Francisco, CA") into structured
city / state / country via the Google Geocoding API.

Uses the same GOOGLE_MAPS_API_KEY as the Map view. Returns {} when no key is set
or the lookup fails, so callers degrade gracefully. Cached per location string.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import httpx

from backend.app.config import settings


@lru_cache(maxsize=512)
def parts(location: str) -> dict[str, str]:
    """{city, state, country} for a location string. Empty on failure."""
    key = settings.google_maps_api_key
    loc = (location or "").strip()
    if not loc or not key:
        return {}
    try:
        r = httpx.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": loc, "key": key}, timeout=15,
        )
        results = r.json().get("results", [])
    except Exception:
        return {}
    if not results:
        return {}
    comps = results[0].get("address_components", [])
    out: dict[str, str] = {}
    for c in comps:
        types = c.get("types", [])
        if "country" in types:
            out["country"] = c.get("long_name", "")
        elif "administrative_area_level_1" in types:
            out["state"] = c.get("long_name", "")
        elif "locality" in types:
            out["city"] = c.get("long_name", "")
    if not out.get("city"):  # some places expose the city as postal_town / level_2
        for c in comps:
            types = c.get("types", [])
            if "postal_town" in types or "administrative_area_level_2" in types:
                out["city"] = c.get("long_name", "")
                break
    return out
