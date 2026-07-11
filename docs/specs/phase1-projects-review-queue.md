# Phase 1 Spec — Persistent Projects, Bulk Upload, Review Queue

*Status: in implementation on branch `quality-overhaul` (2026-07-11).*
*This document is the contract between backend and frontend work. If the
implementation must deviate, update this file in the same commit.*

## Goal

A user drops 400 scans into a named project, detection runs in the
background, and they review only the scans the machine is unsure about —
keyboard-first. Projects survive restarts.

The existing single-session flow ("Quick mode") stays fully working and
untouched; Projects is an additional top-level mode.

## Storage

- Root: `~/.scansplitter/projects/` (override with env
  `SCANSPLITTER_DATA_DIR`, which replaces `~/.scansplitter`).
- Layout per project:
  ```
  <data_dir>/projects/<project_id>/
    project.json        # all state below, atomic-written (tmp + rename)
    scans/<scan_id>.png|jpg   # stored scan images (PDF pages rendered once)
    thumbs/<scan_id>.jpg      # 320px-wide cached thumbnails
  ```
- `project.json` writes are atomic (write `.tmp`, `os.replace`) and guarded
  by a per-project `threading.Lock`.
- Filenames on disk are always server-generated ids — never client input
  (same rule as `sanitize_name` elsewhere).

## Data model (`project.json`, version 1)

```json
{
  "version": 1,
  "id": "<uuid hex>",
  "name": "Shoebox 1975",
  "created_at": "2026-07-11T10:00:00Z",
  "updated_at": "...",
  "settings": {
    "detection_mode": "scansplitterv2",
    "min_area_ratio": 2.0,
    "max_area_ratio": 80.0,
    "auto_rotate": true,
    "format": "jpeg",
    "quality": 85,
    "include_gps": false
  },
  "scans": [
    {
      "id": "<uuid hex>",
      "original_name": "IMG_1234.jpg",
      "stored_file": "scans/<id>.jpg",
      "page": null,
      "width": 1600,
      "height": 1200,
      "status": "pending",
      "boxes": [],
      "flags": [],
      "detected_count": null,
      "reviewed_at": null
    }
  ]
}
```

- `page`: null for images; 1-based page number when the scan came from a
  PDF (each PDF page becomes its own scan entry).
- `boxes`: same shape as the existing detect/crop API
  (`{id, x, y, width, height, angle}` — center-based, like `BoundingBox`).
- `status` lifecycle:
  `pending → detecting → (auto_approved | needs_review | failed)`;
  user actions move any of the last three to `approved` (or back to
  `needs_review` by editing). `pending` = not yet detected.
- `flags`: list of `{code, box_id, message}` (see Confidence below);
  `box_id` null for scan-level flags.

## Confidence flagging (module `src/scansplitter/confidence.py`)

Pure functions, no I/O, no FastAPI imports:

```python
@dataclass(frozen=True)
class Flag:
    code: str          # machine-readable, from the codes below
    box_id: str | None # offending box, or None for scan-level
    message: str       # human sentence, e.g. "Box touches the right edge"

def evaluate_scan(
    boxes: list[dict],       # [{id,x,y,width,height,angle}] center-based px
    image_width: int,
    image_height: int,
    expected_count: int | None = None,  # e.g. modal count across the project
) -> list[Flag]
```

Flag codes (v1):

| code              | trigger                                                        |
|-------------------|----------------------------------------------------------------|
| `no_boxes`        | zero boxes detected                                             |
| `touches_edge`    | any box corner within 0.5% of image min-dimension of any edge   |
| `extreme_aspect`  | box aspect ratio > 3:1 (either orientation)                     |
| `area_outlier`    | box area < 35% of the median box area on the scan (≥3 boxes)    |
| `overlap`         | two boxes with IoU > 0.15 (axis-aligned approximation is fine)  |
| `count_mismatch`  | expected_count given and detected count differs                 |

A scan with zero flags after detection gets status `auto_approved`;
otherwise `needs_review`. The caller (projects layer) computes
`expected_count` as the modal `detected_count` across the project's
detected scans when ≥ 5 scans are detected, else passes None.

## Backend API

All endpoints follow existing conventions: sync `def` (threadpool), 404 via
`HTTPException`, names sanitized, no client-controlled paths. New module
`src/scansplitter/projects.py` holds the store; endpoints live in `api.py`.

