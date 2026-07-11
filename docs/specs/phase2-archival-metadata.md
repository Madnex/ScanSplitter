# Phase 2 Spec — Archival Metadata

*Status: complete (2026-07-11).*
*If implementation must deviate, update this file in the same commit.*

## Goal

A user describes a scan once and every exported crop from it carries useful,
portable archival metadata. The same metadata can be applied to many scans in
one operation. Originals remain untouched.

This phase builds on persistent Projects mode. Quick mode remains unchanged.

## Delivery slices

1. **Core metadata (this implementation):** dates (including approximate
   dates), place + coordinates, caption, people, event and album; batch edit;
   EXIF/XMP export.
2. **Front/back pairing + OCR:** one-to-one scan pairing, local Tesseract OCR,
   reviewed transcription, and explicit attachment to the front caption.
3. **Place-name lookup:** an explicit button calls OpenStreetMap Nominatim,
   identifies the provider, and never sends a request merely because the
   editor is opened.

## Stored schema

`project.json` remains version 1. Every scan gains a `metadata` object. Older
manifests are read compatibly: a missing object is returned as these defaults
and is persisted on the next mutation.

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
  }
}
```

- `date`: representative ISO date (`YYYY-MM-DD`) or null.
- `date_label`: the user's archival wording, e.g. `circa 1980` or
  `summer 1975`. Exact dates may leave it null.
- `date_precision`: null, `day`, `month`, `year`, `season`, or `circa`.
- Coordinates must either both be null or both be present; latitude is
  `[-90, 90]`, longitude `[-180, 180]`.
- Text is trimmed, empty strings normalize to null, people are trimmed,
  de-duplicated case-insensitively, and empty entries are removed.
- Limits: 2,000 characters for caption; 200 for other text values; at most
  100 people.

For approximate dates the UI chooses a representative date while retaining
the human meaning: year → January 1, month → first day, season → first day of
the chosen meteorological season, circa → the entered representative date.
The approximation is never silently presented as exact because
`date_label` and `date_precision` travel in XMP.

## API

| Method & path | Body | Returns |
|---|---|---|
| `PATCH /api/projects/{pid}/scans/{sid}/metadata` | partial metadata object | updated scan |
| `PATCH /api/projects/{pid}/metadata` | `{scan_ids: [id...] | null, metadata: partial metadata object}` | `{scans: [updated scan...]}` |

`scan_ids: null` means all scans. An empty list is rejected. The batch
operation validates every id and the whole metadata patch before writing, so
it is all-or-nothing. Fields omitted from a patch are preserved; explicit
null clears scalar fields; `people: []` clears people.

## Export contract

Metadata is embedded in every JPEG crop at export time. Stored scans and
archival crops are never modified. PNG export retains image pixels but does
not promise portable metadata; the UI explains that JPEG is required for
library-grade metadata.

JPEG output contains:

- EXIF `DateTimeOriginal` and `DateTimeDigitized` from representative `date`.
- EXIF GPS latitude/longitude only when the existing `include_gps` export
  setting is true. `place_name` itself is not private-coordinate data and is
  retained in XMP either way.
- An Adobe-compatible XMP packet with Dublin Core description, subject
  keywords (people, event and album), IPTC location, and ScanSplitter's
  `dateLabel` / `datePrecision` properties.

Keywords are stable strings: each person as `Person: <name>`, plus optional
`Event: <event>` and `Album: <album>`. The caption is the XMP description.
The place is the IPTC location. Exact and representative dates use ISO text.

If no metadata is set, JPEG bytes have no synthetic EXIF/XMP added. GPS is
privacy-off by default, as in Phase 1.

## Frontend

The project overview adds a **Metadata** action. It opens a compact editor
that applies to either the currently selected scan or all scans. The initial
core slice uses explicit current/all scope so a later multi-select grid can
extend it without changing the API.

Fields: date, precision, archival date wording, place, latitude, longitude,
caption, comma-separated people, event and album. Saving refreshes the
project. A metadata marker on scan thumbnails makes coverage visible.

The editor must state that coordinates are only exported when “Include GPS”
is enabled and that portable metadata requires JPEG export.

## Testing

- Normalization and validation: dates, coordinate pairs/ranges, text limits,
  people de-duplication, partial updates and explicit clears.
- Storage compatibility for old scans without `metadata`.
- Single and batch endpoints, including all-or-nothing invalid scan ids.
- JPEG export contains the expected EXIF date, optional GPS and XMP fields;
  GPS is absent by default.
- Existing project and Quick-mode tests remain green.
- Frontend lint and production build remain clean.

## Non-goals for the core slice

Automatic geocoding, OCR, face recognition, controlled-vocabulary person
records, per-crop overrides, sidecar files, and metadata in PNG exports.
