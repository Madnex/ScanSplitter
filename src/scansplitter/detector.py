"""Photo detection for scanned images."""

import threading
from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np
from PIL import Image

_v3_kmeans_lock = threading.Lock()


def _apply_clahe(gray: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
    """Apply Contrast Limited Adaptive Histogram Equalization."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _adaptive_kernel_size(image_shape: tuple[int, int], base: int = 5) -> int:
    """Scale morphology kernel size based on image resolution."""
    # Reference: 3000x4000 image uses base size
    reference_area = 3000 * 4000
    actual_area = image_shape[0] * image_shape[1]
    scale = (actual_area / reference_area) ** 0.5
    size = int(base * max(0.5, min(2.0, scale)))
    # Kernel must be odd and at least 3
    size = max(3, size)
    return size if size % 2 == 1 else size + 1


def _compute_contour_quality(contour: np.ndarray) -> dict:
    """Compute shape quality metrics for contour filtering."""
    area = cv2.contourArea(contour)
    x, y, w, h = cv2.boundingRect(contour)
    hull = cv2.convexHull(contour)
    hull_area = cv2.contourArea(hull)

    return {
        "area": area,
        "aspect_ratio": max(w, h) / max(1, min(w, h)),
        "solidity": area / max(1, hull_area),
        "extent": area / max(1, w * h),
    }


def _passes_quality_filter(
    metrics: dict,
    min_solidity: float,
    max_aspect_ratio: float,
    min_extent: float,
) -> bool:
    """Check if contour passes quality filters."""
    return (
        metrics["solidity"] >= min_solidity
        and metrics["aspect_ratio"] <= max_aspect_ratio
        and metrics["extent"] >= min_extent
    )


RotatedRect = tuple[tuple[float, float], tuple[float, float], float]


def _refine_rect_to_edges(
    gray: np.ndarray,
    rect: RotatedRect,
    search_margin_ratio: float = 0.05,
) -> RotatedRect:
    """Snap a candidate rotated rectangle to nearby continuous image edges.

    Adaptive thresholding is intentionally generous so that texture inside a
    photo forms one connected contour. On high-resolution scans that contour
    can also absorb a soft scanner shadow outside the print. This pass
    deskews a small band around the candidate and locates the strongest
    *average* gradient near each side. Averaging along a whole side favors the
    physical photo border over short edges within the picture.

    A side is left unchanged when its peak does not stand out from the local
    gradient profile, so low-contrast scans retain the contour result.
    """
    (center_x, center_y), (width, height), angle = rect
    if width < 10 or height < 10:
        return rect

    margin = int(np.clip(round(min(width, height) * search_margin_ratio), 8, 140))
    patch_width = max(3, round(width) + 2 * margin)
    patch_height = max(3, round(height) + 2 * margin)

    theta = np.deg2rad(angle)
    width_axis = np.array([np.cos(theta), np.sin(theta)])
    height_axis = np.array([-np.sin(theta), np.cos(theta)])

    # Map destination patch coordinates back into the source image. Keeping
    # the candidate centered in the patch makes the expected sides land at
    # ``margin`` and ``margin + size`` respectively.
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

    # Compute one direction at a time to keep peak memory bounded on large
    # scans. CV_16S is sufficient for an 8-bit Sobel derivative.
    gradient_x = cv2.Sobel(patch, cv2.CV_16S, 1, 0, ksize=3)
    np.abs(gradient_x, out=gradient_x)
    x_profile = np.mean(gradient_x[margin : patch_height - margin], axis=0)
    del gradient_x
    gradient_y = cv2.Sobel(patch, cv2.CV_16S, 0, 1, ksize=3)
    np.abs(gradient_y, out=gradient_y)
    y_profile = np.mean(gradient_y[:, margin : patch_width - margin], axis=1)
    del gradient_y

    def strongest_edge(profile: np.ndarray, expected: float) -> int:
        expected_index = int(round(expected))
        start = max(0, expected_index - margin)
        stop = min(len(profile), expected_index + margin + 1)
        candidates = profile[start:stop]
        if candidates.size == 0:
            return expected_index

        relative_index = int(np.argmax(candidates))
        peak = float(candidates[relative_index])
        baseline = float(np.median(candidates))
        deviation = float(np.median(np.abs(candidates - baseline)))
        # Require both an absolute signal and clear separation from local
        # texture. Uniform/ambiguous bands therefore preserve the candidate.
        if peak < 8.0 or peak < baseline + max(6.0, 4.0 * deviation):
            return expected_index
        return start + relative_index

    left = strongest_edge(x_profile, margin)
    right = strongest_edge(x_profile, margin + width)
    top = strongest_edge(y_profile, margin)
    bottom = strongest_edge(y_profile, margin + height)

    refined_width = float(right - left)
    refined_height = float(bottom - top)
    if refined_width <= 0 or refined_height <= 0:
        return rect

    local_shift_x = (left + right - patch_width) / 2
    local_shift_y = (top + bottom - patch_height) / 2
    refined_center = (
        float(center_x + width_axis[0] * local_shift_x + height_axis[0] * local_shift_y),
        float(center_y + width_axis[1] * local_shift_x + height_axis[1] * local_shift_y),
    )
    return refined_center, (refined_width, refined_height), angle


@dataclass
class DetectedRegion:
    """A detected photo/document region in a scan."""

    # Rotated rectangle properties (from minAreaRect)
    center: tuple[float, float]  # Center point (cx, cy)
    size: tuple[float, float]  # (width, height) of rotated rect
    angle: float  # Rotation angle in degrees
    area: float
    area_ratio: float  # Ratio of region area to total image area

    # Axis-aligned bounding box (for backward compat and quick checks)
    x: int
    y: int
    width: int
    height: int

    # Optional: convex hull points for border preservation mode
    hull_points: np.ndarray | None = field(default=None, repr=False)

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Return axis-aligned bounding box as (x, y, x+width, y+height)."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)


def detect_photos_v1(
    image: Image.Image,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    blur_kernel: int = 5,
    threshold_block_size: int = 11,
    threshold_c: int = 2,
    padding: int = 0,
    inset: int = 10,
) -> list[DetectedRegion]:
    """
    Detect multiple photos/documents in a scanned image (ScanSplitterv1).

    This is the original contour-based detector from `main`.
    """
    cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    total_area = cv_image.shape[0] * cv_image.shape[1]

    gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), 0)

    thresh = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        threshold_block_size,
        threshold_c,
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    img_height, img_width = cv_image.shape[:2]

    for contour in contours:
        rect = cv2.minAreaRect(contour)
        center, size, angle = rect
        rect_width, rect_height = size
        area = rect_width * rect_height
        area_ratio = area / total_area

        if not (min_area_ratio <= area_ratio <= max_area_ratio):
            continue

        x, y, w, h = cv2.boundingRect(contour)

        net_adjust = padding - inset
        x_padded = max(0, x - net_adjust)
        y_padded = max(0, y - net_adjust)
        w_padded = max(1, min(img_width - x_padded, w + 2 * net_adjust))
        h_padded = max(1, min(img_height - y_padded, h + 2 * net_adjust))

        padded_width = max(1, rect_width + 2 * net_adjust)
        padded_height = max(1, rect_height + 2 * net_adjust)

        if rect_width < rect_height:
            padded_width, padded_height = padded_height, padded_width
            angle = angle + 90

        regions.append(
            DetectedRegion(
                center=center,
                size=(padded_width, padded_height),
                angle=angle,
                area=area,
                area_ratio=area_ratio,
                x=x_padded,
                y=y_padded,
                width=w_padded,
                height=h_padded,
            )
        )

    regions.sort(key=lambda r: (r.y // 100, r.x))
    return regions


def detect_photos_v2(
    image: Image.Image,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    blur_kernel: int = 5,
    threshold_block_size: int = 11,
    threshold_c: int = 2,
    padding: int = 0,
    inset: int = 10,
    # Phase 1 improvements
    enhance_contrast: bool = True,
    adaptive_morphology: bool = True,
    min_solidity: float = 0.7,
    max_aspect_ratio: float = 5.0,
    min_extent: float = 0.4,
    border_mode: Literal["minAreaRect", "convexHull"] = "minAreaRect",
    border_padding: float = 0.02,
    refine_edges: bool = True,
) -> list[DetectedRegion]:
    """
    Detect multiple photos/documents in a scanned image.

    Uses contour detection to find distinct regions separated by whitespace.

    Args:
        image: PIL Image to analyze
        min_area_ratio: Minimum region area as fraction of total (default 2%)
        max_area_ratio: Maximum region area as fraction of total (default 80%)
        blur_kernel: Gaussian blur kernel size (must be odd)
        threshold_block_size: Block size for adaptive thresholding
        threshold_c: Constant subtracted from threshold
        padding: Extra pixels to include around detected regions
        inset: Pixels to shrink the bounding box inward (removes border artifacts)
        enhance_contrast: Apply CLAHE for better low-contrast detection
        adaptive_morphology: Scale morphology kernel based on image size
        min_solidity: Minimum solidity (area/hull_area) to filter noise (0-1)
        max_aspect_ratio: Maximum aspect ratio to filter thin strips
        min_extent: Minimum extent (area/bbox_area) to filter irregular shapes
        border_mode: "minAreaRect" (tight) or "convexHull" (preserves irregular borders)
        border_padding: Padding ratio when using convexHull mode (fraction of image)
        refine_edges: Snap contour rectangles to nearby continuous photo edges

    Returns:
        List of DetectedRegion objects sorted by position (top-to-bottom, left-to-right)
    """
    # Convert PIL to OpenCV format
    cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    img_height, img_width = cv_image.shape[:2]
    total_area = img_height * img_width

    # Step 1: Convert to grayscale
    gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

    # Step 1.5: Apply CLAHE for better contrast (helps with low-contrast photos)
    if enhance_contrast:
        gray = _apply_clahe(gray)

    # Step 2: Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), 0)

    # Step 3: Apply adaptive thresholding for better results with varying lighting
    # This creates a binary image where photos become distinct from background
    thresh = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        threshold_block_size,
        threshold_c,
    )

    # Step 4: Morphological operations to clean up the mask
    if adaptive_morphology:
        kernel_size = _adaptive_kernel_size((img_height, img_width))
    else:
        kernel_size = 5
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # Step 5: Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Step 6: Filter contours by area and quality metrics
    regions = []

    for contour in contours:
        # Compute quality metrics for filtering
        quality = _compute_contour_quality(contour)

        # Get minimum area rotated rectangle
        if border_mode == "convexHull":
            hull = cv2.convexHull(contour)
            rect = cv2.minAreaRect(hull)
            hull_points = hull
        else:
            rect = cv2.minAreaRect(contour)
            hull_points = None

        center, size, angle = rect
        rect_width, rect_height = size
        area = rect_width * rect_height
        area_ratio = area / total_area

        # Filter by area ratio
        if not (min_area_ratio <= area_ratio <= max_area_ratio):
            continue

        # Filter by quality metrics (solidity, aspect ratio, extent)
        if not _passes_quality_filter(quality, min_solidity, max_aspect_ratio, min_extent):
            continue

        if refine_edges:
            rect = _refine_rect_to_edges(gray, rect)
            center, size, angle = rect
            rect_width, rect_height = size
            area = rect_width * rect_height
            area_ratio = area / total_area

        # Get axis-aligned bounding box for quick reference
        rect_points = cv2.boxPoints(rect)
        x, y, w, h = cv2.boundingRect(rect_points)

        # Apply padding then inset to axis-aligned box while staying within image bounds
        # Net effect = padding - inset (e.g., padding=0, inset=3 shrinks by 3px each side)
        net_adjust = padding - inset

        # Add border_padding if using convexHull mode
        if border_mode == "convexHull":
            extra_padding = int(min(img_width, img_height) * border_padding)
            net_adjust += extra_padding

        x_padded = max(0, x - net_adjust)
        y_padded = max(0, y - net_adjust)
        w_padded = max(1, min(img_width - x_padded, w + 2 * net_adjust))
        h_padded = max(1, min(img_height - y_padded, h + 2 * net_adjust))

        # Apply padding then inset to rotated rect size
        padded_width = max(1, rect_width + 2 * net_adjust)
        padded_height = max(1, rect_height + 2 * net_adjust)

        # Normalize OpenCV's minAreaRect output:
        # minAreaRect returns angle in [-90, 0) with arbitrary width/height order.
        # We normalize so that:
        # - angle is always 0 when the box is axis-aligned
        # - width corresponds to the dimension along the angle direction
        # This matches what the user sees and edits in the UI
        if rect_width < rect_height:
            # Swap to make width the larger dimension and adjust angle
            padded_width, padded_height = padded_height, padded_width
            angle = angle + 90

        regions.append(
            DetectedRegion(
                center=center,
                size=(padded_width, padded_height),
                angle=angle,
                area=area,
                area_ratio=area_ratio,
                x=x_padded,
                y=y_padded,
                width=w_padded,
                height=h_padded,
                hull_points=hull_points,
            )
        )

    # Sort by position: top-to-bottom, then left-to-right
    regions.sort(key=lambda r: (r.y // 100, r.x))  # Group rows within 100px

    return regions


def _v3_background_colors(lab: np.ndarray) -> np.ndarray:
    """Estimate the scan background as one or more Lab color clusters.

    Multiple clusters are retained because scanner falloff and album-page
    shadows often make the same sheet of paper span a wide lightness range.
    K-means is seeded under a short lock because OpenCV's RNG is process-global;
    this keeps concurrent detection jobs deterministic.
    """
    height, width = lab.shape[:2]
    stride = max(1, int(np.sqrt(height * width / 30_000)))
    sampled = lab[::stride, ::stride]
    pixels = sampled.reshape(-1, 3).astype(np.float32)
    if len(pixels) < 5:
        return np.mean(pixels, axis=0, keepdims=True)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    with _v3_kmeans_lock:
        cv2.setRNGSeed(0)
        _, labels, centers = cv2.kmeans(
            pixels,
            5,
            None,
            criteria,
            3,
            cv2.KMEANS_PP_CENTERS,
        )

    counts = np.bincount(labels.ravel(), minlength=len(centers))
    lightness = centers[:, 0] / 255.0
    # Prefer a large, light cluster. This selects white/cream scanner paper
    # instead of a large dark photograph while still supporting colored paper.
    score = counts * np.clip(lightness, 0.15, 1.0) ** 2
    primary = centers[int(np.argmax(score))]

    chroma_delta = np.linalg.norm(centers[:, 1:] - primary[1:], axis=1)
    similar = (centers[:, 0] >= primary[0] - 55) & (chroma_delta <= 24)

    # Do not mistake a pale/sepia photograph's dominant tone for another
    # shade of paper. Real page/background clusters recur around the scan's
    # outer band; a color confined to a print does not.
    label_grid = labels.reshape(sampled.shape[:2])
    border_depth = max(1, round(min(label_grid.shape) * 0.06))
    border_mask = np.zeros(label_grid.shape, dtype=bool)
    border_mask[:border_depth] = True
    border_mask[-border_depth:] = True
    border_mask[:, :border_depth] = True
    border_mask[:, -border_depth:] = True
    border_counts = np.bincount(label_grid[border_mask], minlength=len(centers))
    border_share = border_counts / max(1, np.count_nonzero(border_mask))
    selected = similar & (border_share >= 0.015)
    selected[int(np.argmax(score))] = True

    # A dark platen or album cover can surround the entire page. When at
    # least three corners agree on such a cluster it is background too.
    corners = np.array(
        [lab[0, 0], lab[0, -1], lab[-1, 0], lab[-1, -1]],
        dtype=np.float32,
    )
    corner_labels = np.argmin(
        np.linalg.norm(corners[:, None, :] - centers[None, :, :], axis=2),
        axis=1,
    )
    for index in np.unique(corner_labels):
        if np.count_nonzero(corner_labels == index) >= 3:
            selected[index] = True
    return centers[selected]


def _v3_snap_angle_to_long_edges(gray: np.ndarray, rect: RotatedRect) -> RotatedRect:
    """Correct a mask-derived angle using long straight edges near it."""
    points = cv2.boxPoints(rect)
    x, y, width, height = cv2.boundingRect(points)
    short_side = min(rect[1])
    if short_side < 10:
        return rect
    margin = max(8, round(short_side * 0.15))
    x1, y1 = max(0, x - margin), max(0, y - margin)
    x2 = min(gray.shape[1], x + width + margin)
    y2 = min(gray.shape[0], y + height + margin)
    patch = gray[y1:y2, x1:x2]
    if patch.size == 0:
        return rect

    edges = cv2.Canny(cv2.GaussianBlur(patch, (5, 5), 0), 35, 110)
    minimum = max(20, round(short_side * 0.32))
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 360,
        threshold=max(18, round(minimum * 0.25)),
        minLineLength=minimum,
        maxLineGap=max(8, round(minimum * 0.12)),
    )
    if lines is None:
        return rect

    raw_angle = float(rect[2])
    observations: list[tuple[float, float]] = []
    for line_x1, line_y1, line_x2, line_y2 in lines.reshape(-1, 4):
        length = float(np.hypot(line_x2 - line_x1, line_y2 - line_y1))
        angle = float(np.degrees(np.arctan2(line_y2 - line_y1, line_x2 - line_x1)))
        # Rectangle orientation is periodic every 90 degrees.
        delta = ((angle - raw_angle + 45.0) % 90.0) - 45.0
        if abs(delta) <= 18:
            observations.append((delta, length * length))
    if len(observations) < 2:
        return rect

    bins = np.linspace(-18, 18, 73)
    histogram = np.zeros(len(bins) - 1, dtype=np.float64)
    for delta, weight in observations:
        index = int(np.clip(np.searchsorted(bins, delta) - 1, 0, len(histogram) - 1))
        histogram[index] += weight
    peak_index = int(np.argmax(histogram))
    peak = (bins[peak_index] + bins[peak_index + 1]) / 2
    nearby = [(delta, weight) for delta, weight in observations if abs(delta - peak) <= 2]
    total_weight = sum(weight for _, weight in nearby)
    if total_weight < minimum * minimum:
        return rect
    snapped_delta = sum(delta * weight for delta, weight in nearby) / total_weight
    return rect[0], rect[1], raw_angle + snapped_delta


def _v3_overlap_fraction(first: RotatedRect, second: RotatedRect) -> float:
    kind, points = cv2.rotatedRectangleIntersection(first, second)
    if kind == cv2.INTERSECT_NONE or points is None:
        return 0.0
    intersection = cv2.contourArea(points)
    first_area = first[1][0] * first[1][1]
    second_area = second[1][0] * second[1][1]
    return intersection / max(1.0, min(first_area, second_area))


def _v3_iou(first: RotatedRect, second: RotatedRect) -> float:
    kind, points = cv2.rotatedRectangleIntersection(first, second)
    if kind == cv2.INTERSECT_NONE or points is None:
        return 0.0
    intersection = cv2.contourArea(points)
    first_area = first[1][0] * first[1][1]
    second_area = second[1][0] * second[1][1]
    return intersection / max(1.0, first_area + second_area - intersection)


def _v3_merge_fragments(rectangles: list[RotatedRect], max_area: float) -> list[RotatedRect]:
    """Merge overlapping mask fragments that belong to one physical print."""
    merged = list(rectangles)
    changed = True
    while changed:
        changed = False
        for first_index in range(len(merged)):
            for second_index in range(first_index + 1, len(merged)):
                first, second = merged[first_index], merged[second_index]
                if _v3_overlap_fraction(first, second) < 0.08:
                    continue
                points = np.vstack([cv2.boxPoints(first), cv2.boxPoints(second)]).astype(
                    np.float32
                )
                union = cv2.minAreaRect(points)
                if union[1][0] * union[1][1] > max_area:
                    continue
                merged[first_index] = union
                merged.pop(second_index)
                changed = True
                break
            if changed:
                break
    return merged


def _v3_split_on_gutter(
    rect: RotatedRect,
    foreground: np.ndarray,
    minimum_area: float,
) -> list[RotatedRect]:
    """Split two touching prints when a narrow background gutter separates them."""
    (center_x, center_y), (width, height), angle = rect
    if min(width, height) <= 0 or max(width, height) / min(width, height) < 1.8:
        return [rect]

    patch_width, patch_height = max(3, round(width)), max(3, round(height))
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
        foreground.astype(np.uint8),
        transform,
        (patch_width, patch_height),
        flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    split_width = width >= height
    profile = np.mean(patch, axis=0 if split_width else 1)
    profile = cv2.blur(profile.reshape(1, -1).astype(np.float32), (7, 1)).ravel()
    length = len(profile)
    start, stop = round(length * 0.25), round(length * 0.75)
    if stop <= start:
        return [rect]
    split = start + int(np.argmin(profile[start:stop]))
    flank = max(5, round(length * 0.12))
    before_density = float(np.mean(profile[max(0, split - flank) : split]))
    after_density = float(np.mean(profile[split + 1 : min(length, split + flank)]))
    if profile[split] > 0.08 or min(before_density, after_density) < 0.16:
        return [rect]

    first_length, second_length = float(split), float(length - split)
    short_side = float(height if split_width else width)
    if first_length * short_side < minimum_area or second_length * short_side < minimum_area:
        return [rect]

    axis = width_axis if split_width else height_axis
    first_center = (
        float(center_x - axis[0] * second_length / 2),
        float(center_y - axis[1] * second_length / 2),
    )
    second_center = (
        float(center_x + axis[0] * first_length / 2),
        float(center_y + axis[1] * first_length / 2),
    )
    if split_width:
        return [
            (first_center, (first_length, float(height)), angle),
            (second_center, (second_length, float(height)), angle),
        ]
    return [
        (first_center, (float(width), first_length), angle),
        (second_center, (float(width), second_length), angle),
    ]


def detect_photos_v3(
    image: Image.Image,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    padding: int = 0,
    inset: int = 10,
    detection_max_dimension: int = 1800,
) -> list[DetectedRegion]:
    """Detect prints using background modeling and region-level evidence.

    Unlike v1/v2, this detector does not treat every thresholded pixel as one
    contour. It models the paper/platen colors in Lab space, measures the
    density of non-background evidence, separates narrow gutters between
    touching prints, and finally snaps candidates to long physical edges.
    Processing at a bounded resolution makes all morphology scale-independent
    and keeps very large scans fast and memory-bounded.
    """
    rgb = np.asarray(image.convert("RGB"))
    original_height, original_width = rgb.shape[:2]
    original_area = original_height * original_width
    scale = min(1.0, detection_max_dimension / max(original_height, original_width))
    width = max(1, round(original_width * scale))
    height = max(1, round(original_height * scale))
    small = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)
    total_area = height * width

    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32)
    backgrounds = _v3_background_colors(lab)
    delta = np.full((height, width), np.inf, dtype=np.float32)
    for background in backgrounds:
        difference = lab - background
        distance = np.sqrt(np.sum(difference * difference, axis=2))
        np.minimum(delta, distance, out=delta)
    color_threshold, _ = cv2.threshold(
        np.clip(delta, 0, 255).astype(np.uint8),
        0,
        255,
        cv2.THRESH_BINARY | cv2.THRESH_OTSU,
    )
    foreground = delta > max(18.0, float(color_threshold))

    density_window = max(11, round(min(height, width) * 0.010)) | 1
    density = cv2.boxFilter(
        foreground.astype(np.float32),
        cv2.CV_32F,
        (density_window, density_window),
    )
    mask = (density > 0.16).astype(np.uint8) * 255
    open_size = max(5, round(min(height, width) * 0.010)) | 1
    close_size = max(5, round(min(height, width) * 0.008)) | 1
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_size, open_size)),
    )
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (close_size, close_size)),
        iterations=2,
    )

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    minimum_area = min_area_ratio * total_area
    maximum_area = max_area_ratio * total_area
    candidates: list[RotatedRect] = []
    for contour in contours:
        rect = cv2.minAreaRect(contour)
        rect_width, rect_height = rect[1]
        rect_area = rect_width * rect_height
        if not minimum_area <= rect_area <= maximum_area:
            continue
        x, y, box_width, box_height = cv2.boundingRect(contour)
        component_fill = cv2.contourArea(contour) / max(1, box_width * box_height)
        aspect = max(rect_width, rect_height) / max(1, min(rect_width, rect_height))
        if component_fill < 0.32 or aspect > 5.0:
            continue
        candidates.append(rect)

    candidates = _v3_merge_fragments(candidates, maximum_area)
    deduplicated: list[RotatedRect] = []
    for rect in sorted(candidates, key=lambda item: item[1][0] * item[1][1], reverse=True):
        if any(_v3_iou(rect, other) > 0.55 for other in deduplicated):
            continue
        deduplicated.append(rect)

    split_candidates: list[RotatedRect] = []
    for rect in deduplicated:
        split_candidates.extend(_v3_split_on_gutter(rect, foreground, minimum_area))

    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    refined = [
        _refine_rect_to_edges(
            gray,
            _v3_snap_angle_to_long_edges(gray, rect),
            search_margin_ratio=0.12,
        )
        for rect in split_candidates
    ]

    regions: list[DetectedRegion] = []
    net_adjust = padding - inset
    for small_rect in refined:
        (center_x, center_y), (rect_width, rect_height), angle = small_rect
        center = (center_x / scale, center_y / scale)
        rect_width /= scale
        rect_height /= scale
        area = rect_width * rect_height
        area_ratio = area / original_area
        if not min_area_ratio <= area_ratio <= max_area_ratio:
            continue

        rect: RotatedRect = (center, (rect_width, rect_height), angle)
        rect_points = cv2.boxPoints(rect)
        x, y, box_width, box_height = cv2.boundingRect(rect_points)
        x_padded = max(0, x - net_adjust)
        y_padded = max(0, y - net_adjust)
        width_padded = max(
            1,
            min(original_width - x_padded, box_width + 2 * net_adjust),
        )
        height_padded = max(
            1,
            min(original_height - y_padded, box_height + 2 * net_adjust),
        )
        padded_width = max(1, rect_width + 2 * net_adjust)
        padded_height = max(1, rect_height + 2 * net_adjust)
        if rect_width < rect_height:
            padded_width, padded_height = padded_height, padded_width
            angle += 90

        regions.append(
            DetectedRegion(
                center=center,
                size=(padded_width, padded_height),
                angle=angle,
                area=area,
                area_ratio=area_ratio,
                x=x_padded,
                y=y_padded,
                width=width_padded,
                height=height_padded,
            )
        )

    regions.sort(key=lambda region: (region.y // 100, region.x))
    return regions


# Backwards-compatible alias: "classic" / previous default points at ScanSplitterv2.
detect_photos = detect_photos_v2


# Global U2-Net session cache (lazy loaded)
# Guarded by a lock: detection may run from multiple worker threads.
_u2net_session: "onnxruntime.InferenceSession | None" = None
_u2net_lite: bool | None = None
_u2net_lock = threading.Lock()


def _get_u2net_session(lite: bool = True) -> "onnxruntime.InferenceSession":
    """Get or create the U2-Net ONNX inference session (thread-safe)."""
    global _u2net_session, _u2net_lite

    with _u2net_lock:
        if _u2net_session is None or _u2net_lite != lite:
            import onnxruntime

            from .models import get_u2net_model_path

            model_path = get_u2net_model_path(lite=lite)
            _u2net_session = onnxruntime.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"],
            )
            _u2net_lite = lite

        return _u2net_session


def _u2net_preprocess(image: np.ndarray, size: int = 320) -> np.ndarray:
    """Preprocess image for U2-Net inference."""
    # Resize to model input size
    resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_LINEAR)

    # Convert BGR to RGB
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

    # Normalize to [0, 1] then apply ImageNet normalization
    normalized = rgb.astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    normalized = (normalized - mean) / std

    # Convert to NCHW format (batch, channels, height, width)
    transposed = normalized.transpose(2, 0, 1)
    batched = np.expand_dims(transposed, axis=0)

    return batched


def _u2net_postprocess(
    output: np.ndarray, original_size: tuple[int, int], threshold: float = 0.5
) -> np.ndarray:
    """Convert U2-Net output to binary mask at original image size."""
    # Output shape is (1, 1, H, W), squeeze to (H, W)
    mask = output.squeeze()

    # Normalize to [0, 1] range
    mask = (mask - mask.min()) / (mask.max() - mask.min() + 1e-8)

    # Resize to original image size
    h, w = original_size
    mask_resized = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)

    # Threshold to binary
    binary = (mask_resized > threshold).astype(np.uint8) * 255

    return binary


def detect_photos_u2net(
    image: Image.Image,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    threshold: float = 0.5,
    lite: bool = True,
    padding: int = 0,
    inset: int = 10,
) -> list[DetectedRegion]:
    """
    Detect photos using U2-Net salient object detection.

    Uses deep learning for more accurate detection of photos on complex backgrounds.
    Best for difficult scans where traditional methods fail.

    Args:
        image: PIL Image to analyze
        min_area_ratio: Minimum region area as fraction of total (default 2%)
        max_area_ratio: Maximum region area as fraction of total (default 80%)
        threshold: Saliency threshold for binary mask (0-1, default 0.5)
        lite: Use lightweight u2netp model (faster) vs full u2net (more accurate)
        padding: Extra pixels to include around detected regions
        inset: Pixels to shrink the bounding box inward

    Returns:
        List of DetectedRegion objects sorted by position
    """
    # Convert PIL to OpenCV format
    cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    img_height, img_width = cv_image.shape[:2]
    total_area = img_height * img_width

    # Get U2-Net session and run inference
    session = _get_u2net_session(lite=lite)
    input_tensor = _u2net_preprocess(cv_image)

    # Run inference - U2-Net outputs multiple scales, we use the first (finest)
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: input_tensor})
    saliency_map = outputs[0]

    # Post-process to binary mask
    binary_mask = _u2net_postprocess(saliency_map, (img_height, img_width), threshold)

    # Apply morphological operations to clean up
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    binary_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    # Find contours
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Convert contours to DetectedRegion objects
    regions = []

    for contour in contours:
        rect = cv2.minAreaRect(contour)
        center, size, angle = rect
        rect_width, rect_height = size
        area = rect_width * rect_height
        area_ratio = area / total_area

        # Filter by area ratio
        if not (min_area_ratio <= area_ratio <= max_area_ratio):
            continue

        # Get axis-aligned bounding box
        x, y, w, h = cv2.boundingRect(contour)

        # Apply padding/inset
        net_adjust = padding - inset
        x_padded = max(0, x - net_adjust)
        y_padded = max(0, y - net_adjust)
        w_padded = max(1, min(img_width - x_padded, w + 2 * net_adjust))
        h_padded = max(1, min(img_height - y_padded, h + 2 * net_adjust))

        padded_width = max(1, rect_width + 2 * net_adjust)
        padded_height = max(1, rect_height + 2 * net_adjust)

        # Normalize angle
        if rect_width < rect_height:
            padded_width, padded_height = padded_height, padded_width
            angle = angle + 90

        regions.append(
            DetectedRegion(
                center=center,
                size=(padded_width, padded_height),
                angle=angle,
                area=area,
                area_ratio=area_ratio,
                x=x_padded,
                y=y_padded,
                width=w_padded,
                height=h_padded,
            )
        )

    # Sort by position
    regions.sort(key=lambda r: (r.y // 100, r.x))

    return regions


def crop_rotated_region(cv_image: np.ndarray, region: DetectedRegion) -> np.ndarray:
    """
    Extract a rotated region from an image and deskew it.

    Uses affine transformation to rotate the image so the detected region
    becomes axis-aligned, then crops the result.

    Args:
        cv_image: OpenCV image (BGR format)
        region: DetectedRegion with rotation info

    Returns:
        Cropped and deskewed image as numpy array
    """
    center = region.center
    width, height = region.size
    angle = region.angle

    width, height = int(round(width)), int(round(height))
    if width <= 0 or height <= 0:
        return np.zeros((0, 0, cv_image.shape[2]), dtype=cv_image.dtype)

    # Rotate the full image so the region becomes axis-aligned, then crop.
    #
    # Important: The rotation center is the region center (not necessarily the
    # image center). The common "new size" formula (based on cos/sin) assumes a
    # center rotation and can clip content when rotating around arbitrary points.
    # Compute the rotated image bounds by transforming the four image corners.
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    img_height, img_width = cv_image.shape[:2]
    corners = np.array(
        [[0, 0], [img_width, 0], [img_width, img_height], [0, img_height]],
        dtype=np.float32,
    )
    ones = np.ones((4, 1), dtype=np.float32)
    corners_h = np.hstack([corners, ones])  # (4, 3)
    rotated_corners = corners_h @ rotation_matrix.T  # (4, 2)
    min_xy = rotated_corners.min(axis=0)
    max_xy = rotated_corners.max(axis=0)

    new_width = int(np.ceil(max_xy[0] - min_xy[0]))
    new_height = int(np.ceil(max_xy[1] - min_xy[1]))
    if new_width <= 0 or new_height <= 0:
        return np.zeros((0, 0, cv_image.shape[2]), dtype=cv_image.dtype)

    # Shift the rotated image so all coordinates are positive.
    rotation_matrix[0, 2] -= float(min_xy[0])
    rotation_matrix[1, 2] -= float(min_xy[1])

    # Rotate the entire image
    rotated = cv2.warpAffine(
        cv_image,
        rotation_matrix,
        (new_width, new_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),  # White background for scans
    )

    # Calculate new center after rotation
    cx, cy = center
    new_cx = cx * rotation_matrix[0, 0] + cy * rotation_matrix[0, 1] + rotation_matrix[0, 2]
    new_cy = cx * rotation_matrix[1, 0] + cy * rotation_matrix[1, 1] + rotation_matrix[1, 2]

    # Crop the now-aligned rectangle
    x1 = int(round(new_cx - width / 2))
    y1 = int(round(new_cy - height / 2))
    x2 = int(round(new_cx + width / 2))
    y2 = int(round(new_cy + height / 2))

    # Clamp to image bounds
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(new_width, x2)
    y2 = min(new_height, y2)

    return rotated[y1:y2, x1:x2]


def crop_regions(image: Image.Image, regions: list[DetectedRegion]) -> list[Image.Image]:
    """
    Crop detected regions from the original image with deskewing.

    Args:
        image: Original PIL Image
        regions: List of DetectedRegion objects

    Returns:
        List of cropped and deskewed PIL Images
    """
    # Convert to OpenCV format once
    cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    cropped = []
    for region in regions:
        # Extract and deskew the rotated region
        cropped_cv = crop_rotated_region(cv_image, region)

        # Convert back to PIL
        cropped_rgb = cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB)
        cropped_img = Image.fromarray(cropped_rgb)
        cropped.append(cropped_img)

    return cropped


def detect_and_crop(
    image: Image.Image,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    **kwargs,
) -> list[Image.Image]:
    """
    Convenience function to detect and crop photos in one step.

    Args:
        image: PIL Image to process
        min_area_ratio: Minimum region area as fraction of total
        max_area_ratio: Maximum region area as fraction of total
        **kwargs: Additional arguments passed to detect_photos

    Returns:
        List of cropped PIL Images
    """
    regions = detect_photos(
        image, min_area_ratio=min_area_ratio, max_area_ratio=max_area_ratio, **kwargs
    )

    # If no regions detected, return the original image
    if not regions:
        return [image]

    return crop_regions(image, regions)
