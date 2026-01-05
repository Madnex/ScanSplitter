<p align="center">
  <img src="https://raw.githubusercontent.com/madnex/scansplitter/main/frontend/public/logo.png" alt="ScanSplitter Logo" width="200">
</p>

<h1 align="center">
  <span>Scan</span><span style="color: #6b7280;">Splitter</span>
</h1>

<p align="center">
  <a href="https://pypi.org/project/scansplitter/"><img alt="PyPI" src="https://img.shields.io/pypi/v/scansplitter"></a>
  <a href="https://pypi.org/project/scansplitter/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/scansplitter"></a>
  <a href="LICENSE"><img alt="License: GPLv3" src="https://img.shields.io/badge/License-GPLv3-blue.svg"></a>
</p>

Automatically detect, split, and rotate multiple photos from scanned images.

Drop a scan containing multiple photos and get individual, correctly-oriented images back.

<p align="center">
  <img src="https://raw.githubusercontent.com/madnex/scansplitter/main/frontend/public/screenshot.png" alt="ScanSplitter Screenshot" width="800">
</p>

## Quick Start

**One-time setup** - Install [uv](https://docs.astral.sh/uv/):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Run ScanSplitter** (no clone needed):
```bash
uvx scansplitter api
```

Opens at http://localhost:8000 - drag & drop your scans and export cropped photos.
If port 8000 is already in use, pick another:
```bash
uvx scansplitter api --port 8001
```

## Features

- **Multiple detection modes** - Choose between ScanSplitterv1, ScanSplitterv2 (default), and AI (U2-Net)
- **Interactive editing** - Adjust, rotate, and resize bounding boxes before cropping
- **Auto-rotation** - Detects and corrects 90°/180°/270° rotations
- **PDF support** - Extract and process pages from PDF files
- **Web UI** - Modern React interface with Fabric.js canvas editor
- **CLI** - Batch process files from the command line

## Detection Modes & Models

### Photo detection (splitter)

- **ScanSplitterv2 (default)**: An improved contour-based detector. It applies contrast enhancement (CLAHE), adaptive thresholding, adaptive morphology (kernel scales with resolution), and contour quality filtering (solidity/aspect/extent). It can also use convex-hull borders for irregular edges.
- **ScanSplitterv1**: The first contour-based detector used with adaptive threshold + fixed morphology + `minAreaRect` filtering. It’s simpler and can be useful as a fallback if v2 behaves unexpectedly on a specific scan.
- **AI (U2-Net)**: A deep-learning salient-object model (ONNX) that produces a mask; ScanSplitter then extracts regions from that mask. It’s best for difficult scans (busy backgrounds, low contrast), but requires downloading a model on first use. Might be less accurate for multiple photos at once.

### Auto-rotation model

- **Orientation model**: An EfficientNetV2-based ONNX classifier that predicts the correct 0°/90°/180°/270° rotation for each cropped photo. ScanSplitter may fall back to classic heuristics if the model can’t be loaded.

### Model downloads

Some modes require downloading models on first use (U2-Net (5Mb / 176MB) and the orientation model (80MB)). The web UI shows download progress while this is happening.

## Installation Options

### Option 1: Run directly with uvx (recommended)

No installation needed - just run:
```bash
uvx scansplitter api
```

### Option 2: Install with pipx

```bash
pipx install scansplitter
scansplitter api
```

### Option 3: Install from source

```bash
git clone https://github.com/janklan/scansplitter
cd scansplitter
uv sync
uv run scansplitter api
```

## Usage

### Web Interface

```bash
scansplitter api
# or: uvx scansplitter api
```

Opens at http://localhost:8000 with:
- Drag & drop file upload (images and PDFs)
- Interactive bounding box editor (drag, resize, rotate)
- Multi-file support with tabs
- PDF page navigation
- ZIP export

### Command Line

```bash
# Process a scanned image
uv run scansplitter process scan.jpg -o ./output/

# Process a PDF
uv run scansplitter process document.pdf -o ./output/

# Multiple files
uv run scansplitter process scan1.jpg scan2.png -o ./output/

# Options
uv run scansplitter process scan.jpg \
  --no-rotate \
  --min-area 5 \
  --max-area 70 \
  --detection-mode scansplitterv2 \
  --format jpg \
  -o ./output/
```

**CLI Options:**

| Option | Description |
| ------ | ----------- |
| `-o, --output` | Output directory (default: `./output`) |
| `--no-rotate` | Disable auto-rotation |
| `--min-area` | Minimum photo size as % of scan (default: 2) |
| `--max-area` | Maximum photo size as % of scan (default: 80) |
| `--detection-mode` | `scansplitterv2` (default), `scansplitterv1` (legacy), or `u2net` (deep learning); `classic` is an alias for `scansplitterv2` |
| `--u2net-full` | Use full U2-Net model instead of lite (slower, more accurate) |
| `--format` | Output format: `png` or `jpg` (default: png) |

## How It Works

1. **Photo detection** - Runs the selected detection mode (ScanSplitterv1 / ScanSplitterv2 / AI (U2-Net)) to produce rotatable bounding boxes.
2. **Interactive adjustment** - You can refine boxes in the web UI before cropping.
3. **Cropping** - Extracts rotated regions using the adjusted boxes.
4. **Auto-rotation (optional)** - Uses the orientation model (with fallbacks) to fix 90°/180°/270° rotations.

## Credits

ScanSplitter depends on excellent open models and upstream work:

- **U²-Net (salient object detection)** by Xuebin Qin et al. — paper: https://arxiv.org/abs/2005.09007, code: https://github.com/xuebinqin/U-2-Net
- **U2-Net ONNX weights** are downloaded from `rembg` releases by Daniel Gatis (with a ScanSplitter backup mirror) — https://github.com/danielgatis/rembg
- **Orientation model (EfficientNetV2)** is downloaded from Duarte Barbosa’s deep image orientation detection project (with a ScanSplitter backup mirror) — https://github.com/duartebarbosadev/deep-image-orientation-detection

## Development

### Frontend Development

```bash
# Start API server
uv run scansplitter api --reload

# In another terminal, start frontend dev server
cd frontend
npm install
npm run dev
```

Frontend runs on http://localhost:5173 with hot reload, proxying API requests to :8000.

### Build Frontend

```bash
cd frontend
npm run build
```

Builds to `src/scansplitter/static/`, which FastAPI serves automatically.
