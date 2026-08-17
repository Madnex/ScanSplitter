"""Experimental OpenRouter vision detector for photographic regions."""

from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .detector import DetectedRegion

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash"
NORMALIZED_SIZE = 1000.0

_PROMPT = """Find every distinct mounted or loose photograph visible in this scan.
Return the INNER PHOTOGRAPHIC IMAGE area, not the white/scalloped paper border,
album page, tape, captions, photo corners, protective plastic sleeve, glare, or
neighboring photos. Include faded and partially obscured photos under translucent
plastic. Do not return empty sleeves or album pages.

For each photograph, give its four corners in clockwise order, starting at the
visual top-left corner. Coordinates are integers from 0 to 1000 relative to the
full supplied image: x=0 is the left edge, x=1000 the right edge, y=0 the top,
and y=1000 the bottom. Inspect the entire image before answering."""

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "photo_regions",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "photos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "corners": {
                                "type": "array",
                                "minItems": 4,
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "x": {"type": "integer", "minimum": 0, "maximum": 1000},
                                        "y": {"type": "integer", "minimum": 0, "maximum": 1000},
                                    },
                                    "required": ["x", "y"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["corners"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["photos"],
            "additionalProperties": False,
        },
    },
}


class OpenRouterDetectionError(RuntimeError):
    """OpenRouter could not produce usable photo regions."""


def is_openrouter_configured() -> bool:
    """Return whether the server has an OpenRouter API key."""
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


def openrouter_model() -> str:
    """Return the configured vision model identifier."""
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _image_data_url(image: Image.Image, max_dimension: int = 2048) -> str:
    rgb = image.convert("RGB")
    if max(rgb.size) > max_dimension:
        scale = max_dimension / max(rgb.size)
        rgb = rgb.resize(
            (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))),
            Image.Resampling.LANCZOS,
        )
    buffer = io.BytesIO()
    rgb.save(buffer, format="JPEG", quality=90, subsampling=0, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _request_openrouter(
    image: Image.Image,
    api_key: str,
    model: str,
    endpoint: str,
    timeout: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_data_url(image), "detail": "high"},
                    },
                ],
            }
        ],
        "response_format": _RESPONSE_FORMAT,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/madnex/scansplitter",
            "X-Title": "ScanSplitter LLM detector",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read())
            message = body.get("error", {}).get("message")
        except (json.JSONDecodeError, AttributeError):
            message = None
        raise OpenRouterDetectionError(
            f"OpenRouter request failed ({exc.code}): {message or exc.reason}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OpenRouterDetectionError(f"OpenRouter request failed: {exc}") from exc

    if isinstance(result, dict) and isinstance(result.get("error"), dict):
        raise OpenRouterDetectionError(
            f"OpenRouter request failed: {result['error'].get('message', 'unknown error')}"
        )
    return result


def _response_content(response: dict[str, Any]) -> dict[str, Any]:
    try:
        content = response["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        decoded = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise OpenRouterDetectionError("OpenRouter returned invalid structured output") from exc
    if not isinstance(decoded, dict) or not isinstance(decoded.get("photos"), list):
        raise OpenRouterDetectionError("OpenRouter response did not contain a photo list")
    return decoded


def _regions_from_response(
    response: dict[str, Any],
    image_size: tuple[int, int],
    min_area_ratio: float,
    max_area_ratio: float,
) -> list[DetectedRegion]:
    image_width, image_height = image_size
    image_area = image_width * image_height
    regions: list[DetectedRegion] = []
    for photo in _response_content(response)["photos"]:
        try:
            corners = photo["corners"]
            if len(corners) != 4:
                continue
            points = np.asarray(
                [
                    [
                        float(point["x"]) * image_width / NORMALIZED_SIZE,
                        float(point["y"]) * image_height / NORMALIZED_SIZE,
                    ]
                    for point in corners
                ],
                dtype=np.float32,
            )
        except (KeyError, TypeError, ValueError):
            continue
        if not np.isfinite(points).all():
            continue
        points[:, 0] = np.clip(points[:, 0], 0, image_width)
        points[:, 1] = np.clip(points[:, 1], 0, image_height)
        rectangle = cv2.minAreaRect(points)
        rect_width, rect_height = rectangle[1]
        area = float(rect_width * rect_height)
        area_ratio = area / image_area
        if not min_area_ratio <= area_ratio <= max_area_ratio:
            continue
        x, y, width, height = cv2.boundingRect(cv2.boxPoints(rectangle))
        regions.append(
            DetectedRegion(
                center=(float(rectangle[0][0]), float(rectangle[0][1])),
                size=(float(rect_width), float(rect_height)),
                angle=float(rectangle[2]),
                area=area,
                area_ratio=area_ratio,
                x=max(0, x),
                y=max(0, y),
                width=min(image_width - max(0, x), width),
                height=min(image_height - max(0, y), height),
            )
        )
    regions.sort(key=lambda region: (region.y // 100, region.x))
    return regions


def detect_photos_openrouter(
    image: Image.Image,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    *,
    api_key: str | None = None,
    model: str | None = None,
    endpoint: str = OPENROUTER_ENDPOINT,
    timeout: float = 120.0,
) -> list[DetectedRegion]:
    """Ask an OpenRouter vision model for rotated photo bounding boxes."""
    resolved_key = (api_key or os.environ.get("OPENROUTER_API_KEY", "")).strip()
    if not resolved_key:
        raise OpenRouterDetectionError("OPENROUTER_API_KEY is not configured")
    response = _request_openrouter(
        image,
        resolved_key,
        model or openrouter_model(),
        endpoint,
        timeout,
    )
    return _regions_from_response(response, image.size, min_area_ratio, max_area_ratio)
