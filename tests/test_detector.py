"""Focused tests for contour border refinement."""

import cv2
import numpy as np
from PIL import Image

from scansplitter.detector import _refine_rect_to_edges, detect_photos_v2


def _shadowed_photo_scan() -> tuple[Image.Image, tuple]:
    """Build a high-resolution print with a soft outer scanner shadow."""
    height, width = 2400, 3200
    canvas = np.full((height, width, 3), 248, dtype=np.uint8)
    photo_rect = ((1600.0, 1200.0), (2100.0, 1300.0), -2.0)

    shadow_rect = ((1612.0, 1216.0), (2180.0, 1380.0), -2.0)
    shadow = cv2.boxPoints(shadow_rect).astype(np.int32)
    cv2.fillConvexPoly(canvas, shadow, (218, 218, 218))
    cv2.polylines(canvas, [shadow], True, (205, 205, 205), 6)

    photo = cv2.boxPoints(photo_rect).astype(np.int32)
    cv2.fillConvexPoly(canvas, photo, (65, 85, 105))
    # Long internal details ensure refinement favors the continuous outer
    # border rather than simply succeeding on a featureless rectangle.
    cv2.line(canvas, (900, 1050), (2250, 1050), (135, 145, 155), 18)
    cv2.circle(canvas, (1600, 1200), 260, (105, 115, 125), -1)

    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb), photo_rect


def _rotated_iou(first: tuple, second: tuple) -> float:
    intersection_type, points = cv2.rotatedRectangleIntersection(first, second)
    if intersection_type == cv2.INTERSECT_NONE or points is None:
        return 0.0
    first_area = first[1][0] * first[1][1]
    second_area = second[1][0] * second[1][1]
    # OpenCV's float intersection vertices can overshoot by a fraction of a
    # pixel for nearly identical rectangles.
    intersection = min(cv2.contourArea(points), first_area, second_area)
    return intersection / (first_area + second_area - intersection)


def test_edge_refinement_rejects_high_resolution_scanner_shadow():
    image, expected = _shadowed_photo_scan()

    unrefined = detect_photos_v2(image, inset=0, refine_edges=False)
    refined = detect_photos_v2(image, inset=0, refine_edges=True)

    assert len(unrefined) == 1
    assert len(refined) == 1
    raw_rect = (unrefined[0].center, unrefined[0].size, unrefined[0].angle)
    refined_rect = (refined[0].center, refined[0].size, refined[0].angle)
    raw_iou = _rotated_iou(raw_rect, expected)
    refined_iou = _rotated_iou(refined_rect, expected)

    assert refined_iou > 0.98
    assert refined_iou > raw_iou + 0.04


def test_edge_refinement_preserves_candidate_when_band_has_no_edge():
    gray = np.full((600, 800), 127, dtype=np.uint8)
    candidate = ((400.0, 300.0), (420.0, 260.0), 3.0)

    assert _refine_rect_to_edges(gray, candidate) == candidate
