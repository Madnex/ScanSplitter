# ScanSplitter

Automatically detect, split, and rotate multiple photos from scanned images.

Drop a scan containing multiple photos and get individual, correctly-oriented images back.

## Features

- **Auto-detection** - Finds multiple photos in a single scan using contour detection
- **Auto-rotation** - Detects and corrects 90°/180°/270° rotations
- **PDF support** - Extract and process pages from PDF files
- **Web UI** - Drag & drop interface with preview and ZIP download
- **CLI** - Batch process files from the command line

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13+.

```bash
git clone <repo-url>
cd ScanSplitter
uv sync
```

## Usage

### Web Interface

```bash
uv run scansplitter
```

Opens a browser with drag & drop upload, gallery preview, and ZIP download.

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
5. **Rotation Detection** - Score each 90° rotation using Hough line detection, pick best alignment
