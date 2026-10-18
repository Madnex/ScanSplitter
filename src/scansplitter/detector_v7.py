"""v7 detector: v5 anchors plus inner-image tightening and cue arbitration."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from . import detector as _d
from .detector import DetectedRegion, RotatedRect

_WORK_MAX = 2000  # working resolution (long side) for border analysis


# --------------------------------------------------------------------------
# Inner-image tightening
# --------------------------------------------------------------------------
def _deskew_patch(gray: np.ndarray, rect: RotatedRect) -> np.ndarray:
    """Rect content, axis aligned (rows follow the rect height)."""
    (cx, cy), (w, h), ang = rect
    w_i, h_i = max(3, int(round(w))), max(3, int(round(h)))
    t = np.deg2rad(ang)
    ux = np.array([np.cos(t), np.sin(t)])
    uy = np.array([-np.sin(t), np.cos(t)])
    m = np.array(
        [
            [ux[0], uy[0], cx - ux[0] * w_i / 2 - uy[0] * h_i / 2],
            [ux[1], uy[1], cy - ux[1] * w_i / 2 - uy[1] * h_i / 2],
        ],
        dtype=np.float32,
    )
    return cv2.warpAffine(
        gray, m, (w_i, h_i),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _side_step(
    strip: np.ndarray,
    max_depth: int,
    min_band: int,
    min_step: float = 7.0,
) -> float | None:
    """Depth of the inner edge of a uniform light band at row 0 of ``strip``.

    Each sampled column votes for the depth where a plateau of near-maximal
    brightness ends in a step towards darker content. The side moves only if
    the plateau is uniform, wide enough, ends within ``max_depth`` and the
    votes lie on one straight line (a physical, possibly slightly skewed edge).
    """
    depth_rows, length = strip.shape
    if depth_rows < max_depth + 3 or length < 20:
        return None
    lo, hi = int(length * 0.10), int(length * 0.90)
    k = max(3, int(length * 0.03)) | 1
    sm = cv2.blur(strip[: max_depth + min_band + 3, lo:hi], (k, 1))
    sm = cv2.blur(sm, (1, 3))
    n = min(60, sm.shape[1])
    xs = np.linspace(0, sm.shape[1] - 1, n).astype(int)
    votes: list[tuple[float, float]] = []
    for x in xs:
        p = sm[:, x]
        head = p[: max_depth + 1]
        dm = int(np.argmax(head))
        peak = float(head[dm])
        thr = peak - min_step
        inward = np.nonzero(p[dm:] < thr)[0]
        if inward.size == 0:
            continue
        step = dm + int(inward[0])
        # plateau start: walk outwards from the peak
        out = np.nonzero(p[: dm + 1] < thr)[0]
        start = int(out[-1]) + 1 if out.size else 0
        if step - start < min_band or step > max_depth:
            continue
        band = p[start:step]
        if band.max() - band.min() > 1.6 * min_step:
            continue
        after = p[step : step + min_band]
        if after.size < min_band or float(after.mean()) > peak - min_step:
            continue
        votes.append((float(x), float(step)))
    if len(votes) < 0.55 * n:
        return None
    arr = np.array(votes)
    # Theil-Sen style robust line
    xs_v, ys_v = arr[:, 0], arr[:, 1]
    slopes = []
    for i in range(0, len(xs_v), 2):
        for j in range(i + 1, len(xs_v), 3):
            if xs_v[j] != xs_v[i]:
                slopes.append((ys_v[j] - ys_v[i]) / (xs_v[j] - xs_v[i]))
    slope = float(np.median(slopes)) if slopes else 0.0
    icpt = float(np.median(ys_v - slope * xs_v))
    res = np.abs(ys_v - (icpt + slope * xs_v))
    tol = max(1.5, 0.004 * length)
    if np.mean(res <= tol) < 0.75 or len(votes) * np.mean(res <= tol) < 0.55 * n:
        return None
    return icpt + slope * (sm.shape[1] / 2.0)


def _tighten_rect(
    gray: np.ndarray, rect: RotatedRect, scale: float, passes: int = 2
) -> RotatedRect:
    """Move each side inward onto the emulsion edge when a clear border exists."""
    (cx, cy), (w, h), ang = rect
    small = ((cx * scale, cy * scale), (w * scale, h * scale), ang)
    (scx, scy), (sw, sh), _ = small
    if sw < 40 or sh < 40:
        return rect
    off = {"l": 0.0, "r": 0.0, "t": 0.0, "b": 0.0}
    for _ in range(passes):
        cur = (
            (scx, scy),
            (sw - off["l"] - off["r"], sh - off["t"] - off["b"]),
            ang,
        )
        # recompute with shifted center
        t = np.deg2rad(ang)
        ux = np.array([np.cos(t), np.sin(t)])
        uy = np.array([-np.sin(t), np.cos(t)])
        c0 = np.array([scx, scy]) + ux * (off["l"] - off["r"]) / 2 + uy * (off["t"] - off["b"]) / 2
        cur = ((float(c0[0]), float(c0[1])), cur[1], ang)
        patch = _deskew_patch(gray, cur)
        ph, pw = patch.shape
        moved = False
        sides = {
            "t": (patch, ph),
            "b": (patch[::-1], ph),
            "l": (patch.T, pw),
            "r": (patch[:, ::-1].T, pw),
        }
        for key, (strip, dim) in sides.items():
            max_depth = max(4, int(round(0.10 * dim)))
            min_band = max(2, int(round(0.012 * dim)))
            step = _side_step(strip, max_depth, min_band)
            if step is not None and step >= 1.5:
                off[key] += step
                moved = True
        if not moved:
            break
    nw = sw - off["l"] - off["r"]
    nh = sh - off["t"] - off["b"]
    if nw < 0.5 * sw or nh < 0.5 * sh:
        return rect
    t = np.deg2rad(ang)
    ux = np.array([np.cos(t), np.sin(t)])
    uy = np.array([-np.sin(t), np.cos(t)])
    c1 = np.array([scx, scy]) + ux * (off["l"] - off["r"]) / 2 + uy * (off["t"] - off["b"]) / 2
    return ((float(c1[0] / scale), float(c1[1] / scale)), (nw / scale, nh / scale), ang)


# --------------------------------------------------------------------------
# v3 proposals with a bounded foreground threshold
# --------------------------------------------------------------------------
def _v3_rects(
    rgb: np.ndarray,
    min_area_ratio: float,
    max_area_ratio: float,
    color_cap: float | None,
    detection_max_dimension: int = 1800,
) -> list[RotatedRect]:
    """v3 proposals in full-resolution coordinates.

    Identical to ``detect_photos_v3`` except that the Otsu colour threshold is
    optionally capped: when large pale areas (lid, bright page edge) dominate,
    Otsu rises far above the contrast of light photographs.
    """
    oh, ow = rgb.shape[:2]
    scale = min(1.0, detection_max_dimension / max(oh, ow))
    width, height = max(1, round(ow * scale)), max(1, round(oh * scale))
    small = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)
    total_area = height * width
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB).astype(np.float32)
    backgrounds = _d._v3_background_colors(lab)
    delta = np.full((height, width), np.inf, dtype=np.float32)
    for background in backgrounds:
        diff = lab - background
        np.minimum(delta, np.sqrt(np.sum(diff * diff, axis=2)), out=delta)
    otsu, _ = cv2.threshold(
        np.clip(delta, 0, 255).astype(np.uint8), 0, 255,
        cv2.THRESH_BINARY | cv2.THRESH_OTSU,
    )
    thr = float(otsu)
    if color_cap is not None:
        thr = min(thr, color_cap)
    foreground = delta > max(18.0 if color_cap is None else 12.0, thr)
    dw = max(11, round(min(height, width) * 0.010)) | 1
    density = cv2.boxFilter(foreground.astype(np.float32), cv2.CV_32F, (dw, dw))
    mask = (density > 0.16).astype(np.uint8) * 255
    open_size = max(5, round(min(height, width) * 0.010)) | 1
    close_size = max(5, round(min(height, width) * 0.008)) | 1
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_size, open_size)),
    )
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (close_size, close_size)),
        iterations=2,
    )
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_a, max_a = min_area_ratio * total_area, max_area_ratio * total_area
    cands: list[RotatedRect] = []
    for contour in contours:
        rect = cv2.minAreaRect(contour)
        area = rect[1][0] * rect[1][1]
        if not min_a <= area <= max_a:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        fill = cv2.contourArea(contour) / max(1, bw * bh)
        aspect = max(rect[1]) / max(1, min(rect[1]))
        if fill < 0.32 or aspect > 5.0:
            continue
        cands.append(rect)
    cands = _d._v3_merge_fragments(cands, max_a)
    dedup: list[RotatedRect] = []
    for rect in sorted(cands, key=lambda r: r[1][0] * r[1][1], reverse=True):
        if any(_d._v3_iou(rect, o) > 0.55 for o in dedup):
            continue
        dedup.append(rect)
    split: list[RotatedRect] = []
    for rect in dedup:
        split.extend(_d._v3_split_on_gutter(rect, foreground, min_a))
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    out: list[RotatedRect] = []
    for rect in split:
        r = _d._refine_rect_to_edges(
            gray, _d._v3_snap_angle_to_long_edges(gray, rect), search_margin_ratio=0.12
        )
        (cx, cy), (rw, rh), ang = r
        full = ((cx / scale, cy / scale), (rw / scale, rh / scale), ang)
        if min_area_ratio <= full[1][0] * full[1][1] / (ow * oh) <= max_area_ratio:
            out.append(full)
    return out


# --------------------------------------------------------------------------
# Candidate scoring
# --------------------------------------------------------------------------
def _side_contrast(gray: np.ndarray, rect: RotatedRect, scale: float) -> list[float]:
    """Robust inside/outside brightness step along each side of ``rect``."""
    (cx, cy), (w, h), ang = rect
    cx, cy, w, h = cx * scale, cy * scale, w * scale, h * scale
    t = np.deg2rad(ang)
    ux = np.array([np.cos(t), np.sin(t)])
    uy = np.array([-np.sin(t), np.cos(t)])
    c = np.array([cx, cy])
    gh, gw = gray.shape
    out: list[float] = []
    band = 3
    for n, tang, half_n, half_t in (
        (ux, uy, w / 2, h / 2),
        (-ux, uy, w / 2, h / 2),
        (uy, ux, h / 2, w / 2),
        (-uy, ux, h / 2, w / 2),
    ):
        fs = np.linspace(-0.8, 0.8, 41)
        base = c[None] + n[None] * half_n + tang[None] * (fs[:, None] * half_t)
        best = np.zeros(len(fs), np.float32)
        for shift in (-3, -1.5, 0, 1.5, 3):
            ins = np.zeros(len(fs), np.float32)
            outs = np.zeros(len(fs), np.float32)
            for k in range(1, band + 1):
                pi = base - n[None] * (shift + k + 0.0)
                po = base - n[None] * (shift - k)
                ins += cv2.remap(gray, pi[:, 0:1].astype(np.float32).T, pi[:, 1:2].astype(np.float32).T,
                                 cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)[0]
                outs += cv2.remap(gray, po[:, 0:1].astype(np.float32).T, po[:, 1:2].astype(np.float32).T,
                                  cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)[0]
            best = np.maximum(best, np.abs(ins - outs) / band)
        out.append(float(np.percentile(best, 30)))
    return out


def _score_rect(gray: np.ndarray, rect: RotatedRect, scale: float) -> float:
    return float(np.mean(np.minimum(_side_contrast(gray, rect, scale), 30.0)))


# --------------------------------------------------------------------------
# Chroma proposals: neutral emulsion on cream paper
# --------------------------------------------------------------------------
def _chroma_rects(
    rgb: np.ndarray, min_area_ratio: float, max_area_ratio: float, max_dim: int = 1500
) -> list[RotatedRect]:
    """Inner-photo proposals from the b* (yellow-blue) channel.

    Aged album paper and print borders are strongly yellow while the silver
    emulsion of black-and-white prints is nearly neutral, so b* separates the
    inner photograph even where its luminance matches the border.
    """
    oh, ow = rgb.shape[:2]
    s = min(1.0, max_dim / max(oh, ow))
    small = cv2.resize(rgb, (round(ow * s), round(oh * s)), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB)
    lum, b = lab[..., 0], cv2.GaussianBlur(lab[..., 2], (0, 0), 2.0)
    bright = lum > 90
    # Only meaningful on yellowed paper; on neutral or coloured pages the
    # b* contrast says nothing about prints.
    if bright.mean() < 0.2 or float(np.percentile(b[bright], 75)) < 138:
        return []
    kk = int(0.15 * max(b.shape)) | 1
    page = cv2.GaussianBlur(
        cv2.dilate(b, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kk, kk))),
        (0, 0), kk / 6,
    )
    mask = (((page.astype(np.float32) - b) > 9.0) & (lum > 90)).astype(np.uint8) * 255
    k = max(5, round(min(mask.shape) * 0.01)) | 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    total = mask.shape[0] * mask.shape[1]
    out: list[RotatedRect] = []
    for cnt in contours:
        rect = cv2.minAreaRect(cnt)
        a = rect[1][0] * rect[1][1]
        if not min_area_ratio * total <= a <= max_area_ratio * total:
            continue
        if cv2.contourArea(cnt) / max(a, 1) < 0.75 or max(rect[1]) / max(1, min(rect[1])) > 4:
            continue
        (cx, cy), (w, h), ang = rect
        out.append(((cx / s, cy / s), (w / s, h / s), ang))
    return out


# --------------------------------------------------------------------------
# Ghost (print seen through a translucent sleeve) rejection
# --------------------------------------------------------------------------
def _ghost_stats(gray1500: np.ndarray, rect: RotatedRect, scale: float) -> tuple[float, float]:
    """(low-frequency contrast, fine-detail energy) inside the central 80%."""
    low = cv2.GaussianBlur(gray1500, (0, 0), 4)
    dog = np.abs(cv2.GaussianBlur(gray1500, (0, 0), 1) - cv2.GaussianBlur(gray1500, (0, 0), 3))
    (cx, cy), (w, h), ang = rect
    mask = np.zeros(gray1500.shape, np.uint8)
    pts = cv2.boxPoints(((cx * scale, cy * scale), (w * scale * 0.8, h * scale * 0.8), ang))
    cv2.fillPoly(mask, [pts.astype(np.int32)], 1)
    sel = mask > 0
    if sel.sum() < 50:
        return 99.0, 99.0
    return float(low[sel].std()), float(dog[sel].mean())


def _edge_sharpness(gray: np.ndarray, rect: RotatedRect, scale: float, half: int = 12) -> float:
    """Weakest side's boundary sharpness: peak gradient / total step.

    A physical print edge completes its brightness step within a couple of
    pixels; a print seen through a translucent sleeve has a blurred boundary.
    The value is a median over samples along each side, minimum over sides.
    """
    (cx, cy), (w, h), ang = rect
    cx, cy, w, h = cx * scale, cy * scale, w * scale, h * scale
    t = np.deg2rad(ang)
    ux = np.array([np.cos(t), np.sin(t)])
    uy = np.array([-np.sin(t), np.cos(t)])
    c = np.array([cx, cy])
    ts = np.arange(-half, half + 1, dtype=np.float32)
    sides: list[float] = []
    for n, tang, half_n, half_t in (
        (ux, uy, w / 2, h / 2), (-ux, uy, w / 2, h / 2),
        (uy, ux, h / 2, w / 2), (-uy, ux, h / 2, w / 2),
    ):
        fs = np.linspace(-0.8, 0.8, 41)
        base = c[None] + n[None] * half_n + tang[None] * (fs[:, None] * half_t)
        pts = base[:, None, :] + ts[None, :, None] * n[None, None, :]
        prof = cv2.remap(
            gray, pts[..., 0].astype(np.float32), pts[..., 1].astype(np.float32),
            cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE,
        )
        step = np.abs(prof[:, -7:].mean(1) - prof[:, :7].mean(1))
        grad = np.abs(prof[:, 2:] - prof[:, :-2]).max(1) / 2
        ok = step >= 6
        sides.append(float(np.median(grad[ok] / step[ok])) if ok.any() else 0.0)
    return min(sides)


def _low_detail(stats: tuple[float, float]) -> bool:
    """Blurred, low-contrast interior (crinkled glassine over a print)."""
    low_std, fine = stats
    return (low_std < 22 and fine < 4.6) or (fine < 2.6 and low_std < 30)


def _overlap(a: RotatedRect, b: RotatedRect) -> float:
    return max(_d._v3_overlap_fraction(a, b), _d._v3_overlap_fraction(b, a))


def _select(
    anchors: list[dict],
    alternatives: list[dict],
    margin: float = 3.0,
    standalone: float = 22.0,
    contained: float = 0.6,
) -> list[dict]:
    """Anchors (v5) survive unless an overlapping alternative scores clearly
    higher; alternatives with no anchor must be strong on their own. Boxes
    mostly contained in a better-scored accepted box are dropped."""
    chosen: list[dict] = []
    for item in anchors:
        best = item
        for alt in alternatives:
            if _overlap(item["rect"], alt["rect"]) > 0.5 and alt["score"] > best["score"] + margin:
                best = alt
        chosen.append(best)
    for alt in sorted(alternatives, key=lambda a: -a["score"]):
        if alt["score"] >= standalone and not any(
            _overlap(alt["rect"], c["rect"]) > 0.5 for c in chosen
        ):
            chosen.append(alt)
    result: list[dict] = []
    for item in sorted(chosen, key=lambda a: -a["score"]):
        if any(_d._v3_overlap_fraction(item["rect"], o["rect"]) > contained for o in result):
            continue
        result.append(item)
    return result


def _drop_ghosts(items: list[dict], q: float = 75.0, k: float = 0.8) -> list[dict]:
    """Remove blurry prints seen through sleeves, judged against the scan itself.

    A candidate is a ghost when its interior is low-detail *and* its boundary
    is softer than the sharp prints on the same scan, so uniformly soft or
    faded scans keep everything.
    """
    if len(items) < 2:
        return items
    detailed = [a for a in items if not _low_detail(a["ghost"])] or items
    ref = float(np.percentile([a["sharp"] for a in detailed], q))
    keep = [
        a for a in items if not (_low_detail(a["ghost"]) and a["sharp"] < k * ref)
    ]
    return keep or items


def detect_photos_v7(
    image: Image.Image,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    padding: int = 0,
    inset: int = 0,
) -> list[DetectedRegion]:
    """v5 cues plus inner-image tightening and evidence-based arbitration.

    v5 proposals anchor the result (where v3, SAM and texture agree the print
    stays). Every proposal, including v3, capped-threshold v3 and chroma
    ones, is moved onto the emulsion edge when a uniform light border is
    present and scored by the brightness step along its four sides. A better
    fitting alternative replaces an anchor, strong stand-alone alternatives
    are added, and mostly-contained duplicates are removed. Finally blurry
    low-contrast prints with soft boundaries (seen through album sleeves) are
    dropped relative to the sharp prints of the same scan.
    """
    rgb = np.asarray(image.convert("RGB"))
    width, height = image.size
    scale = min(1.0, _WORK_MAX / max(width, height))
    gray = np.asarray(image.convert("L").resize(
        (max(1, round(width * scale)), max(1, round(height * scale))), Image.BILINEAR
    )).astype(np.float32)
    gray_s = cv2.GaussianBlur(gray, (0, 0), 1.0)
    gray_e = cv2.GaussianBlur(gray, (0, 0), 0.7)
    g_scale = min(1.0, 1500 / max(width, height))
    g1500 = np.asarray(image.convert("L").resize(
        (max(1, round(width * g_scale)), max(1, round(height * g_scale))), Image.BILINEAR
    )).astype(np.float32)

    v3 = _v3_rects(rgb, min_area_ratio, max_area_ratio, None)
    v3c = _v3_rects(rgb, min_area_ratio, max_area_ratio, 30.0)
    chroma = _chroma_rects(rgb, min_area_ratio, max_area_ratio)
    v5 = _v5_rectangles(image, rgb, v3, min_area_ratio, max_area_ratio)

    def prep(rects: list[RotatedRect]) -> list[dict]:
        out = []
        for rect in rects:
            tight = _tighten_rect(gray, rect, scale)
            out.append({
                "rect": tight,
                "score": _score_rect(gray_s, tight, scale),
                "sharp": _edge_sharpness(gray_e, tight, scale),
                "ghost": _ghost_stats(g1500, tight, g_scale),
            })
        return out

    chosen = _select(prep(v5), prep(v3) + prep(v3c) + prep(chroma))
    area = width * height
    chosen = [
        a for a in chosen
        if min_area_ratio <= a["rect"][1][0] * a["rect"][1][1] / area <= max_area_ratio
    ]
    chosen = _drop_ghosts(chosen)
    return _d._v5_regions_from_rectangles(
        [a["rect"] for a in chosen], image_size=image.size,
        min_area_ratio=min_area_ratio, max_area_ratio=max_area_ratio,
        net_adjust=padding - inset,
    )


def _v5_rectangles(
    image: Image.Image,
    rgb: np.ndarray,
    proposals: list[RotatedRect],
    min_area_ratio: float,
    max_area_ratio: float,
) -> list[RotatedRect]:
    """The rectangle set v5 would convert to regions (before padding).

    Reuses the already computed v3 proposals instead of rerunning v3 inside
    the SAM stage.
    """
    refined = _d._v4_refine_rectangles(rgb, proposals, prompt_margin_ratio=0.08)
    image_area = image.size[0] * image.size[1]
    base_rects: list[RotatedRect] = []
    for proposal, rect in zip(proposals, refined, strict=True):
        if not min_area_ratio <= rect[1][0] * rect[1][1] / image_area <= max_area_ratio:
            rect = proposal
        # v5 shrinks the SAM base by its fixed 20 px inset
        base_rects.append(
            (rect[0], (max(1.0, rect[1][0] - 40), max(1.0, rect[1][1] - 40)), rect[2])
        )
    tex = _d._v5_texture_rectangles(rgb, min_area_ratio=min_area_ratio, max_area_ratio=max_area_ratio)
    rects = _d._v5_combine_rectangles(base_rects, tex)
    rects = _d._v5_expand_stacked_sleeve_rectangles(rects, tex, image.size)
    for frame in _d._v5_frame_rectangles(rgb, min_area_ratio=min_area_ratio, max_area_ratio=max_area_ratio):
        if frame[1][0] * frame[1][1] > image.size[0] * image.size[1] * 0.18:
            continue
        if not any(_d._v3_overlap_fraction(frame, e) > 0.65 for e in rects):
            rects.append(frame)
    rects.extend(
        _d._v5_recover_boundary_rectangles(
            rgb, tex, rects, min_area_ratio=min_area_ratio, max_area_ratio=max_area_ratio
        )
    )
    return rects
