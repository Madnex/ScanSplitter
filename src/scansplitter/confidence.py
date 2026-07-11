"""Confidence flagging for detected scan regions."""

import math
import statistics
from dataclasses import dataclass

EDGE_TOLERANCE_RATIO = 0.005
EXTREME_ASPECT_RATIO = 3.0
AREA_OUTLIER_RATIO = 0.35
AREA_OUTLIER_MIN_BOXES = 3
OVERLAP_IOU_THRESHOLD = 0.15


@dataclass(frozen=True)
class Flag:
    """A reason that a detected scan needs human review."""

    code: str
    box_id: str | None
    message: str


def _rotated_corners(box: dict) -> list[tuple[float, float]]:
    """Return corners at the center plus rotated signed half-extents."""
    center_x = float(box["x"])
    center_y = float(box["y"])
    half_width = float(box["width"]) / 2
    half_height = float(box["height"]) / 2
    angle = math.radians(float(box["angle"]))
    cosine = math.cos(angle)
    sine = math.sin(angle)

    return [
        (
            center_x + local_x * cosine - local_y * sine,
            center_y + local_x * sine + local_y * cosine,
        )
        for local_x, local_y in (
            (-half_width, -half_height),
            (half_width, -half_height),
            (half_width, half_height),
            (-half_width, half_height),
        )
    ]


def _bounding_rect(box: dict) -> tuple[float, float, float, float]:
    corners = _rotated_corners(box)
    x_coordinates = [corner[0] for corner in corners]
    y_coordinates = [corner[1] for corner in corners]
    return (
        min(x_coordinates),
        min(y_coordinates),
        max(x_coordinates),
        max(y_coordinates),
    )


def _intersection_over_union(first: dict, second: dict) -> float:
    first_left, first_top, first_right, first_bottom = _bounding_rect(first)
    second_left, second_top, second_right, second_bottom = _bounding_rect(second)
    intersection_width = max(0.0, min(first_right, second_right) - max(first_left, second_left))
    intersection_height = max(
        0.0, min(first_bottom, second_bottom) - max(first_top, second_top)
    )
    intersection_area = intersection_width * intersection_height
    first_area = max(0.0, first_right - first_left) * max(0.0, first_bottom - first_top)
    second_area = max(0.0, second_right - second_left) * max(
        0.0, second_bottom - second_top
    )
    union_area = first_area + second_area - intersection_area
    return intersection_area / union_area if union_area else 0.0


def evaluate_scan(
    boxes: list[dict],
    image_width: int,
    image_height: int,
    expected_count: int | None = None,
) -> list[Flag]:
    """Evaluate detected boxes and return every confidence warning."""
    flags: list[Flag] = []

    if not boxes:
        flags.append(Flag("no_boxes", None, "No photos found"))

    edge_tolerance = min(image_width, image_height) * EDGE_TOLERANCE_RATIO
    for box in boxes:
        box_id = str(box["id"])
        corners = _rotated_corners(box)
        touched_edges = []
        if any(x <= edge_tolerance for x, _ in corners):
            touched_edges.append("left")
        if any(x >= image_width - edge_tolerance for x, _ in corners):
            touched_edges.append("right")
        if any(y <= edge_tolerance for _, y in corners):
            touched_edges.append("top")
        if any(y >= image_height - edge_tolerance for _, y in corners):
            touched_edges.append("bottom")
        for edge in touched_edges:
            flags.append(Flag("touches_edge", box_id, f"Box touches the {edge} edge"))

        width = float(box["width"])
        height = float(box["height"])
        shorter_side = min(width, height)
        aspect_ratio = max(width, height) / shorter_side if shorter_side > 0 else math.inf
        if aspect_ratio > EXTREME_ASPECT_RATIO:
            flags.append(
                Flag("extreme_aspect", box_id, f"Box has an extreme {aspect_ratio:.1f}:1 aspect ratio")
            )

    if len(boxes) >= AREA_OUTLIER_MIN_BOXES:
        areas = [float(box["width"]) * float(box["height"]) for box in boxes]
        median_area = statistics.median(areas)
        for box, area in zip(boxes, areas, strict=True):
            if area < median_area * AREA_OUTLIER_RATIO:
                flags.append(
                    Flag("area_outlier", str(box["id"]), "Box is much smaller than the others")
                )

    for first_index, first in enumerate(boxes):
        for second in boxes[first_index + 1 :]:
            iou = _intersection_over_union(first, second)
            if iou > OVERLAP_IOU_THRESHOLD:
                flags.append(
                    Flag(
                        "overlap",
                        str(first["id"]),
                        f"Box overlaps box {second['id']} ({iou:.0%} overlap)",
                    )
                )

    if expected_count is not None and len(boxes) != expected_count:
        qualifier = "Only " if len(boxes) < expected_count else ""
        flags.append(
            Flag(
                "count_mismatch",
                None,
                f"{qualifier}{len(boxes)} photos found where most scans have {expected_count}",
            )
        )

    return flags
