"""Configurable removal of scan background left around a cropped photo.

The detector works on a complete scan and deliberately prefers a slightly
generous box over clipping the photograph.  This module solves the smaller
follow-up problem: after that box has been deskewed and cropped, identify a
light, low-variation border that is connected to an outer edge and trim it.

Ambiguous sides are left untouched.  The implementation is intentionally
classical and deterministic so archival exports never depend on a generated
or reconstructed image.
"""

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from PIL import Image

EdgeCleanupMode = Literal["off", "conservative", "tight"]


@dataclass(frozen=True)
class _SideLine:
    """Inward depth as ``slope * position + intercept`` for one crop side."""

    slope: float
    intercept: float
    confidence: float


@dataclass(frozen=True)
class EdgeCleanupDetail:
    """A compact description suitable for previews, manifests, and tests."""

    applied: bool
    sides: tuple[str, ...]
    removed_fraction: float


@dataclass(frozen=True)
class _CleanupConfig:
    max_depth_ratio: float
    max_depth_pixels: int
    seed_depth_max: int
    corner_margin_ratio: float
    min_lightness: float
    max_seed_variation: float
    max_chroma: float
    partial_seed_fraction: float
    expanded_color_distance: float
    color_threshold_max: float
    morphology_size: int
    candidate_support: float
    line_support: float
    max_slope: float
    transition_floor: float
    transition_factor: float
    safety_percentile: float
    safety_inset: float
    include_candidate_outliers: bool
    allow_axis_fallback: bool
    confidence_floor: float
    max_removed_fraction: float


_CONSERVATIVE = _CleanupConfig(
    max_depth_ratio=0.10,
    max_depth_pixels=256,
    seed_depth_max=6,
    corner_margin_ratio=0.06,
    min_lightness=155,
    max_seed_variation=24,
    max_chroma=48,
    partial_seed_fraction=0.0,
    expanded_color_distance=26,
    color_threshold_max=26,
    morphology_size=3,
    candidate_support=0.55,
    line_support=0.52,
    max_slope=0.18,
    transition_floor=7,
    transition_factor=0.4,
    safety_percentile=92,
    safety_inset=0.5,
    include_candidate_outliers=False,
    allow_axis_fallback=False,
    confidence_floor=0.38,
    max_removed_fraction=0.28,
)

_TIGHT = _CleanupConfig(
    max_depth_ratio=0.22,
    max_depth_pixels=512,
    seed_depth_max=2,
    corner_margin_ratio=0.02,
    min_lightness=135,
    max_seed_variation=48,
    max_chroma=62,
    partial_seed_fraction=0.18,
    expanded_color_distance=48,
    color_threshold_max=34,
    morphology_size=5,
    candidate_support=0.26,
    line_support=0.24,
    max_slope=0.30,
    transition_floor=5,
    transition_factor=0.25,
    safety_percentile=99,
    safety_inset=2.0,
    include_candidate_outliers=True,
    allow_axis_fallback=True,
    confidence_floor=0.15,
    max_removed_fraction=0.48,
)


def _connected_boundary_mask(mask: np.ndarray) -> np.ndarray:
    """Keep only matching pixels connected to the outermost row."""
    count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    if count <= 1:
        return np.zeros_like(mask, dtype=bool)
    touching = np.unique(labels[0, :])
    touching = touching[touching != 0]
    if touching.size == 0:
        return np.zeros_like(mask, dtype=bool)
    return np.isin(labels, touching)


