# Phase 4 — Library delivery

Phase 4 exports one canonical artifact set. JPEG/PNG derivatives may be joined
by an opt-in lossless PNG or deflate-compressed TIFF master. Metadata folders
use sanitized `album/year/event` components and fall back to `Unsorted`.

JSON and CSV digitization manifests record project, source scan, crop box,
output/master names, SHA-256, metadata, and restoration settings. Manifests
describe provenance; originals remain untouched.

The ZIP download, local watched folder, Immich, and Nextcloud all consume this
artifact set. Local-folder writes remain disabled outside local mode. Network
targets are explicit background jobs; credentials are request-scoped, never
logged or persisted. Immich uses its stable multipart asset upload endpoint.
Nextcloud uses authenticated WebDAV folder creation and file PUT.
