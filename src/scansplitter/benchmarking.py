"""Opt-in access to the repository's fixed visual detector benchmark."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

from .album_detector import detect_album_pages
from .benchmark_metrics import score_rectangles
from .detector import DetectedRegion, detect_photos_v3, detect_photos_v4, detect_photos_v5

BENCHMARK_ROOT = Path(__file__).resolve().parents[2] / "benchmarks"
_ENABLED_VALUES = {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    """Return whether the explicitly opt-in benchmark surface is enabled."""
    return os.environ.get("SCANSPLITTER_BENCHMARK", "").strip().lower() in _ENABLED_VALUES


@lru_cache(maxsize=1)
def _manifest() -> dict[str, Any]:
    return json.loads((BENCHMARK_ROOT / "manifest.json").read_text())


def _case(case_id: str) -> dict[str, Any]:
    for case in _manifest()["cases"]:
        if case["id"] == case_id:
            return case
    raise KeyError(case_id)


def _rect(values: list[float]) -> tuple:
    return (
        (float(values[0]), float(values[1])),
        (float(values[2]), float(values[3])),
        float(values[4]),
    )


def _box(rect: tuple, box_id: str) -> dict[str, Any]:
    return {
        "id": box_id,
        "center_x": float(rect[0][0]),
        "center_y": float(rect[0][1]),
        "width": float(rect[1][0]),
        "height": float(rect[1][1]),
        "angle": float(rect[2]),
    }


def _region_rect(region: DetectedRegion) -> tuple:
    return region.center, region.size, region.angle


def list_cases() -> dict[str, Any]:
    """Return browser-safe metadata and ground truth for every fixture."""
    manifest = _manifest()
    width, height = manifest["image_size"]
    return {
        "image_width": width,
        "image_height": height,
        "cases": [
            {
                "id": case["id"],
                "suite": case["suite"],
                "layout": case.get("layout"),
                "target": case.get("target"),
                "image_url": f"/api/benchmark/{case['id']}/image",
                "ground_truth": [
                    _box(_rect(rectangle), f"ground-truth-{index}")
                    for index, rectangle in enumerate(case["rectangles"])
                ],
            }
            for case in manifest["cases"]
        ],
    }


def fixture_path(case_id: str) -> Path:
    """Resolve one manifest-owned image path without accepting a path from the client."""
    case = _case(case_id)
    path = (BENCHMARK_ROOT / case["image"]).resolve()
    if not path.is_relative_to(BENCHMARK_ROOT.resolve()) or not path.is_file():
        raise FileNotFoundError(case_id)
    return path


def run_case(case_id: str) -> dict[str, Any]:
    """Run every applicable detector version for one fixed fixture."""
    case = _case(case_id)
    expected = [_rect(rectangle) for rectangle in case["rectangles"]]
    with Image.open(fixture_path(case_id)) as source:
        image = source.convert("RGB")
    if case["suite"] == "scansplitter":
        runs = [
            ("v3", "ScanSplitter v3", detect_photos_v3(image)),
            ("v4", "ScanSplitter v4", detect_photos_v4(image)),
            ("v5", "ScanSplitter v5", detect_photos_v5(image)),
        ]
    else:
        runs = [
            (
                "album",
                f"Album Splitter ({case['layout']})",
                detect_album_pages(image, layout=case["layout"]),
            )
        ]
    variants = []
    for key, label, regions in runs:
        actual = [_region_rect(region) for region in regions]
        variants.append(
            {
                "key": key,
                "label": label,
                "boxes": [_box(rect, f"{key}-{index}") for index, rect in enumerate(actual)],
                "metrics": score_rectangles(expected, actual),
            }
        )
    return {"id": case_id, "variants": variants}
