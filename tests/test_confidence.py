"""Tests for scan confidence flagging."""

import pytest

from scansplitter.confidence import Flag, evaluate_scan


def box(
    box_id: str,
    x: float,
    y: float,
    width: float = 100,
    height: float = 80,
    angle: float = 0,
) -> dict:
    return {"id": box_id, "x": x, "y": y, "width": width, "height": height, "angle": angle}


def codes(flags: list[Flag]) -> set[str]:
    return {flag.code for flag in flags}


def test_no_boxes_positive_and_negative() -> None:
    assert evaluate_scan([], 1000, 800) == [Flag("no_boxes", None, "No photos found")]
    assert "no_boxes" not in codes(evaluate_scan([box("one", 500, 400)], 1000, 800))


def test_touches_edge_positive_and_negative() -> None:
    flags = evaluate_scan([box("edge", 949, 400)], 1000, 800)
    assert Flag("touches_edge", "edge", "Box touches the right edge") in flags
    assert "touches_edge" not in codes(evaluate_scan([box("inside", 500, 400)], 1000, 800))


def test_rotated_corner_touches_edge_despite_unrotated_bounds_being_inside() -> None:
    candidate = box("rotated", 60, 400, width=100, height=100, angle=45)
    assert candidate["x"] - candidate["width"] / 2 > 0
    assert "touches_edge" in codes(evaluate_scan([candidate], 1000, 800))


def test_extreme_aspect_positive_and_negative() -> None:
    assert "extreme_aspect" in codes(
        evaluate_scan([box("wide", 500, 400, width=301, height=100)], 1000, 800)
    )
    assert "extreme_aspect" not in codes(
        evaluate_scan([box("normal", 500, 400, width=300, height=100)], 1000, 800)
    )


def test_area_outlier_positive_and_negative() -> None:
    outlier_boxes = [
        box("small", 150, 150, 40, 40),
        box("large-1", 450, 200, 100, 100),
        box("large-2", 750, 200, 100, 100),
    ]
    flags = evaluate_scan(outlier_boxes, 1000, 800)
    assert any(flag.code == "area_outlier" and flag.box_id == "small" for flag in flags)

    equal_boxes = [box("a", 150, 200), box("b", 500, 200), box("c", 850, 200)]
    assert "area_outlier" not in codes(evaluate_scan(equal_boxes, 1000, 800))


def test_overlap_positive_and_negative() -> None:
    overlapping = [box("a", 400, 400, 200, 200), box("b", 450, 400, 200, 200)]
    assert "overlap" in codes(evaluate_scan(overlapping, 1000, 800))

    separate = [box("a", 250, 400, 200, 200), box("b", 750, 400, 200, 200)]
    assert "overlap" not in codes(evaluate_scan(separate, 1000, 800))


@pytest.mark.parametrize("detected", [2, 5])
def test_count_mismatch_positive(detected: int) -> None:
    boxes = [box(str(index), 100 + index * 150, 400, 80, 80) for index in range(detected)]
    assert "count_mismatch" in codes(evaluate_scan(boxes, 1000, 800, expected_count=4))


def test_count_mismatch_negative() -> None:
    boxes = [box(str(index), 150 + index * 220, 400, 100, 80) for index in range(4)]
    assert "count_mismatch" not in codes(evaluate_scan(boxes, 1000, 800, expected_count=4))


def test_clean_multi_box_scan_has_no_flags() -> None:
    boxes = [
        box("top-left", 250, 220, 240, 160),
        box("top-right", 750, 220, 240, 160),
        box("bottom-left", 250, 580, 240, 160),
        box("bottom-right", 750, 580, 240, 160),
    ]
    assert evaluate_scan(boxes, 1000, 800, expected_count=4) == []
