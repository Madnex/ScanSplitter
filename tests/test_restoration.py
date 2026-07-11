import numpy as np
import pytest
from PIL import Image, ImageDraw

from scansplitter.restoration import auto_deskew, comparison_image, estimate_skew_angle


def _lined_image(angle: float = 0) -> Image.Image:
    image = Image.new("RGB", (640, 420), "white")
    draw = ImageDraw.Draw(image)
    for y in (90, 180, 270, 360):
        draw.line((50, y, 590, y), fill="black", width=5)
    return image.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=False)


def test_estimate_skew_angle_finds_small_clockwise_tilt():
    assert estimate_skew_angle(_lined_image(3.0)) == pytest.approx(3.0, abs=0.4)


def test_auto_deskew_corrects_derivative_without_mutating_source():
    source = _lined_image(2.5)
    original = np.asarray(source).copy()
    corrected, angle = auto_deskew(source)
    assert angle == pytest.approx(2.5, abs=0.4)
    assert abs(estimate_skew_angle(corrected)) < 0.5
    assert np.array_equal(np.asarray(source), original)


def test_estimator_ignores_large_rotation_and_blank_images():
    assert estimate_skew_angle(_lined_image(12)) == 0.0
    assert estimate_skew_angle(Image.new("RGB", (300, 200), "white")) == 0.0


def test_comparison_image_labels_and_bounds_derivative():
    result = comparison_image(_lined_image(), _lined_image(2), "deskew +2.00°")
    assert result.mode == "RGB"
    assert result.height <= 764
    assert result.width > result.height
