import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scansplitter.api import app
from scansplitter.benchmark_metrics import best_pairs, rotated_iou

BENCHMARK = Path(__file__).parents[1] / "benchmarks"
SPEC = importlib.util.spec_from_file_location("benchmark_evaluate", BENCHMARK / "evaluate.py")
assert SPEC is not None and SPEC.loader is not None
EVALUATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATE)
CLIENT = TestClient(app)


def test_benchmark_has_ten_cases_per_algorithm_and_all_images_exist():
    manifest = json.loads((BENCHMARK / "manifest.json").read_text())
    cases = manifest["cases"]

    assert sum(case["suite"] == "scansplitter" for case in cases) == 10
    assert sum(case["suite"] == "album" for case in cases) == 10
    assert all((BENCHMARK / case["image"]).is_file() for case in cases)
    assert all(case["rectangles"] for case in cases)
    assert manifest["version"] >= 2
    assert all(
        case.get("target") == "photographic_content"
        for case in cases
        if case["suite"] == "scansplitter"
    )


def test_rotated_iou_and_assignment_are_order_independent():
    first = ((100.0, 100.0), (80.0, 60.0), 5.0)
    second = ((300.0, 200.0), (120.0, 90.0), -8.0)

    assert rotated_iou(first, first) == pytest.approx(1.0, abs=1e-5)
    pairs = best_pairs([first, second], [second, first])
    assert {(expected, actual) for expected, actual, _ in pairs} == {(0, 1), (1, 0)}
    assert EVALUATE.score_case([first, second], [second, first], 0.5)["f1"] == 1.0


def test_box_quality_penalizes_loose_box_that_passes_detection_f1():
    expected = ((100.0, 100.0), (100.0, 100.0), 0.0)
    loose = ((125.0, 100.0), (100.0, 100.0), 0.0)

    score = EVALUATE.score_case([expected], [loose], 0.5, 0.85)

    assert score["f1"] == 1.0
    assert score["strict_f1"] == 0.0
    assert score["box_quality"] == pytest.approx(0.6)
    assert score["crop_tightness"] == pytest.approx(0.75)
    assert score["content_coverage"] == pytest.approx(0.75)


def test_directional_crop_metrics_distinguish_overshoot_from_lost_content():
    expected = ((100.0, 100.0), (100.0, 100.0), 0.0)
    oversized = ((100.0, 100.0), (120.0, 120.0), 0.0)
    undersized = ((100.0, 100.0), (80.0, 80.0), 0.0)

    loose = EVALUATE.score_case([expected], [oversized], 0.5, 0.85)
    clipped = EVALUATE.score_case([expected], [undersized], 0.5, 0.85)

    assert loose["content_coverage"] == pytest.approx(1.0)
    assert loose["crop_tightness"] == pytest.approx(10000 / 14400)
    assert clipped["content_coverage"] == pytest.approx(0.64)
    assert clipped["crop_tightness"] == pytest.approx(1.0)


def test_benchmark_api_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SCANSPLITTER_BENCHMARK", raising=False)

    assert CLIENT.get("/api/benchmark").status_code == 404


def test_benchmark_api_lists_fixed_cases_when_enabled(monkeypatch):
    monkeypatch.setenv("SCANSPLITTER_BENCHMARK", "1")

    response = CLIENT.get("/api/benchmark")

    assert response.status_code == 200
    assert len(response.json()["cases"]) == 20
    assert response.json()["cases"][0]["ground_truth"]
