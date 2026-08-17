#!/usr/bin/env -S uv run
"""Rebuild ScanSplitter fixtures with realistic mounted-photo geometry.

The photographic textures and blank album surface were created with the
built-in OpenAI image generator. This script composes them deterministically
so the benchmark can label the *photographic image area* exactly, independently
of paper borders, tape, shadows, and album-page texture.

This is intentionally separate from ``_build_dataset.py``: the Album Splitter
fixtures remain unchanged while the ScanSplitter suite can evolve its realism
without losing exact ground truth.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1400, 1000


@dataclass(frozen=True)
class Print:
    """One mounted print; ``rect`` describes its inner photographic image."""

    rect: tuple[float, float, float, float, float]
    source: int
    border: tuple[int, int, int, int] = (18, 18, 18, 18)
    treatment: str = "normal"
    mount: str = "plain"


@dataclass(frozen=True)
class Case:
    name: str
    prints: tuple[Print, ...]
    page_treatment: str = "cream"
    glare: bool = False


CASES = (
    Case(
        "aged-album-spread",
        (
            Print((270, 215, 310, 205, -2), 0, (22, 27, 22, 30), "monochrome", "tape"),
            Print((565, 225, 220, 300, 2), 1, (17, 20, 20, 27), "faded", "scalloped"),
            Print((905, 215, 300, 205, -1), 2, (25, 25, 25, 29), "monochrome", "corners"),
            Print((1190, 225, 210, 300, 2), 3, (16, 18, 21, 24), "monochrome", "plain"),
            Print((345, 650, 400, 255, 1), 4, (24, 22, 24, 32), "sepia", "scalloped"),
            Print((1015, 650, 430, 265, -2), 5, (21, 22, 25, 31), "monochrome", "tape"),
        ),
    ),
    Case(
        "wide-paper-margins",
        (
            Print((285, 260, 360, 230, -4), 6, (35, 44, 31, 52), "sepia", "corners"),
            Print((730, 235, 300, 215, 2), 7, (46, 38, 39, 47), "faded", "plain"),
            Print((1135, 275, 255, 350, 4), 8, (31, 35, 38, 48), "monochrome", "tape"),
            Print((410, 700, 380, 245, 3), 9, (40, 34, 43, 56), "normal", "scalloped"),
            Print((960, 700, 390, 250, -3), 0, (32, 39, 35, 49), "monochrome", "plain"),
        ),
        glare=True,
    ),
    Case(
        "tape-and-photo-corners",
        (
            Print((285, 245, 365, 240, -5), 1, (17, 22, 20, 28), "faded", "tape"),
            Print((760, 240, 360, 235, 3), 2, (20, 19, 20, 27), "monochrome", "corners"),
            Print((1160, 280, 230, 335, 5), 3, (18, 21, 18, 30), "monochrome", "tape"),
            Print((380, 700, 410, 260, 2), 4, (24, 25, 24, 34), "sepia", "corners"),
            Print((980, 700, 420, 265, -2), 5, (20, 23, 27, 32), "faded", "tape"),
        ),
        page_treatment="foxed",
    ),
    Case(
        "scalloped-low-contrast",
        (
            Print((305, 285, 390, 250, -3), 6, (28, 31, 30, 38), "pale", "scalloped"),
            Print((825, 255, 390, 245, 2), 7, (26, 27, 28, 37), "faded", "scalloped"),
            Print((1180, 295, 220, 330, 4), 8, (23, 25, 27, 35), "pale", "scalloped"),
            Print((500, 715, 440, 265, 1), 9, (30, 31, 32, 43), "pale", "scalloped"),
            Print((1050, 720, 390, 255, -2), 0, (25, 29, 28, 40), "faded", "scalloped"),
        ),
        page_treatment="faded",
        glare=True,
    ),
    Case(
        "narrow-mounted-gutters",
        (
            Print((315, 255, 340, 220, -1), 1, (21, 22, 21, 28), "monochrome", "plain"),
            Print((735, 255, 340, 220, 1), 2, (21, 22, 21, 28), "monochrome", "plain"),
            Print((1148, 255, 330, 220, -1), 3, (19, 22, 23, 28), "faded", "plain"),
            Print((315, 665, 340, 230, 1), 4, (22, 23, 22, 30), "sepia", "plain"),
            Print((735, 665, 340, 230, -1), 5, (22, 23, 22, 30), "monochrome", "plain"),
            Print((1148, 665, 330, 230, 1), 6, (20, 23, 24, 30), "faded", "plain"),
        ),
    ),
    Case(
        "dark-scrapbook-page",
        (
            Print((285, 270, 360, 235, -4), 7, (27, 29, 25, 39), "faded", "corners"),
            Print((755, 255, 350, 230, 3), 8, (25, 27, 28, 36), "monochrome", "tape"),
            Print((1145, 285, 250, 345, 5), 9, (22, 25, 24, 34), "normal", "corners"),
            Print((405, 710, 430, 270, 2), 0, (30, 30, 32, 43), "monochrome", "plain"),
            Print((1010, 710, 425, 265, -2), 1, (27, 29, 30, 40), "sepia", "tape"),
        ),
        page_treatment="dark",
    ),
    Case(
        "mixed-print-formats",
        (
            Print((210, 280, 220, 335, -4), 2, (20, 24, 22, 31), "monochrome", "scalloped"),
            Print((525, 245, 255, 255, 3), 3, (24, 24, 24, 32), "faded", "plain"),
            Print((890, 270, 350, 225, -2), 4, (21, 24, 25, 31), "sepia", "corners"),
            Print((1220, 300, 205, 320, 5), 5, (18, 22, 20, 29), "monochrome", "tape"),
            Print((345, 735, 420, 250, 2), 6, (28, 27, 29, 39), "normal", "plain"),
            Print((950, 720, 430, 270, -2), 7, (24, 26, 27, 36), "faded", "scalloped"),
        ),
        page_treatment="foxed",
    ),
    Case(
        "page-edge-and-binding",
        (
            Print((190, 250, 310, 215, -5), 8, (24, 27, 22, 35), "monochrome", "tape"),
            Print((575, 265, 300, 220, 3), 9, (20, 25, 25, 32), "pale", "plain"),
            Print((945, 245, 315, 220, -2), 0, (26, 25, 24, 34), "monochrome", "corners"),
            Print((1245, 270, 210, 330, 4), 1, (18, 23, 22, 30), "faded", "scalloped"),
            Print((300, 720, 390, 255, 2), 2, (28, 29, 27, 40), "monochrome", "plain"),
            Print((930, 715, 470, 275, -2), 3, (25, 28, 31, 38), "normal", "tape"),
        ),
        glare=True,
    ),
    Case(
        "faded-glossy-protection",
        (
            Print((300, 280, 390, 250, -3), 4, (31, 34, 29, 44), "pale", "plain"),
            Print((810, 265, 390, 250, 2), 5, (28, 31, 32, 42), "faded", "tape"),
            Print((1180, 300, 225, 340, 4), 6, (24, 27, 25, 36), "pale", "corners"),
            Print((470, 730, 440, 265, 1), 7, (31, 33, 34, 45), "faded", "scalloped"),
            Print((1050, 720, 390, 255, -2), 8, (26, 30, 29, 39), "pale", "plain"),
        ),
        page_treatment="faded",
        glare=True,
    ),
    Case(
        "irregular-real-world-layout",
        (
            Print((250, 235, 340, 225, -6), 9, (23, 27, 21, 35), "monochrome", "tape"),
            Print((730, 255, 390, 245, 3), 0, (27, 29, 30, 40), "faded", "corners"),
            Print((1160, 265, 235, 340, 5), 1, (20, 24, 23, 32), "monochrome", "scalloped"),
            Print((365, 700, 420, 270, 2), 2, (31, 29, 33, 43), "sepia", "plain"),
            Print((980, 690, 450, 275, -3), 3, (25, 28, 31, 39), "monochrome", "tape"),
        ),
        page_treatment="foxed",
        glare=True,
    ),
)


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


def treat_photo(image: Image.Image, treatment: str) -> Image.Image:
    if treatment == "monochrome":
        return ImageOps.grayscale(image).convert("RGB")
    if treatment == "sepia":
        gray = np.asarray(ImageOps.grayscale(image), dtype=np.float32)
        rgb = np.stack((gray * 1.08 + 14, gray * 0.96 + 7, gray * 0.78), axis=-1)
        return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    if treatment == "faded":
        image = ImageEnhance.Color(image).enhance(0.45)
        image = ImageEnhance.Contrast(image).enhance(0.78)
        return ImageEnhance.Brightness(image).enhance(1.07)
    if treatment == "pale":
        image = ImageEnhance.Color(image).enhance(0.25)
        image = ImageEnhance.Contrast(image).enhance(0.58)
        return Image.blend(image, Image.new("RGB", image.size, (229, 220, 198)), 0.16)
    return image


def scalloped_mask(size: tuple[int, int], depth: int = 8, period: int = 18) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    points: list[tuple[float, float]] = []
    for x in range(0, width + 1, 3):
        points.append((x, depth + depth * 0.35 * math.sin(2 * math.pi * x / period)))
    for y in range(0, height + 1, 3):
        points.append((width - depth - depth * 0.35 * math.sin(2 * math.pi * y / period), y))
    for x in range(width, -1, -3):
        points.append((x, height - depth - depth * 0.35 * math.sin(2 * math.pi * x / period)))
    for y in range(height, -1, -3):
        points.append((depth + depth * 0.35 * math.sin(2 * math.pi * y / period), y))
    draw.polygon(points, fill=255)
    return mask


def add_mounting(tile: Image.Image, mount: str) -> None:
    draw = ImageDraw.Draw(tile, "RGBA")
    width, height = tile.size
    if mount == "tape":
        tape = (207, 185, 132, 115)
        draw.polygon(((0, 8), (60, 2), (68, 24), (5, 31)), fill=tape)
        draw.polygon(((width - 58, height - 25), (width, height - 32), (width, height - 5), (width - 65, height)), fill=tape)
    elif mount == "corners":
        corner = (190, 166, 112, 210)
        length = min(42, width // 5, height // 5)
        draw.polygon(((0, 0), (length, 0), (0, length)), fill=corner)
        draw.polygon(((width, 0), (width - length, 0), (width, length)), fill=corner)
        draw.polygon(((0, height), (length, height), (0, height - length)), fill=corner)
        draw.polygon(((width, height), (width - length, height), (width, height - length)), fill=corner)


def make_print(source: Image.Image, spec: Print, seed: int) -> Image.Image:
    _, _, width, height, _ = spec.rect
    content_size = (round(width), round(height))
    content = treat_photo(crop_texture(source, content_size, seed), spec.treatment)
    left, top, right, bottom = spec.border
    outer_size = (content.width + left + right, content.height + top + bottom)
    paper_color = (232, 225, 207) if spec.treatment in {"pale", "faded"} else (246, 242, 229)
    tile = Image.new("RGBA", outer_size, paper_color + (255,))
    tile.paste(content, (left, top))

    # Physical print edge, separate from the desired inner photographic edge.
    draw = ImageDraw.Draw(tile, "RGBA")
    draw.rectangle((left - 1, top - 1, left + content.width, top + content.height), outline=(80, 70, 58, 80), width=2)
    add_mounting(tile, spec.mount)
    if spec.mount == "scalloped":
        tile.putalpha(scalloped_mask(tile.size))
    return tile


def page_background(index: int, treatment: str) -> Image.Image:
    source = Image.open(ROOT / "source_textures" / "blank-album-spread.png").convert("RGB")
    # Crop away most of the table so the album page itself exceeds the detector's
    # max-area threshold, as in a real close overhead capture.
    source = source.crop((45, 72, source.width - 42, source.height - 42))
    if index % 2:
        source = ImageOps.mirror(source)
    page = source.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    if treatment == "foxed":
        page = ImageEnhance.Color(page).enhance(0.72)
        page = ImageEnhance.Contrast(page).enhance(1.08)
    elif treatment == "faded":
        page = ImageEnhance.Contrast(page).enhance(0.82)
        page = ImageEnhance.Brightness(page).enhance(1.04)
    elif treatment == "dark":
        overlay = Image.new("RGB", page.size, (62, 48, 45))
        page = Image.blend(page, overlay, 0.68)
        page = ImageEnhance.Contrast(page).enhance(0.92)
    return page


def paste_print(canvas: Image.Image, tile: Image.Image, spec: Print) -> None:
    cx, cy, _, _, angle = spec.rect
    left, top, right, bottom = spec.border
    local_x = (left - right) / 2
    local_y = (top - bottom) / 2
    radians = math.radians(angle)
    rotated_x = math.cos(radians) * local_x - math.sin(radians) * local_y
    rotated_y = math.sin(radians) * local_x + math.cos(radians) * local_y
    outer_cx = cx - rotated_x
    outer_cy = cy - rotated_y
    shadow = Image.new("RGBA", (tile.width + 38, tile.height + 38), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 92), (18, 18, tile.width + 18, tile.height + 18), tile.getchannel("A"))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12)).rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
    canvas.paste(shadow, (round(outer_cx - shadow.width / 2 + 8), round(outer_cy - shadow.height / 2 + 10)), shadow)
    rotated = tile.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
    canvas.paste(rotated, (round(outer_cx - rotated.width / 2), round(outer_cy - rotated.height / 2)), rotated)


def add_page_artifacts(canvas: Image.Image, case: Case, index: int) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    # Abstract blue-ink strokes are intentionally unreadable but reproduce the
    # local edges and colors created by handwritten album captions.
    rng = np.random.default_rng(5000 + index)
    for print_spec in case.prints[::2]:
        cx, cy, width, height, _ = print_spec.rect
        y = min(HEIGHT - 20, cy + height / 2 + print_spec.border[3] + 18)
        x = max(15, cx - width * 0.22)
        points = [(x + step * 12, y + float(rng.normal(0, 3))) for step in range(7)]
        draw.line(points, fill=(35, 55, 116, 150), width=3)
    if case.glare:
        draw.polygon(((120, 0), (310, 0), (1040, HEIGHT), (830, HEIGHT)), fill=(255, 255, 250, 22))
        draw.polygon(((970, 0), (1060, 0), (1390, 680), (1310, 700)), fill=(255, 255, 255, 28))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

    # Mild sensor noise, illumination falloff, and JPEG-like softness.
    arr = np.asarray(canvas, dtype=np.float32)
    yy, xx = np.mgrid[:HEIGHT, :WIDTH]
    radial = ((xx - WIDTH / 2) / WIDTH) ** 2 + ((yy - HEIGHT / 2) / HEIGHT) ** 2
    arr *= (1.0 - 0.10 * radial[..., None])
    arr += rng.normal(0, 1.8, arr.shape[:2])[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.35))


def build_case(case: Case, sources: list[Image.Image], index: int) -> Image.Image:
    canvas = page_background(index, case.page_treatment)
    for print_index, spec in enumerate(case.prints):
        tile = make_print(sources[spec.source], spec, index * 100 + print_index)
        paste_print(canvas, tile, spec)
    return add_page_artifacts(canvas, case, index)


def main() -> None:
    photo_paths = sorted((ROOT / "source_textures" / "photos").glob("photo-*.jpg"))
    if len(photo_paths) != 10:
        raise SystemExit(f"expected ten generated photo textures, found {len(photo_paths)}")
    sources = [Image.open(path).convert("RGB") for path in photo_paths]
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    album_cases = [case for case in manifest["cases"] if case["suite"] == "album"]

    scan_cases = []
    for index, case in enumerate(CASES):
        case_id = f"scansplitter-{index + 1:02d}-{case.name}"
        relative = f"fixtures/{case_id}.jpg"
        build_case(case, sources, index).save(ROOT / relative, quality=91, subsampling=0)
        scan_cases.append(
            {
                "id": case_id,
                "suite": "scansplitter",
                "image": relative,
                "target": "photographic_content",
                "rectangles": [list(spec.rect) for spec in case.prints],
            }
        )

    manifest.update(
        {
            "version": 2,
            "image_size": [WIDTH, HEIGHT],
            "target_definition": {
                "scansplitter": "inner photographic image area; exclude paper borders, tape, corners, shadows, and album page",
                "album": "complete album page or leaf",
            },
            "cases": scan_cases + album_cases,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
