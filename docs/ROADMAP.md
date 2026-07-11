# ScanSplitter Roadmap

*Last updated: 2026-07-11. Status legend: ✅ done · 🔨 in progress · ⬜ planned*

## Vision

ScanSplitter is a "scan splitter" today; the job users actually bring to it is
emptying a shoebox of hundreds of old prints into their photo library,
correctly dated and captioned, in an evening. The unit of work should be the
**project** (the whole collection), not the single scan on screen.

Target user: family archivists and genealogists, mostly non-technical,
privacy-minded, often self-hosted. They repeat the scan→split→fix→tag→file
loop hundreds of times per sitting — every click removed compounds.

## Principles

- **Progressive disclosure** — the simple path (upload → review → export)
  stays untouched; power features stay tucked away until wanted.
- **Keyboard-first** — everything in the review loop reachable without the
  mouse.
- **Non-destructive** — originals are sacred; crops, rotations, and
  enhancements are always reversible.
- **Library-grade output** — valid EXIF/XMP so photos sort by real date and
  place in Apple/Google Photos, Immich, etc.
- **Local & private** — processing stays local; any cloud step must be
  explicit and optional.
- **Trust the machine, verify the doubt** — automate the obvious silently,
  surface only the uncertain for human review.

## Foundations (done)

- ✅ Security hardening: path-traversal sanitization, upload caps,
  decompression-bomb guard, SHA-256-pinned model downloads, local-mode
  gating of host-filesystem endpoints.
- ✅ Background job system (`jobs.py`): `/api/jobs/*` endpoints with
  progress, stage, cancellation, structured errors; frontend progress bars.
- ✅ EXIF privacy: GPS opt-in on export, clearable dates.
- ✅ Correctness: detection race fix (AbortController + stale-result guard),
  undo for box deletion, duplicate-filename guard, export scope honoring
  the Current/All toggle.
- ✅ CI (ruff + pytest + frontend lint/build + wheel content check),
  Dependabot, release smoke tests.

## Phase 1 — Throughput & trust 🔨

*Turns an hour of clicking into ten minutes of review.*
Spec: [docs/specs/phase1-projects-review-queue.md](specs/phase1-projects-review-queue.md)

- Persistent, named projects saved to disk; reopenable across restarts.
- Bulk/folder upload; detection queues in the background per scan.
- Keyboard-first review queue: approve (Enter), navigate (arrows), edit
  boxes only when needed.
- Confidence flagging: auto-approve unambiguous scans, flag the doubtful
  ones (box touching edge, odd aspect ratio, count/area outliers).
- Progress everywhere, powered by the job endpoints.

## Phase 2 — Metadata a genealogist would keep ⬜

- Batch-apply per scan: one time/place/event written to every crop.
- Approximate dates as first-class ("1975", "circa 1980", "summer '75"),
  written as valid EXIF.
- Place name → GPS geotag.
- Captions, people tags, album/roll grouping as XMP keywords.
- Front/back pairing with OCR: scan the back, read the handwriting, attach
  date and note to the front.

## Phase 3 — Non-destructive restoration ⬜

- Auto-deskew for the 1–5° tilt that 90° auto-rotate can't fix.
- Color & fade restoration (white-balance yellowed prints); optional
  colorization.
- Dust & scratch removal.
- Opt-in super-resolution for low-DPI scans.
- Always before/after; never overwrite the archival crop. Runs as
  background jobs.

## Phase 4 — Land where the memories live ⬜

- Direct library targets: Immich, watched folder for Apple/Google Photos,
  Nextcloud.
- Optional lossless TIFF/PNG master alongside JPEG.
- Folder structure from metadata (album/year/event).
- Digitization manifest (CSV/JSON provenance record).

## Quick wins (schedulable anytime)

- Auto-deskew toggle (~half a day; rotatable-box crop already supports it).
- Persist user settings across sessions.
- First-run scanning tips (dark backing sheet, gaps between prints).
- Low-DPI warning before export.
- Per-scan expected photo count ("I put 4 down") with mismatch warning.
- Click-to-detect a single missed photo.

## Explicitly out of scope / decided against

- Lowering `requires-python` below 3.13 (owner decision, 2026-07-11).
- Hosted/multi-user deployment: no auth layer exists; local-first by design.
  Scanning is a local act — a hosted instance adds little.

## Open operational items

- Switch PyPI publishing to Trusted Publishing (requires configuring the
  GitHub repo as a trusted publisher on pypi.org first — owner action).
