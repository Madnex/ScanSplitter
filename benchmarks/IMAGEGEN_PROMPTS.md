# Image generation provenance

The source images were generated with the built-in OpenAI image tool on
2026-08-17. All prompts shared these constraints: photorealistic analog or
archival imagery, anonymous people only, no readable text, logos, watermarks,
or famous people. Scan sources were single-scene, full-bleed photographs with
explicit prohibitions against collages, montages, and contact sheets. Album
textures were straight-on, full-bleed page surfaces with no surrounding table.

Scan texture subjects, in order:

1. Mid-century family picnic in a sunny garden.
2. 1970s seaside holiday beside colorful beach huts.
3. Black-and-white family portrait outside a farmhouse.
4. 1980s indoor birthday table with direct-camera flash.
5. 1960s family holiday beside a European mountain lake.
6. High-key winter family scene with a sled.
7. Sepia 1950s snapshot of children with bicycles.
8. 1990s backyard barbecue with a family and dog.
9. Rainy European city street with two travelers.
10. Mid-century family sailing on a small wooden boat.

Album texture subjects, in order:

1. Cream 1950s page, mounted monochrome family prints and photo corners.
2. Matte black scrapbook, faded color snapshots and cream corners.
3. Pale blue 1970s page, four snapshots and transparent mounting strips.
4. Foxed tan leaf, two portraits, landscape print, old corners.
5. Olive-green leaf, five faded travel photos and decorative mounts.
6. Ivory wedding leaf, three formal monochrome groups and embossed paper.
7. Burgundy scrapbook, square 1960s snapshots, tape, dust, caption cards.
8. Yellowed children's leaf, irregular mounts, pencil marks, stains.
9. Charcoal page, two city photographs, portrait, black corners.
10. Rose-pink 1980s leaf, four color photos under glossy protective film.

## Authentic ScanSplitter v2 surface

On 2026-08-17, the built-in OpenAI image tool generated
`source_textures/blank-album-spread.png`. A private real-world scan was used
only as a reference for physical capture characteristics. The prompt explicitly
forbade reproducing its people, photographs, handwriting, identifiers, or exact
layout. The generated output contains no photographs.

Prompt summary: an empty mid-century cream-paper album spread photographed
directly overhead on a cool gray-blue surface, with a center binding seam,
curled page edges, foxing, paper waviness, gentle glare, soft shadows, and mild
perspective; no photographs, photo-like rectangles, people, readable text,
labels, logos, or watermark.

The ten previously generated scan photographs were recovered at high quality
for benchmark use into `source_textures/photos/`. The deterministic compositor
in `_build_authentic_scans.py` places them as mounted prints and separately
labels their inner photographic image areas.
