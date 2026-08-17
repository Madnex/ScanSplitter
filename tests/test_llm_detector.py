"""Tests for the experimental OpenRouter vision detector."""

import base64
import json
import urllib.error
from email.message import Message
from io import BytesIO

import pytest
from PIL import Image

from scansplitter import llm_detector


class _Response:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.body


def test_openrouter_sends_private_image_as_data_url_and_converts_corners(monkeypatch, tmp_path):
    monkeypatch.setenv("SCANSPLITTER_LLM_CACHE_DIR", str(tmp_path))
    captured = None
    model_output = {
        "photos": [
            {
                "corners": [
                    {"x": 100, "y": 200},
                    {"x": 500, "y": 200},
                    {"x": 500, "y": 600},
                    {"x": 100, "y": 600},
                ]
            }
        ]
    }

    def fake_urlopen(request, timeout):
        nonlocal captured
        captured = (request, timeout, json.loads(request.data))
        return _Response({"choices": [{"message": {"content": json.dumps(model_output)}}]})

    monkeypatch.setattr(llm_detector.urllib.request, "urlopen", fake_urlopen)
    regions = llm_detector.detect_photos_openrouter(
        Image.new("RGB", (2000, 1000), "white"),
        api_key="secret",
        model="vendor/vision-model",
    )

    request, timeout, payload = captured
    assert request.get_header("Authorization") == "Bearer secret"
    assert timeout == 120.0
    assert payload["model"] == "vendor/vision-model"
    image_url = payload["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")
    Image.open(BytesIO(base64.b64decode(image_url.split(",", 1)[1]))).verify()
    assert len(regions) == 1
    assert regions[0].center == (600.0, 400.0)
    assert regions[0].area_ratio == 0.16


def test_openrouter_requires_server_side_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    try:
        llm_detector.detect_photos_openrouter(Image.new("RGB", (100, 100)))
    except llm_detector.OpenRouterDetectionError as exc:
        assert "OPENROUTER_API_KEY" in str(exc)
    else:
        raise AssertionError("missing API key should fail")


def test_invalid_or_tiny_regions_are_ignored():
    content = {
        "photos": [
            {"corners": [{"x": 1, "y": 1}] * 4},
            {"corners": [{"x": 10, "y": 10}] * 3},
            {
                "corners": [
                    {"x": -1, "y": 10},
                    {"x": 500, "y": 10},
                    {"x": 500, "y": 500},
                    {"x": 10, "y": 500},
                ]
            },
        ]
    }
    response = {"choices": [{"message": {"content": json.dumps(content)}}]}

    assert llm_detector._regions_from_response(response, (1000, 1000), 0.02, 0.8) == []


def test_near_duplicate_regions_are_collapsed():
    corners = [
        {"x": 100, "y": 100},
        {"x": 500, "y": 100},
        {"x": 500, "y": 500},
        {"x": 100, "y": 500},
    ]
    shifted = [{"x": point["x"] + 2, "y": point["y"] + 2} for point in corners]
    response = {
        "choices": [
            {"message": {"content": json.dumps({"photos": [{"corners": corners}, {"corners": shifted}]})}}
        ]
    }

    assert len(llm_detector._regions_from_response(response, (1000, 1000), 0.02, 0.8)) == 1


def test_identical_scan_and_model_use_persistent_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("SCANSPLITTER_LLM_CACHE_DIR", str(tmp_path))
    calls = 0
    model_output = {
        "photos": [
            {
                "corners": [
                    {"x": 100, "y": 100},
                    {"x": 600, "y": 100},
                    {"x": 600, "y": 600},
                    {"x": 100, "y": 600},
                ]
            }
        ]
    }

    def fake_urlopen(_request, timeout):
        nonlocal calls
        assert timeout == 120.0
        calls += 1
        return _Response({"choices": [{"message": {"content": json.dumps(model_output)}}]})

    monkeypatch.setattr(llm_detector.urllib.request, "urlopen", fake_urlopen)
    image = Image.new("RGB", (1000, 1000), "white")

    first = llm_detector.detect_photos_openrouter(image, api_key="secret", model="model-a")
    # Area thresholds are local post-processing and intentionally do not cause
    # another paid request for the same prepared image/model/prompt.
    second = llm_detector.detect_photos_openrouter(
        image,
        api_key="secret",
        model="model-a",
        min_area_ratio=0.30,
    )

    assert calls == 1
    assert len(first) == 1
    assert second == []
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_can_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("SCANSPLITTER_LLM_CACHE_DIR", str(tmp_path))
    calls = 0
    response = {"choices": [{"message": {"content": '{"photos": []}'}}]}

    def fake_urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        return _Response(response)

    monkeypatch.setattr(llm_detector.urllib.request, "urlopen", fake_urlopen)
    image = Image.new("RGB", (100, 100), "white")
    llm_detector.detect_photos_openrouter(image, api_key="secret", use_cache=False)
    llm_detector.detect_photos_openrouter(image, api_key="secret", use_cache=False)

    assert calls == 2
    assert list(tmp_path.iterdir()) == []


def test_transient_openrouter_failure_is_retried(monkeypatch):
    attempts = 0
    sleeps = []
    headers = Message()
    headers["Retry-After"] = "0"

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "rate limited",
                headers,
                BytesIO(b'{"error":{"message":"slow down"}}'),
            )
        return _Response({"choices": [{"message": {"content": '{"photos": []}'}}]})

    monkeypatch.setattr(llm_detector.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(llm_detector.time, "sleep", sleeps.append)
    regions = llm_detector.detect_photos_openrouter(
        Image.new("RGB", (100, 100)),
        api_key="secret",
        use_cache=False,
    )

    assert regions == []
    assert attempts == 2
    assert sleeps == [0.0]


def test_permanent_openrouter_failure_is_not_retried(monkeypatch):
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "bad request",
            Message(),
            BytesIO(b'{"error":{"message":"unsupported model"}}'),
        )

    monkeypatch.setattr(llm_detector.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(llm_detector.OpenRouterDetectionError, match="unsupported model"):
        llm_detector.detect_photos_openrouter(
            Image.new("RGB", (100, 100)),
            api_key="secret",
            use_cache=False,
        )

    assert attempts == 1
