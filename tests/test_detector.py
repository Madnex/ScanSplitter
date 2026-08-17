"""Focused tests for shared edge refinement and background-aware detection."""

from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PIL import Image

from scansplitter.detector import (
    _refine_rect_to_edges,
    _v4_mask_rect,
    detect_photos_v3,
)


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


def _procedural_album_scan(
    rectangles: list[tuple],
    *,
    background: tuple[int, int, int] = (238, 232, 216),
    photo_color: tuple[int, int, int] = (211, 205, 191),
    size: tuple[int, int] = (1600, 1200),
) -> Image.Image:
    """Create private-data-free album pages with low-contrast textured prints."""
    width, height = size
    canvas = np.full((height, width, 3), background, dtype=np.uint8)
    rng = np.random.default_rng(7)
    for index, rect in enumerate(rectangles):
        polygon = cv2.boxPoints(rect).astype(np.int32)
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillConvexPoly(mask, polygon, 255)
        texture = np.full_like(canvas, photo_color)
        # Low-frequency tonal variation resembles sky, clothing, and foliage
        # while keeping the print's pale edge close to the album paper.
        coarse = np.clip(rng.normal(-30, 10, (24, 32)), -48, -15).astype(np.float32)
        noise = cv2.resize(coarse, (width, height), interpolation=cv2.INTER_CUBIC)
        texture = np.clip(texture.astype(np.float32) + noise[..., None], 0, 255).astype(np.uint8)
        canvas[mask > 0] = texture[mask > 0]
        # Each print gets distinct broad photographic content. Thin page marks
        # outside prints are intentionally not added to the region mask.
        center = tuple(round(value) for value in rect[0])
        cv2.circle(canvas, center, round(min(rect[1]) * 0.22), (145, 150, 145), -1)
        offset = 35 + index * 8
        cv2.line(
            canvas,
            (center[0] - offset, center[1] - 55),
            (center[0] + offset, center[1] + 55),
            (105, 115, 112),
            13,
        )
        cv2.polylines(canvas, [polygon], True, (185, 179, 168), 4)
    return Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))


def test_edge_refinement_preserves_candidate_when_band_has_no_edge():
    gray = np.full((600, 800), 127, dtype=np.uint8)
    candidate = ((400.0, 300.0), (420.0, 260.0), 3.0)

    assert _refine_rect_to_edges(gray, candidate) == candidate


def test_v3_detects_multiple_low_contrast_rotated_album_photos():
    expected = [
        ((360.0, 330.0), (430.0, 285.0), -7.0),
        ((1080.0, 325.0), (390.0, 290.0), 5.0),
        ((765.0, 825.0), (500.0, 320.0), -3.0),
    ]
    image = _procedural_album_scan(expected)

    detected = detect_photos_v3(image, inset=0)

    assert len(detected) == len(expected)
    actual = [(region.center, region.size, region.angle) for region in detected]
    for target in expected:
        assert max(_rotated_iou(candidate, target) for candidate in actual) > 0.88


def test_v3_splits_touching_photos_at_a_narrow_background_gutter():
    expected = [
        ((528.0, 600.0), (480.0, 350.0), 0.0),
        ((1022.0, 600.0), (480.0, 350.0), 0.0),
    ]
    image = _procedural_album_scan(expected)

    detected = detect_photos_v3(image, inset=0)

    assert len(detected) == 2
    assert all(region.area_ratio > 0.07 for region in detected)


def test_v3_is_deterministic_across_concurrent_detection():
    rectangles = [
        ((410.0, 360.0), (490.0, 310.0), -4.0),
        ((1080.0, 760.0), (430.0, 300.0), 6.0),
    ]
    image = _procedural_album_scan(rectangles)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: detect_photos_v3(image, inset=0), range(4)))

    assert all(result == results[0] for result in results[1:])


def test_v4_accepts_rectangular_mask_that_expands_a_v3_content_box():
    proposal = ((100.0, 100.0), (90.0, 60.0), 0.0)
    mask = np.zeros((220, 220), dtype=np.uint8)
    cv2.rectangle(mask, (40, 55), (160, 145), 1, -1)

    refined = _v4_mask_rect(mask, proposal, predicted_iou=0.95)

    assert refined is not None
    assert refined[1][0] * refined[1][1] > proposal[1][0] * proposal[1][1] * 1.8


def test_v4_rejects_nonrectangular_object_mask_inside_photo():
    proposal = ((100.0, 100.0), (120.0, 90.0), 0.0)
    mask = np.zeros((220, 220), dtype=np.uint8)
    cv2.rectangle(mask, (65, 50), (90, 155), 1, -1)
    cv2.rectangle(mask, (90, 125), (155, 155), 1, -1)

    assert _v4_mask_rect(mask, proposal, predicted_iou=0.95) is None
