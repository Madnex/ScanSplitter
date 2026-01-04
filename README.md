<p align="center">
  <img src="frontend/public/logo.png" alt="ScanSplitter Logo" width="200">
</p>

<p align="center">
  <a href="https://pypi.org/project/scansplitter/"><img alt="PyPI" src="https://img.shields.io/pypi/v/scansplitter"></a>
  <a href="https://pypi.org/project/scansplitter/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/scansplitter"></a>
  <a href="LICENSE"><img alt="License: GPLv3" src="https://img.shields.io/badge/License-GPLv3-blue.svg"></a>
</p>

# ScanSplitter

Automatically detect, split, and rotate multiple photos from scanned images.

Drop a scan containing multiple photos and get individual, correctly-oriented images back.

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

- **Auto-detection** - Finds multiple photos in a single scan using contour detection
- **Interactive editing** - Adjust, rotate, and resize bounding boxes before cropping
- **Auto-rotation** - Detects and corrects 90°/180°/270° rotations
- **PDF support** - Extract and process pages from PDF files
- **Web UI** - Modern React interface with Fabric.js canvas editor
- **CLI** - Batch process files from the command line

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
| `--format` | Output format: `png` or `jpg` (default: png) |

## How It Works

1. **Preprocessing** - Convert to grayscale, apply Gaussian blur
2. **Thresholding** - Adaptive binary threshold to separate photos from background
3. **Contour Detection** - Find distinct regions using OpenCV
4. **Filtering** - Keep regions between min/max area thresholds
5. **Interactive Adjustment** - User can modify detected boxes in the web UI
6. **Rotation Detection** - Score each 90° rotation using Hough line detection
7. **Cropping** - Extract photos using adjusted bounding boxes

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
