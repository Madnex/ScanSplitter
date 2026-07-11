# Phase 3 — Non-destructive restoration

Status: auto-deskew and before/after preview implemented. This is the binding
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

## Later slices

- White balance and fade restoration.
- Dust and scratch removal.
- Optional colorization and super-resolution, with explicit model downloads.
- Per-photo overrides where a project-wide setting is too coarse.
