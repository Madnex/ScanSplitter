# Detector v7 (`scansplitterv7`)

Status: DEFAULT detector. Binding: keep this file updated in the same commit as
any change to `src/scansplitter/detector_v7.py`. v5 stays selectable ("v5 ·
Previous"), v6 stays "experimental", and stored projects with older modes keep
working unchanged.

## Contract

`detect_photos_v7(image, min_area_ratio=0.02, max_area_ratio=0.80, padding=0,
inset=0) -> list[DetectedRegion]`. It builds on v5 and therefore uses
MobileSAM (`mobilesam_encoder` / `mobilesam_decoder`); everywhere v5 triggers
the MobileSAM download or hint (Quick, settings panel), v7 does too. It is
registered as `scansplitterv7` (aliases `v7`, `ScanSplitterv7` in the API) in
`detection.py`, `processor.py`, `cli.py`, `api.py`, `validation.py`,
`projects.py`, `benchmarking.py`, `benchmarks/evaluate.py` and the frontend.

## Target definition

A region is the **inner photographic image** of one print. Excluded: white and
scalloped print borders, photo corners, tape, and the album page. Regions are
rotated rectangles in input coordinates, same as every other detector.

## Pipeline

1. **Proposals.** v5 rectangles (v3 + tightly prompted MobileSAM, texture and
   frame passes) are the anchors. Alternatives: v3 proposals, v3 with the Otsu
   colour threshold capped at 30 (when large pale areas dominate), and b*
   (yellow-blue) chroma proposals, which separate neutral silver emulsion from
   yellowed paper borders.
2. **Inner-edge tightening.** Every proposal is deskewed and each of its four
   sides is moved independently onto the inner emulsion edge when a uniform
   light band (plateau of near-maximal brightness ending in a step towards
   darker content, within a bounded depth, with column votes on one straight
   line) is found. Two passes. Sides without such a band do not move.
3. **Scoring and arbitration.** Each tightened rectangle is scored by the
   brightness step along its four sides. A v5 anchor is replaced by an
   overlapping alternative only if that scores clearly higher (margin 3);
   alternatives with no anchor are added only if strong on their own (score
   >= 22); boxes mostly (>60%) contained in a better-scored box are dropped.
4. **Relative ghost rejection.** Prints seen through glassine sleeves on the
   facing page have a low-detail interior and a soft boundary. A box is dropped
   only if both hold *and* its boundary sharpness is below 0.8 x the 75th
   percentile of the sharp prints on the same scan, so uniformly soft or faded
   scans keep everything.
5. **Output.** Area-ratio filtering, then conversion to `DetectedRegion` with
   `padding - inset` as the net adjustment.

## Evaluation protocol

Real-scan quality, not synthetic scores, decides detector changes (see the v6
post-mortem in `detector-v6.md`).

- A **private real-scan benchmark** of user-approved scans with re-annotated
  inner-photo ground truth lives OUTSIDE the repository at
  `~/.scansplitter/real-benchmark/` for privacy. Real scans, their annotations
  and real-scan result files must never be committed.
- Scans are split **dev / holdout**. Tune on dev only; judge on the holdout
  and report it separately.
- Synthetic suites (`benchmarks/results/v7.*`, `robust-{dev,holdout}-v7.*`)
  are regression guards only.
- Reproduce synthetic runs with
  `uv run benchmarks/evaluate.py --scan-detector v7 --suite scansplitter --output benchmarks/results/v7.md`
  and `--manifest benchmarks/robustness/manifest.json --suite robust-dev|robust-holdout`.

## Results

Box quality / F1@0.5 / F1@0.85 / count accuracy (%).

| Set | v7 | v5 | v3 |
|---|---|---|---|
| Real holdout (14 unseen scans, 59 prints) | 90.3 / 95.9 / 87.6 / 64.3 | 81.7 / 91.7 / 61.7 / 64.3 | 84.1 / 91.5 / 72.9 / 50.0 |
| Real dev (26 scans) | 90.0 / 97.0 / 79.8 / 92.3 | 76.6 / 87.7 / 57.5 / 57.7 | n/a |
| Synthetic album suite | 92.7 / 100 / 83.3 / 100 | 89.2 / 98.1 / 74.1 / 100 | n/a |

Robustness holdout box quality: v7 88.8 vs v5 74.5. Runtime is about 1.8 s per
10000 px scan versus 1.3 s for v5.

## Known failure modes

- Photos visible through glassine sleeves on the facing page are sometimes
  still reported (extra box).
- Light-sky or snow photos whose content blends into the white border are
  clipped or missed.
- Colour-print albums are not covered by the real benchmark; behaviour there is
  unmeasured.

## Tests

`tests/test_detector_v7.py` covers two bordered prints on a cream page (boxes
exclude the white border) and an empty page. It is skipped when the MobileSAM
models are not in `src/scansplitter/model_cache`.
