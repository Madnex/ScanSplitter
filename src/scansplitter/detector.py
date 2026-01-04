"""Contour-based photo detection for scanned images."""

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


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

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Return axis-aligned bounding box as (x, y, x+width, y+height)."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)


def detect_photos(
    image: Image.Image,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    blur_kernel: int = 5,
    threshold_block_size: int = 11,
    threshold_c: int = 2,
    padding: int = 5,
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

    Returns:
        List of DetectedRegion objects sorted by position (top-to-bottom, left-to-right)
    """
    # Convert PIL to OpenCV format
    cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    total_area = cv_image.shape[0] * cv_image.shape[1]

    # Step 1: Convert to grayscale
    gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

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
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # Step 5: Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Step 6: Filter contours by area using rotated rectangles
    regions = []
    img_height, img_width = cv_image.shape[:2]

    for contour in contours:
        # Get minimum area rotated rectangle
        rect = cv2.minAreaRect(contour)
        center, size, angle = rect
        rect_width, rect_height = size
        area = rect_width * rect_height
        area_ratio = area / total_area

        # Filter by area ratio
        if min_area_ratio <= area_ratio <= max_area_ratio:
            # Also get axis-aligned bounding box for quick reference
            x, y, w, h = cv2.boundingRect(contour)

            # Apply padding to axis-aligned box while staying within image bounds
            x_padded = max(0, x - padding)
            y_padded = max(0, y - padding)
            w_padded = min(img_width - x_padded, w + 2 * padding)
            h_padded = min(img_height - y_padded, h + 2 * padding)

            # Apply padding to rotated rect size
            padded_width = rect_width + 2 * padding
            padded_height = rect_height + 2 * padding

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
                )
            )

    # Sort by position: top-to-bottom, then left-to-right
    regions.sort(key=lambda r: (r.y // 100, r.x))  # Group rows within 100px

    return regions


def crop_rotated_region(cv_image: np.ndarray, region: DetectedRegion) -> np.ndarray:
    """
    Extract a rotated region from an image and deskew it.

    Uses perspective transformation to extract the exact rotated rectangle
    and warp it to an axis-aligned output.

    Args:
        cv_image: OpenCV image (BGR format)
        region: DetectedRegion with rotation info

    Returns:
        Cropped and deskewed image as numpy array
    """
    center = region.center
    width, height = region.size
    angle = region.angle

    # Create the rotated rectangle in OpenCV format
    # OpenCV's RotatedRect uses (center, size, angle) where angle is in degrees
    # Note: We negate the angle because Fabric.js uses clockwise-positive,
    # but OpenCV's boxPoints expects counter-clockwise-positive angles
    rect = (center, (width, height), -angle)

    # Get the 4 corners of the rotated rectangle
    box_points = cv2.boxPoints(rect)
    box_points = np.float32(box_points)

    # Define the destination points (axis-aligned rectangle)
    # boxPoints returns corners in order: bottom-left, top-left, top-right, bottom-right
    # We want to map to a width x height output
    dst_points = np.float32([
        [0, height],      # bottom-left
        [0, 0],           # top-left
        [width, 0],       # top-right
        [width, height],  # bottom-right
    ])

    # Get the perspective transformation matrix
    matrix = cv2.getPerspectiveTransform(box_points, dst_points)

    # Apply the transformation
    result = cv2.warpPerspective(
        cv_image,
        matrix,
        (int(width), int(height)),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),  # White background for scans
    )

    return result


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
