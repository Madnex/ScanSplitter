"""Explicit network geocoding for archival metadata."""

import json
import urllib.parse
import urllib.request

from fastapi import HTTPException


def lookup_place(query: str) -> dict:
    """Explicit Nominatim lookup; never called automatically."""
    clean = query.strip()
    if not clean:
        raise HTTPException(status_code=400, detail="Place query is required")
    params = urllib.parse.urlencode({"q": clean, "format": "jsonv2", "limit": 5})
    request = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": "ScanSplitter/0.4 (local archival metadata lookup)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Place lookup failed: {exc}") from exc
    return {
        "provider": "OpenStreetMap Nominatim",
        "results": [
            {
                "name": item.get("display_name", clean),
                "latitude": float(item["lat"]),
                "longitude": float(item["lon"]),
            }
            for item in payload
        ],
    }
