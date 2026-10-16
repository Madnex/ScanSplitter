"""Photo detector v6b: surface model, rectangle hypotheses, edge evidence.

All work happens on a copy scaled to ``WORK`` pixels, so every parameter is
relative to the image and results do not depend on scan resolution.

1. Surface model.  The colour and fine-texture statistics of the image border
   are clustered into a few background components; slow drifts of the surface
   (vignetting, soft shadow, a lit patch) are subtracted.  Pixels improbable
   under every component are foreground, refined by a seeded watershed that
   respects image edges.
2. Hypotheses.  Blobs that are huge or not rectangular are re-modelled from
   the surface just inside their outline (album pages, glare); fragments of
   one print are merged when their union is a clean rectangle; touching prints
   are separated at outline notches.
3. Straight-edge evidence.  Gaps between prints are found as pairs of opposite,
   full-length straight edges around a uniform strip.  Rectangle sides are
   snapped to nearby straight edges and grown onto much stronger ones when a
   print is under-segmented.
4. Picture extraction.  Uniform border bands that surround the picture
   (white margins, Polaroid frames) are trimmed to leave the photographic area.

``detect_photos_v6`` returns :class:`DetectedRegion` objects like the other
detectors.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from scansplitter.detector import DetectedRegion, _v3_kmeans_lock

WORK = 800  # working resolution (longest side, pixels)


def _features(small: np.ndarray) -> np.ndarray:
    """Per-pixel Lab colour (lightly blurred) plus a local texture energy channel."""
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    colour = cv2.GaussianBlur(lab, (0, 0), 1.5)
    gray = lab[:, :, 0]
    high = np.abs(gray - cv2.GaussianBlur(gray, (0, 0), 1.5))
    texture = np.log1p(cv2.GaussianBlur(high, (0, 0), 2.5)) * 10
    return np.dstack([colour, texture])


def _bg_models(feat: np.ndarray, sample: np.ndarray, k: int = 4):
    """Gaussian background components fitted to the sampled pixels.

    Components far lighter in weight than the dominant one are discarded so a
    print touching the image edge does not become part of the surface.
    """
    x = feat[sample]
    if len(x) < 50:
        return []
    k = min(k, max(1, len(x) // 50))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    with _v3_kmeans_lock:
        cv2.setRNGSeed(1)
        _, lab, _ = cv2.kmeans(x, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    lab = lab.ravel()
    wts = np.bincount(lab, minlength=k) / len(lab)
    models = []
    for i in range(k):
        if wts[i] < 0.3 * wts.max() or (lab == i).sum() < 20:
            continue
        xi = x[lab == i]
        mu = xi.mean(0)
        cov = np.cov(xi.T) + np.diag([9, 4, 4, 4.0])
        models.append((mu, np.linalg.inv(cov)))
    return models


def _zmap(feat: np.ndarray, models, with_mean: bool = False):
    """Mahalanobis distance to the nearest background component.

    With ``with_mean`` the mean of that nearest component is returned per pixel.
    """
    h, w, c = feat.shape
    flat = feat.reshape(-1, c)
    best = np.full(h * w, np.inf, dtype=np.float32)
    choice = np.zeros(h * w, dtype=np.int32)
    for i, (mu, prec) in enumerate(models):
        whiten = np.linalg.cholesky(prec).astype(np.float32)  # prec = L L^T
        proj = (flat - mu.astype(np.float32)) @ whiten
        dist = np.einsum("ij,ij->i", proj, proj)
        closer = dist < best
        best[closer] = dist[closer]
        choice[closer] = i
    z = np.sqrt(best).reshape(h, w)
    if not with_mean:
        return z
    means = np.stack([mu for mu, _ in models]).astype(np.float32)
    return z, means[choice].reshape(h, w, c)


def _border_sample(shape, width_ratio=0.025) -> np.ndarray:
    """Mask of the outer frame of the image, where the surface is sampled."""
    h, w = shape[:2]
    b = max(4, int(width_ratio * min(h, w)))
    m = np.zeros((h, w), bool)
    m[:b] = m[-b:] = True
    m[:, :b] = m[:, -b:] = True
    return m


def _threshold(z: np.ndarray, sample: np.ndarray) -> float:
    """Decision threshold from the background's own z distribution."""
    zs = z[sample]
    return float(np.clip(1.4 * np.percentile(zs, 99.7), 2.8, 6.0))


