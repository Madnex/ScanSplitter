#!/usr/bin/env -S uv run
"""Build the fixed benchmark fixtures from 20 Image API source textures.

This is a maintainer utility. Pass one directory containing exactly ten
single-scene photographs and another containing exactly ten album-page
textures. The committed fixture JPEGs and manifest are the benchmark.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

WIDTH, HEIGHT = 1400, 1000


SCAN_CASES = [
    ("clean-grid", (242, 239, 226), [(330, 265, 440, 300, 0), (870, 265, 440, 300, 0), (330, 720, 440, 300, 0), (870, 720, 440, 300, 0)]),
    ("rotated-three", (238, 235, 218), [(350, 310, 500, 325, -7), (1035, 300, 430, 300, 6), (730, 745, 520, 330, -3)]),
    ("low-contrast", (225, 218, 198), [(350, 300, 470, 310, -2), (1010, 310, 430, 295, 3), (690, 740, 560, 340, 1)]),
    ("mixed-sizes", (246, 243, 235), [(245, 245, 330, 225, -5), (710, 235, 400, 265, 2), (1160, 250, 270, 360, 5), (350, 700, 500, 310, 4), (970, 720, 430, 280, -6)]),
    ("narrow-gutters", (236, 230, 214), [(455, 300, 430, 290, 0), (895, 300, 430, 290, 0), (455, 690, 430, 290, 0), (895, 690, 430, 290, 0)]),
    ("dark-platen", (39, 45, 50), [(330, 300, 470, 310, -4), (1020, 300, 460, 300, 5), (690, 735, 560, 350, 0)]),
    ("portrait-and-square", (240, 234, 215), [(245, 320, 300, 430, -4), (630, 300, 340, 340, 3), (1085, 315, 300, 430, 6), (665, 750, 520, 300, -2)]),
    ("edge-near", (232, 229, 216), [(245, 220, 430, 300, -3), (1135, 235, 420, 290, 4), (355, 755, 480, 320, 5), (1000, 750, 470, 310, -5)]),
    ("faded-pale", (232, 224, 205), [(350, 315, 490, 320, -5), (1020, 310, 450, 310, 4), (700, 745, 570, 345, 1)]),
    ("irregular-spacing", (241, 237, 223), [(330, 300, 470, 310, -7), (1030, 300, 450, 300, 8), (700, 740, 500, 310, -1)]),
]

ALBUM_CASES = [
    ("cream-single", "single", (79, 93, 110), [(700, 500, 1040, 760, -3)], (224, 214, 187)),
    ("black-single", "single", (169, 145, 119), [(700, 500, 1000, 740, 4)], (39, 40, 39)),
    ("wide-auto-spread", "auto", (73, 88, 102), [(415, 500, 570, 620, 0), (985, 500, 570, 620, 0)], (218, 207, 177)),
    ("forced-spread", "spread", (107, 91, 80), [(420, 500, 500, 720, -2), (920, 500, 500, 720, -2)], (196, 183, 143)),
    ("portrait-page", "single", (84, 103, 120), [(700, 500, 650, 840, 5)], (213, 205, 176)),
    ("ivory-single", "auto", (61, 70, 76), [(700, 500, 980, 720, -6)], (230, 224, 204)),
    ("burgundy-page", "single", (177, 162, 141), [(700, 500, 970, 720, 2)], (91, 37, 45)),
    ("small-page", "single", (63, 75, 91), [(700, 500, 720, 560, -4)], (219, 201, 163)),
    ("landscape-single", "auto", (123, 110, 93), [(700, 500, 1050, 690, 3)], (71, 72, 75)),
    ("rose-auto-spread", "auto", (70, 82, 91), [(415, 500, 570, 620, -1), (985, 500, 570, 620, -1)], (204, 160, 160)),
]


def crop_texture(source: Image.Image, size: tuple[int, int], seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    target_ratio = size[0] / size[1]
    source_ratio = source.width / source.height
    if source_ratio > target_ratio:
        height = source.height
        width = round(height * target_ratio)
    else:
        width = source.width
        height = round(width / target_ratio)
    max_x, max_y = source.width - width, source.height - height
    x = int(rng.integers(0, max_x + 1)) if max_x else 0
    y = int(rng.integers(0, max_y + 1)) if max_y else 0
    return source.crop((x, y, x + width, y + height)).resize(size, Image.Resampling.LANCZOS)


def paste_rotated(canvas: Image.Image, tile: Image.Image, rect: tuple[float, ...], shadow: bool = True) -> None:
    cx, cy, width, height, angle = rect
    width, height = round(width), round(height)
    if shadow:
        shadow_tile = Image.new("RGBA", (width + 26, height + 26), (0, 0, 0, 0))
        shadow_tile.paste((0, 0, 0, 105), (13, 13, width + 13, height + 13))
        shadow_tile = shadow_tile.filter(ImageFilter.GaussianBlur(11)).rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
        canvas.paste(shadow_tile, (round(cx - shadow_tile.width / 2 + 7), round(cy - shadow_tile.height / 2 + 9)), shadow_tile)
    rotated = tile.convert("RGBA").rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
    canvas.paste(rotated, (round(cx - rotated.width / 2), round(cy - rotated.height / 2)), rotated)


def make_scan(
    sources: list[Image.Image],
    background: tuple[int, int, int],
    rects: list[tuple],
    index: int,
) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), background)
    rng = np.random.default_rng(1000 + index)
    noise = rng.normal(0, 2.2, (HEIGHT, WIDTH, 1))
    paper = np.clip(np.asarray(canvas, dtype=np.float32) + noise, 0, 255).astype(np.uint8)
    canvas = Image.fromarray(paper)
    for photo_index, rect in enumerate(rects):
        _, _, width, height, _ = rect
        border = 14 if index not in {2, 8} else 8
        source = sources[(index + photo_index) % len(sources)]
        inner = crop_texture(source, (round(width) - border * 2, round(height) - border * 2), index * 10 + photo_index)
        if index in {2, 8}:
            inner = ImageEnhance.Contrast(inner).enhance(0.72)
            inner = ImageEnhance.Color(inner).enhance(0.65)
        tile = Image.new("RGB", (round(width), round(height)), (238, 233, 218) if index in {2, 8} else (249, 247, 239))
        tile.paste(inner, (border, border))
        paste_rotated(canvas, tile, rect, shadow=index not in {2, 4, 8})
    return canvas


def make_album(source: Image.Image, background: tuple[int, int, int], full_rect: tuple, page_color: tuple[int, int, int], index: int) -> Image.Image:
    canvas = Image.new("RGB", (WIDTH, HEIGHT), background)
    cx, cy, width, height, angle = full_rect
    tile = Image.new("RGB", (round(width), round(height)), page_color)
    border = max(24, round(min(width, height) * 0.045))
    content = crop_texture(source, (tile.width - border * 2, tile.height - border * 2), 200 + index)
    tile.paste(content, (border, border))
    paste_rotated(canvas, tile, full_rect, shadow=True)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scan_sources", type=Path)
    parser.add_argument("album_sources", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    scan_paths = sorted(args.scan_sources.glob("*.png"))
    album_paths = sorted(args.album_sources.glob("*.png"))
    if len(scan_paths) != 10 or len(album_paths) != 10:
        raise SystemExit(
            f"expected 10 scan and 10 album PNG sources, found "
            f"{len(scan_paths)} and {len(album_paths)}"
        )
    scan_sources = [Image.open(path).convert("RGB") for path in scan_paths]
    fixtures = args.output / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    cases = []
    for index, (name, background, rects) in enumerate(SCAN_CASES):
        image = make_scan(scan_sources, background, rects, index)
        relative = f"fixtures/scansplitter-{index + 1:02d}-{name}.jpg"
        image.save(args.output / relative, quality=91, subsampling=0)
        cases.append({"id": f"scansplitter-{index + 1:02d}-{name}", "suite": "scansplitter", "image": relative, "rectangles": [list(rect) for rect in rects]})
    for index, (name, layout, background, expected, page_color) in enumerate(ALBUM_CASES):
        if len(expected) == 2:
            first, second = expected
            angle = first[4]
            full = ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2, first[2] + second[2], first[3], angle)
        else:
            full = expected[0]
        album_source = Image.open(album_paths[index]).convert("RGB")
        image = make_album(album_source, background, full, page_color, index)
        relative = f"fixtures/album-{index + 1:02d}-{name}.jpg"
        image.save(args.output / relative, quality=91, subsampling=0)
        cases.append({"id": f"album-{index + 1:02d}-{name}", "suite": "album", "layout": layout, "image": relative, "rectangles": [list(rect) for rect in expected]})
    manifest = {"version": 1, "image_size": [WIDTH, HEIGHT], "rectangle_format": ["center_x", "center_y", "width", "height", "angle_degrees"], "cases": cases}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
