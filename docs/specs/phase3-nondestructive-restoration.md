# Phase 3 — Non-destructive restoration

Status: complete. This is the binding
contract for Phase 3 work.

## Invariants

- Project scans in `scans/` are archival sources and are never modified.
- Restoration runs on in-memory crops and produces derivatives only.
- Every restoration is opt-in and its settings persist in `project.json`.
- Long-running restoration is executed inside the existing background export
  job, with progress and cancellation.
- Before/after comparison is available from review mode before export.

## Slice 1: auto-deskew

Projects gain an `auto_deskew` setting, defaulting to `false` for new and old
manifests. When enabled, each exported crop is corrected after 90-degree
orientation and before encoding/metadata insertion.

The estimator considers only strong lines within 5 degrees of a horizontal or
vertical axis. It uses a line-length-weighted median, ignores corrections below
0.25 degrees, and declines corrections when there is insufficient evidence.
It never converts a large rotation into a deskew operation.

## Slice 2: before/after preview

Review mode can request a preview for the first photo box. The server crops
the current stored geometry, applies restoration to an in-memory derivative,
and returns a labeled side-by-side JPEG through a cancellable background job.
The preview is ephemeral and is never written into the project.

## Slice 3: color and fade restoration

Projects gain an opt-in `restore_color` setting. Export and preview use the
same local pipeline: capped highlight-based gray-world balancing followed by
a gently blended luminance stretch. Channel gains are bounded to 0.85–1.18,
preventing intentional lighting or already-balanced photos from receiving an
extreme correction. No source scan is modified.

## Later slices

## Slice 4: defect repair and archival upscale

Sparse dust and thin scratches are detected using bounded morphological masks;
only small connected components are inpainted. The optional 2× upscale uses
Lanczos and restrained sharpening and is explicitly non-generative. Restoration
keys can also be stored on an individual photo box to override project defaults.

Semantic colorization is deliberately excluded: generated colors are not
historical facts and conflict with library-grade archival output. It remains
possible for a future plugin to provide colorized derivatives with provenance,
but core exports do not invent colors.
