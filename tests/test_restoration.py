import numpy as np
import pytest
from PIL import Image, ImageDraw

from scansplitter.restoration import (
    apply_restorations,
    auto_deskew,
    comparison_image,
    estimate_skew_angle,
    restore_color_and_fade,
)


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


def test_color_restoration_reduces_yellow_cast_and_expands_faded_range():
    ramp = np.linspace(70, 190, 300, dtype=np.uint8)
    faded = np.tile(ramp, (180, 1))
    warm = np.clip(faded.astype(np.int16) + 35, 0, 255).astype(np.uint8)
    cast = np.stack((warm, faded, faded // 2), axis=2)
    restored, metrics = restore_color_and_fade(Image.fromarray(cast))
    before = np.asarray(Image.fromarray(cast), dtype=np.float32)
    after = np.asarray(restored, dtype=np.float32)
    assert abs(after[:, :, 0].mean() - after[:, :, 2].mean()) < abs(
        before[:, :, 0].mean() - before[:, :, 2].mean()
    )
    before_luma = before.mean(axis=2)
    after_luma = after.mean(axis=2)
    assert np.ptp(np.percentile(after_luma, (1, 99))) > np.ptp(
        np.percentile(before_luma, (1, 99))
    )
    assert metrics["blue_gain"] > 1


def test_restoration_pipeline_honors_opt_in_settings():
    source = _lined_image(2)
    unchanged, detail = apply_restorations(source, {})
    assert unchanged is source
    assert detail == "no restoration enabled"
    restored, detail = apply_restorations(source, {"auto_deskew": True, "restore_color": True})
    assert restored is not source
    assert "deskew" in detail and "color/fade" in detail
