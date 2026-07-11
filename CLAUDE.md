# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (includes dev group: pytest, ruff, httpx)
uv sync

# Lint and test (CI runs both on every push/PR)
uv run ruff check src tests
uv run pytest

# Run web UI (FastAPI + React with interactive bounding box editor)
uv run scansplitter api

# Process files via CLI
uv run scansplitter process <files> -o ./output/

# Run with specific options
uv run scansplitter process scan.jpg --no-rotate --min-area 5 --max-area 70 --format jpg

# Frontend development
cd frontend && npm install && npm run dev  # Dev server on :5173
cd frontend && npm run build               # Build to src/scansplitter/static/

# Build and publish to PyPI
cd frontend && npm run build               # Build frontend first
uv build                                   # Creates dist/*.whl and dist/*.tar.gz
uv publish                                 # Publish to PyPI (requires API token)
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
- `api.py` - FastAPI backend with REST endpoints for the React frontend
- `session.py` - Session management for temporary file storage (idle-based
  expiry) plus `sanitize_name()`, the mandatory sanitizer for every
  client-supplied name that reaches a filesystem or zip path
- `jobs.py` - Background job registry + thread pool; long operations run as
  jobs with progress/stage/cancellation (see `/api/jobs/*` endpoints);
  failed jobs preserve HTTPException status/detail as
  `error_status`/`error_detail`
- `confidence.py` - Pure scan-confidence heuristics (flags like
  `touches_edge`, `count_mismatch`) used to auto-approve or flag scans
- `projects.py` - Persistent project store under `~/.scansplitter/projects/`
  (`SCANSPLITTER_DATA_DIR` overrides); atomic project.json writes
- `metadata.py` - Pure project-metadata validation plus export-time EXIF GPS/date
  and Adobe-compatible XMP packet generation; project originals are never modified
- `models.py` - ML model downloads, SHA-256 pinned with atomic rename
- `cli.py` - Subcommands: `api` (web UI), `process` (batch CLI). Binding to
  a non-loopback host sets local mode off: endpoints that touch the host
  filesystem (`/api/select-directory`, `/api/export-local`) return 403

**Conventions:**
- Endpoints are sync `def` (FastAPI threadpool) because the work is
  CPU-bound OpenCV/ONNX; never introduce blocking work in an `async def`
- Every client-controlled name goes through `sanitize_name()`; local writes
  are contained with `resolve().is_relative_to(base)`
- GPS EXIF is stripped on export unless the request sets `include_gps`
- Project metadata is a partial-patch contract: omitted fields are preserved,
  explicit null clears scalars, and latitude/longitude must be set or cleared together

**Product direction:** see `docs/ROADMAP.md` (phases, principles, decisions)
and `docs/specs/` for binding feature specs. Keep spec files updated in the
same commit when an implementation deviates.

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
