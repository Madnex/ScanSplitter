"""Whole-page detection for photographed physical photo albums.

Unlike the photo detectors in :mod:`scansplitter.detector`, this module treats
the album leaf as the object and deliberately ignores photographs, captions,
and other content inside it.  The detector is classical OpenCV so Album
Splitter remains available without downloading an ML model.
"""

import threading
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from .detector import DetectedRegion, RotatedRect, _refine_rect_to_edges

AlbumLayout = Literal["auto", "single", "spread"]

_kmeans_lock = threading.Lock()
_MAX_WORKING_DIMENSION = 1800


def _normalized_rect(rect: RotatedRect) -> RotatedRect:
    """Return a rectangle whose width follows its visually longer axis."""
    center, (width, height), angle = rect
    if width < height:
        return center, (height, width), angle + 90.0
    return center, (width, height), angle


def _upright_rect(rect: RotatedRect) -> RotatedRect:
    """Represent identical geometry with an angle nearest the camera horizon.

    This preserves a portrait page as portrait when auto-rotation is disabled;
    OpenCV otherwise tends to describe it as a wide rectangle rotated 90°.
    """
    center, (width, height), angle = rect
    while angle >= 45.0:
        angle -= 90.0
        width, height = height, width
    while angle < -45.0:
        angle += 90.0
        width, height = height, width
    return center, (width, height), angle


def _nearest_center_labels(
    pixels: np.ndarray,
    centers: np.ndarray,
    shape: tuple[int, int],
) -> np.ndarray:
    """Assign Lab pixels without allocating an image×clusters×channels cube."""
    best_distance = np.full(len(pixels), np.inf, dtype=np.float32)
    labels = np.zeros(len(pixels), dtype=np.uint8)
    for index, center in enumerate(centers):
        delta = pixels - center
        distance = np.einsum("ij,ij->i", delta, delta)
        closer = distance < best_distance
        best_distance[closer] = distance[closer]
        labels[closer] = index
    return labels.reshape(shape)


