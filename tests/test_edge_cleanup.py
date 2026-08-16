import cv2
import numpy as np
from PIL import Image

from scansplitter.edge_cleanup import cleanup_photo_edges


def _bordered_photo() -> Image.Image:
    height, width = 360, 520
    canvas = np.full((height, width, 3), (244, 239, 218), dtype=np.uint8)
    yy, xx = np.mgrid[:height, :width]
    photograph = np.stack(
        (
            35 + (xx % 120),
            45 + (yy % 105),
            65 + ((xx + yy) % 110),
        ),
        axis=2,
    ).astype(np.uint8)
    polygon = np.array([[24, 17], [493, 25], [486, 338], [31, 343]], dtype=np.int32)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(mask, polygon, 255)
    canvas[mask != 0] = photograph[mask != 0]
    return Image.fromarray(canvas)


def test_cleanup_trims_sloped_light_border_and_rectifies_photo():
    source = _bordered_photo()

    cleaned, detail = cleanup_photo_edges(source)

    assert detail.applied
    assert set(detail.sides) == {"top", "right", "bottom", "left"}
    assert 0.1 < detail.removed_fraction < 0.25
    assert 440 <= cleaned.width <= 480
    assert 300 <= cleaned.height <= 330
    pixels = np.asarray(cleaned)
    assert pixels[:, :, 0].mean() < 180


def test_cleanup_leaves_uniform_bright_image_unchanged():
    source = Image.new("RGB", (420, 300), (242, 242, 238))

    cleaned, detail = cleanup_photo_edges(source)

    assert cleaned is source
    assert not detail.applied
    assert detail.sides == ()


def test_cleanup_does_not_treat_dark_border_as_scan_whitespace():
    pixels = np.full((300, 420, 3), 25, dtype=np.uint8)
    pixels[20:-20, 20:-20] = (160, 130, 100)
    source = Image.fromarray(pixels)

    cleaned, detail = cleanup_photo_edges(source)

    assert cleaned is source
    assert not detail.applied


def test_cleanup_can_trim_one_confident_side_without_changing_others():
    pixels = np.empty((280, 400, 3), dtype=np.uint8)
    yy, xx = np.mgrid[:280, :400]
    pixels[:, :, 0] = 30 + (xx % 150)
    pixels[:, :, 1] = 45 + (yy % 130)
    pixels[:, :, 2] = 55 + ((xx + yy) % 140)
    pixels[:, :18] = (245, 240, 220)
    source = Image.fromarray(pixels)

    cleaned, detail = cleanup_photo_edges(source)

    assert detail.applied
    assert detail.sides == ("left",)
    assert cleaned.width < source.width
    assert abs(cleaned.height - source.height) <= 1


def test_off_mode_returns_original_object():
    source = _bordered_photo()

    cleaned, detail = cleanup_photo_edges(source, mode="off")

    assert cleaned is source
    assert not detail.applied


def test_tight_mode_removes_page_border_and_white_print_margin():
    height, width = 360, 520
    pixels = np.full((height, width, 3), (236, 211, 162), dtype=np.uint8)
    pixels[12:-12, 12:-12] = (248, 248, 244)
    yy, xx = np.mgrid[:height, :width]
    photo = np.stack((30 + xx % 130, 45 + yy % 110, 60 + (xx + yy) % 120), axis=2).astype(np.uint8)
    pixels[36:-36, 42:-42] = photo[36:-36, 42:-42]
    source = Image.fromarray(pixels)

    conservative, conservative_detail = cleanup_photo_edges(source, mode="conservative")
    tight, tight_detail = cleanup_photo_edges(source, mode="tight")

    assert conservative_detail.applied
    assert tight_detail.applied
    assert tight.width < conservative.width - 30
    assert tight.height < conservative.height - 30
    assert tight_detail.removed_fraction > conservative_detail.removed_fraction


