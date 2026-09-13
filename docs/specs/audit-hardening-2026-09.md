# Audit hardening contract — September 2026

Approved by the owner on 13 September 2026. This addendum supersedes conflicting storage, confidence, export, and lifecycle statements in the phase specifications; unrelated feature contracts remain binding.

## A. Original retention and rendering

- New projects use manifest version 2. Each imported file has an immutable `originals/<server-id>.<ext>` copy and SHA-256 checksum. PDF pages share the retained PDF. `scans/<scan-id>.png` is a separate lossless processing proxy; editor and thumbnail JPEGs are display assets.
- Raster processing uses the retained source; PDF detection/review coordinates use 150 DPI and scale to a 300-DPI source render at crop/export time. Originals retain their bit depth, profiles, and metadata byte-for-byte. The current OpenCV processing pipeline produces 8-bit RGB derivatives; processed PNG/TIFF masters are not substitutes for the immutable original.
- Version-1 projects remain readable, with `source_integrity=legacy_derivative`. Discarded source data cannot be reconstructed. The UI warns to re-import original files for archival output. Re-import creates new scans; existing boxes and metadata remain available for comparison. Automatic relinking across mismatched page dimensions is deliberately unsupported.
- Quick crops retain independent server-generated lossless PNG assets. Their bounded JPEG previews are never used for new-client exports. Rotation is a final transpose applied to the retained crop; rotating a preview does not alter downloadable pixels. Each export reference carries the immutable session and crop IDs.
- Individual, ZIP and local downloads use the same encoding and metadata policy. Project previews and exports share cleanup, orientation, restoration and manual rotation. Preview sizes remain explicitly bounded. GPS remains opt-in.

## B. Work and draft safety

- Detection scheduling deduplicates work per scan. Each job captures a scan revision; subsequent edits invalidate its right to persist results. Optional PATCH revisions reject stale saves with HTTP 409.
- Interrupted detection is reconciled on store startup to pending or needs-review. Cancellation also restores a retryable state. Failure preserves the structured job error. Restart never automatically repeats cloud requests.
- Deleting a project cancels its jobs; late completion cannot recreate or update the removed manifest.
- Review writes are serialized, the editor is inert during saves, and dependent navigation/export/preview actions stop on failure. Unsaved drafts block mode switches and browser unload. Polling retries transient failures with bounded backoff and discards out-of-order responses.
- Quick keeps visited page drafts independently; Crop All includes every edited page with boxes. Unvisited PDF pages still require navigation/detection before cropping. Results are attributed by session/page/crop identity; file indices are retained only for display order and naming. Closing a file cancels current cropping and releases its server session.

## C. Interface and accessibility

- Both modes use `DetectionControls`: Photos/Album pages, Local/Cloud AI, layout, auto-detect, auto-rotate, area limits and cleanup. Detector versions live under Advanced. Cloud transmission is disclosed in both workflows.
- The visible workflow is Upload → Review → Export. Quick has separate narrow-screen panels; project review supports full editing on small screens with normal scrolling. The canvas refits on resize, offers zoom and scroll-to-pan, and has keyboard-accessible numeric geometry controls.
- Only the selected photo exposes filename/caption fields. Save state and an explicit Save edits action are visible.
- Project export options and delivery entry are grouped in one export dialog. Native dialogs isolate background focus and restore focus on closing. Review shortcuts do not intercept selects, buttons, text editing or open dialogs. Main landmark and skip link are present.
- Unavailable place lookup is not offered. Metadata scope changes/closing protect dirty fields; coordinate edits preserve paired partial-patch semantics. Metadata wording covers JPEG/PNG/TIFF with interoperability caveats.
- Front/back relationships are one-to-one pairs, never chains or cycles. UI shows the selected front's current back, and permits unlinking/reassignment.

## D. Resource and delivery limits

- Project imports stage a whole batch and commit only after every file validates. Failure removes staged data. HTTP ingestion retains only one file's bytes at a time. Limits: 200 MB per file, 500 MB per project batch, 200 pages per PDF, 100 million decoded pixels per image/render. PDF limits are checked before raster allocation.
- The executor has three workers and 64 total running/queued slots. Saturation returns HTTP 429; bulk detection preserves already queued jobs and leaves remaining scans pending for the next explicit run.
- Crop preview caches are keyed by box/settings/size and keep at most 32 variants per scan. Export jobs build ZIP artifacts on disk and stream downloads. Artifacts are temporary, cleaned periodically; session cleanup does not delete sessions with active jobs.
- Delivery checks cancellation between files and records confirmed filename/content hashes in a connection-specific project journal. Retrying the same connection skips confirmed unchanged files. Folder retries recreate missing confirmed files and reject conflicting content unless overwrite is selected. Nextcloud uses conditional PUT by default. Cancellation does not undo files already delivered.
- Passwords and API keys are preserved exactly. Saved secrets cannot be combined with a different URL (or Nextcloud username). Journals never contain plaintext credentials.
- A lost remote acknowledgment is inherently uncertain: local journals cannot guarantee exactly-once delivery on an arbitrary remote service. Confirmed files resume; unconfirmed files retry using the remote service's conflict/duplicate behavior. No claim of production certification for an Immich/Nextcloud version is made.

## E. Confidence

All newly detected scans require manual review. A lack of geometry flags means only that those checks found no problem. Manual approval is labelled Reviewed; legacy automatic statuses are labelled Detected. Existing legacy automatic approvals remain exportable for compatibility; new detection never creates one.

`uv run python -m benchmarks.calibrate_confidence` measures the previous approval rule against strict IoU 0.85. The repository's 20 synthetic challenge scans yielded 20 no-flag approvals, of which 9 failed strict boundary correctness (45%). This is evidence against the old rule, not a population error estimate. Restoring automatic approval requires a consented representative real-scan corpus and an agreed acceptable error rate.

## F. Services and verification

Shared modules: `sources.py` (bounded source decode), `detection.py` (detector dispatch), `rendering.py` (pixel processing), and `validation.py` (strict settings/geometry). The existing encoder is shared by individual and bundle exports. Geometry must be finite, uniquely identified, positive in size, centered inside the image and bounded by its diagonal; modest rotated edge overhang remains supported. Portable export names use case-folded collision detection.

Regression coverage includes transactional ingestion, immutable originals/PDFs, restart/cancellation/stale-result behavior, stale save conflicts, validation, pixel/metadata export parity, delivery resume, per-page drafts, failed-save navigation and polling retries. Native browser verification supplements DOM tests; it is not screen-reader certification or large-collection load certification. Benchmark is lazy-loaded, production chunks stay under the warning threshold, and packaging reuses CI's tested frontend artifact.
