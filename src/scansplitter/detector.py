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
            padded_size = (rect_width + 2 * padding, rect_height + 2 * padding)

            regions.append(
                DetectedRegion(
                    center=center,
                    size=padded_size,
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

    Uses affine transformation to rotate the image so the detected region
    becomes axis-aligned, then crops the result.

    Args:
        cv_image: OpenCV image (BGR format)
        region: DetectedRegion with rotation info

    Returns:
        Cropped and deskewed image as numpy array
    """
    center = region.center
    size = region.size
    angle = region.angle

    # OpenCV's minAreaRect angle convention:
    # - Angle is between -90 and 0 degrees
    # - We need to handle the rotation correctly to avoid flipped results

    width, height = size
    width, height = int(width), int(height)

    # Ensure width > height for consistent orientation
    if width < height:
        width, height = height, width
        angle += 90

    # Get rotation matrix to straighten the region
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    # Calculate the size of the rotated image to avoid clipping
    img_height, img_width = cv_image.shape[:2]
    cos_angle = abs(rotation_matrix[0, 0])
    sin_angle = abs(rotation_matrix[0, 1])
    new_width = int(img_height * sin_angle + img_width * cos_angle)
    new_height = int(img_height * cos_angle + img_width * sin_angle)

    # Adjust the rotation matrix to account for the new image size
    rotation_matrix[0, 2] += (new_width - img_width) / 2
    rotation_matrix[1, 2] += (new_height - img_height) / 2

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
    x1 = int(new_cx - width / 2)
    y1 = int(new_cy - height / 2)
    x2 = int(new_cx + width / 2)
    y2 = int(new_cy + height / 2)

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