def _estimate_side(
    oriented_lab: np.ndarray,
    minimum_dimension: int,
    config: _CleanupConfig,
) -> _SideLine | None:
    """Estimate one edge after arranging it as depth × distance-along-edge."""
    available_depth, span = oriented_lab.shape[:2]
    max_depth = min(
        max(4, round(minimum_dimension * config.max_depth_ratio)),
        config.max_depth_pixels,
        available_depth - 2,
    )
    if max_depth < 4 or span < 32:
        return None

    band = oriented_lab[: max_depth + 2].astype(np.float32)
    corner_margin = max(1, round(span * config.corner_margin_ratio))
    usable = slice(corner_margin, span - corner_margin)
    if usable.stop - usable.start < 24:
        return None

    seed_depth = min(
        max(2, round(minimum_dimension * 0.003)),
        config.seed_depth_max,
        max_depth // 2,
    )
    seed = band[:seed_depth, usable].reshape(-1, 3)
    seed_chroma = np.linalg.norm(seed[:, 1:] - 128.0, axis=1)
    if config.partial_seed_fraction > 0:
        # A partial wedge may cover less than half of the side, so a plain
        # median would learn the photograph instead of its white fringe.
        # Build the tight-mode model from the brightest low-chroma cluster.
        lightness_floor = max(
            config.min_lightness,
            float(np.percentile(seed[:, 0], 70)),
        )
        paper_seed = (seed[:, 0] >= lightness_floor) & (
            seed_chroma <= config.max_chroma
        )
        if float(np.mean(paper_seed)) < config.partial_seed_fraction:
            return None
        model_seed = seed[paper_seed]
    else:
        model_seed = seed
    background = np.median(model_seed, axis=0)
    seed_distance = np.linalg.norm(model_seed - background, axis=1)

    # Both automatic modes target paper/whitespace. Dark scanner beds and
    # intentional black photo borders are too easy to confuse with image
    # content and are therefore not auto-trimmed; tight merely lowers the
    # lightness floor for aged paper.
    if (
        float(background[0]) < config.min_lightness
        or float(np.percentile(seed_distance, 90)) > config.max_seed_variation
    ):
        return None

    color_threshold = float(
        np.clip(np.percentile(seed_distance, 85) + 7, 10, config.color_threshold_max)
    )
    distance = np.linalg.norm(band - background, axis=2)
    similar = distance <= color_threshold
    if config.partial_seed_fraction > 0:
        band_chroma = np.linalg.norm(band[:, :, 1:] - 128.0, axis=2)
        varied_paper = (band[:, :, 0] >= config.min_lightness) & (
            band_chroma <= config.max_chroma
        )
        similar |= varied_paper & (distance <= config.expanded_color_distance)
    similar = similar.astype(np.uint8)
    similar = cv2.morphologyEx(
        similar,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (config.morphology_size, config.morphology_size),
        ),
    )
    connected = _connected_boundary_mask(similar)

    extents = np.full(span, -1, dtype=np.int32)
    for position in range(usable.start, usable.stop):
        rows = np.flatnonzero(connected[: max_depth + 1, position])
        if rows.size:
            extents[position] = int(rows[-1])

    positions = np.arange(span)
    candidate = (positions >= usable.start) & (positions < usable.stop)
    candidate &= extents >= max(1, seed_depth - 1)
    candidate &= extents < max_depth

    # A genuine border should finish at a visible color/texture transition.
    # Requiring that transition prevents a uniform bright region inside the
    # photograph from being treated as whitespace merely because it touches
    # one side.
    transition = np.zeros(span, dtype=np.float32)
    valid_positions = np.flatnonzero(candidate)
    for position in valid_positions:
        depth = int(extents[position])
        before = band[max(0, depth - 1), position]
        after = band[min(max_depth + 1, depth + 2), position]
        transition[position] = float(np.linalg.norm(after - before))
    candidate &= transition >= max(
        config.transition_floor,
        color_threshold * config.transition_factor,
    )

    usable_count = usable.stop - usable.start
    if int(candidate.sum()) < max(20, round(usable_count * config.candidate_support)):
        return None

    x = positions[candidate].astype(np.float64)
    y = extents[candidate].astype(np.float64) + 1.0
    inliers = np.ones(x.size, dtype=bool)
    slope = 0.0
    intercept = float(np.median(y))
    for _ in range(3):
        if int(inliers.sum()) < 16:
            return None
        slope, intercept = np.polyfit(x[inliers], y[inliers], 1)
        residual = y - (slope * x + intercept)
        median = float(np.median(residual[inliers]))
        mad = float(np.median(np.abs(residual[inliers] - median)))
        tolerance = max(2.0, 3.5 * 1.4826 * mad)
        inliers = np.abs(residual - median) <= tolerance

    support = float(inliers.sum() / usable_count)
    if support < config.line_support or abs(float(slope)) > config.max_slope:
        return None

    # Shift the fitted line inward far enough to cover almost all of a wavy
    # edge.  Very isolated deep points remain outliers and cannot consume a
    # large strip of the photograph.
    if config.include_candidate_outliers:
        residual = y - (slope * x + intercept)
    else:
        residual = y[inliers] - (slope * x[inliers] + intercept)
    intercept += (
        max(0.0, float(np.percentile(residual, config.safety_percentile)))
        + config.safety_inset
    )
    predicted = slope * np.array([usable.start, usable.stop - 1]) + intercept
    if float(np.min(predicted)) < 1 or float(np.max(predicted)) > max_depth * 0.95:
        if not config.allow_axis_fallback:
            return None
        slope = 0.0
        intercept = float(np.percentile(y, config.safety_percentile)) + config.safety_inset
        predicted = np.array([intercept, intercept])
        if float(np.max(predicted)) > min(max_depth * 0.95, minimum_dimension * 0.08):
            return None

    transition_score = min(1.0, float(np.median(transition[candidate])) / 32.0)
    confidence = round(min(1.0, support * 1.25) * transition_score, 3)
    if confidence < config.confidence_floor:
        return None
    return _SideLine(float(slope), float(intercept), confidence)


