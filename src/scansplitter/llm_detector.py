"""Experimental OpenRouter vision detector for photographic regions."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .detector import DetectedRegion

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.7-flash"
NORMALIZED_SIZE = 1000.0
DEFAULT_MAX_RETRIES = 2
_CACHE_VERSION = 1
_CACHE_LOCKS: dict[str, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()

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


class OpenRouterConfigurationError(OpenRouterDetectionError):
    """The OpenRouter detector is not configured on this server."""


def is_openrouter_configured() -> bool:
    """Return whether the server has an OpenRouter API key."""
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


def openrouter_model() -> str:
    """Return the configured vision model identifier."""
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _image_bytes(image: Image.Image, max_dimension: int = 2048) -> bytes:
    rgb = image.convert("RGB")
    if max(rgb.size) > max_dimension:
        scale = max_dimension / max(rgb.size)
        rgb = rgb.resize(
            (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))),
            Image.Resampling.LANCZOS,
        )
    buffer = io.BytesIO()
    rgb.save(buffer, format="JPEG", quality=90, subsampling=0, optimize=True)
    return buffer.getvalue()


def _image_data_url(image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _cache_enabled() -> bool:
    return os.environ.get("SCANSPLITTER_LLM_CACHE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _cache_dir() -> Path:
    override = os.environ.get("SCANSPLITTER_LLM_CACHE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    data_dir = os.environ.get("SCANSPLITTER_DATA_DIR", "").strip()
    root = Path(data_dir).expanduser() if data_dir else Path.home() / ".scansplitter"
    return root / "llm-cache"


def _cache_key(image_bytes: bytes, model: str, endpoint: str) -> str:
    request_identity = json.dumps(
        {
            "version": _CACHE_VERSION,
            "model": model,
            "endpoint": endpoint,
            "prompt": _PROMPT,
            "response_format": _RESPONSE_FORMAT,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256()
    digest.update(request_identity)
    digest.update(b"\0")
    digest.update(image_bytes)
    return digest.hexdigest()


def _lock_for_cache_key(key: str) -> threading.Lock:
    with _CACHE_LOCKS_GUARD:
        return _CACHE_LOCKS.setdefault(key, threading.Lock())


def _read_cache(key: str) -> dict[str, Any] | None:
    try:
        value = json.loads((_cache_dir() / f"{key}.json").read_text())
        if not isinstance(value, dict) or value.get("version") != _CACHE_VERSION:
            return None
        response = value.get("response")
        if not isinstance(response, dict):
            return None
        # Never let corrupt or manually edited cache entries become detections.
        _response_content(response)
        return response
    except (OSError, json.JSONDecodeError, OpenRouterDetectionError):
        return None


def _write_cache(key: str, response: dict[str, Any]) -> None:
    cache_dir = _cache_dir()
    temporary: Path | None = None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = cache_dir / f".{key}.{uuid.uuid4().hex}.tmp"
        temporary.write_text(
            json.dumps(
                {"version": _CACHE_VERSION, "response": response},
                separators=(",", ":"),
            )
        )
        os.replace(temporary, cache_dir / f"{key}.json")
    except OSError:
        # Detection must still work if the cache directory is read-only or full.
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _retry_delay(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(10.0, max(0.0, float(retry_after)))
        except ValueError:
            pass
    return min(4.0, 0.5 * (2**attempt))


def _request_openrouter(
    image_bytes: bytes,
    api_key: str,
    model: str,
    endpoint: str,
    timeout: float,
    max_retries: int,
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
                        "image_url": {"url": _image_data_url(image_bytes), "detail": "high"},
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
    result: Any = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read())
            break
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or exc.code in {408, 409} or 500 <= exc.code < 600
            if retryable and attempt < max_retries:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                time.sleep(_retry_delay(attempt, retry_after))
                continue
            try:
                body = json.loads(exc.read())
                message = body.get("error", {}).get("message")
            except (json.JSONDecodeError, AttributeError):
                message = None
            raise OpenRouterDetectionError(
                f"OpenRouter request failed ({exc.code}): {message or exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < max_retries:
                time.sleep(_retry_delay(attempt, None))
                continue
            raise OpenRouterDetectionError(f"OpenRouter request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise OpenRouterDetectionError("OpenRouter returned invalid JSON") from exc

    if not isinstance(result, dict):
        raise OpenRouterDetectionError("OpenRouter returned an invalid response")
    if isinstance(result.get("error"), dict):
        raise OpenRouterDetectionError(
            f"OpenRouter request failed: {result['error'].get('message', 'unknown error')}"
        )
    return result


def _response_content(response: dict[str, Any]) -> dict[str, Any]:
    try:
        message = response["choices"][0]["message"]
        parsed = message.get("parsed")
        if isinstance(parsed, dict):
            decoded = parsed
        else:
            content = message["content"]
            if isinstance(content, dict):
                decoded = content
            else:
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
            normalized_points = np.asarray(
                [
                    [float(point["x"]), float(point["y"])]
                    for point in corners
                ],
                dtype=np.float32,
            )
        except (KeyError, TypeError, ValueError):
            continue
        if (
            not np.isfinite(normalized_points).all()
            or (normalized_points < 0).any()
            or (normalized_points > NORMALIZED_SIZE).any()
        ):
            continue
        points = normalized_points * np.asarray(
            [image_width / NORMALIZED_SIZE, image_height / NORMALIZED_SIZE],
            dtype=np.float32,
        )
        points[:, 0] = np.clip(points[:, 0], 0, image_width)
        points[:, 1] = np.clip(points[:, 1], 0, image_height)
        if cv2.contourArea(cv2.convexHull(points)) < 4.0:
            continue
        rectangle = cv2.minAreaRect(points)
        rect_width, rect_height = rectangle[1]
        area = float(rect_width * rect_height)
        area_ratio = area / image_area
        if not min_area_ratio <= area_ratio <= max_area_ratio:
            continue
        x, y, width, height = cv2.boundingRect(cv2.boxPoints(rectangle))
        candidate = DetectedRegion(
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
        candidate_rect = (candidate.center, candidate.size, candidate.angle)
        duplicate = False
        for existing in regions:
            existing_rect = (existing.center, existing.size, existing.angle)
            _, intersection = cv2.rotatedRectangleIntersection(candidate_rect, existing_rect)
            if intersection is None:
                continue
            intersection_area = float(cv2.contourArea(intersection))
            union = candidate.area + existing.area - intersection_area
            if union > 0 and intersection_area / union >= 0.90:
                duplicate = True
                break
        if not duplicate:
            regions.append(candidate)
    row_height = max(1, round(image_height * 0.05))
    regions.sort(key=lambda region: (region.y // row_height, region.x))
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
    max_retries: int = DEFAULT_MAX_RETRIES,
    use_cache: bool | None = None,
) -> list[DetectedRegion]:
    """Ask an OpenRouter vision model for rotated photo bounding boxes."""
    resolved_key = (api_key or os.environ.get("OPENROUTER_API_KEY", "")).strip()
    if not resolved_key:
        raise OpenRouterConfigurationError("OPENROUTER_API_KEY is not configured")
    resolved_model = model or openrouter_model()
    prepared_image = _image_bytes(image)
    cache_enabled = _cache_enabled() if use_cache is None else use_cache
    key = _cache_key(prepared_image, resolved_model, endpoint)
    with _lock_for_cache_key(key):
        response = _read_cache(key) if cache_enabled else None
        if response is None:
            response = _request_openrouter(
                prepared_image,
                resolved_key,
                resolved_model,
                endpoint,
                timeout,
                max(0, max_retries),
            )
            # Validate before persisting. A malformed provider response should
            # never poison every subsequent detection for this scan.
            _response_content(response)
            if cache_enabled:
                _write_cache(key, response)
    return _regions_from_response(response, image.size, min_area_ratio, max_area_ratio)
