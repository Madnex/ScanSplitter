"""Tests for whole-page Album Splitter detection."""

import cv2
import numpy as np
from PIL import Image

from scansplitter.album_detector import (
    _refine_leaf_from_border_background,
    _refine_page_rect_to_continuous_edges,
    _single_leaf_from_candidates,
    detect_album_pages,
)


def _rotated_iou(first: tuple, second: tuple) -> float:
    kind, points = cv2.rotatedRectangleIntersection(first, second)
    if kind == cv2.INTERSECT_NONE or points is None:
        return 0.0
    intersection = cv2.contourArea(points)
    first_area = first[1][0] * first[1][1]
    second_area = second[1][0] * second[1][1]
    return intersection / max(1.0, first_area + second_area - intersection)


def _album_photo(page_rect: tuple, size: tuple[int, int] = (1200, 900)) -> Image.Image:
    """Build a synthetic album page with photos and handwritten-like marks."""
    width, height = size
    canvas = np.full((height, width, 3), (80, 98, 125), dtype=np.uint8)
    page = cv2.boxPoints(page_rect).astype(np.int32)
    cv2.fillConvexPoly(canvas, page, (220, 211, 185))

    # Mounted prints are deliberately large, dark holes in the page color.
    cv2.rectangle(canvas, (330, 270), (570, 460), (55, 65, 75), -1)
    cv2.rectangle(canvas, (660, 310), (900, 520), (85, 80, 70), -1)
    cv2.putText(
        canvas,
        "Summer 1958",
        (390, 610),
        cv2.FONT_HERSHEY_SCRIPT_SIMPLEX,
        1.0,
        (80, 65, 105),
        3,
        cv2.LINE_AA,
    )
    return Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))


def test_detects_album_page_instead_of_mounted_photos():
    expected = ((610.0, 455.0), (920.0, 690.0), -3.0)
    image = _album_photo(expected)

    detected = detect_album_pages(image, layout="single")

    assert len(detected) == 1
    actual = (detected[0].center, detected[0].size, detected[0].angle)
    assert _rotated_iou(actual, expected) > 0.82


def test_auto_splits_an_unusually_wide_two_page_spread():
    spread = ((600.0, 400.0), (1000.0, 420.0), 0.0)
    image = _album_photo(spread, size=(1200, 800))

    detected = detect_album_pages(image, layout="auto")

    assert len(detected) == 2
    assert detected[0].center[0] < detected[1].center[0]
    assert all(0.17 < region.area_ratio < 0.30 for region in detected)
    assert all(abs(region.angle) < 5 for region in detected)


def test_single_layout_keeps_a_wide_spread_together():
    spread = ((600.0, 400.0), (1000.0, 420.0), 0.0)
    image = _album_photo(spread, size=(1200, 800))

    detected = detect_album_pages(image, layout="single")

    assert len(detected) == 1
    assert detected[0].area_ratio > 0.35


def test_spread_layout_splits_even_when_auto_would_keep_one_page():
    page = ((600.0, 450.0), (850.0, 650.0), 0.0)
    image = _album_photo(page)

    detected = detect_album_pages(image, layout="spread")

    assert len(detected) == 2
    assert sum(region.area for region in detected) == detected[0].area * 2


def test_single_leaf_fuses_outer_height_with_page_side_edges():
    outer = ((600.0, 450.0), (1100.0, 760.0), 0.0)
    # The page-color candidate is shortened vertically by mounted photos but
    # accurately identifies the spine and outside edge.
    page_candidate = ((760.0, 440.0), (560.0, 640.0), -2.0)
    translucent_leaf = ((180.0, 450.0), (360.0, 760.0), 0.0)

    fused = _single_leaf_from_candidates(
        [(2.8, page_candidate), (2.2, translucent_leaf)], outer
    )

    assert fused is not None
    assert abs(fused[0][0] - 760.0) < 15
    assert fused[1][0] > 560.0
    assert fused[1][1] == outer[1][1]
    assert fused[2] == 0.0


def test_continuous_edge_refinement_ignores_mounted_photo_border():
    gray = np.full((900, 1200), 65, dtype=np.uint8)
    cv2.rectangle(gray, (250, 100), (950, 800), 215, -1)
    # A much darker internal border is strong but does not span the leaf.
    cv2.rectangle(gray, (390, 260), (880, 610), 25, 12)
    candidate = ((605.0, 450.0), (590.0, 660.0), 0.0)

    refined = _refine_page_rect_to_continuous_edges(
        gray, candidate, search_margin_ratio=0.12
    )

    left = refined[0][0] - refined[1][0] / 2
    right = refined[0][0] + refined[1][0] / 2
    assert abs(left - 250) < 8
    assert abs(right - 950) < 8


def test_border_background_recovers_faint_page_edge_before_strong_background_line():
    rng = np.random.default_rng(7)
    rgb = np.full((900, 1200, 3), (115, 105, 145), dtype=np.int16)
    rgb += rng.integers(-5, 6, rgb.shape, dtype=np.int16)
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    page = np.full((741, 651, 3), (218, 210, 188), dtype=np.int16)
    page += rng.integers(-7, 8, page.shape, dtype=np.int16)
    rgb[80:821, 250:901] = np.clip(page, 0, 255).astype(np.uint8)
    cv2.rectangle(rgb, (330, 220), (610, 480), (35, 45, 55), -1)
    cv2.rectangle(rgb, (1040, 0), (1100, 899), (20, 22, 25), -1)
    rough = ((625.0, 450.0), (750.0, 740.0), 0.0)

    refined = _refine_leaf_from_border_background(rgb, rough)

    right = refined[0][0] + refined[1][0] / 2
    assert right < 930
    assert refined[1][0] < rough[1][0] * 0.90
