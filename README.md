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
- **Persistent projects** - Import large collections, review only uncertain scans, and continue across restarts
- **Archival workflow** - Add dates, places, captions, people, restoration settings, lossless masters, and manifests
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
git clone https://github.com/madnex/scansplitter
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
- JPEG or lossless PNG export

The web interface has two modes:

- **Quick** processes an ad-hoc set of scans and exports the current results.
- **Projects** keeps a named collection on disk, detects bulk uploads in the
  background, and tracks review, metadata, restoration, and delivery settings.

### Projects workflow

Projects are intended for larger collections that may take more than one
session to finish:

1. Open **Projects**, create a named project, and add images or PDFs. PDF pages
   become individual scans. Detection starts in the background.
2. ScanSplitter automatically approves clear detections and marks uncertain
   scans **CHECK**. Use **Start review** or open a scan from the grid.
3. In review, adjust the photo boxes when necessary and choose **Approve**.
   Press `Enter` to approve and advance, or use the arrow keys to move through
   the queue. **Re-detect** runs detection again for the current scan.
4. Add collection or per-scan metadata such as dates, places, captions, people,
   album/roll, and event. Front/back pairing links a photographed print's
   reverse side to its front; record any inscription manually in the caption.
5. Optionally enable non-destructive deskew, color/fade correction, or 2×
   upscale. **Compare** previews the first photo without
   changing the stored scan; each photo can override the project defaults.
6. Export approved photos as JPEG or lossless PNG. Projects can also create a
   PNG/TIFF master, organize files by metadata, include a JSON/CSV manifest, or
   deliver to a watched folder, Immich, or Nextcloud WebDAV.

#### Connect Immich

ScanSplitter only uploads approved JPEG or PNG access copies. It does not read,
modify, or delete assets already stored in Immich, so its API key needs only the
`asset.upload` permission:

1. Sign in to Immich as the user who should own the uploaded photos.
2. Open **Account Settings → API Keys** and create a key named, for example,
   `ScanSplitter`.
3. Choose custom/scoped permissions and enable only **`asset.upload`**. Do not
   grant `all`, asset deletion, or administrator permissions.
4. In ScanSplitter, open the project, choose **Deliver → Immich**, and enter:
   - **Immich server:** the public base URL, such as
     `https://photos.example.com`. A URL ending in `/api` also works.
   - **API key:** the key created above.
5. Choose **Deliver**. The credentials are used for that delivery only and are
   not saved in the project.

The uploaded photos belong to the Immich user who created the API key. If
delivery returns `401` or `403`, check that the key is valid and has
`asset.upload`. A reverse proxy must allow `POST` requests and the size of the
photos being uploaded to Immich's `/api/assets` endpoint.

Flags explain why a scan needs review. They can report that no photo was found,
a box touches a scan edge, a box has an unusual aspect ratio or size, boxes
overlap, or the detected photo count differs from most scans in the project.
Flags are warnings rather than hard errors: correct the boxes if needed, then
approve the scan. Only approved and automatically approved scans are exported.

Projects persist under `~/.scansplitter/projects/`. Set
`SCANSPLITTER_DATA_DIR` to use another data directory. Original project scans
remain untouched by metadata, restoration, and export operations. ScanSplitter
is designed as a local, single-user application and does not provide an
authentication layer for a publicly exposed server.

For implementation details, see the [roadmap](docs/ROADMAP.md) and the binding
[feature specifications](docs/specs/).

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
