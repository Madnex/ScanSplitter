"""Automatic rotation detection and correction for photos."""

import cv2
import numpy as np
from PIL import Image


def score_rotation(image: Image.Image) -> float:
    """
    Score an image orientation based on edge alignment.

    Higher scores indicate better alignment (more horizontal/vertical edges).
    Uses Hough line detection to find dominant line angles.

    Args:
        image: PIL Image to analyze

    Returns:
        Score where higher = better orientation
    """
    # Convert to OpenCV format
    cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

    # Apply edge detection
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # Detect lines using probabilistic Hough transform
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=50,
        minLineLength=30,
        maxLineGap=10,
    )

    if lines is None:
        return 0.0

    # Score based on how many lines are near horizontal (0°) or vertical (90°)
    score = 0.0
    for line in lines:
        x1, y1, x2, y2 = line[0]
        # Calculate angle in degrees
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Normalize angle to 0-90 range
        angle = abs(angle) % 90

        # Score lines that are close to horizontal (0°) or vertical (90°)
        # Lines at 0° or 90° get high scores, lines at 45° get low scores
        if angle < 10 or angle > 80:  # Within 10° of horizontal/vertical
            line_length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            score += line_length

    return score


def detect_rotation(image: Image.Image) -> int:
    """
    Detect the best rotation angle for an image.

    Tests 0°, 90°, 180°, and 270° rotations and returns the best one.

    Args:
        image: PIL Image to analyze

    Returns:
        Best rotation angle in degrees (0, 90, 180, or 270)
    """
    best_angle = 0
    best_score = -1.0

    for angle in [0, 90, 180, 270]:
        if angle == 0:
            rotated = image
        else:
            # PIL.Image.rotate uses counterclockwise, expand=True keeps full image
            rotated = image.rotate(-angle, expand=True)

        score = score_rotation(rotated)

        if score > best_score:
            best_score = score
            best_angle = angle

    return best_angle


def auto_rotate(image: Image.Image) -> tuple[Image.Image, int]:
    """
    Automatically rotate an image to the correct orientation.

    Args:
        image: PIL Image to rotate

    Returns:
        Tuple of (rotated image, angle applied)
    """
    angle = detect_rotation(image)

    if angle == 0:
        return image, 0

    # Rotate the image (negative because PIL rotates counterclockwise)
    rotated = image.rotate(-angle, expand=True)
    return rotated, angle


def rotate_images(images: list[Image.Image]) -> list[tuple[Image.Image, int]]:
    """
    Auto-rotate a list of images.

    Args:
        images: List of PIL Images

    Returns:
        List of tuples (rotated image, angle applied)
    """
    return [auto_rotate(img) for img in images]
