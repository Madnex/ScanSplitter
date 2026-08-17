"""Shared geometry-aware metrics for the fixed detector benchmark."""

from __future__ import annotations

import itertools
from typing import Any

import cv2

RotatedRect = tuple[tuple[float, float], tuple[float, float], float]


def _intersection_area(first: RotatedRect, second: RotatedRect) -> float:
    """Return the bounded intersection area of two rotated rectangles."""
    kind, points = cv2.rotatedRectangleIntersection(first, second)
    if kind == cv2.INTERSECT_NONE or points is None:
        return 0.0
    first_area = first[1][0] * first[1][1]
    second_area = second[1][0] * second[1][1]
    return min(float(cv2.contourArea(points)), first_area, second_area)


def rotated_iou(first: RotatedRect, second: RotatedRect) -> float:
    """Return intersection-over-union for two OpenCV rotated rectangles."""
    intersection = _intersection_area(first, second)
    if intersection == 0:
        return 0.0
    first_area = first[1][0] * first[1][1]
    second_area = second[1][0] * second[1][1]
    return intersection / max(1.0, first_area + second_area - intersection)


def best_pairs(
    expected: list[RotatedRect], actual: list[RotatedRect]
) -> list[tuple[int, int, float]]:
    """Return the one-to-one assignment with maximum total rotated IoU."""
    if not expected or not actual:
        return []
    best: list[tuple[int, int, float]] = []
    best_total = -1.0
    if len(expected) <= len(actual):
        assignments = (
            [(index, permutation[index]) for index in range(len(expected))]
            for permutation in itertools.permutations(range(len(actual)), len(expected))
        )
    else:
        assignments = (
            [(permutation[index], index) for index in range(len(actual))]
            for permutation in itertools.permutations(range(len(expected)), len(actual))
        )
    for assignment in assignments:
        pairs = [
            (expected_index, actual_index, rotated_iou(expected[expected_index], actual[actual_index]))
            for expected_index, actual_index in assignment
        ]
        total = sum(pair[2] for pair in pairs)
        if total > best_total:
            best, best_total = pairs, total
    return best


def _classification(
    assigned: list[tuple[int, int, float]],
    expected_count: int,
    actual_count: int,
    threshold: float,
) -> dict[str, float | int]:
    true_positive = sum(pair[2] >= threshold for pair in assigned)
    false_positive = actual_count - true_positive
    false_negative = expected_count - true_positive
    precision = (
        true_positive / actual_count
        if actual_count
        else (1.0 if not expected_count else 0.0)
    )
    recall = (
        true_positive / expected_count
        if expected_count
        else (1.0 if not actual_count else 0.0)
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def score_rectangles(
    expected: list[RotatedRect],
    actual: list[RotatedRect],
    detection_threshold: float = 0.5,
    strict_threshold: float = 0.85,
) -> dict[str, Any]:
    """Score both region discovery and crop geometry.

    ``f1`` remains the conventional binary detection score at IoU 0.50.
    ``strict_f1`` raises that boundary to 0.85. ``box_quality`` is an
    IoU-weighted F1: every assigned region contributes its actual overlap,
    while missing and extra boxes contribute zero. It therefore cannot report
    a perfect score for merely adequate, visibly loose boxes.
    """
    assigned = best_pairs(expected, actual)
    detection = _classification(
        assigned, len(expected), len(actual), detection_threshold
    )
    strict = _classification(assigned, len(expected), len(actual), strict_threshold)
    iou_sum = sum(pair[2] for pair in assigned)
    intersection_area_sum = sum(
        _intersection_area(expected[expected_index], actual[actual_index])
        for expected_index, actual_index, _ in assigned
    )
    expected_area_sum = sum(rect[1][0] * rect[1][1] for rect in expected)
    actual_area_sum = sum(rect[1][0] * rect[1][1] for rect in actual)
    denominator = len(expected) + len(actual)
    box_quality = 2 * iou_sum / denominator if denominator else 1.0
    unmatched = abs(len(expected) - len(actual))
    comparison_ious = [pair[2] for pair in assigned] + [0.0] * unmatched
    return {
        "expected": len(expected),
        "detected": len(actual),
        **detection,
        "strict_true_positive": strict["true_positive"],
        "strict_false_positive": strict["false_positive"],
        "strict_false_negative": strict["false_negative"],
        "strict_precision": strict["precision"],
        "strict_recall": strict["recall"],
        "strict_f1": strict["f1"],
        "detection_threshold": detection_threshold,
        "strict_threshold": strict_threshold,
        "box_quality": box_quality,
        "iou_sum": iou_sum,
        "intersection_area_sum": intersection_area_sum,
        "expected_area_sum": expected_area_sum,
        "actual_area_sum": actual_area_sum,
        # Coverage answers "did the crop retain the wanted photograph?";
        # tightness answers "how much of the crop is actually wanted?". IoU
        # alone cannot explain which side of the boundary caused a regression.
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
        "assigned_count": len(assigned),
        "mean_iou": iou_sum / len(assigned) if assigned else 0.0,
        "worst_iou": min(comparison_ious) if comparison_ious else 1.0,
        "assigned_ious": [round(pair[2], 6) for pair in assigned],
        "count_correct": len(expected) == len(actual),
    }
