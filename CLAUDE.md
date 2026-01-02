# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run web UI
uv run scansplitter

# Process files via CLI
uv run scansplitter process <files> -o ./output/

# Run with specific options
uv run scansplitter process scan.jpg --no-rotate --min-area 5 --max-area 70 --format jpg
```

## Architecture

ScanSplitter detects and extracts multiple photos from scanned images using OpenCV contour detection.

**Processing Pipeline** (`processor.py` orchestrates):
1. **Input** - Load image or extract pages from PDF (`pdf_handler.py`)
2. **Detection** - Grayscale → Gaussian blur → Adaptive threshold → Contour detection → Filter by area ratio (`detector.py`)
3. **Rotation** - Score each 90° rotation using Hough line detection, pick best alignment (`rotator.py`)
4. **Output** - Cropped, rotated images

**Key parameters:**
- `min_area_ratio` / `max_area_ratio` (default 2%-80%) - Contour area relative to total image; filters noise and full-page detections
- Detection uses `cv2.findContours()` with `RETR_EXTERNAL` to get outermost contours only

**Interfaces:**
- `ui.py` - Gradio web app with file upload, gallery preview, ZIP download
- `cli.py` - Subcommands: `ui` (launch web), `process` (batch CLI)
