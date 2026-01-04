# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run new web UI (FastAPI + React with interactive bounding box editor)
uv run scansplitter api

# Run legacy Gradio UI
uv run scansplitter ui

# Process files via CLI
uv run scansplitter process <files> -o ./output/

# Run with specific options
uv run scansplitter process scan.jpg --no-rotate --min-area 5 --max-area 70 --format jpg

# Frontend development
cd frontend && npm install && npm run dev  # Dev server on :5173
cd frontend && npm run build               # Build to src/scansplitter/static/
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
- `api.py` - FastAPI backend with REST endpoints for the new React frontend
- `session.py` - Session management for temporary file storage
- `ui.py` - Legacy Gradio web app (still available via `scansplitter ui`)
- `cli.py` - Subcommands: `api` (new UI), `ui` (legacy Gradio), `process` (batch CLI)

**Frontend** (`frontend/`):
- React + TypeScript + Vite
- Tailwind CSS for styling
- Fabric.js for interactive, rotatable bounding box editing
- Built output goes to `src/scansplitter/static/` and is served by FastAPI

**API Endpoints** (`/api/...`):
- `POST /upload` - Upload image/PDF, returns session ID
- `POST /detect` - Run detection, returns bounding boxes
- `POST /crop` - Crop with user-adjusted boxes
- `POST /export` - Download results as ZIP
- `GET /image/{session_id}/{filename}` - Serve uploaded images
