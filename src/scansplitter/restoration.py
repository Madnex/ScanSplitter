"""Non-destructive photo restoration primitives."""

import cv2
import numpy as np
from PIL import Image, ImageDraw

MAX_DESKEW_DEGREES = 5.0
MIN_DESKEW_DEGREES = 0.25


def estimate_skew_angle(image: Image.Image, max_degrees: float = MAX_DESKEW_DEGREES) -> float:
    """Estimate a small clockwise tilt from strong near-axis lines."""
    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    longest = max(gray.shape)
    if longest > 1200:
        scale = 1200 / longest
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    min_length = max(30, int(min(gray.shape) * 0.2))
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 720,
        threshold=max(30, min_length // 2),
        minLineLength=min_length,
        maxLineGap=max(8, min_length // 8),
    )
    if lines is None:
        return 0.0

    candidates: list[tuple[float, float]] = []
    for x1, y1, x2, y2 in lines[:, 0]:
        raw = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        axis_angle = ((raw + 45.0) % 90.0) - 45.0
        if abs(axis_angle) <= max_degrees:
            candidates.append((axis_angle, float(np.hypot(x2 - x1, y2 - y1))))
    if not candidates:
        return 0.0

    candidates.sort(key=lambda item: item[0])
    half_weight = sum(weight for _, weight in candidates) / 2
    running = 0.0
    angle = 0.0
    for candidate, weight in candidates:
        running += weight
        if running >= half_weight:
            angle = candidate
            break
    return 0.0 if abs(angle) < MIN_DESKEW_DEGREES else round(angle, 2)


def auto_deskew(image: Image.Image) -> tuple[Image.Image, float]:
    """Return a corrected derivative and the clockwise tilt that was found."""
    angle = estimate_skew_angle(image)
    if angle == 0.0:
        return image, 0.0
    rgb = image.convert("RGB")
    pixels = np.asarray(rgb)
    border = np.concatenate((pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]))
    fill = tuple(int(value) for value in np.median(border, axis=0))
    return (
        rgb.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=fill),
        angle,
    )


def comparison_image(before: Image.Image, after: Image.Image, detail: str) -> Image.Image:
    """Compose a bounded side-by-side preview derivative."""
    target_height = min(720, max(before.height, after.height))

    def scaled(image: Image.Image) -> Image.Image:
        ratio = target_height / image.height
        return image.convert("RGB").resize(
            (max(1, round(image.width * ratio)), target_height), Image.Resampling.LANCZOS
        )

    left, right = scaled(before), scaled(after)
    header = 44
    canvas = Image.new("RGB", (left.width + right.width, target_height + header), "#18181b")
    canvas.paste(left, (0, header))
    canvas.paste(right, (left.width, header))
    draw = ImageDraw.Draw(canvas)
    draw.text((14, 14), "Before", fill="white")
    draw.text((left.width + 14, 14), f"After · {detail}", fill="white")
    draw.line((left.width, 0, left.width, canvas.height), fill="white", width=2)
    return canvas