def _surface_candidates(rgb: np.ndarray) -> list[tuple[float, RotatedRect]]:
    """Find large, rectangular color surfaces that could be an album page.

    Album pages may be cream, black, or colored.  K-means therefore supplies
    several possible surface colors instead of hard-coding "white paper".
    Broad morphology reconnects a surface across mounted photos and writing.
    Candidate scoring rejects the surrounding table/floor, which normally
    forms a frame touching most image corners rather than a centered sheet.
    """
    height, width = rgb.shape[:2]
    image_area = float(width * height)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)

    stride = max(1, int(np.sqrt(image_area / 45_000)))
    sampled = lab[::stride, ::stride].reshape(-1, 3).astype(np.float32)
    cluster_count = min(7, max(2, len(sampled)))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.4)
    center_sets: list[np.ndarray] = []
    with _kmeans_lock:
        # Several fixed starts are intentional: page paper can be a smaller
        # color population than photographs or the surrounding surface.  A
        # single K-means start sometimes merges it away.  Keeping every fixed
        # start supplies candidates without making the output nondeterministic.
        for seed in (3, 11, 29):
            cv2.setRNGSeed(seed)
            _, _, centers = cv2.kmeans(
                sampled,
                cluster_count,
                None,
                criteria,
                1,
                cv2.KMEANS_PP_CENTERS,
            )
            center_sets.append(centers)

    flat = lab.reshape(-1, 3).astype(np.float32)

    close_width = max(13, round(width * 0.055)) | 1
    close_height = max(13, round(height * 0.055)) | 1
    close_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (close_width, close_height)
    )
    open_size = max(5, round(min(width, height) * 0.012)) | 1
    open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_size, open_size))

    candidates: list[tuple[float, RotatedRect]] = []
    for centers in center_sets:
        labels = _nearest_center_labels(flat, centers, (height, width))
        for cluster_index in range(len(centers)):
            mask = np.where(labels == cluster_index, 255, 0).astype(np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                contour_area = cv2.contourArea(contour)
                if contour_area < image_area * 0.10:
                    continue
                rect = _normalized_rect(cv2.minAreaRect(contour))
                rect_area = rect[1][0] * rect[1][1]
                area_ratio = rect_area / image_area
                if not 0.16 <= area_ratio <= 0.985:
                    continue

                fill = contour_area / max(1.0, rect_area)
                if fill < 0.42:
                    continue

                cx, cy = rect[0]
                center_distance = np.hypot(cx - width / 2, cy - height / 2)
                center_score = 1.0 - min(
                    1.0, center_distance / np.hypot(width / 2, height / 2)
                )

                points = cv2.boxPoints(rect)
                margin = max(2, round(min(width, height) * 0.015))
                corner_contacts = sum(
                    (x <= margin or x >= width - margin)
                    and (y <= margin or y >= height - margin)
                    for x, y in points
                )
                # Pages are large, centrally relevant, and mostly rectangular.
                # A cluster representing the exterior background commonly spans
                # almost the entire frame and hits all four corners.
                score = (
                    area_ratio * 3.0
                    + fill * 1.7
                    + center_score
                    - corner_contacts * 0.22
                )
                if area_ratio > 0.94:
                    score -= (area_ratio - 0.94) * 12.0
                candidates.append((score, rect))

    return candidates


def _edge_fallback(gray: np.ndarray) -> RotatedRect | None:
    """Find a page-like outer contour when its surface color is fragmented."""
    height, width = gray.shape
    image_area = float(width * height)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (7, 7), 0), 35, 110)
    kernel_size = max(7, round(min(width, height) * 0.018)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    joined = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best: tuple[float, RotatedRect] | None = None
    for contour in contours:
        rect = _normalized_rect(cv2.minAreaRect(contour))
        rect_area = rect[1][0] * rect[1][1]
        ratio = rect_area / image_area
        if not 0.16 <= ratio <= 0.985:
            continue
        hull_area = cv2.contourArea(cv2.convexHull(contour))
        rectangularity = hull_area / max(1.0, rect_area)
        if rectangularity < 0.45:
            continue
        score = ratio * 2.0 + rectangularity
        if best is None or score > best[0]:
            best = score, rect
    return best[1] if best else None


def _split_spread(rect: RotatedRect) -> list[RotatedRect]:
    """Split a normalized outer spread into its left and right page boxes."""
    (cx, cy), (width, height), angle = _normalized_rect(rect)
    theta = np.deg2rad(angle)
    width_axis = np.array([np.cos(theta), np.sin(theta)])
    quarter_offset = width_axis * (width / 4.0)
    page_size = (width / 2.0, height)
    return [
        ((float(cx - quarter_offset[0]), float(cy - quarter_offset[1])), page_size, angle),
        ((float(cx + quarter_offset[0]), float(cy + quarter_offset[1])), page_size, angle),
    ]


def _single_leaf_from_candidates(
    candidates: list[tuple[float, RotatedRect]],
    outer: RotatedRect,
) -> RotatedRect | None:
    """Fuse full-height outer edges with a credible single-page candidate.

    An open album often contains a translucent interleaf beside the actual
    page.  Color clustering sees the complete album assembly (excellent top
    and bottom edges) and, separately, the content-bearing leaf (excellent
    spine and outer-side edges).  Combining their reliable axes produces the
    physical page the user expects without trimming around its mounted photos.
    """
    outer = _upright_rect(outer)
    (outer_cx, outer_cy), (outer_width, outer_height), outer_angle = outer
    theta = np.deg2rad(outer_angle)
    width_axis = np.array([np.cos(theta), np.sin(theta)], dtype=np.float32)
    height_axis = np.array([-np.sin(theta), np.cos(theta)], dtype=np.float32)
    outer_center = np.array([outer_cx, outer_cy], dtype=np.float32)

    best: tuple[float, float, float] | None = None
    for detector_score, raw_candidate in candidates:
        candidate = _upright_rect(raw_candidate)
        angle_delta = ((candidate[2] - outer_angle + 45.0) % 90.0) - 45.0
        if abs(angle_delta) > 10.0:
            continue

        points = cv2.boxPoints(candidate).astype(np.float32) - outer_center
        horizontal = points @ width_axis
        vertical = points @ height_axis
        left, right = float(horizontal.min()), float(horizontal.max())
        top, bottom = float(vertical.min()), float(vertical.max())
        width_ratio = (right - left) / max(1.0, outer_width)
        height_ratio = (bottom - top) / max(1.0, outer_height)
        if not 0.35 <= width_ratio <= 0.78 or height_ratio < 0.65:
            continue

        # The detector's own score distinguishes a content-bearing paper
        # surface from an empty/translucent leaf.  Coverage rewards candidates
        # whose evidence spans most of the page height.
        score = float(detector_score) + height_ratio
        if best is None or score > best[0]:
            best = score, left, right

    if best is None:
        return None

    _, left, right = best
    left = max(-outer_width / 2.0, left)
    right = min(outer_width / 2.0, right)
    if right - left < outer_width * 0.35:
        return None

    local_center = width_axis * ((left + right) / 2.0)
    center = outer_center + local_center
    return (
        (float(center[0]), float(center[1])),
        (float(right - left), float(outer_height)),
        float(outer_angle),
    )


def _refine_page_rect_to_continuous_edges(
    gray: np.ndarray,
    rect: RotatedRect,
    search_margin_ratio: float = 0.08,
) -> RotatedRect:
    """Snap a page rectangle to long edges rather than mounted-photo edges.

    A mean gradient alone is easily dominated by a high-contrast photograph
    inside a pale album page.  The lower-quartile gradient measures how much
    of a candidate line remains visible along the *whole* leaf.  Combining it
    with a smaller mean-gradient term still handles stained or partly hidden
    page edges.  The top boundary includes the outside shoulder of a broad
    perspective edge so the physical cover is not clipped.
    """
    (center_x, center_y), (width, height), angle = _upright_rect(rect)
    if width < 20 or height < 20:
        return rect

    margin = int(np.clip(round(min(width, height) * search_margin_ratio), 10, 240))
    patch_width = max(3, round(width) + 2 * margin)
    patch_height = max(3, round(height) + 2 * margin)
    theta = np.deg2rad(angle)
    width_axis = np.array([np.cos(theta), np.sin(theta)])
    height_axis = np.array([-np.sin(theta), np.cos(theta)])
    transform = np.array(
        [
            [
                width_axis[0],
                height_axis[0],
                center_x
                - width_axis[0] * patch_width / 2
                - height_axis[0] * patch_height / 2,
            ],
            [
                width_axis[1],
                height_axis[1],
                center_y
                - width_axis[1] * patch_width / 2
                - height_axis[1] * patch_height / 2,
            ],
        ],
        dtype=np.float32,
    )
    patch = cv2.warpAffine(
        gray,
        transform,
        (patch_width, patch_height),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )
    patch = cv2.GaussianBlur(patch, (3, 3), 0)

    inset_x = max(3, round(width * 0.025))
    inset_y = max(3, round(height * 0.025))
    y_slice = slice(margin + inset_y, patch_height - margin - inset_y)
    x_slice = slice(margin + inset_x, patch_width - margin - inset_x)

    gradient_x = np.abs(cv2.Sobel(patch, cv2.CV_16S, 1, 0, ksize=3)).astype(
        np.float32
    )
    x_values = gradient_x[y_slice]
    x_mean = np.mean(x_values, axis=0)
    x_quartile = np.percentile(x_values, 25, axis=0)
    del gradient_x, x_values

    gradient_y = np.abs(cv2.Sobel(patch, cv2.CV_16S, 0, 1, ksize=3)).astype(
        np.float32
    )
    y_values = gradient_y[:, x_slice]
    y_mean = np.mean(y_values, axis=1)
    y_quartile = np.percentile(y_values, 25, axis=1)
    del gradient_y, y_values

    def smooth(profile: np.ndarray) -> np.ndarray:
        return cv2.GaussianBlur(profile.reshape(1, -1), (0, 0), 2.0).ravel()

    x_mean, x_quartile = smooth(x_mean), smooth(x_quartile)
    y_mean, y_quartile = smooth(y_mean), smooth(y_quartile)

    def continuous_edge(
        mean_profile: np.ndarray,
        quartile_profile: np.ndarray,
        expected: float,
        outward: int,
        include_outer_shoulder: bool = False,
    ) -> int:
        expected_index = int(round(expected))
        start = max(0, expected_index - margin)
        stop = min(len(mean_profile), expected_index + margin + 1)
        if stop <= start:
            return expected_index

        mean_band = mean_profile[start:stop]
        quartile_band = quartile_profile[start:stop]
        combined = quartile_band + mean_band * 0.20
        # A small distance penalty prevents two similarly continuous parallel
        # lines (for example a cover seam) from pulling the result away from
        # the surface candidate that identified this leaf.
        distance = np.abs(np.arange(start, stop) - expected_index) / max(1, margin)
        combined -= float(np.max(combined)) * 0.08 * distance
        relative_peak = int(np.argmax(combined))
        peak = start + relative_peak

        baseline = float(np.median(combined))
        peak_value = float(combined[relative_peak])
        deviation = float(np.median(np.abs(combined - baseline)))
        if peak_value < 5.0 or peak_value < baseline + max(2.5, 2.5 * deviation):
            return expected_index

        if not include_outer_shoulder:
            return peak

        # Include the outside shoulder of a broad/slanted page edge instead
        # of cutting through its strongest (central) gradient row or column.
        mean_threshold = float(mean_profile[peak]) * 0.65
        quartile_threshold = float(quartile_profile[peak]) * 0.80
        shoulder = peak
        while 0 <= shoulder + outward < len(mean_profile):
            candidate = shoulder + outward
            if (
                mean_profile[candidate] < mean_threshold
                or quartile_profile[candidate] < quartile_threshold
            ):
                break
            shoulder = candidate
        return shoulder

    left = continuous_edge(x_mean, x_quartile, margin, -1)
    right = continuous_edge(x_mean, x_quartile, margin + width, 1)
    # Perspective often turns the top cover edge into a wide diagonal band.
    # Preserve its leading shoulder so the axis-aligned crop contains it all.
    top = continuous_edge(
        y_mean, y_quartile, margin, -1, include_outer_shoulder=True
    )
    bottom = continuous_edge(y_mean, y_quartile, margin + height, 1)
    refined_width = float(right - left)
    refined_height = float(bottom - top)
    if refined_width <= width * 0.70 or refined_height <= height * 0.70:
        return rect

    local_shift_x = (left + right - patch_width) / 2
    local_shift_y = (top + bottom - patch_height) / 2
    refined_center = (
        float(center_x + width_axis[0] * local_shift_x + height_axis[0] * local_shift_y),
        float(center_y + width_axis[1] * local_shift_x + height_axis[1] * local_shift_y),
    )
    return refined_center, (refined_width, refined_height), float(angle)


def _refine_leaf_from_border_background(
    rgb: np.ndarray,
    rect: RotatedRect,
) -> RotatedRect:
    """Use border-connected colors to recover faint exterior page edges.

    A pale page against a pale table may have a weaker gradient than objects
    farther into the background.  Color clusters sampled along the relevant
    camera-frame border identify *all* exterior colors (for example a purple
    table plus a dark wall).  Their aggregate transition supplies a second,
    independent page-edge estimate.  Low-contrast or internal sides simply do
    not meet the reliability checks and retain the surface candidate.

    The method intentionally handles only modest camera tilt.  More strongly
    rotated pages already receive a useful angle from their surface contour,
    while axis-aligned profiles would be inappropriate for them.
    """
    rect = _upright_rect(rect)
    (center_x, center_y), (width, height), angle = rect
    image_height, image_width = rgb.shape[:2]
    if width < 40 or height < 40 or abs(angle) > 6.0:
        return rect

    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    image_area = image_width * image_height
    stride = max(1, int(np.sqrt(image_area / 45_000)))
    sampled = lab[::stride, ::stride].reshape(-1, 3).astype(np.float32)
    cluster_count = min(7, max(2, len(sampled)))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.4)
    with _kmeans_lock:
        cv2.setRNGSeed(17)
        _, _, centers = cv2.kmeans(
            sampled,
            cluster_count,
            None,
            criteria,
            1,
            cv2.KMEANS_PP_CENTERS,
        )
    labels = _nearest_center_labels(
        lab.reshape(-1, 3).astype(np.float32),
        centers,
        (image_height, image_width),
    )

    points = cv2.boxPoints(rect)
    raw_left = int(np.clip(np.floor(points[:, 0].min()), 0, image_width - 1))
    raw_right = int(np.clip(np.ceil(points[:, 0].max()), 1, image_width))
    raw_top = int(np.clip(np.floor(points[:, 1].min()), 0, image_height - 1))
    raw_bottom = int(np.clip(np.ceil(points[:, 1].max()), 1, image_height))
    margin = int(np.clip(round(min(width, height) * 0.22), 30, 260))
    border = max(8, round(min(image_width, image_height) * 0.025))

    def selected_labels(samples: np.ndarray) -> np.ndarray:
        counts = np.bincount(samples.ravel(), minlength=cluster_count)
        # Thin frame-adjacent structures can occupy very little border area
        # yet still interrupt an otherwise uniform exterior band.  Retain
        # these genuine border colors; clusters absent from the border remain
        # excluded and represent the page surface.
        minimum = max(4, round(samples.size * 0.0005))
        return np.flatnonzero(counts >= minimum)

    x_middle = int(np.clip(round(center_x), 0, image_width - 1))
    top_samples = labels[:border, max(0, raw_left - margin) : min(image_width, raw_right + margin)]
    bottom_samples = labels[
        image_height - border :,
        max(0, raw_left - margin) : min(image_width, raw_right + margin),
    ]
    left_samples = np.concatenate(
        (
            labels[:, :border].ravel(),
            labels[:border, : max(border, x_middle)].ravel(),
            labels[image_height - border :, : max(border, x_middle)].ravel(),
        )
    )
    right_samples = np.concatenate(
        (
            labels[:, image_width - border :].ravel(),
            labels[:border, x_middle:].ravel(),
            labels[image_height - border :, x_middle:].ravel(),
        )
    )

    side_masks = {
        "left": np.isin(labels, selected_labels(left_samples)),
        "right": np.isin(labels, selected_labels(right_samples)),
        "top": np.isin(labels, selected_labels(top_samples)),
        "bottom": np.isin(labels, selected_labels(bottom_samples)),
    }
    inset_x = max(3, round(width * 0.025))
    inset_y = max(3, round(height * 0.025))
    x1 = max(0, raw_left + inset_x)
    x2 = min(image_width, raw_right - inset_x)
    y1 = max(0, raw_top + inset_y)
    y2 = min(image_height, raw_bottom - inset_y)
    if x2 - x1 < 20 or y2 - y1 < 20:
        return rect

    def smooth_profile(profile: np.ndarray) -> np.ndarray:
        sigma = max(4.0, len(profile) * 0.008)
        return cv2.GaussianBlur(profile.reshape(1, -1), (0, 0), sigma).ravel()

    profiles = {
        "left": smooth_profile(side_masks["left"][y1:y2].mean(axis=0)),
        "right": smooth_profile(side_masks["right"][y1:y2].mean(axis=0)),
        "top": smooth_profile(side_masks["top"][:, x1:x2].mean(axis=1)),
        "bottom": smooth_profile(side_masks["bottom"][:, x1:x2].mean(axis=1)),
    }

    def exterior_transition(
        profile: np.ndarray,
        expected: int,
        outward: int,
    ) -> int | None:
        start = max(0, expected - margin)
        stop = min(len(profile), expected + margin + 1)
        band = profile[start:stop]
        if band.size < 12:
            return None
        low, high = np.percentile(band, (10, 90))
        contrast = float(high - low)
        if contrast < 0.22:
            return None
        # Bias toward the exterior shoulder.  The transition is deliberately
        # conservative so pale paper is preserved instead of clipped at the
        # point where its color becomes fully dominant.
        threshold = float(low + contrast * 0.86)
        outer_width = max(3, round(band.size * 0.12))
        outer = band[:outer_width] if outward < 0 else band[-outer_width:]
        if float(np.median(outer)) < threshold:
            return None

        indexes = range(start, stop) if outward < 0 else range(stop - 1, start - 1, -1)
        for index in indexes:
            if profile[index] < threshold:
                return int(np.clip(index - outward, 0, len(profile) - 1))
        return None

    transitions = {
        "left": exterior_transition(profiles["left"], raw_left, -1),
        "right": exterior_transition(profiles["right"], raw_right, 1),
        "top": exterior_transition(profiles["top"], raw_top, -1),
        "bottom": exterior_transition(profiles["bottom"], raw_bottom, 1),
    }
    outward_tolerance = max(3, round(min(width, height) * 0.015))
    if (
        transitions["left"] is not None
        and transitions["left"] < raw_left - outward_tolerance
    ):
        transitions["left"] = None
    if (
        transitions["right"] is not None
        and transitions["right"] > raw_right + outward_tolerance
    ):
        transitions["right"] = None
    if (
        transitions["top"] is not None
        and transitions["top"] < raw_top - outward_tolerance
    ):
        transitions["top"] = None
    if (
        transitions["bottom"] is not None
        and transitions["bottom"] > raw_bottom + outward_tolerance
    ):
        transitions["bottom"] = None

    inward_shifts = [
        transitions["left"] - raw_left if transitions["left"] is not None else 0,
        raw_right - transitions["right"] if transitions["right"] is not None else 0,
        transitions["top"] - raw_top if transitions["top"] is not None else 0,
        raw_bottom - transitions["bottom"] if transitions["bottom"] is not None else 0,
    ]
    # Small shifts are better handled by the gradient refinement. Requiring a
    # material inward correction keeps adjacent pale album leaves from being
    # mistaken for exterior background.
    if max(inward_shifts) < min(width, height) * 0.035:
        return rect

    # A fitted vertical exterior boundary also estimates small in-plane tilt.
    # This works even when the boundary itself is low contrast, because every
    # row contributes a background/non-background classification.
    angle_observations: list[tuple[float, int, float]] = []
    for side, outward in (("left", -1), ("right", 1)):
        transition = transitions[side]
        if transition is None:
            continue
        blurred = cv2.GaussianBlur(
            side_masks[side].astype(np.float32),
            (0, 0),
            sigmaX=8,
            sigmaY=3,
        )
        start = max(0, (raw_left if side == "left" else raw_right) - margin)
        stop = min(
            image_width,
            (raw_left if side == "left" else raw_right) + margin + 1,
        )
        boundary_points: list[tuple[int, int]] = []
        for row in range(y1, y2, 4):
            non_background = np.flatnonzero(blurred[row, start:stop] < 0.45) + start
            if non_background.size == 0:
                continue
            coordinate = int(non_background[0] if outward < 0 else non_background[-1])
            if abs(coordinate - transition) <= max(40, round(margin * 0.50)):
                boundary_points.append((coordinate, row))
        if len(boundary_points) < max(12, (y2 - y1) // 24):
            continue
        vx, vy, line_x, line_y = (
            float(value)
            for value in cv2.fitLine(
                np.float32(boundary_points), cv2.DIST_HUBER, 0, 0.01, 0.01
            ).ravel()
        )
        if abs(vy) < 0.7:
            continue
        fitted_angle = ((np.degrees(np.arctan2(vy, vx)) + 135.0) % 180.0) - 45.0
        residuals = [
            abs(x - (line_x + vx / vy * (y - line_y))) for x, y in boundary_points
        ]
        residual = float(np.median(residuals))
        if abs(fitted_angle - angle) <= 6.0 and residual <= max(12.0, margin * 0.12):
            angle_observations.append((float(fitted_angle), len(boundary_points), residual))

    refined_angle = angle
    if angle_observations:
        refined_angle = max(
            angle_observations,
            key=lambda item: item[1] / max(1.0, item[2]),
        )[0]

    theta = np.deg2rad(refined_angle)
    width_axis = np.array([np.cos(theta), np.sin(theta)], dtype=np.float32)
    height_axis = np.array([-np.sin(theta), np.cos(theta)], dtype=np.float32)
    original_center = np.array([center_x, center_y], dtype=np.float32)
    # Preserve the current side locations while rotating their axes. Projecting
    # the old rectangle's *corners* would artificially enlarge both dimensions
    # whenever the fitted angle changes.
    left, right = -width / 2.0, width / 2.0
    top, bottom = -height / 2.0, height / 2.0

    if transitions["left"] is not None:
        point = np.array([transitions["left"], center_y], dtype=np.float32)
        left = float((point - original_center) @ width_axis)
    if transitions["right"] is not None:
        point = np.array([transitions["right"], center_y], dtype=np.float32)
        right = float((point - original_center) @ width_axis)
    if transitions["top"] is not None:
        point = np.array([center_x, transitions["top"]], dtype=np.float32)
        top = float((point - original_center) @ height_axis)
    if transitions["bottom"] is not None:
        point = np.array([center_x, transitions["bottom"]], dtype=np.float32)
        bottom = float((point - original_center) @ height_axis)
    if transitions["top"] is not None or transitions["bottom"] is not None:
        # Color classification changes gradually through shadows and aged
        # paper. Keep a small vertical safety margin around the transition;
        # this preserves the full leaf without reintroducing the much larger
        # camera background removed above.
        vertical_padding = min(right - left, bottom - top) * 0.01
        if transitions["top"] is not None:
            top -= vertical_padding
        if transitions["bottom"] is not None:
            bottom += vertical_padding
    if right - left < width * 0.55 or bottom - top < height * 0.70:
        return rect

    local_center = width_axis * ((left + right) / 2) + height_axis * ((top + bottom) / 2)
    refined_center = original_center + local_center
    return (
        (float(refined_center[0]), float(refined_center[1])),
        (float(right - left), float(bottom - top)),
        float(refined_angle),
    )


def _as_region(rect: RotatedRect, image_width: int, image_height: int) -> DetectedRegion:
    center, (width, height), angle = _upright_rect(rect)
    points = cv2.boxPoints((center, (width, height), angle))
    x, y, box_width, box_height = cv2.boundingRect(points)
    x = max(0, x)
    y = max(0, y)
    box_width = max(1, min(image_width - x, box_width))
    box_height = max(1, min(image_height - y, box_height))
    area = float(width * height)
    return DetectedRegion(
        center=(float(center[0]), float(center[1])),
        size=(float(width), float(height)),
        angle=float(angle),
        area=area,
        area_ratio=area / max(1, image_width * image_height),
        x=x,
        y=y,
        width=box_width,
        height=box_height,
    )


def detect_album_pages(
    image: Image.Image,
    layout: AlbumLayout = "auto",
) -> list[DetectedRegion]:
    """Detect one physical album page or split a photographed spread.

    ``auto`` selects a credible content-bearing leaf, but splits very wide page
    surfaces (aspect ratio >= 1.75).  The conservative threshold avoids turning
    a common landscape album page into two outputs.  ``single`` always selects
    one physical leaf, while ``spread`` deterministically produces left and
    right pages.

    A partially clipped page is valid: sides already touching the photograph
    boundary remain there, while visible sides are snapped to strong edges.
    """
    if layout not in {"auto", "single", "spread"}:
        raise ValueError("layout must be one of: auto, single, spread")

    rgb = np.asarray(image.convert("RGB"))
    original_height, original_width = rgb.shape[:2]
    if original_width < 2 or original_height < 2:
        return []

    scale = min(1.0, _MAX_WORKING_DIMENSION / max(original_width, original_height))
    if scale < 1.0:
        working = cv2.resize(
            rgb,
            (max(2, round(original_width * scale)), max(2, round(original_height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    else:
        working = rgb
    gray = cv2.cvtColor(working, cv2.COLOR_RGB2GRAY)

    candidates = _surface_candidates(working)
    rect = max(candidates, key=lambda item: item[0])[1] if candidates else _edge_fallback(gray)
    if rect is None:
        return []

    # The surface mask is intentionally broad so mounted photographs cannot
    # punch holes in it.  This final pass pulls visible sides back onto the
    # long physical page edges and leaves ambiguous/clipped sides unchanged.
    outer = _normalized_rect(_refine_rect_to_edges(gray, rect, search_margin_ratio=0.075))
    aspect_ratio = outer[1][0] / max(1.0, outer[1][1])
    should_split = layout == "spread" or (layout == "auto" and aspect_ratio >= 1.75)
    if should_split:
        working_rects = _split_spread(outer)
    else:
        leaf = _single_leaf_from_candidates(candidates, outer)
        page = leaf or outer
        page = _refine_page_rect_to_continuous_edges(gray, page)
        working_rects = [_refine_leaf_from_border_background(working, page)]

    rects = [
        (
            (item[0][0] / scale, item[0][1] / scale),
            (item[1][0] / scale, item[1][1] / scale),
            item[2],
        )
        for item in working_rects
    ]
    regions = [_as_region(item, original_width, original_height) for item in rects]
    regions.sort(key=lambda region: (region.center[1], region.center[0]))
    return regions
