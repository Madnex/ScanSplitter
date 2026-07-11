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


def restore_color_and_fade(image: Image.Image) -> tuple[Image.Image, dict[str, float]]:
    """Apply capped gray-world balance and a gentle luminance expansion.

    Gains and contrast are deliberately bounded: archival photos often have
    intentional warm lighting, so this corrects obvious aging casts without
    forcing every image to mathematically neutral gray.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    highlights = rgb.reshape(-1, 3)
    brightness = highlights.mean(axis=1)
    highlights = highlights[brightness >= np.percentile(brightness, 70)]
    channel_means = highlights.mean(axis=0)
    neutral = float(channel_means.mean())
    gains = np.clip(neutral / np.maximum(channel_means, 1.0), 0.85, 1.18)
    balanced = np.clip(rgb * gains, 0, 255).astype(np.uint8)

    lab = cv2.cvtColor(balanced, cv2.COLOR_RGB2LAB)
    luminance = lab[:, :, 0].astype(np.float32)
    low, high = np.percentile(luminance, (1.0, 99.0))
    contrast_gain = 1.0
    if high - low >= 24 and high - low < 210:
        stretched = np.clip((luminance - low) * 255 / (high - low), 0, 255)
        blend = 0.35
        lab[:, :, 0] = np.clip(luminance * (1 - blend) + stretched * blend, 0, 255)
        contrast_gain = round(255 / float(high - low), 3)
    restored = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    return Image.fromarray(restored), {
        "red_gain": round(float(gains[0]), 3),
        "green_gain": round(float(gains[1]), 3),
        "blue_gain": round(float(gains[2]), 3),
        "contrast_gain": contrast_gain,
    }


def remove_dust_and_scratches(image: Image.Image) -> tuple[Image.Image, float]:
    """Repair sparse, high-contrast specks and thin scratches conservatively."""
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    bright = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
    dark = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    defects = np.maximum(bright, dark)
    threshold = max(22, int(np.percentile(defects, 99.7)))
    mask = np.where(defects >= threshold, 255, 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    filtered = np.zeros_like(mask)
    max_area = max(12, int(mask.size * 0.00015))
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        thin = min(width, height) <= 3 and max(width, height) <= 80
        speck = area <= max_area and width <= 18 and height <= 18
        if speck or thin:
            filtered[labels == label] = 255
    ratio = float(np.count_nonzero(filtered) / filtered.size)
    if ratio == 0 or ratio > 0.02:
        return image, 0.0
    repaired = cv2.inpaint(rgb, filtered, 2, cv2.INPAINT_TELEA)
    return Image.fromarray(repaired), round(ratio * 100, 3)


def archival_upscale(image: Image.Image, factor: int = 2) -> Image.Image:
    """Non-generative Lanczos upscale with a restrained unsharp pass."""
    rgb = np.asarray(image.convert("RGB"))
    enlarged = cv2.resize(rgb, None, fx=factor, fy=factor, interpolation=cv2.INTER_LANCZOS4)
    blurred = cv2.GaussianBlur(enlarged, (0, 0), 1.0)
    sharpened = cv2.addWeighted(enlarged, 1.18, blurred, -0.18, 0)
    return Image.fromarray(sharpened)


def apply_restorations(image: Image.Image, settings: dict) -> tuple[Image.Image, str]:
    """Apply enabled restoration operations in a stable order."""
    restored = image
    details: list[str] = []
    if settings.get("auto_deskew"):
        restored, angle = auto_deskew(restored)
        details.append(f"deskew {angle:+.2f}°" if angle else "deskew not needed")
    if settings.get("restore_color"):
        restored, metrics = restore_color_and_fade(restored)
        strongest = max(abs(metrics[key] - 1) for key in ("red_gain", "green_gain", "blue_gain"))
        details.append(f"color/fade corrected ({strongest * 100:.0f}% max balance)")
    if settings.get("remove_dust"):
        restored, repaired = remove_dust_and_scratches(restored)
        details.append(f"dust/scratches repaired ({repaired:.3f}% pixels)")
    if settings.get("upscale_2x"):
        restored = archival_upscale(restored)
        details.append("2× archival upscale")
    return restored, ", ".join(details) if details else "no restoration enabled"


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
