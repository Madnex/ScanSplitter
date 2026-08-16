# Edge Post-processing Spec

*Status: implemented on branch `edge-post-processing` (2026-08-16).*
*This document is the binding contract between backend and frontend work.*

## Goal

Remove light scan or album whitespace left around a roughly detected crop
without risking automatic removal of ambiguous photographic content.

## Invariants

- Stored source scans and stored box geometry are never modified.
- Cleanup runs on the in-memory, deskewed crop before 90-degree orientation,
  restoration, upscaling, encoding, and metadata insertion.
- Preview, quick-mode crop, CLI processing, per-scan export, project export,
  and delivery use the same deterministic cleanup function.
- A side is changed only when a light, low-variation region is connected to
  the outer crop boundary and ends at a sustained color/texture transition.
- Conservative mode leaves ambiguous and dark borders unchanged, searches no
  more than 10% of the shorter crop dimension, and rejects a proposal removing
  more than 28% of the crop area. Tight mode searches up to 22%, accepts
  moderately weaker evidence, may repeat the operation three times, and caps
  total removal at 48%.
- The fitted edges may slope independently. Their intersections form a
  quadrilateral that is perspective-warped to the rectangular derivative.

## Settings and overrides

New projects and legacy manifests default `settings.edge_cleanup_mode` to
`"conservative"`. The setting accepts `off`, `conservative`, or `tight`, is
exposed in the project overview, and may be overridden per photo through
`box.restoration.edge_cleanup_mode`. Legacy boolean `edge_cleanup` settings and
overrides migrate to `conservative`/`off` while loading.

Quick-mode crop requests accept `edge_cleanup_mode`, defaulting to
`conservative`; the former boolean request field remains an alias. Quick mode
exposes all three choices. The CLI accepts
`--edge-cleanup {off,conservative,tight}` and keeps `--no-edge-cleanup` as an
alias for `off`.

## Algorithm

For each side, the crop is represented as inward depth by distance along the
edge. A Lab-color model is learned from the outer strip, and matching pixels
not connected to the boundary are discarded. The deepest connected pixel in
each row or column becomes an edge candidate only when followed by a strong
transition. A robust linear fit removes outliers and is shifted just inside a
high percentile of the remaining uneven boundary. Tight mode relaxes the
thresholds, learns from the brightest low-chroma boundary cluster, bridges
small color/shadow gaps, uses a safety inset that grows from two to eight pixels
with crop resolution, and repeats the pass. A final axis-aligned shave searches
the outer 4% for pale remnants covering as little as 8% of a side; it is capped
at 15% area for that pass and does not resample the image again. This allows
thin fringes, small partial wedges, color-varied aged borders, an album
background, and then a white print margin to be removed separately. Sides
without sufficient support or confidence retain their original crop boundary.

## Testing

- Sloped light borders on all four sides are removed and rectified.
- A single confident side can be removed independently.
- Tight mode removes nested page and white print borders more deeply than
  conservative mode; off returns the original object.
- Tight mode covers two-pixel high-resolution fringes, partial wedges, and
  alternating white/yellowed border segments.
- The final shave removes a pale remnant covering less than the fitted-line
  support threshold.
- Uniform bright images and dark borders remain unchanged.
- The quick crop API honors enabled and disabled cleanup.
- Project defaults, legacy-manifest defaults, and per-photo overrides persist.

## Non-goals

Removal of black photo borders, semantic content detection, inpainting, and
mutation of archival source files or review geometry. Tight mode intentionally
allows removal of confidently detected white print borders.
