# Phase 4 Spec — Library Delivery

*Status: complete on branch `quality-overhaul` (2026-07-11).*
*This document is the binding contract between backend and frontend work. If the
implementation must deviate, update this file in the same commit.*

## Goal

Build one canonical, provenance-carrying artifact set from approved project
photos and either download it as a ZIP or explicitly deliver it to a watched
folder, Immich, or Nextcloud.

## Invariants

- Only boxes from `approved` and `auto_approved` scans are exported.
- Originals are never changed. Access copies and optional masters are derived
  in memory from stored geometry and effective restoration settings.
- Client-derived folder components pass through `sanitize_name`; ZIP/local
  paths remain contained. Credentials are request-scoped and never persisted.
- GPS coordinates enter EXIF and JSON manifests only when the current export or
  delivery request sets `include_gps: true`; the stored project setting is only
  a frontend default.
- Folder delivery is available only in local mode. Every network delivery is an
  explicit background job.

## Canonical export request

`POST /api/projects/{pid}/export` accepts this partial body and returns
`202 {"job_id"}`. Missing project is `404`.

| Field | Type/default | Contract |
|---|---|---|
| `format` | string or null; project `settings.format` | Lowercased; `png` produces PNG access copies and every other current value follows the JPEG branch (`.jpg`). There is no explicit enum rejection in the current backend. |
| `quality` | integer or null; project `settings.quality` | Passed to JPEG encoding; request type errors are `422`. There is no explicit range check or `400` validation. |
| `include_gps` | boolean or null; backend default false | When omitted/null, the backend uses false rather than the stored project value. True gates both derivative GPS EXIF and manifest latitude/longitude. |
| `master_format` | `png`, `tiff`, or null; project setting | Other/case-mismatched values return `400`. Null means no master. |
| `organize_folders` | boolean or null; project setting | Enables metadata-derived access/master subfolders. |
| `manifest_format` | `json`, `csv`, `both`, or null; project setting | Other/case-mismatched values return `400`. Null means no manifest. |

The job result exposes `download_url`; that URL returns `application/zip`.

## ZIP layout and naming

```text
<album>/<year>/<event>/<source_stem>_<box_index>.jpg|png
masters/<album>/<year>/<event>/<source_stem>_<box_index>.png|tif
digitization-manifest.json
digitization-manifest.csv
```

- Metadata folders are ordered album, four-digit year from `date`, event;
  absent components are skipped. Each present component uses `sanitize_name`.
  If all are absent the folder is `Unsorted`.
- Folder organization applies to access copies and masters. Masters always
  have the top-level `masters/` prefix.
- With organization disabled, access copies are at ZIP root and masters under
  `masters/`.
- The source filename stem is separately made filesystem-safe; the box index is
  1-based. Collisions receive `_2`, `_3`, and so on.
- TIFF masters are deliberately uncompressed: Pillow cannot combine TIFF
  compression with nested EXIF plus XMP tag 700 in this implementation.

## Manifest contract

JSON is an array of records with:

| Field | Value |
|---|---|
| `project_id` | Project id. |
| `scan_id` | Source scan id. |
| `box_id` | Stored photo box id. |
| `source` | Original uploaded filename. |
| `output` | Access-copy path in the artifact set. |
| `master` | Master path, or null. |
| `sha256` | SHA-256 of the access-copy bytes. |
| `metadata` | Full normalized scan metadata, except latitude/longitude are removed unless this request has `include_gps: true`. |
| `restoration` | Effective merged project settings plus per-box overrides used for the derivative. |

CSV contains the columns `project_id,scan_id,box_id,source,output,master,sha256`.
`both` writes both fixed filenames shown above.

## Delivery API

`POST /api/projects/{pid}/deliver` returns `202 {"job_id"}`. The job result is
`{target,count}`. Job-time HTTP failures retain `error_status` and
`error_detail` in the shared job record.

Common optional fields are `include_gps` (default false), `master_format`
(default null in the request model), `organize_folders` (default true),
`manifest_format` (default `both`), and `overwrite` (default false).
`master_format` and `manifest_format` use the same lowercase-only enums and
return `400` before queueing when invalid. An unknown target is `400`.

| Target | Required/request fields | Delivery behavior and errors |
|---|---|---|
| `folder` | `target: "folder"`, non-empty `destination`; optional `overwrite` | Outside local mode returns `403`. Destination must already be a directory; missing/empty or nonexistent is `400`. The canonical ZIP is expanded beneath it. If any target exists and overwrite is false, the job fails `409` and lists sorted conflicting artifact names; no files are written before that conflict check. True permits replacement. |
| `immich` | `target: "immich"`, non-empty `server_url`, `api_key` | URL must be HTTP(S), else `400`. Only access `.jpg`, `.jpeg`, and `.png` images are built/uploaded for this target: masters, manifests, and folder organization are disabled. Follows Immich's generated OpenAPI upload contract: multipart `POST {server}/api/assets` (or `{server}/assets` when the supplied root already ends in `/api`) with `x-api-key`; `assetData`, `fileCreatedAt`, `fileModifiedAt`, filename, and metadata are included. The asset part uses its real `image/jpeg` or `image/png` MIME type. Both response status `200` and `201` are success; other/network failures become `502`. |
| `nextcloud` | `target: "nextcloud"`, non-empty `base_url`, `username`, `password`; optional `folder` default `ScanSplitter` | `base_url` must be the HTTP(S) WebDAV files root, conventionally `https://host/remote.php/dav/files/USERNAME`. Each artifact is Basic-authenticated `PUT` below the requested folder. Both `X-NC-WebDAV-Auto-Mkcol: 1` and `X-NC-WebDAV-AutoMkcol: 1` are sent. On PUT `409`, the client issues `MKCOL` per path segment (accepting existing-collection `405`) and retries. Other/network failures become `502`. |

All string request values are trimmed before required-field validation. Passwords
and API keys exist only in the delivery request/job closure and are not written
to `project.json`.

## Frontend

The project overview stores access format/quality, master choice, folder
organization, manifest choice, and GPS preference as UI defaults and submits
them explicitly for export/delivery. Export uses the shared progress/download
flow.

The Delivery dialog selects watched folder, Immich, or Nextcloud; shows only
that target's required fields; offers overwrite only for folder delivery;
labels the Nextcloud field as the WebDAV files URL; states that credentials are
used once; tells Immich users to grant only `asset.upload` and accepts a server
base URL with or without `/api`; and displays shared job progress/errors.

## Testing

- `tests/test_projects.py`: masters/folder layout/manifests, metadata privacy,
  lowercase enum validation, canonical folder delivery, local validation, and
  overwrite conflict behavior.
- `tests/test_delivery.py`: archive iteration/path validation, authenticated
  Immich and Nextcloud requests, both auto-MKCOL headers, 409 MKCOL fallback,
  and watched-folder all-before-write conflict detection.
- Frontend lint and production build remain clean.

## Non-goals

Credential storage, automatic/scheduled network delivery, remote library
deletion or synchronization, source replacement, and TIFF compression.
