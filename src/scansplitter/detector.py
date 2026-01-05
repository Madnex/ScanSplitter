"""Photo detection for scanned images."""

from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np
from PIL import Image


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

        # Get axis-aligned bounding box for quick reference
        x, y, w, h = cv2.boundingRect(contour)

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


# Backwards-compatible alias: "classic" / previous default points at ScanSplitterv2.
detect_photos = detect_photos_v2


# Global U2-Net session cache (lazy loaded)
_u2net_session: "onnxruntime.InferenceSession | None" = None
_u2net_lite: bool | None = None


def _get_u2net_session(lite: bool = True) -> "onnxruntime.InferenceSession":
    """Get or create the U2-Net ONNX inference session."""
    global _u2net_session, _u2net_lite

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
