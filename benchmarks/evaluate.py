#!/usr/bin/env -S uv run
"""Evaluate ScanSplitter detectors against the fixed image benchmark."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from PIL import Image

from scansplitter.album_detector import detect_album_pages
from scansplitter.benchmark_metrics import score_rectangles
from scansplitter.detector import detect_photos_v3, detect_photos_v4, detect_photos_v5
from scansplitter.llm_detector import detect_photos_openrouter, openrouter_model

ROOT = Path(__file__).resolve().parent


def as_rect(values: list[float]) -> tuple:
    return ((float(values[0]), float(values[1])), (float(values[2]), float(values[3])), float(values[4]))


def score_case(
    expected: list[tuple],
    actual: list[tuple],
    threshold: float,
    strict_threshold: float = 0.85,
) -> dict[str, Any]:
    return score_rectangles(expected, actual, threshold, strict_threshold)


def detector_for(case: dict[str, Any], scan_detector: str):
    if case["suite"] == "album":
        return lambda image: detect_album_pages(image, layout=case["layout"])
    return {
        "v3": detect_photos_v3,
        "v4": detect_photos_v4,
        "v5": detect_photos_v5,
        "openrouter": detect_photos_openrouter,
    }[scan_detector]


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    true_positive = sum(item["true_positive"] for item in results)
    false_positive = sum(item["false_positive"] for item in results)
    false_negative = sum(item["false_negative"] for item in results)
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    strict_true_positive = sum(item["strict_true_positive"] for item in results)
    strict_false_positive = sum(item["strict_false_positive"] for item in results)
    strict_false_negative = sum(item["strict_false_negative"] for item in results)
    strict_precision = strict_true_positive / max(
        1, strict_true_positive + strict_false_positive
    )
    strict_recall = strict_true_positive / max(
        1, strict_true_positive + strict_false_negative
    )
    expected_regions = sum(item["expected"] for item in results)
    detected_regions = sum(item["detected"] for item in results)
    iou_sum = sum(item["iou_sum"] for item in results)
    intersection_area_sum = sum(item["intersection_area_sum"] for item in results)
    expected_area_sum = sum(item["expected_area_sum"] for item in results)
    actual_area_sum = sum(item["actual_area_sum"] for item in results)
    assigned_count = sum(item["assigned_count"] for item in results)
    return {
        "cases": len(results),
        "expected_regions": expected_regions,
        "detected_regions": detected_regions,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "strict_true_positive": strict_true_positive,
        "strict_false_positive": strict_false_positive,
        "strict_false_negative": strict_false_negative,
        "strict_precision": strict_precision,
        "strict_recall": strict_recall,
        "strict_f1": (
            2 * strict_precision * strict_recall / (strict_precision + strict_recall)
            if strict_precision + strict_recall
            else 0.0
        ),
        "box_quality": (
            2 * iou_sum / (expected_regions + detected_regions)
            if expected_regions + detected_regions
            else 1.0
        ),
        "content_coverage": (
            intersection_area_sum / expected_area_sum
            if expected_area_sum
            else (1.0 if not actual_area_sum else 0.0)
        ),
        "crop_tightness": (
            intersection_area_sum / actual_area_sum
            if actual_area_sum
            else (1.0 if not expected_area_sum else 0.0)
        ),
        "mean_iou": iou_sum / assigned_count if assigned_count else 0.0,
        "count_accuracy": sum(item["count_correct"] for item in results) / max(1, len(results)),
        "runtime_seconds": sum(item["runtime_seconds"] for item in results),
    }


def markdown_report(report: dict[str, Any]) -> str:
    detector = f"`{report['scan_detector']}`"
    if report.get("scan_detector_model"):
        detector += f" using `{report['scan_detector_model']}`"
    lines = [
        "# ScanSplitter benchmark result",
        "",
        f"Scan detector: {detector}. Detection F1 uses IoU "
        f"`{report['iou_threshold']:.2f}`; strict F1 uses IoU "
        f"`{report['strict_iou_threshold']:.2f}`. Box quality is IoU-weighted F1. "
        "Tightness is wanted image area divided by detected crop area; coverage is "
        "wanted image area retained.",
        "",
        "| Suite | Cases | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Count accuracy | Time |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("scansplitter", "album", "all"):
        if name not in report["summary"]:
            continue
        value = report["summary"][name]
        lines.append(
            f"| {name} | {value['cases']} | {value['box_quality']:.1%} | "
            f"{value['crop_tightness']:.1%} | {value['content_coverage']:.1%} | "
            f"{value['f1']:.1%} | {value['strict_f1']:.1%} | "
            f"{value['count_accuracy']:.1%} | {value['runtime_seconds']:.2f}s |"
        )
    lines.extend(
        [
            "",
            "## Per case",
            "",
            "| Case | Expected | Found | Box quality | Tightness | Coverage | F1@0.50 | F1@0.85 | Grade |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in report["cases"]:
        quality = item["box_quality"]
        grade = "excellent" if quality >= 0.90 else "good" if quality >= 0.80 else "loose" if quality >= 0.65 else "poor"
        lines.append(
            f"| {item['id']} | {item['expected']} | {item['detected']} | "
            f"{quality:.1%} | {item['crop_tightness']:.1%} | "
            f"{item['content_coverage']:.1%} | {item['f1']:.1%} | "
            f"{item['strict_f1']:.1%} | {grade} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("all", "scansplitter", "album"), default="all")
    parser.add_argument(
        "--scan-detector",
        choices=("v3", "v4", "v5", "openrouter"),
        default="v5",
    )
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--strict-iou-threshold", type=float, default=0.85)
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "latest.md")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    if not 0 < args.iou_threshold <= 1:
        parser.error("--iou-threshold must be in (0, 1]")
    if not args.iou_threshold < args.strict_iou_threshold <= 1:
        parser.error("--strict-iou-threshold must be greater than --iou-threshold and at most 1")

    manifest = json.loads((ROOT / "manifest.json").read_text())
    cases = [case for case in manifest["cases"] if args.suite == "all" or case["suite"] == args.suite]
    results = []
    for case in cases:
        with Image.open(ROOT / case["image"]) as image:
            started = time.perf_counter()
            detected = detector_for(case, args.scan_detector)(image.convert("RGB"))
            elapsed = time.perf_counter() - started
        expected = [as_rect(rect) for rect in case["rectangles"]]
        actual = [(region.center, region.size, region.angle) for region in detected]
        result = score_case(
            expected, actual, args.iou_threshold, args.strict_iou_threshold
        )
        result.update({"id": case["id"], "suite": case["suite"], "runtime_seconds": elapsed})
        results.append(result)

    suites = sorted({item["suite"] for item in results})
    summary = {suite: summarize([item for item in results if item["suite"] == suite]) for suite in suites}
    if len(suites) > 1:
        summary["all"] = summarize(results)
    report = {
        "benchmark_version": manifest["version"],
        "scan_detector": args.scan_detector,
        "scan_detector_model": (
            openrouter_model() if args.scan_detector == "openrouter" else None
        ),
        "iou_threshold": args.iou_threshold,
        "strict_iou_threshold": args.strict_iou_threshold,
        "summary": summary,
        "cases": results,
    }
    markdown = markdown_report(report)
    if not args.no_write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown)
        args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(markdown)


if __name__ == "__main__":
    main()
