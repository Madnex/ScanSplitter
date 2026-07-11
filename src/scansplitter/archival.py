"""Optional archival helpers: local OCR and explicit network geocoding."""

import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import HTTPException


def transcribe_image(path: Path, language: str = "eng") -> str:
    """Run local Tesseract OCR without uploading image data anywhere."""
    if not re.fullmatch(r"[A-Za-z0-9_+.-]{2,40}", language):
        raise HTTPException(status_code=400, detail="Invalid OCR language")
    executable = shutil.which("tesseract")
    if not executable:
        raise HTTPException(
            status_code=503,
            detail="Local OCR requires Tesseract. Install tesseract and retry.",
        )
    result = subprocess.run(
        [executable, str(path), "stdout", "-l", language, "--psm", "6"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=422, detail=result.stderr.strip() or "OCR failed")
    return "\n".join(line.strip() for line in result.stdout.splitlines() if line.strip())[:10_000]


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
