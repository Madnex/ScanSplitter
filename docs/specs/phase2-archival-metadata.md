# Phase 2 Spec — Archival Metadata

*Status: complete on branch `quality-overhaul` (2026-07-11).*
*This document is the binding contract between backend and frontend work. If the
implementation must deviate, update this file in the same commit.*

## Goal

A user describes a scan once and every exported crop from it carries useful,
portable archival metadata. Metadata may be applied atomically to one, several,
or all scans. Front/back pairing and explicit place lookup support archival
description without modifying project originals.

Quick mode remains unchanged.

## Invariants

- Stored scans are never modified; metadata is inserted only into export and
  delivery derivatives.
- Metadata patches are partial: omitted fields are preserved and explicit
  `null` clears scalar fields. Coordinates must be set or cleared together.
- Pairing is one-to-one. A front has at most one back and a back points to at
  most one front; deleting a front clears its back scan's `back_of` value.
- Place lookup is the only Phase 2 network action, is explicitly initiated,
  and is never triggered by opening the editor.
- GPS coordinates appear in derivative EXIF **and manifest metadata only when
  that export or delivery request sets `include_gps: true`**. The stored project
  `settings.include_gps` value is a UI default and does not authorize backend
  export by itself.

## Data model (`project.json`, version 1)

Each scan has these additional fields; old manifests receive the defaults when
read and persist them on their next mutation.

```json
{
  "metadata": {
    "date": null,
    "date_label": null,
    "date_precision": null,
    "place_name": null,
    "latitude": null,
    "longitude": null,
    "caption": null,
    "people": [],
    "event": null,
    "album": null
  },
  "back_of": null
}
```

| Field | Contract |
|---|---|
| `date` | ISO `YYYY-MM-DD`, or null. |
| `date_label` | User's archival wording, such as `circa 1980`; text up to 200 characters. |
| `date_precision` | null, `day`, `month`, `year`, `season`, or `circa`. |
| `place_name`, `event`, `album` | Trimmed text up to 200 characters; empty becomes null. |
| `latitude`, `longitude` | Both null or both numbers; latitude `[-90,90]`, longitude `[-180,180]`. Booleans are not numbers. |
| `caption` | Trimmed text up to 2,000 characters; empty becomes null. |
| `people` | A list, never null: at most 100 text entries, each at most 200 characters. Entries are trimmed, empties removed, and duplicates removed case-insensitively while preserving first spelling/order. `[]` clears the list. |
| `back_of` | On a back scan, the paired front scan id; otherwise null. |

For approximate dates the UI stores a representative ISO date while retaining
the wording and precision: year uses January 1, month the first day, and season
the first day of the selected meteorological season.

## Backend API

Validation failures below return `400`; missing projects/scans return `404`.
Pydantic request-shape/type failures return `422`.

| Method & path | Body | Returns / errors |
|---|---|---|
| `PATCH /api/projects/{pid}/scans/{sid}/metadata` | Any subset of `{date,date_label,date_precision,place_name,latitude,longitude,caption,people,event,album}` | Updated scan. Omitted fields remain; scalar nulls clear; `people: []` clears. Invalid metadata returns `400`. |
| `PATCH /api/projects/{pid}/metadata` | `{scan_ids: [id...] \| null, metadata: <partial object>}` | `{"scans":[updated scan...]}`. `scan_ids: null` targets all scans; `[]` is `400`. Every id and every resulting metadata object is validated before the single write, so the operation is all-or-nothing. |
| `POST /api/projects/{pid}/scans/{sid}/pair` | `{back_scan_id: string \| null}` where `{sid}` is the front | The front scan. A scan cannot pair to itself (`400`). A non-null back is moved from any prior front and replaces the front's prior back; null unpairs the front. Pair state is visible on the back scan as `back_of`. |
| `POST /api/geocode` | `{query: string}` | `{"provider":"OpenStreetMap Nominatim","results":[{"name", "latitude", "longitude"}]}` (up to five). Empty query is `400`; provider/network failure is `502`. This is an explicit Nominatim request with a ScanSplitter user agent, never an automatic lookup. |

## Export metadata contract

All supported access/master encoders receive the representative-date EXIF and
Adobe-compatible XMP generated from scan metadata. JPEG uses an Adobe XMP APP1
segment; PNG uses `XML:com.adobe.xmp`; TIFF uses tag 700.

- EXIF `DateTimeOriginal` and `DateTimeDigitized` come from `date`.
- EXIF GPS latitude/longitude is emitted only for a request with
  `include_gps: true`.
- XMP carries ScanSplitter `representativeDate`, `dateLabel`, and
  `datePrecision`; Photoshop location; Dublin Core caption; and keywords
  `Person: <name>`, `Event: <event>`, and `Album: <album>`.
- Manifest JSON includes the metadata object, but removes `latitude` and
  `longitude` unless that same request has `include_gps: true`.
- With no metadata, no synthetic EXIF/XMP is added.

## Frontend

The project overview exposes a Metadata editor scoped to one selected scan or
all scans. It submits only dirty fields, so untouched values remain intact.
Fields cover date/precision/wording, place and coordinates, caption, people,
event, and album. Place search is a button action and identifies Nominatim.

The front/back editor selects and pairs two scans. It directs users to record
inscriptions manually in the front scan's caption. Thumbnail metadata markers
show coverage. The UI exposes an Include GPS export/delivery default and
explains that coordinates are omitted unless it is enabled.

## Testing

- `tests/test_metadata.py`: normalization, partial updates/null clearing,
  dates, coordinate pairing/ranges, people rules, and XMP placement.
- `tests/test_projects.py`: persistent single/batch atomic updates, pairing,
  explicit geocoding, EXIF/XMP and GPS request gating across export
  formats/manifests.
- Frontend lint and production build remain clean.

## Non-goals

Automatic geocoding, built-in OCR, face recognition, controlled-vocabulary
person records, per-crop metadata overrides, and metadata sidecar files.