def test_tight_mode_removes_two_pixel_high_resolution_fringe():
    height, width = 900, 1200
    yy, xx = np.mgrid[:height, :width]
    pixels = np.stack((25 + xx % 150, 40 + yy % 130, 55 + (xx + yy) % 140), axis=2).astype(np.uint8)
    pixels[:2] = (250, 250, 246)
    source = Image.fromarray(pixels)

    conservative, conservative_detail = cleanup_photo_edges(source, mode="conservative")
    tight, tight_detail = cleanup_photo_edges(source, mode="tight")

    assert conservative is source
    assert not conservative_detail.applied
    assert tight_detail.applied
    assert "top" in tight_detail.sides
    assert tight.height < source.height


def test_tight_mode_removes_partial_white_wedge():
    height, width = 600, 800
    yy, xx = np.mgrid[:height, :width]
    pixels = np.stack((30 + xx % 140, 45 + yy % 120, 60 + (xx + yy) % 130), axis=2).astype(np.uint8)
    wedge = np.array([[0, 0], [32, 0], [5, 290], [0, 310]], dtype=np.int32)
    cv2.fillConvexPoly(pixels, wedge, (249, 248, 242))
    source = Image.fromarray(pixels)

    tight, detail = cleanup_photo_edges(source, mode="tight")

    assert detail.applied
    assert "left" in detail.sides
    assert tight.width <= source.width - 25


def test_tight_mode_accepts_color_varied_aged_white_border():
    height, width = 420, 640
    yy, xx = np.mgrid[:height, :width]
    pixels = np.stack((25 + xx % 145, 40 + yy % 125, 55 + (xx + yy) % 135), axis=2).astype(np.uint8)
    for start in range(0, width, 80):
        color = (248, 247, 241) if (start // 80) % 2 == 0 else (242, 229, 185)
        pixels[:14, start : start + 80] = color
    source = Image.fromarray(pixels)

    tight, detail = cleanup_photo_edges(source, mode="tight")

    assert detail.applied
    assert "top" in detail.sides
    assert tight.height < source.height - 10


def test_tight_mode_final_shave_removes_low_coverage_pale_remnant():
    height, width = 520, 760
    yy, xx = np.mgrid[:height, :width]
    pixels = np.stack((25 + xx % 135, 40 + yy % 115, 55 + (xx + yy) % 125), axis=2).astype(np.uint8)
    pixels[:7, 180:255] = (249, 248, 243)
    source = Image.fromarray(pixels)

    tight, detail = cleanup_photo_edges(source, mode="tight")

    assert detail.applied
    assert "top" in detail.sides
    assert tight.height <= source.height - 7


def test_tight_mode_snaps_to_photo_boundary_when_scene_is_also_bright():
    height, width = 900, 1200
    pixels = np.full((height, width, 3), (245, 238, 216), dtype=np.uint8)
    pixels[45:-45, 60:-60] = (222, 222, 218)
    yy, xx = np.mgrid[: height - 90, : width - 120]
    scene = pixels[45:-45, 60:-60]
    scene[180:700, 80:360] = (75, 82, 78)
    scene[420:740, 650:940] = (95, 91, 85)
    scene[:, :, 0] = np.minimum(255, scene[:, :, 0] + (xx % 7)).astype(np.uint8)
    source = Image.fromarray(pixels)

    tight, detail = cleanup_photo_edges(source, mode="tight")

    assert set(detail.sides) == {"top", "right", "bottom", "left"}
    assert 1060 <= tight.width <= 1090
    assert 790 <= tight.height <= 820


def test_tight_mode_ignores_internal_line_without_light_outer_margin():
    height, width = 600, 800
    yy, xx = np.mgrid[:height, :width]
    pixels = np.stack((35 + xx % 90, 45 + yy % 80, 55 + (xx + yy) % 70), axis=2).astype(np.uint8)
    pixels[55:58] = (235, 235, 230)
    source = Image.fromarray(pixels)

    tight, detail = cleanup_photo_edges(source, mode="tight")

    assert tight is source
    assert not detail.applied
