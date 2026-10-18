"""Shared geometry-aware metrics for the fixed detector benchmark."""

from __future__ import annotations

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


def _assign_min_cost(cost: list[list[float]]) -> list[int]:
    """Hungarian algorithm (O(n^2 m)) for an n x m cost matrix with n <= m.

    Returns, for each row, the column it is assigned to.
    """
    n, m = len(cost), len(cost[0])
    inf = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    owner = [0] * (m + 1)  # owner[j] = row (1-based) assigned to column j
    way = [0] * (m + 1)
    for row in range(1, n + 1):
        owner[0] = row
        j0 = 0
        minv = [inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = owner[j0], inf, 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                current = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if current < minv[j]:
                    minv[j], way[j] = current, j0
                if minv[j] < delta:
                    delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[owner[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if owner[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            owner[j0] = owner[j1]
            j0 = j1
    result = [0] * n
    for j in range(1, m + 1):
        if owner[j]:
            result[owner[j] - 1] = j - 1
    return result


def best_pairs(
    expected: list[RotatedRect], actual: list[RotatedRect]
) -> list[tuple[int, int, float]]:
    """Return the one-to-one assignment with maximum total rotated IoU."""
    if not expected or not actual:
        return []
    iou = [[rotated_iou(e, a) for a in actual] for e in expected]
    if len(expected) <= len(actual):
        columns = _assign_min_cost([[-value for value in row] for row in iou])
        return [(i, j, iou[i][j]) for i, j in enumerate(columns)]
    transposed = [[-iou[i][j] for i in range(len(expected))] for j in range(len(actual))]
    rows = _assign_min_cost(transposed)
    return [(i, j, iou[i][j]) for j, i in enumerate(rows)]


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
