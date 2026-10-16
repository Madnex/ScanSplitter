#!/usr/bin/env -S uv run
"""Procedurally generate the DEV / HOLDOUT photo-scan robustness benchmark.

Every case is composed from real photographic textures (``source_textures``)
onto procedural or generated backgrounds, so ground truth is exact: the inner
photographic image area as a rotated rectangle ``[cx, cy, w, h, angle]`` in
output-pixel coordinates. Print borders, Polaroid frames, tape, corners and
shadows are never part of the target.

* DEV and HOLDOUT use different RNG seeds *and* disjoint source photo groups
  (photos 01-30 are split by a fixed permutation) so a detector tuned on DEV
  cannot memorise images.
* Output is deterministic for a given set of source files.

Usage::

    uv run benchmarks/_build_robustness.py                 # generate everything
    uv run benchmarks/_build_robustness.py --split dev     # only one split
    uv run benchmarks/_build_robustness.py --overlay DIR   # draw GT boxes for QA
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import _build_authentic_scans as authentic  # noqa: E402

OUT = ROOT / "robustness"
PHOTOS = ROOT / "source_textures" / "photos"
BACKGROUNDS = ROOT / "source_textures" / "backgrounds"
SPLIT_SEEDS = {"dev": 1001, "holdout": 2002}

# (scenario, cases per split)
SCENARIOS = (
    ("flatbed-white", 5),
    ("flatbed-black", 4),
    ("rotated", 4),
    ("single-large", 4),
    ("many-small", 3),
    ("tight-gutters", 4),
    ("edge-touching", 4),
    ("low-contrast", 4),
    ("polaroid", 4),
    ("phone-capture", 4),
    ("album", 4),
    ("mixed-hard", 3),
)
LETTER_FIRST = {"flatbed-white", "flatbed-black", "single-large"}
LARGE_SECOND = {"rotated", "tight-gutters", "polaroid", "edge-touching", "low-contrast", "mixed-hard"}


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------
def rot(angle_deg: float) -> np.ndarray:
    """Clockwise-on-screen rotation (image coordinates, y down)."""
    a = math.radians(angle_deg)
    return np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])


@dataclass
class Spec:
    """One print; ``(cx, cy, iw, ih, angle)`` is the inner photographic rect."""

    cx: float
    cy: float
    iw: int
    ih: int
    angle: float
    border: tuple[int, int, int, int]  # lf, t, r, b
    source: int = 0
    treatment: str = "normal"
    paper: tuple[float, float, float] = (247, 245, 238)
    photo_mod: str = ""
    shadow: dict = field(default_factory=dict)
    kind: str = "print"

    @property
    def rect(self) -> list[float]:
        return [round(self.cx, 2), round(self.cy, 2), self.iw, self.ih, round(self.angle, 3)]

    def outer_polygon(self, inflate: float = 0.0) -> np.ndarray:
        lf, t, r, b = self.border
        ow, oh = self.iw + lf + r + 2 * inflate, self.ih + t + b + 2 * inflate
        local = np.array([(lf - r) / 2.0, (t - b) / 2.0])
        centre = np.array([self.cx, self.cy]) - rot(self.angle) @ local
        half = np.array([(-ow / 2, -oh / 2), (ow / 2, -oh / 2), (ow / 2, oh / 2), (-ow / 2, oh / 2)])
        return centre + half @ rot(self.angle).T


def bbox_size(w: float, h: float, angle: float) -> tuple[float, float]:
    c, s = abs(math.cos(math.radians(angle))), abs(math.sin(math.radians(angle)))
    return w * c + h * s, w * s + h * c


def fit_print(
    rng: np.random.Generator,
    cell: tuple[float, float, float, float],
    aspect: float,
    border_fn,
    angle: float,
    fill: float,
    snap: tuple[str, ...] = (),
    snap_gap: float = 0.0,
    min_inner: float = 24.0,
):
    """Largest inner rect (aspect ``aspect``) whose rotated outer bbox fits ``fill`` of ``cell``.

    Returns ``(cx, cy, iw, ih, border)`` or ``None``. ``snap`` sides ("left",
    "right", "top", "bottom") push the outer bbox to ``snap_gap`` px from that
    cell side instead of centring it.
    """
    x0, y0, x1, y1 = cell
    cw, ch = (x1 - x0) * fill, (y1 - y0) * fill
    lo, hi = 0.0, max(cw, ch) * 2
    for _ in range(40):
        k = (lo + hi) / 2
        lf, t, r, b = border_fn(k)
        bw, bh = bbox_size(aspect * k + lf + r, k + t + b, angle)
        if bw <= cw and bh <= ch:
            lo = k
        else:
            hi = k
    ih = int(lo)
    iw = int(round(aspect * lo))
    if ih < min_inner or iw < min_inner:
        return None
    lf, t, r, b = border_fn(lo)
    ow, oh = iw + lf + r, ih + t + b
    bw, bh = bbox_size(ow, oh, angle)
    slack_x, slack_y = (x1 - x0) - bw, (y1 - y0) - bh
    left = x0 + slack_x * float(rng.uniform(0.15, 0.85))
    top = y0 + slack_y * float(rng.uniform(0.15, 0.85))
    if "left" in snap:
        left = x0 + snap_gap
    if "right" in snap:
        left = x1 - bw - snap_gap
    if "top" in snap:
        top = y0 + snap_gap
    if "bottom" in snap:
        top = y1 - bh - snap_gap
    centre = np.array([left + bw / 2, top + bh / 2])
    local = np.array([(lf - r) / 2.0, (t - b) / 2.0])
    inner_c = centre + rot(angle) @ local
    return float(inner_c[0]), float(inner_c[1]), iw, ih, (lf, t, r, b)


def grid_cells(rng, n, width, height, margin=(0.0, 0.0, 0.0, 0.0), prefer=None):
    """Return ``n`` cells of a rows x cols grid covering the canvas minus margins."""
    options = []
    for rows in range(1, n + 1):
        cols = math.ceil(n / rows)
        score = abs(math.log((width / cols) / (height / rows))) + 0.08 * (rows * cols - n)
        options.append((score, rows, cols))
    options.sort()
    if prefer:
        rows, cols = prefer
    else:
        _, rows, cols = options[0] if len(options) < 2 or rng.random() < 0.6 else options[1]
    mx0, my0, mx1, my1 = margin
    gx0, gy0, gx1, gy1 = mx0, my0, width - mx1, height - my1
    cells = []
    for row in range(rows):
        for col in range(cols):
            cells.append(
                (
                    gx0 + (gx1 - gx0) * col / cols,
                    gy0 + (gy1 - gy0) * row / rows,
                    gx0 + (gx1 - gx0) * (col + 1) / cols,
                    gy0 + (gy1 - gy0) * (row + 1) / rows,
                )
            )
    rng.shuffle(cells)
    return cells[:n], rows, cols


# --------------------------------------------------------------------------
# procedural noise / backgrounds
# --------------------------------------------------------------------------
def lowfreq(rng, h, w, cells=5):
    gh = max(2, int(round(cells * h / max(h, w))) + 1)
    gw = max(2, int(round(cells * w / max(h, w))) + 1)
    return cv2.resize(rng.normal(size=(gh, gw)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)


def background_files() -> list[Path]:
    if not BACKGROUNDS.is_dir():
        return []
    return sorted(p for p in BACKGROUNDS.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"})


def split_backgrounds(split: str) -> list[Path]:
    files = background_files()
    if len(files) < 4:
        return files  # too few to split; both splits share them (different crops)
    return files[0::2] if split == "dev" else files[1::2]


def file_background(rng, path: Path, w: int, h: int) -> np.ndarray:
    with Image.open(path) as image:
        image = image.convert("RGB")
    if rng.random() < 0.5:
        image = ImageOps.mirror(image)
    if rng.random() < 0.5:
        image = ImageOps.flip(image)
    if (w > h) != (image.width > image.height) and rng.random() < 0.7:
        image = image.transpose(Image.Transpose.TRANSPOSE)
    zoom = float(rng.uniform(1.0, 1.6))
    cw = min(image.width, max(32, int(image.width / zoom)))
    ch = min(image.height, max(32, int(image.height / zoom)))
    x = int(rng.integers(0, image.width - cw + 1))
    y = int(rng.integers(0, image.height - ch + 1))
    image = image.crop((x, y, x + cw, y + ch)).resize((w, h), Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.float32)


def procedural_texture(rng, kind: str, w: int, h: int) -> np.ndarray:
    fine = rng.normal(size=(h, w)).astype(np.float32)
    if kind == "kraft":
        fibre = cv2.GaussianBlur(fine, (0, 0), sigmaX=7, sigmaY=0.9) * 22
        base = np.array([176, 140, 98], np.float32) * (1 + 0.05 * lowfreq(rng, h, w, 4))[..., None]
        return base + fibre[..., None] * np.array([1.0, 0.85, 0.6], np.float32) + fine[..., None] * 2.5
    if kind == "wood":
        yy = np.arange(h, dtype=np.float32)[:, None] + 60 * lowfreq(rng, h, w, 3)
        grain = 0.5 + 0.5 * np.sin(yy / float(rng.uniform(9, 16))) * (0.7 + 0.3 * np.sin(yy / 3.1))
        grain = grain + cv2.GaussianBlur(fine, (0, 0), sigmaX=12, sigmaY=0.8) * 3.5
        base = np.array([122, 82, 50], np.float32)
        return base * (0.72 + 0.4 * grain[..., None]) + fine[..., None] * 2
    if kind == "carpet":
        base = np.array([108, 112, 118], np.float32) * (1 + 0.08 * lowfreq(rng, h, w, 4))[..., None]
        return base + cv2.GaussianBlur(fine, (0, 0), 0.8)[..., None] * 24
    raise ValueError(kind)


def make_background(rng, kind: str, w: int, h: int, split: str):
    """Return ``(float32 HxWx3, tag)``."""
    if kind == "white":
        base = np.array([250.0, 250.0, 248.0]) + rng.uniform(-2, 1, 3)
        yy, xx = np.mgrid[:h, :w].astype(np.float32)
        ang = float(rng.uniform(0, 2 * np.pi))
        ramp = (np.cos(ang) * xx / w + np.sin(ang) * yy / h)
        img = base * (1 - 0.018 * ramp[..., None]) + 0.7 * lowfreq(rng, h, w, 3)[..., None]
        streak = cv2.GaussianBlur(rng.normal(size=(1, w)).astype(np.float32), (0, 0), 25)[0] * 0.25
        return img + streak[None, :, None], "lid-white"
    if kind == "black":
        fine = cv2.GaussianBlur(rng.normal(size=(h, w)).astype(np.float32), (0, 0), 0.7)
        img = np.array([13.0, 13.0, 14.0]) + fine[..., None] * 3.2 + lowfreq(rng, h, w, 3)[..., None] * 0.8
        return img, "felt-black"
    if kind == "beige":
        base = np.array([238.0, 232.0, 216.0])
        return base + lowfreq(rng, h, w, 3)[..., None] * 1.2 + rng.normal(size=(h, w, 1)) * 0.8, "lid-beige"
    pool = [p for p in split_backgrounds(split) if kind in p.stem.lower()] if kind != "textured" else []
    if not pool and kind in {"wood", "carpet", "kraft"}:
        pool = [p for p in split_backgrounds(split) if kind in p.stem.lower()]
    if kind == "textured":
        pool = split_backgrounds(split)
        kind = str(rng.choice(["wood", "carpet", "kraft"]))
    if pool:
        path = pool[int(rng.integers(len(pool)))]
        return file_background(rng, path, w, h), f"bg-{path.stem}"
    return procedural_texture(rng, kind, w, h), f"proc-{kind}"


# --------------------------------------------------------------------------
# prints
# --------------------------------------------------------------------------
def crop_photo(rng, source: np.ndarray, iw: int, ih: int) -> np.ndarray:
    sh, sw = source.shape[:2]
    if rng.random() < 0.5:
        source = source[:, ::-1]
    ratio = iw / ih
    if sw / sh > ratio:
        ch = sh
        cw = int(round(sh * ratio))
    else:
        cw = sw
        ch = int(round(sw / ratio))
    zoom = float(rng.uniform(0.7, 1.0))
    cw, ch = max(16, int(cw * zoom)), max(16, int(ch * zoom))
    x = int(rng.integers(0, sw - cw + 1))
    y = int(rng.integers(0, sh - ch + 1))
    crop = np.ascontiguousarray(source[y : y + ch, x : x + cw])
    return cv2.resize(crop, (iw, ih), interpolation=cv2.INTER_CUBIC if iw > cw else cv2.INTER_AREA)


KRAFT = np.array([176.0, 140.0, 98.0])


def treat(rng, photo: np.ndarray, treatment: str, mod: str) -> np.ndarray:
    image = Image.fromarray(np.clip(photo, 0, 255).astype(np.uint8))
    arr = np.asarray(authentic.treat_photo(image, treatment), dtype=np.float32)
    if mod == "highkey":
        arr = 255 - (255 - arr) * float(rng.uniform(0.28, 0.42))
    elif mod == "dark":
        arr = (arr / 255) ** float(rng.uniform(1.7, 2.2)) * 255 * float(rng.uniform(0.45, 0.6))
    elif mod == "beige":
        gray = arr.mean(axis=2, keepdims=True) / 255
        arr = KRAFT * (0.78 + 0.34 * gray) + rng.normal(0, 1.5, arr.shape)
    return arr


def make_tile(rng, spec: Spec, sources: list[np.ndarray]) -> np.ndarray:
    iw, ih = spec.iw, spec.ih
    lf, t, r, b = spec.border
    photo = treat(rng, crop_photo(rng, sources[spec.source], iw, ih).astype(np.float32), spec.treatment, spec.photo_mod)
    # small random colour / gamma jitter (scanner white balance, print ageing)
    gamma = float(rng.uniform(0.88, 1.14))
    gains = rng.uniform(0.96, 1.04, 3)
    photo = np.clip((np.clip(photo, 0, 255) / 255) ** gamma * 255 * gains, 0, 255)
    photo = photo + rng.normal(0, 1.6, photo.shape[:2])[..., None]  # film grain
    # paper curl / edge darkening: one or two edges noticeably darker
    yy = np.arange(ih, dtype=np.float32)[:, None]
    xx = np.arange(iw, dtype=np.float32)[None, :]
    decay = 0.012 * min(iw, ih) + 3
    factor = np.ones((ih, iw), np.float32)
    strengths = rng.uniform(0.01, 0.04, 4)
    strengths[int(rng.integers(4))] = float(rng.uniform(0.06, 0.15))
    for dist, strength in zip((xx, iw - 1 - xx, yy, ih - 1 - yy), strengths):
        factor = factor * (1 - strength * np.exp(-dist / decay))
    photo = photo * factor[..., None]
    gradient = 1 + float(rng.uniform(-0.04, 0.04)) * ((xx / iw) - 0.5 + (yy / ih) - 0.5)
    photo = photo * gradient[..., None]

    th, tw = ih + t + b, iw + lf + r
    paper = np.array(spec.paper, np.float32) + rng.uniform(-3, 3, 3).astype(np.float32)
    tile = np.empty((th, tw, 3), np.float32)
    tile[:] = paper
    tile += (lowfreq(rng, th, tw, 4) * 1.2 + rng.normal(0, 0.8, (th, tw)))[..., None]
    tile[t : t + ih, lf : lf + iw] = photo
    if lf + t + r + b > 0:
        # thin darker line where photo emulsion meets the paper border
        cv2.rectangle(tile, (lf - 1, t - 1), (lf + iw, t + ih), tuple(float(v) * 0.9 for v in paper), 1)
        # border edge darkening mirrors the photo curl
        border_factor = np.ones((th, tw), np.float32)
        ys = np.arange(th, dtype=np.float32)[:, None]
        xs = np.arange(tw, dtype=np.float32)[None, :]
        for dist, strength in zip((xs, tw - 1 - xs, ys, th - 1 - ys), strengths):
            border_factor = border_factor * (1 - 0.6 * strength * np.exp(-dist / (decay * 1.5)))
        mask = np.ones((th, tw), bool)
        mask[t : t + ih, lf : lf + iw] = False
        tile[mask] *= border_factor[mask][:, None]
    return tile


def composite_print(canvas: np.ndarray, spec: Spec, tile: np.ndarray) -> None:
    h, w = canvas.shape[:2]
    th, tw = tile.shape[:2]
    lf, t = spec.border[0], spec.border[1]
    rotation = rot(spec.angle)
    c_in = np.array([lf + spec.iw / 2.0, t + spec.ih / 2.0])
    centre = np.array([spec.cx, spec.cy])
    corners = np.array([(0, 0), (tw, 0), (tw, th), (0, th)], float)
    placed = (corners - c_in) @ rotation.T + centre
    shadow = spec.shadow
    sigma = float(shadow.get("sigma", 0.0))
    off = np.array(shadow.get("off", (0.0, 0.0)), float)
    pad = int(3 * sigma + np.abs(off).max() + 4)
    x0, y0 = max(0, int(placed[:, 0].min()) - pad), max(0, int(placed[:, 1].min()) - pad)
    x1, y1 = min(w, int(placed[:, 0].max()) + pad + 2), min(h, int(placed[:, 1].max()) + pad + 2)
    if x1 <= x0 or y1 <= y0:
        return
    translation = centre - 0.5 - rotation @ (c_in - 0.5) - np.array([x0, y0])
    matrix = np.hstack([rotation, translation[:, None]]).astype(np.float64)
    size = (x1 - x0, y1 - y0)
    coverage = cv2.warpAffine(np.ones((th, tw), np.float32), matrix, size, flags=cv2.INTER_LINEAR)
    colour = cv2.warpAffine(tile, matrix, size, flags=cv2.INTER_LINEAR)
    roi = canvas[y0:y1, x0:x1]
    if shadow:
        soft = cv2.GaussianBlur(coverage, (0, 0), max(0.3, sigma))
        soft = cv2.warpAffine(soft, np.float64([[1, 0, off[0]], [0, 1, off[1]]]), size)
        roi *= (1 - float(shadow["strength"]) * soft)[..., None]
    roi[...] = roi * (1 - coverage[..., None]) + colour


def sample_shadow(rng, s: float, soft: bool = False) -> dict:
    """Thin scanner-light shadow on one side (flatbed) or a wider cast shadow."""
    direction = rng.choice(["r", "b", "rb", "lf", "t", "lt"])
    dx = (1 if "r" in direction else -1 if "lf" in direction else 0) * float(rng.uniform(1.5, 3.5))
    dy = (1 if "b" in direction else -1 if "t" in direction else 0) * float(rng.uniform(1.5, 3.5))
    if soft:
        return {
            "off": (dx * 3.5 * s, dy * 3.5 * s + 4 * s),
            "sigma": float(rng.uniform(5, 10)) * s,
            "strength": float(rng.uniform(0.3, 0.5)),
        }
    return {"off": (dx * s, dy * s), "sigma": float(rng.uniform(1.2, 2.8)) * s, "strength": float(rng.uniform(0.2, 0.42))}


# --------------------------------------------------------------------------
# post processing
# --------------------------------------------------------------------------
def add_dust(rng, canvas: np.ndarray, s: float) -> None:
    h, w = canvas.shape[:2]
    overlay = np.zeros((h, w), np.float32)
    count = int(rng.integers(25, 90) * (w * h) / (1400 * 1000))
    for _ in range(count):
        x, y = int(rng.integers(w)), int(rng.integers(h))
        radius = float(rng.uniform(0.5, 2.0)) * s
        cv2.circle(overlay, (x, y), max(1, int(round(radius))), float(rng.uniform(0.25, 0.7)), -1, cv2.LINE_AA)
    for _ in range(int(rng.integers(0, 5))):
        x, y = int(rng.integers(w)), int(rng.integers(h))
        pts = np.array([(x + i * 6 * s, y + float(rng.normal(0, 5 * s))) for i in range(int(rng.integers(3, 8)))], np.int32)
        cv2.polylines(overlay, [pts], False, 0.45, 1, cv2.LINE_AA)
    local = cv2.GaussianBlur(canvas.mean(axis=2), (0, 0), 6 * s)
    target = np.where(local[..., None] > 110, 35.0, 62.0)
    canvas[...] = canvas * (1 - overlay[..., None]) + target * overlay[..., None]


def finish_scan(rng, canvas: np.ndarray, s: float, phone: bool = False) -> np.ndarray:
    h, w = canvas.shape[:2]
    if not phone:
        yy, xx = np.mgrid[:h, :w].astype(np.float32)
        radial = ((xx - w / 2) / w) ** 2 + ((yy - h / 2) / h) ** 2
        canvas *= (1 - float(rng.uniform(0.01, 0.05)) * radial)[..., None]
    add_dust(rng, canvas, s)
    sigma = float(rng.uniform(0.7, 1.4)) * math.sqrt(s) if phone else float(rng.uniform(0.25, 0.55))
    canvas = cv2.GaussianBlur(canvas, (0, 0), sigma)
    noise = float(rng.uniform(2.5, 5.0)) if phone else float(rng.uniform(0.8, 2.2))
    canvas = canvas + rng.normal(0, noise, (h, w, 1)).astype(np.float32) + rng.normal(0, noise * 0.35, (h, w, 3)).astype(np.float32)
    return np.clip(canvas, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# scene assembly
# --------------------------------------------------------------------------
@dataclass
class Result:
    image: np.ndarray
    rects: list[list[float]]
    tags: list[str]


class Context:
    def __init__(self, rng, split: str, photos: list[np.ndarray], width: int, height: int):
        self.rng, self.split, self.photos = rng, split, photos
        self.w, self.h = width, height
        self.s = math.sqrt(width * height / (1400 * 1000))
        self.order = list(rng.permutation(len(photos)))
        self.counter = 0

    def next_source(self) -> int:
        index = self.order[self.counter % len(self.order)]
        self.counter += 1
        return int(index)

    def treatment(self, weights=(0.62, 0.1, 0.06, 0.14, 0.08)) -> str:
        return str(self.rng.choice(["normal", "monochrome", "sepia", "faded", "pale"], p=weights))

    def flat_border(self, allow_none: float = 0.5, wide: tuple[float, float] = (8, 30)):
        if self.rng.random() < allow_none:
            return lambda k: (0, 0, 0, 0), "borderless"
        px = int(round(float(self.rng.uniform(*wide)) * self.s))
        jitter = [max(1, int(round(px * float(self.rng.uniform(0.85, 1.15))))) for _ in range(4)]
        return (lambda k: tuple(jitter)), "bordered"

    def aspect_for(self, cell) -> float:
        landscape = (cell[2] - cell[0]) >= (cell[3] - cell[1])
        base = float(self.rng.choice([1.5, 1.333, 1.5, 1.25, 1.0, 1.78]))
        if self.rng.random() < 0.15:
            landscape = not landscape
        return base if landscape else 1 / base

    def place_cell(self, cell, *, border_fn, angle, fill, shadow, paper=(247, 245, 238), snap=(), snap_gap=0.0,
                   treatment=None, photo_mod="", aspect=None, kind="print"):
        placed = None
        for _ in range(4):
            placed = fit_print(
                self.rng, cell, aspect or self.aspect_for(cell), border_fn, angle, fill, snap, snap_gap
            )
            if placed:
                break
            fill = min(0.98, fill * 1.05)
        if not placed:
            return None
        cx, cy, iw, ih, border = placed
        return Spec(cx, cy, iw, ih, angle, tuple(int(v) for v in border), self.next_source(),
                    treatment or self.treatment(), paper, photo_mod, shadow, kind)


def _separated(first: np.ndarray, second: np.ndarray, gap: float) -> bool:
    """Separating-axis test for two convex quads; True if they are >= ``gap`` apart."""
    for poly in (first, second):
        for i in range(4):
            edge = poly[(i + 1) % 4] - poly[i]
            axis = np.array([-edge[1], edge[0]]) / (np.linalg.norm(edge) or 1.0)
            a, b = first @ axis, second @ axis
            if a.max() + gap <= b.min() or b.max() + gap <= a.min():
                return True
    return False


def specs_overlap(specs: list[Spec], gap: float = 1.0) -> bool:
    polys = [s.outer_polygon() for s in specs]
    return any(
        not _separated(polys[i], polys[j], gap)
        for i in range(len(polys))
        for j in range(i + 1, len(polys))
    )


def render(ctx: Context, background: np.ndarray, specs: list[Spec]) -> np.ndarray:
    canvas = background.astype(np.float32).copy()
    for spec in specs:
        tile = make_tile(ctx.rng, spec, ctx.photos)
        composite_print(canvas, spec, tile)
    return canvas


def signed(rng, lo, hi):
    return float(rng.uniform(lo, hi)) * (1 if rng.random() < 0.5 else -1)


# ---- scenario builders: return (specs, background_kind, tags, extra) ----
def scene_flatbed(ctx: Context, dark: bool):
    rng = ctx.rng
    n = int(rng.integers(1, 7))
    cells, rows, cols = grid_cells(rng, n, ctx.w, ctx.h, margin=(ctx.w * 0.03, ctx.h * 0.03, ctx.w * 0.03, ctx.h * 0.03))
    specs, tags = [], ["flatbed"]
    for cell in cells:
        border_fn, tag = ctx.flat_border(allow_none=0.45)
        spec = ctx.place_cell(
            cell, border_fn=border_fn, angle=signed(rng, 0, 8), fill=float(rng.uniform(0.62, 0.92)),
            shadow=sample_shadow(rng, ctx.s), paper=(250, 249, 245) if not dark else (244, 242, 236),
        )
        if spec:
            specs.append(spec)
            tags.append(tag)
    return specs, "black" if dark else "white", sorted(set(tags))


def scene_rotated(ctx: Context):
    rng = ctx.rng
    n = int(rng.integers(2, 5))
    cells, _, _ = grid_cells(rng, n, ctx.w, ctx.h, margin=(ctx.w * 0.02,) * 2 + (ctx.w * 0.02,) * 2)
    specs = []
    for cell in cells:
        border_fn, _ = ctx.flat_border(allow_none=0.4)
        spec = ctx.place_cell(cell, border_fn=border_fn, angle=signed(rng, 10, 45), fill=float(rng.uniform(0.88, 0.97)),
                              shadow=sample_shadow(rng, ctx.s))
        if spec:
            specs.append(spec)
    bg = str(rng.choice(["white", "black", "white", "kraft"]))
    return specs, bg, ["rotated"]


def scene_single_large(ctx: Context):
    rng = ctx.rng
    fraction = float(rng.uniform(0.45, 0.80))
    angle = signed(rng, 0.2, 4.0) if rng.random() < 0.5 else 0.0
    aspect = (ctx.w / ctx.h) * float(rng.uniform(0.82, 1.0))
    if rng.random() < 0.2:
        aspect = 1 / aspect if aspect > 1 else aspect
    border_fn, tag = ctx.flat_border(allow_none=0.4, wide=(8, 26))
    # outer area target: solve for inner scale k by bisection on area fraction
    lo, hi = 10.0, float(max(ctx.w, ctx.h))
    for _ in range(40):
        k = (lo + hi) / 2
        lf, t, r, b = border_fn(k)
        bw, bh = bbox_size(aspect * k + lf + r, k + t + b, angle)
        area_ok = (aspect * k + lf + r) * (k + t + b) <= fraction * ctx.w * ctx.h
        fits = bw <= ctx.w - 20 * ctx.s and bh <= ctx.h - 20 * ctx.s
        lo, hi = (k, hi) if area_ok and fits else (lo, k)
    lf, t, r, b = border_fn(lo)
    ih, iw = int(lo), int(round(aspect * lo))
    bw, bh = bbox_size(iw + lf + r, ih + t + b, angle)
    centre = np.array([
        ctx.w / 2 + float(rng.uniform(-1, 1)) * max(0.0, ctx.w - bw) / 2 * 0.8,
        ctx.h / 2 + float(rng.uniform(-1, 1)) * max(0.0, ctx.h - bh) / 2 * 0.8,
    ])
    inner_c = centre + rot(angle) @ np.array([(lf - r) / 2.0, (t - b) / 2.0])
    spec = Spec(float(inner_c[0]), float(inner_c[1]), iw, ih, angle, (lf, t, r, b), ctx.next_source(),
                ctx.treatment(), (250, 248, 243), "", sample_shadow(rng, ctx.s))
    bg = str(rng.choice(["white", "black", "white"]))
    tags = ["single-large", tag, f"area~{int(fraction * 100)}%"]
    return [spec], bg, tags


def scene_many_small(ctx: Context):
    rng = ctx.rng
    n = int(rng.integers(8, 13))
    cells, _, _ = grid_cells(rng, n, ctx.w, ctx.h, margin=(ctx.w * 0.03, ctx.h * 0.03, ctx.w * 0.03, ctx.h * 0.03))
    specs = []
    for cell in cells:
        border_fn, _ = ctx.flat_border(allow_none=0.5, wide=(6, 18))
        spec = ctx.place_cell(cell, border_fn=border_fn, angle=signed(rng, 0, 5), fill=float(rng.uniform(0.7, 0.92)),
                              shadow=sample_shadow(rng, ctx.s))
        if spec:
            specs.append(spec)
    return specs, str(rng.choice(["white", "black", "white"])), ["many-small"]


def tight_group(ctx: Context, angle: float, rows: int, cols: int, n: int, gap_range=(3, 12)):
    """Rows x cols block of prints with ``gap`` px between outer edges, rotated as one group."""
    rng = ctx.rng
    gap = float(rng.uniform(*gap_range)) * ctx.s
    avail_w, avail_h = ctx.w * 0.9, ctx.h * 0.9
    # shrink until the rotated group fits
    col_weights = [rng.uniform(0.75, 1.25, cols) for _ in range(1)][0]
    row_weights = rng.uniform(0.8, 1.2, rows)
    border_choice = rng.random()
    base_border = int(round(float(rng.uniform(8, 24)) * ctx.s))
    for shrink in np.linspace(1.0, 0.4, 25):
        gw, gh = avail_w * shrink, avail_h * shrink
        bw, bh = bbox_size(gw, gh, angle)
        if bw <= ctx.w * 0.96 and bh <= ctx.h * 0.96:
            break
    col_w = (gw - gap * (cols - 1)) * col_weights / col_weights.sum()
    row_h = (gh - gap * (rows - 1)) * row_weights / row_weights.sum()
    group_c = np.array([ctx.w / 2, ctx.h / 2]) + np.array(
        [float(rng.uniform(-1, 1)) * (ctx.w - bw) / 2 * 0.6, float(rng.uniform(-1, 1)) * (ctx.h - bh) / 2 * 0.6]
    )
    slots = [(r, c) for r in range(rows) for c in range(cols)]
    chosen = [slots[i] for i in sorted(rng.choice(len(slots), size=n, replace=False))]
    specs = []
    y = -gh / 2
    ys = []
    for r in range(rows):
        ys.append(y)
        y += row_h[r] + gap
    xs, x = [], -gw / 2
    for c in range(cols):
        xs.append(x)
        x += col_w[c] + gap
    for r, c in chosen:
        if border_choice < 0.35:
            border = (0, 0, 0, 0)
        else:
            border = tuple(max(1, int(round(base_border * float(rng.uniform(0.7, 1.3))))) for _ in range(4))
        ow, oh = col_w[c], row_h[r]
        iw, ih = int(ow - border[0] - border[2]), int(oh - border[1] - border[3])
        if iw < 24 or ih < 24:
            continue
        # outer rect centre in group frame, then rotate with the group
        local_outer = np.array([xs[c] + ow / 2, ys[r] + oh / 2])
        inner_local = local_outer + np.array([(border[0] - border[2]) / 2.0, (border[1] - border[3]) / 2.0])
        inner_c = group_c + rot(angle) @ inner_local
        specs.append(
            Spec(float(inner_c[0]), float(inner_c[1]), iw, ih, angle, border, ctx.next_source(), ctx.treatment(),
                 (250, 248, 243), "", sample_shadow(rng, ctx.s))
        )
    return specs, gap / ctx.s


def scene_tight(ctx: Context):
    rng = ctx.rng
    n = int(rng.integers(4, 7))
    rows, cols = {4: (2, 2), 5: (2, 3), 6: (2, 3)}[n]
    if n == 6 and ctx.w < ctx.h and rng.random() < 0.8:
        rows, cols = 3, 2
    specs, gap = tight_group(ctx, signed(rng, 0, 3.0), rows, cols, n)
    return specs, str(rng.choice(["white", "white", "black"])), ["tight-gutters", f"gap~{gap:.0f}px"]


def scene_edge(ctx: Context):
    rng = ctx.rng
    n = int(rng.integers(1, 4))
    cells, rows, cols = grid_cells(rng, n, ctx.w, ctx.h)
    specs, tags = [], ["edge-touching"]
    for cell in cells:
        snap = []
        if cell[0] <= 1:
            snap.append("left")
        if cell[2] >= ctx.w - 1:
            snap.append("right")
        if cell[1] <= 1:
            snap.append("top")
        if cell[3] >= ctx.h - 1:
            snap.append("bottom")
        snap = [str(rng.choice(snap))] if snap else []
        border_fn, tag = ctx.flat_border(allow_none=0.5, wide=(8, 24))
        spec = ctx.place_cell(
            cell, border_fn=border_fn, angle=signed(rng, 0, 3.0), fill=float(rng.uniform(0.7, 0.9)),
            snap=tuple(snap), snap_gap=float(rng.uniform(0, 4)), shadow=sample_shadow(rng, ctx.s),
        )
        if spec:
            specs.append(spec)
            tags.append(tag)
    return specs, str(rng.choice(["white", "black", "white"])), sorted(set(tags))


def scene_lowcontrast(ctx: Context, variant: str):
    rng = ctx.rng
    n = int(rng.integers(1, 5))
    cells, _, _ = grid_cells(rng, n, ctx.w, ctx.h, margin=(ctx.w * 0.03,) * 2 + (ctx.w * 0.03,) * 2)
    specs = []
    for cell in cells:
        angle = signed(rng, 0, 7)
        shadow = sample_shadow(rng, ctx.s)
        if variant == "snow":
            border_fn, _ = ctx.flat_border(allow_none=0.15, wide=(10, 26))
            spec = ctx.place_cell(cell, border_fn=border_fn, angle=angle, fill=0.85, shadow=shadow, paper=(252, 252, 249),
                                  treatment="normal", photo_mod="highkey")
        elif variant == "dark":
            if rng.random() < 0.4:
                border_fn, paper = (lambda k: (12, 12, 12, 12)), (28, 28, 28)
            else:
                border_fn, paper = (lambda k: (0, 0, 0, 0)), (28, 28, 28)
            spec = ctx.place_cell(cell, border_fn=border_fn, angle=angle, fill=0.85, shadow=shadow, paper=paper,
                                  photo_mod="dark")
        else:
            border_fn, _ = ctx.flat_border(allow_none=0.3, wide=(8, 20))
            spec = ctx.place_cell(cell, border_fn=border_fn, angle=angle, fill=0.85, shadow=shadow, paper=(205, 175, 135),
                                  photo_mod="beige")
        if spec:
            specs.append(spec)
    bg = {"snow": "white", "dark": "black", "beige": "kraft"}[variant]
    return specs, bg, ["low-contrast", variant]


def scene_polaroid(ctx: Context):
    rng = ctx.rng
    n = int(rng.integers(1, 5))
    cells, _, _ = grid_cells(rng, n, ctx.w, ctx.h, margin=(ctx.w * 0.03,) * 2 + (ctx.w * 0.03,) * 2)
    specs = []
    for cell in cells:
        side = float(rng.uniform(0.05, 0.065))
        bottom = float(rng.uniform(0.22, 0.32))
        border_fn = lambda k, side=side, bottom=bottom: (int(k * side), int(k * side), int(k * side), int(k * bottom))  # noqa: E731
        spec = ctx.place_cell(
            cell, border_fn=border_fn, angle=signed(rng, 0, 25), fill=float(rng.uniform(0.8, 0.95)),
            shadow=sample_shadow(rng, ctx.s), paper=(244, 241, 230), aspect=float(rng.uniform(0.93, 1.02)),
            treatment=str(rng.choice(["normal", "faded", "faded"])), kind="polaroid",
        )
        if spec:
            specs.append(spec)
    bg = str(rng.choice(["white", "black", "kraft", "wood", "carpet"]))
    return specs, bg, ["polaroid"]


def scene_mixed(ctx: Context, variant: int):
    rng = ctx.rng
    if variant == 0:  # rotated tight block on textured background
        n = int(rng.integers(4, 7))
        rows, cols = (2, 2) if n == 4 else (2, 3)
        specs, gap = tight_group(ctx, signed(rng, 5, 14), rows, cols, n)
        return specs, "textured", ["mixed-hard", "tight-gutters", "rotated", "textured-bg", f"gap~{gap:.0f}px"]
    if variant == 1:  # strongly rotated prints on textured background
        n = int(rng.integers(3, 6))
        cells, _, _ = grid_cells(rng, n, ctx.w, ctx.h, margin=(ctx.w * 0.03,) * 4)
        specs = []
        for cell in cells:
            border_fn, _ = ctx.flat_border(allow_none=0.4)
            spec = ctx.place_cell(cell, border_fn=border_fn, angle=signed(rng, 8, 30), fill=float(rng.uniform(0.9, 0.97)),
                                  shadow=sample_shadow(rng, ctx.s, soft=True))
            if spec:
                specs.append(spec)
        return specs, "textured", ["mixed-hard", "rotated", "textured-bg"]
    # variant 2: dark + tight on black felt with a bright print too
    n = 4
    specs, gap = tight_group(ctx, signed(rng, 1, 6), 2, 2, n)
    for index, spec in enumerate(specs):
        if index % 2 == 0:
            spec.photo_mod, spec.paper = "dark", (28, 28, 28)
    return specs, "black", ["mixed-hard", "tight-gutters", "dark-on-dark", f"gap~{gap:.0f}px"]


# ---- special pipelines ----
def phone_homography(rng, w: int, h: int) -> np.ndarray:
    src = np.float32([(0, 0), (w, 0), (w, h), (0, h)])
    jitter = rng.uniform(-0.025, 0.025, (4, 2)) * np.float32([w, h])
    return cv2.getPerspectiveTransform(src, src + jitter.astype(np.float32))


def render_phone(ctx: Context):
    rng = ctx.rng
    n = int(rng.integers(1, 5))
    margin = (ctx.w * 0.07, ctx.h * 0.07, ctx.w * 0.07, ctx.h * 0.07)
    cells, _, _ = grid_cells(rng, n, ctx.w, ctx.h, margin=margin)
    specs = []
    for cell in cells:
        border_fn, _ = ctx.flat_border(allow_none=0.35, wide=(8, 28))
        spec = ctx.place_cell(cell, border_fn=border_fn, angle=signed(rng, 0, 25), fill=float(rng.uniform(0.75, 0.95)),
                              shadow=sample_shadow(rng, ctx.s, soft=True), paper=(246, 244, 236))
        if spec:
            specs.append(spec)
    bg_kind = str(rng.choice(["wood", "carpet", "kraft"]))
    bg, bg_tag = make_background(rng, bg_kind, ctx.w, ctx.h, ctx.split)
    canvas = render(ctx, bg, specs)
    # global perspective + cast shadow + vignette + gradient + colour cast
    homography = phone_homography(rng, ctx.w, ctx.h)
    canvas = cv2.warpPerspective(canvas, homography, (ctx.w, ctx.h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
    rects = []
    for spec in specs:
        quad = np.float32([[(spec.cx, spec.cy)]])  # placeholder to keep shapes simple
        del quad
        half = np.array([(-spec.iw / 2, -spec.ih / 2), (spec.iw / 2, -spec.ih / 2), (spec.iw / 2, spec.ih / 2), (-spec.iw / 2, spec.ih / 2)])
        corners = (half @ rot(spec.angle).T + [spec.cx, spec.cy]).astype(np.float32)
        warped = cv2.perspectiveTransform(corners[None], homography)[0]
        (cx, cy), (rw, rh), angle = cv2.minAreaRect(warped)
        if rw < rh:
            rw, rh, angle = rh, rw, angle + 90
        angle = (angle + 90) % 180 - 90
        rects.append([round(float(cx), 2), round(float(cy), 2), round(float(rw), 2), round(float(rh), 2), round(float(angle), 3)])
    yy, xx = np.mgrid[:ctx.h, :ctx.w].astype(np.float32)
    radial = (((xx - ctx.w / 2) / (ctx.w / 2)) ** 2 + ((yy - ctx.h / 2) / (ctx.h / 2)) ** 2) / 2
    canvas *= (1 - float(rng.uniform(0.2, 0.42)) * radial)[..., None]
    ang = float(rng.uniform(0, 2 * np.pi))
    ramp = np.cos(ang) * (xx / ctx.w - 0.5) + np.sin(ang) * (yy / ctx.h - 0.5)
    canvas *= (1 + float(rng.uniform(0.12, 0.28)) * ramp)[..., None]
    shadow = np.zeros((ctx.h, ctx.w), np.float32)
    edge = int(rng.integers(4))
    depth = float(rng.uniform(0.12, 0.3))
    polygon = [
        [(0, 0), (ctx.w * depth * 2, 0), (0, ctx.h)],
        [(ctx.w, 0), (ctx.w * (1 - depth * 2), 0), (ctx.w, ctx.h)],
        [(0, ctx.h), (ctx.w, ctx.h), (ctx.w, ctx.h * (1 - depth * 2))],
        [(0, 0), (ctx.w, 0), (ctx.w, ctx.h * depth * 2)],
    ][edge]
    cv2.fillConvexPoly(shadow, np.int32(polygon), 1.0)
    shadow = cv2.GaussianBlur(shadow, (0, 0), 0.06 * ctx.w)
    canvas *= (1 - float(rng.uniform(0.2, 0.38)) * shadow)[..., None]
    canvas *= np.array([1.0, float(rng.uniform(0.95, 1.0)), float(rng.uniform(0.88, 0.98))], np.float32)
    return Result(finish_scan(rng, canvas, ctx.s, phone=True), rects, ["phone-capture", "perspective", bg_tag])


def render_album_magnetic(ctx: Context):
    rng = ctx.rng
    n = int(rng.integers(2, 7))
    cells, _, _ = grid_cells(rng, n, ctx.w, ctx.h, margin=(ctx.w * 0.07, ctx.h * 0.07, ctx.w * 0.07, ctx.h * 0.07))
    specs = []
    for cell in cells:
        border_fn, _ = ctx.flat_border(allow_none=0.5, wide=(6, 16))
        spec = ctx.place_cell(cell, border_fn=border_fn, angle=signed(rng, 0, 3), fill=float(rng.uniform(0.72, 0.9)),
                              shadow={"off": (2 * ctx.s, 3 * ctx.s), "sigma": 3 * ctx.s, "strength": 0.3})
        if spec:
            specs.append(spec)
    h, w = ctx.h, ctx.w
    tone = np.array([float(rng.uniform(205, 236)), float(rng.uniform(196, 224)), float(rng.uniform(160, 196))], np.float32)
    fibre = cv2.GaussianBlur(rng.normal(size=(h, w)).astype(np.float32), (0, 0), sigmaX=2.5, sigmaY=0.6) * 6
    page = tone * (1 + 0.025 * lowfreq(rng, h, w, 4))[..., None] + fibre[..., None]
    # binding shadow
    xs = np.arange(w, dtype=np.float32)[None, :]
    edge_x = float(rng.choice([0.04, 0.96])) * w
    page *= (1 - 0.18 * np.exp(-((xs - edge_x) / (0.03 * w)) ** 2))[..., None]
    canvas = render(ctx, page, specs)
    # plastic sleeve: slight milky veil, diagonal glare bands, hard border lines
    canvas = canvas * 0.95 + 255 * 0.05 * np.array([0.95, 1.0, 1.0], np.float32)
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    phi = float(rng.uniform(0.3, 1.2))
    coordinate = (xx * math.cos(phi) + yy * math.sin(phi)) / (w * math.cos(phi) + h * math.sin(phi))
    glare = np.zeros((h, w), np.float32)
    for _ in range(int(rng.integers(1, 4))):
        centre, width_ = float(rng.uniform(0.15, 0.85)), float(rng.uniform(0.04, 0.14))
        glare += float(rng.uniform(0.18, 0.4)) * np.exp(-((coordinate - centre) / width_) ** 2)
    canvas += (255 - canvas) * np.clip(glare, 0, 0.55)[..., None]
    m = int(0.025 * w)
    cv2.rectangle(canvas, (m, m), (w - m, h - m), (150.0, 150.0, 145.0), max(1, int(2 * ctx.s)), cv2.LINE_AA)
    cv2.rectangle(canvas, (m + 3, m + 3), (w - m - 3, h - m - 3), (252.0, 252.0, 250.0), max(1, int(1.5 * ctx.s)), cv2.LINE_AA)
    return Result(finish_scan(rng, canvas, ctx.s), [s.rect for s in specs], ["album", "magnetic-album", "plastic-glare"])


def render_album_spread(ctx: Context):
    """Existing realistic compositing: blank album spread with tape/corners/scalloped mounts."""
    rng = ctx.rng
    n = int(rng.integers(3, 7))
    cells, _, _ = grid_cells(rng, n, 1400, 1000, margin=(120, 90, 120, 90), prefer=(2, math.ceil(n / 2)))
    prints = []
    sources = [Image.fromarray(np.clip(p, 0, 255).astype(np.uint8)) for p in ctx.photos]
    for cell in cells:
        border = tuple(int(rng.integers(16, 42)) for _ in range(4))
        angle = signed(rng, 0, 5)
        placed = fit_print(rng, cell, ctx.aspect_for(cell), lambda k, b=border: b, angle, 0.88)
        if not placed:
            continue
        cx, cy, iw, ih, _ = placed
        prints.append(authentic.Print((cx, cy, iw, ih, angle), ctx.next_source(), border,
                                      str(rng.choice(["normal", "monochrome", "sepia", "faded", "pale"])),
                                      str(rng.choice(["plain", "tape", "corners", "scalloped", "plain"]))))
    case = authentic.Case("robust-spread", tuple(prints), page_treatment=str(rng.choice(["cream", "foxed", "faded", "dark"])),
                          glare=bool(rng.random() < 0.5))
    image = authentic.build_case(case, sources, int(rng.integers(0, 10_000)))
    arr = np.asarray(image, dtype=np.float32).copy()
    return Result(finish_scan(rng, arr, 1.0), [list(p.rect) for p in prints],
                  ["album", "blank-spread", "mounts", case.page_treatment])


# --------------------------------------------------------------------------
# case driver
# --------------------------------------------------------------------------
def canvas_size(rng, scenario: str, index: int) -> tuple[int, int, str]:
    if scenario in {"album"} and index < 2:
        return 1400, 1000, "1400"
    if index == 0 and scenario in LETTER_FIRST:
        return 2550, 3300, "letter"
    if index == 1 and scenario in LARGE_SECOND:
        return (2400, 1700, "2400") if rng.random() < 0.6 else (1700, 2400, "2400")
    return (1000, 1400, "1400") if rng.random() < 0.25 else (1400, 1000, "1400")


def build_case(split: str, scen_index: int, scenario: str, index: int, photos: list[np.ndarray]):
    rng = np.random.default_rng([SPLIT_SEEDS[split], scen_index, index])
    w, h, size_tag = canvas_size(rng, scenario, index)
    if scenario == "album":
        # album cases always use the 1400x1000 page layouts
        w, h, size_tag = 1400, 1000, "1400"
    ctx = Context(rng, split, photos, w, h)
    quality = int(rng.integers(72, 93))
    if size_tag != "1400":
        quality = min(quality, 80)
    if scenario == "phone-capture":
        result = render_phone(ctx)
    elif scenario == "album":
        result = render_album_magnetic(ctx) if index % 2 else render_album_spread(ctx)
        if index % 2 == 0:
            ctx.w, ctx.h = 1400, 1000
    else:
        if scenario == "flatbed-white":
            specs, bg, tags = scene_flatbed(ctx, False)
        elif scenario == "flatbed-black":
            specs, bg, tags = scene_flatbed(ctx, True)
        elif scenario == "rotated":
            specs, bg, tags = scene_rotated(ctx)
        elif scenario == "single-large":
            specs, bg, tags = scene_single_large(ctx)
        elif scenario == "many-small":
            specs, bg, tags = scene_many_small(ctx)
        elif scenario == "tight-gutters":
            specs, bg, tags = scene_tight(ctx)
        elif scenario == "edge-touching":
            specs, bg, tags = scene_edge(ctx)
        elif scenario == "low-contrast":
            specs, bg, tags = scene_lowcontrast(ctx, ["snow", "dark", "beige", "snow"][index % 4])
        elif scenario == "polaroid":
            specs, bg, tags = scene_polaroid(ctx)
        elif scenario == "mixed-hard":
            specs, bg, tags = scene_mixed(ctx, index % 3)
        else:
            raise ValueError(scenario)
        if not specs:
            raise RuntimeError(f"{split}/{scenario}/{index}: no prints placed")
        if specs_overlap(specs, gap=0.0):
            raise RuntimeError(f"{split}/{scenario}/{index}: prints overlap")
        background, bg_tag = make_background(rng, bg, w, h, split)
        canvas = render(ctx, background, specs)
        result = Result(finish_scan(rng, canvas, ctx.s), [s.rect for s in specs], tags + [bg_tag])
    result.tags.append(f"{ctx.w}x{ctx.h}")
    return result, quality, (ctx.w, ctx.h)


def load_photos(split: str) -> tuple[list[np.ndarray], list[int]]:
    paths = sorted(PHOTOS.glob("photo-*.jpg"))
    numbers = [int(p.stem.split("-")[1]) for p in paths]
    perm = np.random.default_rng(7).permutation(len(paths))
    half = len(paths) // 2
    chosen = perm[:half] if split == "dev" else perm[half:]
    if len(paths) < 4:
        chosen = np.arange(len(paths))
    photos = [np.asarray(Image.open(paths[i]).convert("RGB"), dtype=np.float32) for i in sorted(chosen)]
    return photos, [numbers[i] for i in sorted(chosen)]


def generate(splits: list[str]) -> None:
    OUT.mkdir(exist_ok=True)
    manifest_path = OUT / "manifest.json"
    cases = []
    photo_groups = {}
    for split in ("dev", "holdout"):
        photos, numbers = load_photos(split)
        photo_groups[split] = numbers
        suite = f"robust-{split}"
        fixtures = OUT / "fixtures" / split
        if split not in splits:
            if manifest_path.exists():
                cases += [c for c in json.loads(manifest_path.read_text())["cases"] if c["suite"] == suite]
            continue
        fixtures.mkdir(parents=True, exist_ok=True)
        for old in fixtures.glob("*.jpg"):
            old.unlink()
        for scen_index, (scenario, count) in enumerate(SCENARIOS):
            for index in range(count):
                result, quality, size = build_case(split, scen_index, scenario, index, photos)
                case_id = f"{suite}-{scenario}-{index + 1:02d}"
                relative = f"fixtures/{split}/{case_id}.jpg"
                Image.fromarray(result.image).save(OUT / relative, quality=quality, subsampling=0 if quality > 85 else 2)
                cases.append(
                    {
                        "id": case_id,
                        "suite": suite,
                        "image": relative,
                        "target": "photographic_content",
                        "scenario": scenario,
                        "tags": result.tags,
                        "image_size": list(size),
                        "rectangles": result.rects,
                    }
                )
                print(case_id, len(result.rects), size, quality)
    manifest = {
        "version": 1,
        "rectangle_format": ["center_x", "center_y", "width", "height", "angle_degrees"],
        "target_definition": {
            "robust-dev": "inner photographic image area; exclude borders, Polaroid frames, tape, corners, shadows",
            "robust-holdout": "inner photographic image area; exclude borders, Polaroid frames, tape, corners, shadows",
        },
        "seeds": SPLIT_SEEDS,
        "source_photos": photo_groups,
        "cases": cases,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def draw_overlays(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((OUT / "manifest.json").read_text())
    for case in manifest["cases"]:
        image = cv2.imread(str(OUT / case["image"]))
        for cx, cy, w, h, angle in case["rectangles"]:
            box = cv2.boxPoints(((cx, cy), (w, h), angle)).astype(np.int32)
            cv2.polylines(image, [box], True, (0, 0, 255), max(1, image.shape[1] // 700), cv2.LINE_AA)
        scale = 1600 / max(image.shape[:2])
        if scale < 1:
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(directory / f"{case['id']}.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"wrote {len(manifest['cases'])} overlays to {directory}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "holdout", "both"), default="both")
    parser.add_argument("--overlay", type=Path, help="draw ground-truth boxes for the existing fixtures into DIR and exit")
    args = parser.parse_args()
    if args.overlay:
        draw_overlays(args.overlay)
        return
    generate(["dev", "holdout"] if args.split == "both" else [args.split])


if __name__ == "__main__":
    main()