| Method & path | Body / params | Returns |
|---|---|---|
| `GET  /api/projects` | – | `{"projects": [{id,name,created_at,updated_at,counts:{total,pending,detecting,auto_approved,needs_review,approved,failed}}]}` |
| `POST /api/projects` | `{name}` | full project JSON |
| `GET  /api/projects/{pid}` | – | full project JSON (scans included) |
| `PATCH /api/projects/{pid}` | `{name?, settings?}` (partial) | full project JSON |
| `DELETE /api/projects/{pid}` | – | `{"status":"deleted"}` |
| `POST /api/projects/{pid}/scans` | multipart, field `files` (repeatable); query `detect` (default `true`) | `{"scans":[scan...], "jobs":[{scan_id, job_id}]}` — PDFs expand to one scan per page; when `detect=true`, one detect job per new scan is queued |
| `GET  /api/projects/{pid}/scans/{sid}/image` | query `thumb` (bool) | image bytes (thumbnail is cached 320px JPEG) |
| `PATCH /api/projects/{pid}/scans/{sid}` | `{boxes?, status?}` | updated scan JSON. Setting `boxes` re-runs `evaluate_scan` and updates flags; allowed `status` values from client: `approved`, `needs_review` |
| `DELETE /api/projects/{pid}/scans/{sid}` | – | `{"status":"deleted"}` |
| `POST /api/projects/{pid}/scans/{sid}/detect` | – | `202 {"job_id"}` (re-detect one scan; job result also persisted into the project) |
| `POST /api/projects/{pid}/detect-pending` | – | `202 {"jobs":[{scan_id, job_id}]}` (all `pending`/`failed` scans) |
| `POST /api/projects/{pid}/export` | `{format?, quality?, include_gps?}` (defaults from project settings) | `202 {"job_id"}` — job crops every **approved + auto_approved** scan's boxes and zips; result `{download_url}` like the existing export job. Note: project scans are re-encoded on ingest and carry no EXIF, so `include_gps` is accepted for API parity but is a no-op in Phase 1 (EXIF-carrying project exports arrive with Phase 2 metadata). |

Job integration: project detect jobs reuse `jobs.submit_job` with kind
`"detect"`; on success the worker persists boxes + flags + status into the
project before marking the job succeeded, so a poller can rely on either
the job result or a project re-fetch. Naming inside the export zip:
`{original_name_stem}_{photo_index}.{ext}` where `photo_index` is 1-based
per box within its scan; cross-scan stem collisions get `_2`/`_3` suffixes.
PDF-page scans share the PDF filename as `original_name` (all pages same
stem) and rely on collision-suffixing to disambiguate.

## Frontend

Top-level mode switch (header): **Quick** (existing UI, unchanged) and
**Projects** (new). State for the new mode lives in new components/hooks —
do not grow App.tsx; add `src/hooks/` and `src/components/projects/`.

Screens:

1. **Project list** — cards with name, counts (e.g. "142/400 reviewed"),
   updated-at; create (name prompt), open, delete (confirm dialog).
2. **Project overview** — dropzone accepting many files (`webkitdirectory`
   optional; multi-select required), grid of scan thumbnails with status
   chips: `OK · n` (auto_approved, green), `CHECK` (needs_review, amber),
   `✓` (approved), `…` (pending/detecting), `!` (failed). Filter tabs:
   All / Needs review / Approved / Pending. A progress header while any
   scan is `detecting` ("Detecting 251/400…"). Poll `GET /api/projects/{pid}`
   every ~1.5s while any scan is pending/detecting; stop when idle.
3. **Review mode** — entered from the grid (or "Start review" button which
   walks `needs_review` scans in order). Full-width scan image with the
   existing `ImageCanvas` box editor; flag messages listed beside it.
   Keyboard (with the standard input-focus guard):
   - `Enter` approve → advance to next needs_review scan
   - `→` / `←` next / previous scan (any status)
   - `E` toggle box editing focus (boxes are always editable on click)
   - `R` re-detect this scan
   - `Esc` back to grid
   Editing boxes PATCHes them on approve/navigate (not per drag).
4. **Export** — button on overview: runs the project export job with the
   existing progress bar + download pattern.

## Testing

- `tests/test_confidence.py` — pure unit tests per flag code, plus a
  no-flags case.
- `tests/test_projects.py` — CRUD, upload (image + 2-page PDF expansion),
  detect job persisting boxes/flags/status, PATCH boxes re-evaluating
  flags, approve flow, export job producing a zip, path-safety (project
  ids validated, no client-controlled paths), storage under a tmp
  `SCANSPLITTER_DATA_DIR`.
- Frontend: `npm run lint` + `npm run build` must stay clean.

## Non-goals for Phase 1

Metadata editing (Phase 2), restoration (Phase 3), library push (Phase 4),
multi-user/auth, project import/export, undo history inside review mode
beyond the existing box-deletion undo.
