"""Fast synthetic checks for the v7 detector (needs the MobileSAM models)."""

import cv2
import numpy as np
import pytest
from PIL import Image

from scansplitter import models
from scansplitter.detector_v7 import detect_photos_v7

pytestmark = pytest.mark.skipif(
    not all(
        (models.MODELS_DIR / models._MODEL_SPECS[key]["filename"]).exists()
        for key in ("mobilesam_encoder", "mobilesam_decoder")
    ),
    reason="MobileSAM models are not downloaded",
)

BORDER = 30


def _photo(width: int, height: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    base = np.stack(
        [
            80 + 60 * np.sin(x / 31 + seed),
            100 + 55 * np.cos(y / 27 + seed),
            90 + 45 * np.sin((x + y) / 37),
        ],
        axis=-1,
    )
    base += rng.normal(0, 8, base.shape)
    return np.clip(base, 0, 255).astype(np.uint8)


def _page_with_prints(boxes):
    """Each box is the OUTER print (white border included): (x, y, w, h)."""
    canvas = np.full((700, 1000, 3), (245, 235, 225), np.uint8)
    for index, (x, y, w, h) in enumerate(boxes):
        canvas[y : y + h, x : x + w] = 252
        canvas[y + BORDER : y + h - BORDER, x + BORDER : x + w - BORDER] = _photo(
            w - 2 * BORDER, h - 2 * BORDER, index + 1
        )
    return Image.fromarray(canvas)


def _extent(region):
    pts = cv2.boxPoints((region.center, region.size, region.angle))
    return (*pts.min(axis=0), *pts.max(axis=0))


def test_v7_excludes_white_print_border():
    outer = [(60, 80, 400, 520), (540, 90, 400, 500)]
    regions = detect_photos_v7(_page_with_prints(outer))
    assert len(regions) == 2
    found = sorted(_extent(r) for r in regions)
    for (x0, y0, x1, y1), (x, y, w, h) in zip(found, outer):
        # Inner photo edges, within a few pixels; clearly inside the border.
        assert abs(x0 - (x + BORDER)) < 12 and abs(y0 - (y + BORDER)) < 12
        assert abs(x1 - (x + w - BORDER)) < 12 and abs(y1 - (y + h - BORDER)) < 12


def test_v7_empty_page_does_not_crash():
    page = Image.fromarray(np.full((700, 1000, 3), (245, 235, 225), np.uint8))
    assert detect_photos_v7(page) == []
