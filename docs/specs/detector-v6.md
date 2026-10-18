# Detector v6 (`scansplitterv6`)

Status: experimental, NOT the default (v5 remains the default). Keep this file
updated in the same commit as any change to `src/scansplitter/detector_v6.py`.

## Real-scan evaluation (2026-10-18)

v6 was tuned on the synthetic robustness suite and does not transfer to real
album scans. On 40 privately held, user-approved real scans (159 boxes,
6020x4015 to ~10000x9000 px, kept outside the repository) it scored box
quality 0.52 / F1@0.50 0.56 / count accuracy 0.28, versus v5 0.78 / 0.89 / 0.58
and v3 0.79 / 0.90 / 0.68. Failure modes: no detections on cream album pages
with scalloped white-bordered prints, page-sized boxes, and single prints split
along tonal edges. Synthetic results below are therefore not evidence of
real-world quality; any future default change must be judged on real scans.

## Contract

`detect_photos_v6(image, min_area_ratio=0.02, max_area_ratio=0.80, padding=0,
inset=0) -> list[DetectedRegion]` is pure OpenCV/NumPy: no MobileSAM, no
network, no model downloads. It is registered as `scansplitterv6` in
`detection.py`, `processor.py`, `cli.py`, `api.py`, `validation.py`,
`projects.py` and the frontend. v3, v4 and v5 remain selectable, and stored
projects with `scansplitterv5` keep working unchanged.

## Target definition

A region is the **inner photographic area** of one print: white margins,
Polaroid frames, album mounts and scan background are excluded. Regions are
rotated rectangles in the coordinates of the input, returned in reading order.
`min_area_ratio` bounds the print outline; `max_area_ratio` bounds the picture.

## Pipeline

All work runs on a copy scaled to 800 px (longest side), so parameters are
relative to the image and results do not depend on scan resolution.

1. **Surface model**: colour and fine-texture statistics of the image border
   are clustered into a few background components; slow drifts (vignetting,
   soft shadow) are subtracted. Pixels improbable under every component are
   foreground, refined by an edge-respecting seeded watershed.
2. **Hypotheses**: huge or non-rectangular blobs are re-modelled from the
   surface just inside their outline; fragments of one print merge when their
   union is a clean rectangle; touching prints split at outline notches.
3. **Straight-edge evidence**: gaps between prints are found as opposite,
   full-length straight edges around a uniform strip. Rectangle sides snap to
   nearby edges and grow onto much stronger ones when under-segmented.
4. **Picture extraction**: uniform border bands surrounding the picture are
   trimmed to leave the photographic area.

## Benchmark protocol

- DEV (`robust-dev`) is for tuning. HOLDOUT (`robust-holdout`) is the judge:
  never tune on it. A fresh unseen split is generated for confirmation.
- Metric: inner-image box quality (rotated IoU based), plus count accuracy.
- Reproduce:
  `uv run benchmarks/evaluate.py --manifest benchmarks/robustness/manifest.json --suite robust-dev --scan-detector v6 --output benchmarks/results/robust-dev-v6.md`
  (and `robust-holdout`, and `--suite scansplitter` for the original album suite).

## Results (box quality, v6 vs v5)

| Suite | v6 | v5 |
|---|---:|---:|
| robust-dev (47 cases) | 95.9% | 65.9% |
| robust-holdout | 93.9% | 74.5% |
| fresh unseen split | 93.3% | 71.9% |
| original album suite | 93.7% | 89.2% |

Count accuracy is 87-98% for v6 versus 64-74% for v5. Runtime is about
0.4 s/image versus 0.5-5 s. Results are scale-invariant from 0.6x to 2.2x.
Raw reports: `benchmarks/results/robust-{dev,holdout}-v6.*` and `v6.*`.

## Known failure modes

- Borderless near-white photos on a white flatbed fragment or are missed.
- Touching prints where one has a white edge can merge.
- Prints whose colour matches the surface and that have smooth borders.

## Tests

`tests/test_detector_v6.py` covers two prints on white, a print on a textured
background, tight-gutter splitting, an empty page, and a large rescaled image.