def _confident_background(z, hi, sample, region, smooth=None) -> np.ndarray:
    """Background-like pixels that are connected to the sampled surface.

    ``smooth`` marks places without any edge; there a moderately unusual
    colour (a lit patch, a soft shadow) is still accepted as surface because
    nothing separates it from the background that surrounds it.
    """
    near = z < 0.5 * hi
    if smooth is not None:
        near = near | ((z < 1.6 * hi) & smooth)
    low = (near * 255).astype(np.uint8)
    _, comp = cv2.connectedComponents(low)
    touching = np.unique(comp[sample & (low > 0)])
    seed = np.isin(comp, touching[touching > 0])
    if region is not None:
        seed &= region > 0
    return seed


def _follow_illumination(feat: np.ndarray, nearest: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """Remove slow background drift (vignetting, soft shadow) from colour.

    The residual of confident background pixels to their nearest background
    component is smoothed over the image (normalised convolution, at reduced
    resolution) and subtracted, so a spotlit or shaded patch of the surface no
    longer looks like a print while multi-coloured surfaces stay untouched.
    """
    h, w = seed.shape
    if seed.sum() < 200:
        return feat
    q = max(1, round(max(h, w) / 200))
    small = (h // q, w // q)
    seed_q = cv2.resize(seed.astype(np.float32), small[::-1], interpolation=cv2.INTER_AREA)
    resid = (feat[..., :3] - nearest[..., :3]) * seed[..., None]
    resid_q = cv2.resize(resid, small[::-1], interpolation=cv2.INTER_AREA)
    sigma = 0.12 * min(small)
    weight = cv2.GaussianBlur(seed_q, (0, 0), sigma)
    num = cv2.GaussianBlur(resid_q, (0, 0), sigma)
    field = np.where(weight[..., None] > 0.02, num / np.maximum(weight, 1e-6)[..., None], 0)
    field = cv2.resize(field.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    out = feat.copy()
    out[..., :3] = feat[..., :3] - field
    return out


def _foreground(feat, sample, region=None, guide=None) -> np.ndarray:
    """Binary foreground mask (uint8 0/255) for pixels that are not surface.

    ``sample`` marks where the surface is observed, ``region`` optionally
    restricts the result, and ``guide`` is the image used for the watershed.
    """
    models = _bg_models(feat, sample)
    z, nearest = _zmap(feat, models, with_mean=True)
    hi = _threshold(z, sample)
    smooth = None
    if guide is not None:
        grey = cv2.GaussianBlur(cv2.cvtColor(guide, cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 2.0)
        edge = np.hypot(cv2.Sobel(grey, cv2.CV_32F, 1, 0), cv2.Sobel(grey, cv2.CV_32F, 0, 1)) / 8.0
        smooth = edge < 1.0
    for _ in range(3):  # each pass lets the confident background creep into soft shadow
        seed = _confident_background(z, hi, sample, region, smooth)
        adjusted = _follow_illumination(feat, nearest, seed)
        z, nearest = _zmap(adjusted, models, with_mean=True)
        hi = _threshold(z, sample)
    k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    seed_fg = ((z > hi) * 255).astype(np.uint8)
    if region is not None:
        seed_fg[region == 0] = 0
    seed_fg = cv2.morphologyEx(seed_fg, cv2.MORPH_OPEN, k5)
    fg = seed_fg
    if guide is not None:
        seed_bg = _confident_background(z, hi, sample, region, smooth)
        markers = np.zeros(z.shape, np.int32)
        markers[seed_bg] = 1
        markers[cv2.erode(seed_fg, np.ones((9, 9), np.uint8)) > 0] = 2
        if region is not None:
            markers[(region == 0) & (markers == 0)] = 1
        if (markers == 2).any() and (markers == 1).any():
            cv2.watershed(guide, markers)
            fg = ((markers == 2) * 255).astype(np.uint8)
            fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, k5)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    return _fill_small_holes(fg)


def _fill_small_holes(mask: np.ndarray, max_ratio: float = 0.3) -> np.ndarray:
    """Fill holes inside blobs, keeping large ones (the inside of a page frame)."""
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = mask.copy()
    if hier is None:
        return out
    for i, c in enumerate(cnts):
        parent = hier[0][i][3]
        if parent != -1 and cv2.contourArea(c) < max_ratio * cv2.contourArea(cnts[parent]):
            cv2.drawContours(out, [c], -1, 255, -1)
    return out


def _rect_fill(cnt) -> tuple[tuple, float]:
    """Minimum-area rectangle of a contour and how much of it the contour fills."""
    rect = cv2.minAreaRect(cnt)
    ra = max(1.0, rect[1][0] * rect[1][1])
    return rect, cv2.contourArea(cnt) / ra


def _convexity(cnt) -> float:
    """Contour area relative to its convex hull (1 = convex)."""
    return cv2.contourArea(cnt) / max(1.0, cv2.contourArea(cv2.convexHull(cnt)))


def _deskew(img, rect, pad=0):
    """Rotate ``rect`` upright and crop it (plus ``pad``); returns crop and matrix."""
    (cx, cy), (w, h), ang = rect
    m = cv2.getRotationMatrix2D((cx, cy), ang, 1.0)
    m[0, 2] += (w + 2 * pad) / 2 - cx
    m[1, 2] += (h + 2 * pad) / 2 - cy
    out = cv2.warpAffine(
        img, m, (int(round(w + 2 * pad)), int(round(h + 2 * pad))),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE,
    )
    return out, m


def _trim_side(lab: np.ndarray, max_frac=0.35) -> tuple[int, np.ndarray | None]:
    """Number of leading columns (axis 1) forming a uniform border band."""
    h, w = lab.shape[:2]
    y0, y1 = int(0.1 * h), int(0.9 * h)
    if y1 - y0 < 8:
        return 0, None
    k_max = int(max_frac * w)
    cols = lab[y0:y1, :k_max]
    mean = np.median(cols, axis=0)  # (k, 3)
    std = cols.std(0).mean(1)
    uniform = std <= 7.0
    start_limit = max(3, int(0.06 * w))
    starts = [
        k
        for k in range(max(1, min(start_limit, k_max - 4)))
        if uniform[k : k + 3].all() and np.linalg.norm(mean[k] - mean[k + 2]) < 3.5
    ]
    if not starts:
        return 0, None
    s0 = starts[0]
    ref = np.median(mean[s0 : s0 + 3], axis=0)
    dist = np.linalg.norm(mean - ref, axis=1)
    bad = (dist > 7) | (std > 7)
    bad[:s0] = False
    run = bad[:-1] & bad[1:]
    idx = np.flatnonzero(run)
    if len(idx) == 0:
        return 0, None
    k = int(idx[0])
    if k - s0 < max(2, int(0.012 * w)) or k < 3 or k + 3 >= k_max:
        return 0, None
    # the inner border edge must be a sharp full-length step, not a gradient
    step = np.linalg.norm(
        np.median(cols[:, k : k + 3], axis=(0, 1)) - np.median(cols[:, k - 3 : k], axis=(0, 1))
    )
    return (k, ref) if step >= 7.0 else (0, None)


def _tighten(lab_small: np.ndarray, rect):
    """Trim uniform border bands from a print outline to expose the picture."""
    (cx, cy), (w, h), ang = rect
    if w < 12 or h < 12:
        return rect
    crop, m = _deskew(lab_small, rect)
    ch, cw = crop.shape[:2]
    inset = 1.5
    ci = crop[int(inset) : ch - int(inset), int(inset) : cw - int(inset)]
    sides = [
        _trim_side(ci),
        _trim_side(ci[:, ::-1]),
        _trim_side(ci.transpose(1, 0, 2)),
        _trim_side(ci.transpose(1, 0, 2)[:, ::-1]),
    ]
    # A real print border surrounds the picture: its bands share one colour on
    # several sides.  A lone smooth band (sky, wall) is picture content.
    keep = [False] * 4
    for i, (ki, ci_col) in enumerate(sides):
        if ki == 0:
            continue
        mates = [
            j for j, (kj, cj) in enumerate(sides)
            if kj and np.linalg.norm(ci_col - cj) < 14
        ]
        if len(mates) >= 2:
            keep[i] = True
    left, right, top, bottom = (
        sides[i][0] + inset if keep[i] else 0 for i in range(4)
    )
    nw = cw - left - right
    nh = ch - top - bottom
    if nw < 0.4 * cw or nh < 0.4 * ch:
        return rect
    # new centre in crop coords -> original coords
    ncx = left + nw / 2
    ncy = top + nh / 2
    inv = cv2.invertAffineTransform(m)
    ox, oy = inv @ np.array([ncx, ncy, 1.0])
    return ((float(ox), float(oy)), (float(nw), float(nh)), ang)


def _contours_tree(mask):
    """Contours with hierarchy (holes and nesting)."""
    cnts, hier = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    return cnts, (hier[0] if hier is not None else [])


def _blobs(mask: np.ndarray, min_area: float) -> list[np.ndarray]:
    """Filled blobs; ring-like frames are dropped and their interiors explored."""
    cnts, hier = _contours_tree(mask)
    out: list[np.ndarray] = []

    def walk(i: int) -> None:
        while i != -1:
            c = cnts[i]
            area = cv2.contourArea(c)
            child = hier[i][2]
            holes = []
            j = child
            while j != -1:
                holes.append(j)
                j = hier[j][0]
            hole_area = sum(cv2.contourArea(cnts[j]) for j in holes)
            hull_area = max(1.0, cv2.contourArea(cv2.convexHull(c)))
            if holes and hole_area > 0.7 * hull_area:
                for j in holes:  # frame: recurse into grandchildren
                    if hier[j][2] != -1:
                        walk(hier[j][2])
            elif area >= min_area:
                out.append(c)
            i = hier[i][0]

    if len(cnts):
        walk(0)
    return out


def _quality(c: np.ndarray) -> float:
    """How rectangular the convex hull of a contour is (1 = perfect rectangle)."""
    return cv2.contourArea(cv2.convexHull(c)) / max(1.0, float(np.prod(cv2.minAreaRect(c)[1])))


def _split_at_notches(c: np.ndarray, min_area: float, depth: int = 0) -> list[np.ndarray]:
    """Separate touching prints by cutting between the notches of a blob.

    Two prints that touch leave concave notches in the outline.  The deepest
    notch is joined to the nearest outline point on the far side; the cut is
    kept only when both halves are clearly more rectangular than the whole.
    """
    if depth > 3 or _quality(c) >= 0.93 or len(c) < 12:
        return [c]
    pts = c.reshape(-1, 2)
    hull_idx = cv2.convexHull(c, returnPoints=False)
    defects = cv2.convexityDefects(c, hull_idx) if len(hull_idx) > 3 else None
    if defects is None:
        return [c]
    scale = np.sqrt(cv2.contourArea(c))
    n = len(pts)
    base = _quality(c)
    best = None
    for _, _, far, depth_fixed in defects.reshape(-1, 4):
        d = depth_fixed / 256.0
        if d < 0.05 * scale:
            continue
        p = pts[far]
        dist = np.linalg.norm(pts - p, axis=1)
        gap = np.minimum(np.abs(np.arange(n) - far), n - np.abs(np.arange(n) - far))
        dist[gap < 0.15 * n] = np.inf
        q = int(np.argmin(dist))
        if not np.isfinite(dist[q]) or dist[q] > 0.9 * scale:
            continue
        i, j = sorted((int(far), q))
        parts = [pts[i : j + 1], np.vstack([pts[j:], pts[: i + 1]])]
        if min(cv2.contourArea(part.reshape(-1, 1, 2)) for part in parts) < 0.4 * min_area:
            continue
        quals = [_quality(part.reshape(-1, 1, 2)) for part in parts]
        if min(quals) < 0.9 or np.mean(quals) < base + 0.04:
            continue
        score = np.mean(quals)
        if best is None or score > best[0]:
            best = (score, parts)
    if best is None:
        return [c]
    out: list[np.ndarray] = []
    for part in best[1]:
        out.extend(_split_at_notches(part.reshape(-1, 1, 2).astype(np.int32), min_area, depth + 1))
    return out


def _extract(feat, shape, sample, region, min_area, big_area, guide, depth=0, max_area=1e18, lab=None):
    """Contours of candidate print components, in working-image coordinates.

    A blob that is huge or clearly not rectangular is re-segmented with a
    surface model taken just inside its outline; the result replaces the blob
    when it looks like prints on a page, otherwise the blob is kept (a mosaic
    of touching prints or a single large print).  Pieces smaller than
    ``min_area`` are returned as debris for the shard merger.
    """
    fg = _foreground(feat, sample, region.astype(np.uint8) if region is not None else None, guide)
    out: list[np.ndarray] = []
    for c in _blobs(fg, 0.12 * min_area):
        rect, fill = _rect_fill(c)
        area = cv2.contourArea(c)
        if area < min_area:
            out.append(c)  # shard: merged (or dropped) later
            continue
        if depth < 2 and (area >= big_area or fill < 0.7):
            blob = np.zeros(shape[:2], np.uint8)
            cv2.drawContours(blob, [c], -1, 255, -1)
            inner = cv2.erode(blob, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
            ring_w = max(4, int(0.025 * min(shape[:2])))
            ring = (inner > 0) & (cv2.erode(inner, np.ones((2 * ring_w + 1,) * 2, np.uint8)) == 0)
            sub = _extract(feat, shape, ring, inner > 0, min_area, big_area, guide, depth + 1, max_area, lab)
            if sub:
                areas = np.array([cv2.contourArea(x) for x in sub])
                ok = np.array([_rect_fill(x)[1] >= 0.85 and _convexity(x) >= 0.9 for x in sub])
                total = float(areas.sum())
                prints = areas >= min_area  # smaller pieces are mere debris
                good = bool(prints.any()) and bool(ok[prints].all())
                if good and ((len(sub) >= 2 and 0.1 * area <= total <= 0.6 * area) or (len(sub) == 1 and total >= 0.5 * area)):
                    out.extend(sub)
                    continue
                mosaic = area > max_area and len(_split_gutters(lab, rect, min_area)) >= 2
                if not mosaic and (fill < 0.7 or area > max_area):
                    out.extend(sub)
                    continue
        out.extend(_split_at_notches(c, min_area))
    return out


def _min_dist(a: np.ndarray, b: np.ndarray) -> float:
    """Approximate smallest distance between two contours."""
    pa = a.reshape(-1, 2).astype(np.float32)
    pb = b.reshape(-1, 2).astype(np.float32)
    if len(pa) > 150:
        pa = pa[:: len(pa) // 150 + 1]
    if len(pb) > 150:
        pb = pb[:: len(pb) // 150 + 1]
    d = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=2)
    return float(d.min())


def _merge_fragments(cnts: list[np.ndarray], gap: float) -> list[np.ndarray]:
    """Merge poor-shaped fragments whose union forms a clean rectangle."""
    cnts = [cv2.convexHull(c) for c in cnts]

    def quality(c):
        return cv2.contourArea(c) / max(1.0, np.prod(cv2.minAreaRect(c)[1]))

    changed = True
    while changed and len(cnts) > 1:
        changed = False
        best = None
        for i in range(len(cnts)):
            for j in range(i + 1, len(cnts)):
                qi, qj = quality(cnts[i]), quality(cnts[j])
                if qi >= 0.88 and qj >= 0.88:
                    continue
                if _min_dist(cnts[i], cnts[j]) > gap:
                    continue
                u = cv2.convexHull(np.vstack([cnts[i], cnts[j]]))
                qu = quality(u)
                if qu >= 0.9 and qu >= max(qi, qj) + 0.03:
                    if best is None or qu > best[0]:
                        best = (qu, i, j, u)
        if best:
            _, i, j, u = best
            cnts = [c for k, c in enumerate(cnts) if k not in (i, j)] + [u]
            changed = True
    return cnts


def _valley(lab: np.ndarray):
    """Best straight gutter: a pair of opposite, full-length straight edges.

    Averaging the signed horizontal gradient down the whole crop cancels
    photographic texture but sums up edges that run straight along the entire
    length, which is what a gap between two prints looks like.
    """
    h, w = lab.shape[:2]
    y0, y1 = int(0.06 * h), int(0.94 * h)
    if y1 - y0 < 16 or w < 40:
        return None
    a = lab[y0:y1]
    gx = (a[:, 2:] - a[:, :-2]) / 2
    mean_g = gx.mean(axis=0)  # (w-2, 3)
    mag = np.linalg.norm(mean_g, axis=1)
    mag = np.concatenate([[0], mag, [0]])
    mean_g = np.vstack([np.zeros((1, 3)), mean_g, np.zeros((1, 3))])
    col_std = a.std(axis=0).mean(axis=1)
    floor = max(8.0, 10.0 * float(np.median(mag)))
    peaks = [
        x
        for x in range(1, w - 1)
        if mag[x] >= floor and mag[x] >= mag[x - 1] and mag[x] >= mag[x + 1]
        and 0.12 * w <= x <= 0.88 * w
    ]
    best = None
    max_width = 0.08 * w + 6
    for i, p in enumerate(peaks):
        for q in peaks[i + 1 :]:
            if q - p > max_width:
                break
            if q - p < 2:
                continue
            if float(mean_g[p] @ mean_g[q]) >= 0:
                continue
            # a real gap is a uniform strip: its interior has almost no
            # variation along its length (photographic bands do)
            ref_std = float(np.median(col_std[max(0, p - 40) : min(w, q + 40)]))
            if col_std[p + 1 : q].min() > max(4.0, 0.35 * ref_std):
                continue
            score = min(mag[p], mag[q]) / (float(np.median(mag)) + 1.0)
            if best is None or score > best[0]:
                best = (score, p, q)
    return best


def _split_gutters(lab: np.ndarray, rect, min_area: float, depth: int = 0) -> list[tuple]:
    """Recursively cut ``rect`` along straight gutters between touching prints."""
    (cx, cy), (w, h), ang = rect
    if depth > 4 or w * h < 2.5 * min_area or min(w, h) < 40:
        return [rect]
    best = None
    for delta in (0, -0.7, 0.7, -1.4, 1.4, -2.2, 2.2, -3.2, 3.2):
        r = ((cx, cy), (w, h), ang + delta)
        crop, m = _deskew(lab, r)
        for axis in (0, 1):
            arr = crop if axis == 0 else crop.transpose(1, 0, 2)
            v = _valley(arr)
            if v and (best is None or v[0] > best[0]):
                best = (v[0], axis, v[1], v[2], r, m, crop.shape[1], crop.shape[0])
        if best and best[0] > 25 and delta == 0:
            break
    if best is None:
        return [rect]
    _, axis, a, b, r, m, cw, ch = best
    inv = cv2.invertAffineTransform(m)
    pieces = []
    spans = ((0, a), (b, (cw if axis == 0 else ch)))
    for lo, hi in spans:
        if axis == 0:
            pc, psz = (lo + hi) / 2, (hi - lo)
            center = (pc, ch / 2)
            size = (psz, ch)
        else:
            pc, psz = (lo + hi) / 2, (hi - lo)
            center = (cw / 2, pc)
            size = (cw, psz)
        ox, oy = inv @ np.array([center[0], center[1], 1.0])
        pieces.append(((float(ox), float(oy)), (float(size[0]), float(size[1])), r[2]))
    out: list[tuple] = []
    for piece in pieces:
        if piece[1][0] * piece[1][1] < min_area:
            continue
        out.extend(_split_gutters(lab, piece, min_area, depth + 1))
    return out


def _edge_profile(strip: np.ndarray) -> np.ndarray:
    """Signed mean gradient magnitude along axis 1 of a (h, w, 3) strip."""
    h = strip.shape[0]
    core = strip[int(0.12 * h) : int(0.88 * h)]
    if core.shape[0] < 6 or core.shape[1] < 5:
        return np.zeros(strip.shape[1])
    gx = (core[:, 2:] - core[:, :-2]) / 2
    mag = np.linalg.norm(gx.mean(axis=0), axis=1)
    return np.concatenate([[0], mag, [0]])


def _snap(lab: np.ndarray, rect, rel_window: float = 0.06):
    """Move every side onto the strongest nearby full-length straight edge."""
    (cx, cy), (w, h), ang = rect
    win = max(4.0, rel_window * min(w, h))
    pad = int(win) + 2
    crop, m = _deskew(lab, rect, pad=pad)
    ch, cw = crop.shape[:2]
    inner = [pad, pad + w, pad, pad + h]  # left, right, top, bottom
    new = list(inner)
    for side in range(4):
        if side < 2:
            span = crop[int(pad + 0.0) : int(pad + h)]
            prof = _edge_profile(span)
            pos = inner[side]
        else:
            span = crop[:, int(pad) : int(pad + w)].transpose(1, 0, 2)
            prof = _edge_profile(span)
            pos = inner[side]
        lo, hi = max(1, int(round(pos - win))), min(len(prof) - 2, int(round(pos + win)))
        if hi <= lo:
            continue
        seg = prof[lo : hi + 1]
        d = np.abs(np.arange(lo, hi + 1) - pos) / win
        score = seg * (1 - 0.3 * d)
        k = int(np.argmax(score))
        if seg[k] >= max(10.0, 3.0 * float(np.median(prof[max(0, lo - 20) : hi + 20]))):
            new[side] = lo + k + 0.5
    nw, nh = new[1] - new[0], new[3] - new[2]
    if nw < 0.5 * w or nh < 0.5 * h:
        return rect
    ncx, ncy = (new[0] + new[1]) / 2, (new[2] + new[3]) / 2
    inv = cv2.invertAffineTransform(m)
    ox, oy = inv @ np.array([ncx, ncy, 1.0])
    return ((float(ox), float(oy)), (float(nw), float(nh)), ang)


def _overlap(a, b) -> float:
    """Intersection area of two rotated rectangles relative to the smaller one."""
    kind, pts = cv2.rotatedRectangleIntersection(a, b)
    if kind == cv2.INTERSECT_NONE or pts is None:
        return 0.0
    return float(cv2.contourArea(pts)) / max(1.0, min(a[1][0] * a[1][1], b[1][0] * b[1][1]))


def _local_surface(lab: np.ndarray, rect) -> np.ndarray:
    """Median colour of the ring just outside a rectangle (the surface there)."""
    mask = np.zeros(lab.shape[:2], np.uint8)
    cv2.fillPoly(mask, [cv2.boxPoints(rect).astype(np.int32)], 255)
    near = cv2.dilate(mask, np.ones((7, 7), np.uint8))
    far = cv2.dilate(mask, np.ones((21, 21), np.uint8))
    ring = (far > 0) & (near == 0)
    if ring.sum() < 50:
        return np.median(lab.reshape(-1, 3), axis=0)
    return np.median(lab[ring], axis=0)


def _extend(lab: np.ndarray, rect, surface: np.ndarray, reach: float = 0.9):
    """Grow sides that stop inside a print onto a much stronger straight edge.

    A print whose lower half resembles the surface is under-segmented: the
    fitted side lies on some inner feature (a horizon) while the real boundary
    is a full-length straight edge further out.  A side moves outward only when
    that edge is clearly stronger than whatever the side currently rests on.
    """
    (cx, cy), (w, h), ang = rect
    pad = int(reach * max(w, h)) + 3
    crop, m = _deskew(lab, rect, pad=pad)
    sides = []
    for side in range(4):
        if side < 2:
            strip = crop[int(pad) : int(pad + h)]
            pos = pad if side == 0 else pad + w
        else:
            strip = crop[:, int(pad) : int(pad + w)].transpose(1, 0, 2)
            pos = pad if side == 2 else pad + h
        prof = _edge_profile(strip)
        core = strip[int(0.1 * strip.shape[0]) : int(0.9 * strip.shape[0])]
        line_std = core.std(axis=0).mean(axis=1)
        line_off = np.linalg.norm(np.median(core, axis=0) - surface, axis=1)
        direction = -1 if side in (0, 2) else 1
        reach_px = int(reach * max(w, h))
        idx = np.arange(1, reach_px + 1) * direction + int(round(pos))
        idx = idx[(idx > 1) & (idx < len(prof) - 2)]
        if len(idx) < 8:
            sides.append(0.0)
            continue
        here = prof[max(1, int(round(pos)) - 3) : int(round(pos)) + 4].max()
        floor = max(12.0, 4.0 * float(np.median(prof)))
        k = int(np.argmax(prof[idx]))
        peak = prof[idx[k]]
        lo, hi = sorted((int(round(pos)), int(idx[k])))
        flat = (line_std[lo + 1 : hi] < 2.0) & (line_off[lo + 1 : hi] < 12.0)
        gap = flat.size >= 3 and bool(np.any(flat[:-2] & flat[1:-1] & flat[2:]))
        if peak >= floor and peak >= 2.0 * here and not gap:
            sides.append(float(abs(idx[k] - pos)))
        else:
            sides.append(0.0)
    if not any(sides):
        return rect
    left, right, top, bottom = sides
    nw, nh = w + left + right, h + top + bottom
    ncx_c = pad + w / 2 + (right - left) / 2
    ncy_c = pad + h / 2 + (bottom - top) / 2
    inv = cv2.invertAffineTransform(m)
    ox, oy = inv @ np.array([ncx_c, ncy_c, 1.0])
    return ((float(ox), float(oy)), (float(nw), float(nh)), ang)


def _merge_shards(cnts: list[np.ndarray], gap: float, min_area: float) -> list[np.ndarray]:
    """Group scattered fragments of one print (texture matching the surface)."""
    small = [c for c in cnts if cv2.contourArea(c) < min_area]
    big = [c for c in cnts if cv2.contourArea(c) >= min_area]
    small.sort(key=cv2.contourArea, reverse=True)
    small = small[:40]
    used = [False] * len(small)
    for i in range(len(small)):
        if used[i]:
            continue
        group = [i]
        grown = True
        while grown:
            grown = False
            for j in range(len(small)):
                if j in group or used[j]:
                    continue
                if any(_min_dist(small[j], small[k]) <= gap for k in group):
                    group.append(j)
                    grown = True
        pts = np.vstack([small[k] for k in group])
        hull = cv2.convexHull(pts)
        harea = cv2.contourArea(hull)
        fill = harea / max(1.0, np.prod(cv2.minAreaRect(hull)[1]))
        covered = sum(cv2.contourArea(small[k]) for k in group)
        if harea >= min_area and fill >= 0.75 and covered >= 0.3 * harea:
            big.append(hull)
            for k in group:
                used[k] = True
    return big


def _find_rects(feat, shape, min_area, big_area, guide, max_area, lab) -> list[tuple]:
    """Rotated-rectangle hypotheses (working-image coordinates), one per print."""
    sample = _border_sample(shape)
    cnts = _extract(feat, shape, sample, None, min_area, big_area, guide, 0, max_area, lab)
    gap = 0.02 * max(shape[:2])
    cnts = _merge_fragments(cnts, gap)
    cnts = _merge_shards(cnts, 4 * gap, min_area)
    rects = [cv2.minAreaRect(c) for c in cnts if cv2.contourArea(c) >= min_area]
    return [r for r in rects if max(r[1]) <= 5.0 * max(1.0, min(r[1]))]  # rulings, binding strips


def _refine_rects(lab: np.ndarray, rects: list[tuple], min_area: float) -> list[tuple]:
    """Split, snap, grow and tighten every hypothesis; returns picture rectangles."""
    pieces = [piece for r in rects for piece in _split_gutters(lab, r, min_area)]
    snapped = [_snap(lab, r) for r in pieces]
    refined = []
    for i, rect in enumerate(snapped):
        grown = _extend(lab, rect, _local_surface(lab, rect))
        others = [q for j, q in enumerate(snapped) if j != i]
        if grown is not rect and any(_overlap(grown, q) > 0.1 for q in others):
            grown = rect  # growing into a neighbour is never right
        refined.append(_tighten(lab, grown))
    return refined


def detect_photos_v6(
    image: Image.Image,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.80,
    padding: int = 0,
    inset: int = 0,
) -> list[DetectedRegion]:
    """Detect the photographic area of every print in a scan.

    Args:
        image: Scan to analyse.
        min_area_ratio: Smallest print (outline) relative to the image area.
        max_area_ratio: Largest picture relative to the image area.
        padding: Pixels added around each region.
        inset: Pixels removed around each region.

    Returns:
        Regions in reading order, in the coordinates of ``image``.
    """
    bgr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    height, width = bgr.shape[:2]
    scale = WORK / max(height, width)
    small = cv2.resize(bgr, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    area = small.shape[0] * small.shape[1]
    min_area = 0.5 * min_area_ratio * area
    rects = _find_rects(
        _features(small),
        small.shape,
        min_area,
        0.45 * area,
        cv2.GaussianBlur(small, (0, 0), 1.0),
        max_area_ratio * area,
        lab,
    )
    scaled = [
        ((c[0] / scale, c[1] / scale), (rw / scale, rh / scale), angle)
        for c, (rw, rh), angle in _refine_rects(lab, rects, min_area)
    ]
    return _regions(scaled, (width, height), 0.5 * min_area_ratio, max_area_ratio, padding - inset)


def _regions(rects, size, min_ar, max_ar, net):
    """Convert rotated rectangles to ``DetectedRegion`` objects (caller padding applied)."""
    iw, ih = size
    regions = []
    for rect in rects:
        center, (rw, rh), angle = rect
        area = rw * rh
        ratio = area / (iw * ih)
        if not min_ar <= ratio <= max_ar:
            continue
        pts = cv2.boxPoints(rect)
        x, y, bw, bh = cv2.boundingRect(pts)
        xa, ya = max(0, x - net), max(0, y - net)
        wa = max(1, min(iw - xa, bw + 2 * net))
        ha = max(1, min(ih - ya, bh + 2 * net))
        aw, ah = max(1, rw + 2 * net), max(1, rh + 2 * net)
        if rw < rh:
            aw, ah = ah, aw
            angle += 90
        regions.append(
            DetectedRegion(
                center=center, size=(aw, ah), angle=angle, area=area, area_ratio=ratio,
                x=xa, y=ya, width=wa, height=ha,
            )
        )
    regions.sort(key=lambda r: (r.y // 100, r.x))
    return regions