def _intersection(horizontal: tuple[float, float], vertical: tuple[float, float]) -> np.ndarray:
    """Intersect ``y = mh*x+bh`` with ``x = mv*y+bv``."""
    mh, bh = horizontal
    mv, bv = vertical
    denominator = 1.0 - mv * mh
    if abs(denominator) < 1e-6:
        raise ValueError("Edge lines are parallel")
    x = (mv * bh + bv) / denominator
    return np.array([x, mh * x + bh], dtype=np.float32)


def _cleanup_once(
    image: Image.Image,
    config: _CleanupConfig,
) -> tuple[Image.Image, EdgeCleanupDetail]:
    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    minimum_dimension = min(width, height)
    unchanged = EdgeCleanupDetail(False, (), 0.0)
    if minimum_dimension < 48:
        return image, unchanged

    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    oriented = {
        "top": lab,
        "right": np.transpose(lab[:, ::-1], (1, 0, 2)),
        "bottom": lab[::-1],
        "left": np.transpose(lab, (1, 0, 2)),
    }
    estimates = {
        side: _estimate_side(values, minimum_dimension, config)
        for side, values in oriented.items()
    }
    applied_sides = tuple(side for side, line in estimates.items() if line is not None)
    if not applied_sides:
        return image, unchanged

    top = estimates["top"] or _SideLine(0.0, 0.0, 0.0)
    bottom = estimates["bottom"] or _SideLine(0.0, 0.0, 0.0)
    left = estimates["left"] or _SideLine(0.0, 0.0, 0.0)
    right = estimates["right"] or _SideLine(0.0, 0.0, 0.0)

    top_line = (top.slope, top.intercept)
    bottom_line = (-bottom.slope, height - 1 - bottom.intercept)
    left_line = (left.slope, left.intercept)
    right_line = (-right.slope, width - 1 - right.intercept)
    try:
        source = np.array(
            [
                _intersection(top_line, left_line),
                _intersection(top_line, right_line),
                _intersection(bottom_line, right_line),
                _intersection(bottom_line, left_line),
            ],
            dtype=np.float32,
        )
    except ValueError:
        return image, unchanged

    if not np.isfinite(source).all():
        return image, unchanged
    if (
        source[:, 0].min() < -1
        or source[:, 1].min() < -1
        or source[:, 0].max() > width
        or source[:, 1].max() > height
    ):
        return image, unchanged

    top_width = float(np.linalg.norm(source[1] - source[0]))
    bottom_width = float(np.linalg.norm(source[2] - source[3]))
    left_height = float(np.linalg.norm(source[3] - source[0]))
    right_height = float(np.linalg.norm(source[2] - source[1]))
    output_width = int(round(max(top_width, bottom_width)))
    output_height = int(round(max(left_height, right_height)))
    if output_width < 32 or output_height < 32:
        return image, unchanged

    output_area = output_width * output_height
    removed_fraction = 1.0 - output_area / float(width * height)
    if removed_fraction <= 0 or removed_fraction > config.max_removed_fraction:
        return image, unchanged

    destination = np.array(
        [
            [0, 0],
            [output_width - 1, 0],
            [output_width - 1, output_height - 1],
            [0, output_height - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source, destination)
    cleaned = cv2.warpPerspective(
        rgb,
        transform,
        (output_width, output_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    detail = EdgeCleanupDetail(True, applied_sides, round(removed_fraction, 4))
    return Image.fromarray(cleaned), detail


def cleanup_photo_edges(
    image: Image.Image,
    mode: EdgeCleanupMode = "conservative",
) -> tuple[Image.Image, EdgeCleanupDetail]:
    """Remove crop-edge whitespace according to the selected mode.

    ``conservative`` performs one confidence-gated pass intended to remove
    only scan or album background. ``tight`` allows deeper candidates and up
    to three passes, so an outer page border and a second white print margin
    can both be removed. ``off`` returns the original object unchanged.
    """
    unchanged = EdgeCleanupDetail(False, (), 0.0)
    if mode == "off":
        return image, unchanged
    if mode not in {"conservative", "tight"}:
        raise ValueError(f"Unknown edge cleanup mode: {mode}")

    config = _CONSERVATIVE if mode == "conservative" else _TIGHT
    maximum_passes = 1 if mode == "conservative" else 3
    current = image
    all_sides: list[str] = []
    original_area = image.width * image.height
    for _ in range(maximum_passes):
        cleaned, detail = _cleanup_once(current, config)
        if not detail.applied:
            break
        cumulative_removed = 1.0 - (cleaned.width * cleaned.height) / float(original_area)
        if cumulative_removed > config.max_removed_fraction:
            break
        current = cleaned
        all_sides.extend(detail.sides)

    if current is image:
        return image, unchanged
    final_area = current.width * current.height
    removed_fraction = 1.0 - final_area / float(original_area)
    return current, EdgeCleanupDetail(
        True,
        tuple(dict.fromkeys(all_sides)),
        round(removed_fraction, 4),
    )
