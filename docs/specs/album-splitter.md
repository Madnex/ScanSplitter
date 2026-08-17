# Album Splitter mode

## Purpose

Album Splitter digitizes the album page as the artifact. Mounted photographs,
handwriting, tape, page patina, and their relative arrangement stay together in
one output. Only the table, floor, scanner bed, or other surface around the
physical album is removed.

The mode is available in Quick mode, persistent Projects, the detect API, and
the batch CLI as `album-splitter`. It is a separate detector; changing its
behavior must not change the existing per-photo detectors.

## Detection contract

- Detection returns a rotatable rectangle for the outer album-page surface,
  not rectangles for mounted prints.
- Detection is model-free and operates on a bounded-resolution working image.
  The resulting geometry is scaled back to original-image coordinates.
- A page may be partially outside the camera frame. Sides that are clipped to
  the source boundary remain valid; visible sides are refined against long
  physical edges.
- Page candidates are inferred from large rectangular color surfaces using
  several deterministic Lab color clusterings. A contour-based fallback handles
  pages whose paper color is too fragmented.
- Final side refinement favors gradients that remain continuous along most of
  the leaf. This prevents high-contrast mounted-photo borders from winning over
  a pale or stained physical page edge.
- If an exterior page edge is too pale for gradient refinement, colors connected
  to the relevant camera-frame border provide a fallback boundary and a small
  tilt estimate. Material inward corrections are required, so this fallback
  cannot expand an inner leaf across an adjacent page or interleaf.
- If no credible page surface exists, detection returns no boxes. The normal
  review/editor flow remains the recovery path; it must not silently export the
  entire camera image.

## Page-layout policy

Every detection request carries `album_layout`:

- `auto` (default): select the strongest physical-page candidate inside the
  complete album assembly. It fuses that candidate's spine/outer-side edges
  with the assembly's reliable top/bottom edges. If the assembly is unusually
  wide (aspect ratio at least 1.75), split it into equal left/right pages.
- `single`: select one physical page even when a protective interleaf or the
  facing page is also visible. If no credible inner leaf exists, retain the
  complete detected surface as the editable fallback.
- `spread`: split the detected surface into ordered left/right page outputs.

The editor remains authoritative: users can resize, rotate, delete, or add boxes
after detection. Equal splitting is predictable and editable; a future
perspective-aware polygon editor may support non-central curved gutters.

## Crop and export behavior

- Photo-oriented edge cleanup is always disabled for Album Splitter outputs.
  It could otherwise remove pale page margins or handwriting close to an edge.
- Auto-rotation remains an explicit user/project setting.
- Quick-mode automatic names begin with `page_`; custom naming patterns remain
  authoritative.
- Persistent Projects store `album_layout` in project settings and apply Album
  Splitter during both initial and repeated detection.

## Known geometric boundary

The current editor and crop API use rotated rectangles. They correct in-plane
rotation but not camera perspective or page curvature. A camera held reasonably
parallel to the album gives the best facsimile. Perspective correction requires
a future four-corner/polygon box contract so manual edits, previews, project
storage, and exports all agree on the same geometry.
