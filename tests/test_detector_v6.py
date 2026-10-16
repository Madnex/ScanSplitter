"""Fast synthetic checks for the pure-OpenCV v6 detector."""

import cv2
import numpy as np
from PIL import Image

from scansplitter.detector_v6 import detect_photos_v6


def _photo(width: int, height: int, seed: int) -> np.ndarray:
    """A smooth, colourful, mildly textured stand-in for a photograph."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    base = np.stack(
        [
            90 + 70 * np.sin(x / 37 + seed),
            110 + 60 * np.cos(y / 29 + seed),
            100 + 50 * np.sin((x + y) / 41),
        ],
        axis=-1,
    )
    base += rng.normal(0, 8, base.shape)
    return np.clip(base, 0, 255).astype(np.uint8)


def _scene(background: np.ndarray, boxes) -> Image.Image:
    canvas = background.copy()
    for index, (x, y, w, h) in enumerate(boxes):
        canvas[y : y + h, x : x + w] = _photo(w, h, index + 1)
    return Image.fromarray(canvas)


def _white(width=1000, height=700) -> np.ndarray:
    return np.full((height, width, 3), 250, np.uint8)


def _boxes(regions):
    out = []
    for r in regions:
        pts = cv2.boxPoints((r.center, r.size, r.angle))
        out.append((*pts.min(axis=0), *pts.max(axis=0)))
    return sorted(out)


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union


def _assert_matches(regions, truth):
    assert len(regions) == len(truth)
    expected = sorted((x, y, x + w, y + h) for x, y, w, h in truth)
    for found, wanted in zip(_boxes(regions), expected):
        assert _iou(found, wanted) > 0.85


def test_v6_finds_two_prints_on_white_background():
    boxes = [(80, 100, 360, 480), (560, 120, 360, 460)]
    regions = detect_photos_v6(_scene(_white(), boxes))
    _assert_matches(regions, boxes)


def test_v6_finds_print_on_textured_background():
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 14, (700, 1000, 1))
    background = np.clip(np.array([150, 130, 100]) + noise, 0, 255).astype(np.uint8)
    boxes = [(300, 150, 400, 400)]
    regions = detect_photos_v6(_scene(background, boxes))
    _assert_matches(regions, boxes)


def test_v6_splits_prints_separated_by_tight_gutter():
    boxes = [(100, 120, 380, 460), (494, 120, 380, 460)]  # 14 px gutter
    regions = detect_photos_v6(_scene(_white(), boxes))
    assert len(regions) == 2


def test_v6_empty_page_returns_nothing():
    assert detect_photos_v6(Image.fromarray(_white())) == []


def test_v6_large_image_is_scale_invariant():
    boxes = [(80, 100, 360, 480), (560, 120, 360, 460)]
    image = _scene(_white(), boxes).resize((2200, 1540), Image.LANCZOS)
    regions = detect_photos_v6(image)
    scaled = [tuple(round(v * 2.2) for v in box) for box in boxes]
    _assert_matches(regions, scaled)
