# Image detection benchmark

This fixed, private-data-free dataset contains ten ScanSplitter inputs and ten
Album Splitter inputs. Its photographic textures were created with the built-in
OpenAI image generation tool; geometry was composed deterministically so every
fixture has exact rotated-rectangle ground truth in `manifest.json`. The
ScanSplitter v2 fixtures model mounted photographs on captured album spreads,
not loose rectangles on a flat synthetic background.

Run both current algorithms and write `results/latest.md` plus JSON:

```bash
uv run benchmarks/evaluate.py
```

Useful comparisons:

```bash
uv run benchmarks/evaluate.py --suite scansplitter --scan-detector v3 --output benchmarks/results/v3.md
uv run benchmarks/evaluate.py --suite scansplitter --scan-detector v4 --output benchmarks/results/v4.md
uv run benchmarks/evaluate.py --suite scansplitter --scan-detector v5 --output benchmarks/results/v5.md
uv run benchmarks/evaluate.py --suite album --output benchmarks/results/album.md
```

For a visual, live comparison page, start the app with the deliberately opt-in
developer flag and open `/benchmark`:

```bash
SCANSPLITTER_BENCHMARK=1 uv run scansplitter api
```

To add an OpenRouter vision-model column to every ScanSplitter row, copy
`.env.example` to `.env`, add the key, and use the helper:

```bash
cp .env.example .env
./scripts/openrouter.py serve
```

For a machine-readable/Markdown OpenRouter-only score instead of the browser:

```bash
./scripts/openrouter.py report
```

The first run makes ten paid external API calls and uploads the ten ScanSplitter
fixtures to OpenRouter/model providers. Identical later runs use the local LLM
response cache; set `SCANSPLITTER_LLM_CACHE=0` when a genuinely fresh benchmark
is required. The Album Splitter rows remain local. Without
`OPENROUTER_API_KEY`, the benchmark continues to show only the local detector
versions.

Every fixture row shows the original, ground truth, and applicable live
detectors side by side (ScanSplitter v3/v4/v5/OpenRouter or Album Splitter). Without the
flag, both the page and its benchmark API return 404.

The evaluator uses one-to-one maximum-IoU matching and separates discovery from
crop accuracy. Detection F1 uses the conventional rotated-IoU threshold of
0.50. Strict F1 uses 0.85. The primary **box quality** metric is IoU-weighted
F1: assigned boxes contribute their actual overlap, while missing and extra
boxes contribute zero. A loose box can therefore pass detection F1 without
receiving a misleading perfect quality score. **Crop tightness** is the wanted
image area divided by detected crop area, so it exposes excess paper around a
photo. **Content coverage** reports how much of the wanted image was retained.
The overview also reports exact-count accuracy, runtime, and every case.
Commit named result files when a long-lived before/after comparison is useful;
`latest.*` is ignored because it is a local working result.

For ScanSplitter, ground truth is deliberately the inner photographic image
area. Paper borders, scalloped mounts, tape, corners, shadows, captions, and the
album page are outside the target. This matches the crop users expect from the
real application. Results from different manifest versions are not directly
comparable.

The cases deliberately include aged album spreads, wide and asymmetric paper
margins, tape, photo corners, scalloped edges, low contrast, glare, narrow
gutters, dark scrapbook pages, mixed print formats, binding and page edges, and
irregular layouts. Album Splitter retains its single leaves, forced spreads,
auto-detected spreads, dark pages, small pages, and portrait/landscape leaves.
Image generation provenance and prompts are in `IMAGEGEN_PROMPTS.md`.
