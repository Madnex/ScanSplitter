"""Photo detection for scanned images."""

import threading
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

_v3_kmeans_lock = threading.Lock()

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


_mobilesam_encoder_session: "onnxruntime.InferenceSession | None" = None
_mobilesam_decoder_session: "onnxruntime.InferenceSession | None" = None
_mobilesam_session_lock = threading.Lock()
_mobilesam_inference_lock = threading.Lock()


def _get_mobilesam_sessions() -> tuple[
    "onnxruntime.InferenceSession", "onnxruntime.InferenceSession"
]:
    """Load the small, checksum-pinned MobileSAM ONNX pair once."""
    global _mobilesam_encoder_session, _mobilesam_decoder_session

    with _mobilesam_session_lock:
        if _mobilesam_encoder_session is None or _mobilesam_decoder_session is None:
            import onnxruntime

            from .models import get_mobilesam_model_paths

            encoder_path, decoder_path = get_mobilesam_model_paths()
            providers = ["CPUExecutionProvider"]
            _mobilesam_encoder_session = onnxruntime.InferenceSession(
                str(encoder_path), providers=providers
            )
            _mobilesam_decoder_session = onnxruntime.InferenceSession(
                str(decoder_path), providers=providers
            )
        return _mobilesam_encoder_session, _mobilesam_decoder_session


def _v4_mask_rect(
    binary_mask: np.ndarray,
    proposal: RotatedRect,
    predicted_iou: float,
) -> RotatedRect | None:
    """Choose a credible rectangular print mask for a v3 proposal."""
    if predicted_iou < 0.70:
        return None

    proposal_area = proposal[1][0] * proposal[1][1]
    contours, _ = cv2.findContours(
        binary_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    candidates: list[tuple[float, RotatedRect]] = []
    for contour in contours:
        contour_area = cv2.contourArea(contour)
        if contour_area < 100:
            continue
        rect = cv2.minAreaRect(contour)
        rect_width, rect_height = rect[1]
        rect_area = rect_width * rect_height
        if rect_area <= 0:
            continue
        area_change = rect_area / max(1.0, proposal_area)
        if not 0.25 <= area_change <= 2.50:
            continue
        rectangularity = contour_area / rect_area
        if rectangularity < 0.62:
            continue
        aspect = max(rect_width, rect_height) / max(1.0, min(rect_width, rect_height))
        if aspect > 5.0:
            continue
        overlap = _v3_overlap_fraction(rect, proposal)
        if overlap < 0.65:
            continue
        # Rectangularity distinguishes a physical print from a person/object
        # segmented inside it. Overlap preserves v3's region identity when
        # album pages contain tightly packed neighboring photos.
        score = rectangularity + 0.5 * overlap + 0.15 * min(1.0, area_change)
        candidates.append((score, rect))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _v4_refine_rectangles(
    rgb: np.ndarray,
    proposals: list[RotatedRect],
) -> list[RotatedRect]:
    """Refine v3 proposals with box-prompted MobileSAM masks."""
    if not proposals:
        return []

    encoder, decoder = _get_mobilesam_sessions()
    original_height, original_width = rgb.shape[:2]
    scale = min(1.0, 1024 / max(original_height, original_width))
    width = max(1, round(original_width * scale))
    height = max(1, round(original_height * scale))
    resized = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)

    refined: list[RotatedRect] = []
    # ORT sessions are thread-safe, but serializing this small model avoids
    # thread-pool oversubscription when a project queues many scans at once.
    with _mobilesam_inference_lock:
        embeddings = encoder.run(
            None, {"input_image": resized.astype(np.float32)}
        )[0]
        for proposal in proposals:
            points = cv2.boxPoints(proposal)
            x1, y1 = np.min(points, axis=0)
            x2, y2 = np.max(points, axis=0)
            margin = 0.04 * min(x2 - x1, y2 - y1)
            prompt = np.array(
                [
                    [
                        [max(0.0, x1 - margin), max(0.0, y1 - margin)],
                        [
                            min(float(original_width - 1), x2 + margin),
                            min(float(original_height - 1), y2 + margin),
                        ],
                    ]
                ],
                dtype=np.float32,
            )
            prompt *= scale
            masks, iou_predictions, _ = decoder.run(
                None,
                {
                    "image_embeddings": embeddings,
                    "point_coords": prompt,
                    "point_labels": np.array([[2, 3]], dtype=np.float32),
                    "mask_input": np.zeros((1, 1, 256, 256), dtype=np.float32),
                    "has_mask_input": np.zeros((1,), dtype=np.float32),
                    "orig_im_size": np.array([height, width], dtype=np.float32),
                },
            )
            small_proposal: RotatedRect = (
                (proposal[0][0] * scale, proposal[0][1] * scale),
                (proposal[1][0] * scale, proposal[1][1] * scale),
                proposal[2],
            )
            mask_rect = _v4_mask_rect(
                masks[0, 0] > 0,
                small_proposal,
                float(iou_predictions[0, 0]),
            )
            if mask_rect is None:
                refined.append(proposal)
            else:
                refined.append(
                    (
                        (mask_rect[0][0] / scale, mask_rect[0][1] / scale),
                        (mask_rect[1][0] / scale, mask_rect[1][1] / scale),
                        mask_rect[2],
                    )
                )
    return refined


