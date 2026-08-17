"""Tests for the experimental OpenRouter vision detector."""

import base64
import json
from io import BytesIO

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


def test_openrouter_sends_private_image_as_data_url_and_converts_corners(monkeypatch):
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
        ]
    }
    response = {"choices": [{"message": {"content": json.dumps(content)}}]}

    assert llm_detector._regions_from_response(response, (1000, 1000), 0.02, 0.8) == []
