# Phase 3 Spec — Non-destructive Restoration

*Status: complete on branch `quality-overhaul` (2026-07-11).*
*This document is the binding contract between backend and frontend work. If the
implementation must deviate, update this file in the same commit.*

## Goal

Provide conservative, opt-in restoration for each exported photo, with an
ephemeral before/after preview and no mutation of archival project scans.

## Invariants

- Files under project `scans/` remain archival sources and are never modified.
- Restoration runs on in-memory crops after optional 90-degree auto-rotation
  and before encoding and metadata insertion.
- Preview and export invoke the same restoration pipeline in this order:
  deskew, color/fade, dust/scratch repair, 2× upscale.
- Project defaults persist in `project.json`; a photo box may override each
  restoration switch independently. Box values merge over project settings.
- Re-detection regenerates the scan's boxes and therefore drops their stored
  restoration overrides. This is a known limitation.
- Export and preview run as cancellable background jobs.

## Data model

Project settings add four booleans, defaulting false for new and old manifests:

```json
{
  "settings": {
    "auto_deskew": false,
    "restore_color": false,
    "remove_dust": false,
    "upscale_2x": false
  }
}
```

Any stored photo box may add a sparse override map:

```json
{
  "id": "photo-1",
  "x": 400,
  "y": 300,
  "width": 400,
  "height": 300,
  "angle": 0,
  "restoration": {
    "auto_deskew": true,
    "restore_color": false
  }
}
```

Overrides are submitted through the existing
`PATCH /api/projects/{pid}/scans/{sid}` `boxes` array. The box normalizer keeps
only `auto_deskew`, `restore_color`, `remove_dust`, and `upscale_2x`, coercing
their values to booleans; other override keys are discarded. At execution,
`{**project.settings, **box.restoration}` is used.

Project settings are submitted through the existing
`PATCH /api/projects/{pid}` `{settings: {...}}` contract. Only known setting
keys are stored. `master_format` and `manifest_format` have explicit enum
validation (`400` for unknown values); the four restoration settings themselves
currently rely on the frontend to send booleans and have no separate backend
type/error validation.

## Restoration operations

| Setting | Behavior |
|---|---|
| `auto_deskew` | Uses strong Hough lines within 5° of a horizontal/vertical axis and a line-length-weighted median. Corrections below 0.25° or without enough evidence are skipped; large rotations are not treated as deskew. |
| `restore_color` | Capped highlight gray-world balance followed by a gently blended luminance stretch. Channel gains are bounded to 0.85–1.18. |
| `remove_dust` | Detects sparse high-contrast specks/thin scratches with bounded morphology and inpaints only small connected components. |
| `upscale_2x` | Non-generative 2× Lanczos resize followed by restrained sharpening. |

Semantic colorization is excluded because generated colors are not archival
facts.

## Backend API

| Method & path | Body | Returns / errors |
|---|---|---|
| `PATCH /api/projects/{pid}` | `{settings: {auto_deskew?, restore_color?, remove_dust?, upscale_2x?}}` | Full project JSON with merged settings. Missing project is `404`. |
| `PATCH /api/projects/{pid}/scans/{sid}` | `{boxes: [{id,x,y,width,height,angle,restoration?}, ...], status?}` | Updated scan with normalized per-box overrides. Missing project/scan is `404`. Editing boxes without an explicit status returns the scan to `needs_review`. |
| `POST /api/projects/{pid}/scans/{sid}/restoration-preview` | `{box_id?: string \| null}` | `202 {"job_id"}`. `box_id` selects any stored box; null/omitted selects the first. No boxes is `400`; an unknown box id is `404`. The job result contains `{detail,download_url}` and the download is an inline `image/jpeg` labeled side-by-side comparison. An empty crop fails the job with `400`. |
| `POST /api/projects/{pid}/export` | Phase 4 export body | `202 {"job_id"}`; applies effective per-box restoration to every exported crop. |

The preview is ephemeral and is not written into the project.

## Frontend

The project overview exposes four opt-in project toggles. Review mode offers
Project default / On / Off overrides for the first displayed photo box and
persists them with the scan's box geometry. Preview can request a selected box
by id and shows the returned comparison image in a dialog. Progress and errors
use the shared job UI.

## Testing

- `tests/test_restoration.py`: conservative deskew, color/fade behavior,
  pipeline opt-in behavior, dust repair, and non-generative upscale.
- `tests/test_projects.py`: old-manifest defaults, preview job/download, and
  restoration exercised as part of canonical export.
- Frontend lint and production build remain clean.

## Non-goals

Source-file mutation, generative reconstruction or colorization, manual brush
retouching, and preservation of per-box overrides across re-detection.