def detect_photos_v4(
    image: Image.Image,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    padding: int = 0,
    inset: int = 10,
) -> list[DetectedRegion]:
    """Detect photos with v3 proposals and MobileSAM border refinement.

    V3 provides stable multi-photo count and separation. A compact promptable
    segmentation model then traces the physical print selected by each box.
    Conservative geometry checks retain the v3 proposal when MobileSAM returns
    a non-rectangular object or an implausibly different region.
    """
    proposals = detect_photos_v3(
        image,
        min_area_ratio=min_area_ratio,
        max_area_ratio=max_area_ratio,
        padding=0,
        inset=0,
    )
    proposal_rects = [
        (region.center, region.size, region.angle) for region in proposals
    ]
    rgb = np.asarray(image.convert("RGB"))
    original_height, original_width = rgb.shape[:2]
    original_area = original_height * original_width
    refined_rects = _v4_refine_rectangles(rgb, proposal_rects)

    regions: list[DetectedRegion] = []
    net_adjust = padding - inset
    for proposal, refined in zip(proposal_rects, refined_rects, strict=True):
        rect_width, rect_height = refined[1]
        area = rect_width * rect_height
        area_ratio = area / original_area
        if not min_area_ratio <= area_ratio <= max_area_ratio:
            refined = proposal
            rect_width, rect_height = refined[1]
            area = rect_width * rect_height
            area_ratio = area / original_area

        center, _, angle = refined
        points = cv2.boxPoints(refined)
        x, y, box_width, box_height = cv2.boundingRect(points)
        x_adjusted = max(0, x - net_adjust)
        y_adjusted = max(0, y - net_adjust)
        width_adjusted = max(
            1,
            min(original_width - x_adjusted, box_width + 2 * net_adjust),
        )
        height_adjusted = max(
            1,
            min(original_height - y_adjusted, box_height + 2 * net_adjust),
        )
        adjusted_width = max(1, rect_width + 2 * net_adjust)
        adjusted_height = max(1, rect_height + 2 * net_adjust)
        if rect_width < rect_height:
            adjusted_width, adjusted_height = adjusted_height, adjusted_width
            angle += 90

        regions.append(
            DetectedRegion(
                center=center,
                size=(adjusted_width, adjusted_height),
                angle=angle,
                area=area,
                area_ratio=area_ratio,
                x=x_adjusted,
                y=y_adjusted,
                width=width_adjusted,
                height=height_adjusted,
            )
        )

    regions.sort(key=lambda region: (region.y // 100, region.x))
    return regions


# Public convenience API follows the current default detector.
detect_photos = detect_photos_v4

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
