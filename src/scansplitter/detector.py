"""Contour-based photo detection for scanned images."""

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass
class DetectedRegion:
    """A detected photo/document region in a scan."""

    x: int
    y: int
    width: int
    height: int
    area: int
    area_ratio: float  # Ratio of region area to total image area

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Return bounding box as (x, y, x+width, y+height)."""
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

    # Step 6: Filter contours by area
    regions = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        area_ratio = area / total_area

        # Filter by area ratio
        if min_area_ratio <= area_ratio <= max_area_ratio:
            # Apply padding while staying within image bounds
            x_padded = max(0, x - padding)
            y_padded = max(0, y - padding)
            w_padded = min(cv_image.shape[1] - x_padded, w + 2 * padding)
            h_padded = min(cv_image.shape[0] - y_padded, h + 2 * padding)

            regions.append(
                DetectedRegion(
                    x=x_padded,
                    y=y_padded,
                    width=w_padded,
                    height=h_padded,
                    area=w_padded * h_padded,
                    area_ratio=area_ratio,
                )
            )

    # Sort by position: top-to-bottom, then left-to-right
    regions.sort(key=lambda r: (r.y // 100, r.x))  # Group rows within 100px

    return regions


def crop_regions(image: Image.Image, regions: list[DetectedRegion]) -> list[Image.Image]:
    """
    Crop detected regions from the original image.

    Args:
        image: Original PIL Image
        regions: List of DetectedRegion objects

    Returns:
        List of cropped PIL Images
    """
    cropped = []
    for region in regions:
        bbox = region.bbox
        cropped_img = image.crop(bbox)
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
