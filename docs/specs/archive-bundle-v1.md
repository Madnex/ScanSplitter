# Archive bundle v1

A portable, consumer-independent digitization export for persistent Projects.
It needs no account or receiving application. Quick mode retains its current
image export. Existing ZIP, folder, Immich and Nextcloud delivery is unchanged.

## Usage

In a Project, open Export and select **Archive bundle**. Optionally include
untouched originals. Download the ZIP and open it in any compatible consumer.
`POST /api/projects/{pid}/export` accepts `archive_bundle: true` and optional
`include_originals: true` alongside photo format, quality, GPS and processed
master options. The standard export job/download contract applies. These flags
are request-specific, not saved project settings. Bundle export ignores folder
organization and the legacy manifest choice. Per-scan export rejects bundle
flags: this workflow exports the reviewed project snapshot.

## ZIP and manifest

The ZIP contains `archive-manifest.json`, plus exactly its declared files:
`scans/` (full scan PNGs), `photos/` (access crops), optional `processed/`
(PNG/TIFF crops), and optional `sources/` (untouched source images/PDFs).
Names are server IDs and hashed box IDs, never user-controlled paths.

The JSON envelope has `schema: scansplitter.archive-bundle`, `version: 1`,
`package_id`, `producer: {name, version}`, `project: {id, name}`,
`ordering: project_scan_order`, and arrays `files`, `scans`, `photos`.
See `archive-bundle-v1.schema.json` for the machine-readable field schema.
Unknown optional fields may be ignored; unsupported versions must be rejected.

Files have unique `id`, relative POSIX `path`, `sha256`, `media_type`, and
`role`: `source_original`, `scan_image`, `access`, `processed_derivative`.
Every included file is checksummed. Consumers must validate relative paths,
unique IDs/paths, references, payload inventory and checksums before import.

Scans have `id`, `file_id`, optional `source_file_id`, `source_name`,
`source_sha256`, `source_integrity`, optional 1-based `source_page`, positive
`sequence`, optional `back_of`, `review_status`, `coordinate_size: [w,h]`,
`image_size: [w,h]`, and `metadata`. Sequences are project order, **not a claim
of physical album order**. A scan is not automatically an album page or cover.
Back references name front scans; individual crop pairing is not inferred.
If only one side is reviewed/exported, `back_of` is null: excluded records cannot
be referenced. PDF pages can share one retained PDF source.

Photos have unique `id`, `scan_id`, original `box_id`, positive per-scan
`sequence`, `access_file_id`, optional `processed_file_id`, `metadata`,
`transformations`, and `geometry: {type: rotated_rect, units: normalized,
center: [x/w,y/h], size: [width/w,height/h], angle}`. Coordinates refer to the
full exported scan image, before crop restoration/manual rotation; angle uses
ScanSplitter/OpenCV image coordinates (x right, y down, positive clockwise).
Rotated boxes may overhang an edge; lengths may exceed one but each pixel
length is bounded by the scan diagonal. Transformations record effective
processing settings and box overrides; automatic operations are recipes,
not measured transform matrices. PDF coordinates originate at review resolution
and are scaled proportionally for the exported full-resolution image.

## Preservation and privacy

Full scan PNGs and processed PNG/TIFF crops are rendered **8-bit derivatives**,
not substitutes for original bit depth, profiles or file metadata. Originals
are optional and copied byte-for-byte, checksum-verified, and deduplicated when
PDF pages share a source. Legacy scans without retained originals fail clearly
if original inclusion is requested; exporting derivatives remains possible.

GPS is opt-in for rendered images and JSON metadata. Untouched originals can
contain GPS and other private metadata regardless of the derivative GPS choice;
the export dialog explains this before original inclusion.

Only approved and legacy auto-approved scans are included. Preserve review status:
legacy auto-approval does not imply human review. Metadata uncertainty and source
relationships remain explicit; consumers should not infer identities or dates.

The package UUID is UUIDv5 of canonical manifest content before `package_id`
(using the URL namespace). Identical catalog/settings/bytes produce identical
manifest content and identity across repeated exports. ZIP timestamps are not
part of that identity. Changed content produces a new bundle; consumers decide
how updates to an already-imported project should be reconciled.
