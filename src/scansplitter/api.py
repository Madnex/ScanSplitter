"""FastAPI backend for ScanSplitter."""

import base64
import io
import logging
import os
import subprocess
import sys
import uuid
import zipfile
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

import scansplitter

from .detector import (
    DetectedRegion,
    crop_rotated_region,
    detect_photos_u2net,
    detect_photos_v1,
    detect_photos_v2,
)
from .exif_handler import apply_exif_to_jpeg, create_exif_bytes, extract_exif
from .jobs import JobCancelled, registry, submit_job
from .models import get_model_statuses, start_model_download
from .pdf_handler import extract_pdf_page, get_pdf_page_count
from .projects import get_project_store
from .rotator import auto_rotate
from .session import Session, get_session_manager, sanitize_name

logger = logging.getLogger(__name__)

# --- Upload limits ---
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_PDF_PAGES = 200
ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".pdf"}
_UPLOAD_CHUNK_SIZE = 1024 * 1024

# Guard against decompression bombs: large scans are fine (300 MP allows
# A3 at 1200 DPI) but PIL will raise beyond 2x this value.
Image.MAX_IMAGE_PIXELS = 300_000_000

# Number of rendered PDF pages kept per session (they are re-rendered on miss)
_PAGE_CACHE_MAX_ENTRIES = 4

# Get the static directory path relative to this file
STATIC_DIR = Path(__file__).parent / "static"

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]


def _noop_progress(percent: int, stage: str) -> None:
    del percent, stage


def _never_cancelled() -> bool:
    return False


def _check_cancelled(is_cancelled: CancelCheck) -> None:
    if is_cancelled():
        raise JobCancelled


def _local_features_enabled() -> bool:
    """Whether host-filesystem features (dir picker, local export) are allowed.

    Enabled by default (ScanSplitter is a local desktop tool). The CLI sets
    SCANSPLITTER_LOCAL_MODE=0 when the server binds to a non-loopback host so
    remote clients cannot browse or write to the server's filesystem.
    """
    return os.environ.get("SCANSPLITTER_LOCAL_MODE", "1") != "0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Mount static files for serving the frontend if available."""
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
        logger.info("Serving frontend from %s", STATIC_DIR)
    else:
        logger.info("No frontend found at %s, running API only", STATIC_DIR)
    yield


app = FastAPI(title="ScanSplitter API", version=scansplitter.__version__, lifespan=lifespan)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---


class BoundingBox(BaseModel):
    """A rotatable bounding box."""

    id: str
    center_x: float
    center_y: float
    width: float
    height: float
    angle: float  # degrees


class UploadResponse(BaseModel):
    """Response from file upload."""

    session_id: str
    filename: str
    page_count: int
    image_width: int
    image_height: int


class DetectRequest(BaseModel):
    """Request for detection."""

    session_id: str
    page: int = 1
    min_area: float = 2.0  # percentage
    max_area: float = 80.0  # percentage
    # Phase 1: Enhanced detection options
    enhance_contrast: bool = True
    adaptive_morphology: bool = True
    min_solidity: float = 0.7
    max_aspect_ratio: float = 5.0
    min_extent: float = 0.4
    border_mode: str = "minAreaRect"  # "minAreaRect" or "convexHull"
    border_padding: float = 0.02
    # Detection algorithms
    detection_mode: str = "scansplitterv2"  # "scansplitterv1", "scansplitterv2", or "u2net"
    u2net_lite: bool = True  # Use lightweight model (faster) vs full (more accurate)


class DetectResponse(BaseModel):
    """Response from detection."""

    boxes: list[BoundingBox]
    image_url: str


class CropRequest(BaseModel):
    """Request for cropping with adjusted boxes."""

    session_id: str
    page: int = 1
    boxes: list[BoundingBox]
    auto_rotate: bool = True


class CroppedImage(BaseModel):
    """A cropped image result."""

    id: str
    data: str  # base64 encoded
    width: int
    height: int
    rotation_applied: int


class CropResponse(BaseModel):
    """Response from cropping."""

    images: list[CroppedImage]


class ImageData(BaseModel):
    """Image data for export."""

    id: str
    data: str  # base64 encoded
    name: str
    date_taken: str | None = None  # Per-image date in YYYY-MM-DD format


class ExportRequest(BaseModel):
    """Request for export."""

    session_id: str
    format: str = "jpeg"  # jpeg or png
    quality: int = 85
    names: dict[str, str] | None = None  # id -> custom name (legacy)
    images: list[ImageData] | None = None  # Direct image data with rotations applied
    include_gps: bool = False  # Copy GPS EXIF onto exports (privacy: off by default)


class ExportLocalRequest(BaseModel):
    """Request for local export."""

    session_id: str
    output_directory: str
    format: str = "jpeg"  # jpeg or png
    quality: int = 85
    names: dict[str, str] | None = None  # id -> custom name (legacy)
    images: list[ImageData] | None = None  # Direct image data with rotations applied
    overwrite: bool = False  # Whether to overwrite existing files
    include_gps: bool = False  # Copy GPS EXIF onto exports (privacy: off by default)


class SelectDirectoryRequest(BaseModel):
    """Request to open a native directory picker."""

    initial_directory: str | None = None


class SelectDirectoryResponse(BaseModel):
    """Response from the native directory picker."""

    directory: str | None = None


class ExifData(BaseModel):
    """EXIF metadata."""

    date_taken: str | None = None
    make: str | None = None
    model: str | None = None
    has_gps: bool = False


class ExifResponse(BaseModel):
    """Response with EXIF data."""

    exif: ExifData | None


class UpdateExifRequest(BaseModel):
    """Request to update EXIF data."""

    session_id: str
    date_taken: str | None = None  # Format: "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"


class ModelDownloadRequest(BaseModel):
    """Request to download an ML model in the background."""

    model: str  # "orientation", "u2net_lite", or "u2net_full"


class ProjectCreateRequest(BaseModel):
    """Request to create a persistent project."""

    name: str


class ProjectPatchRequest(BaseModel):
    """Partial update of a project's name and/or settings."""

    name: str | None = None
    settings: dict | None = None


class ScanPatchRequest(BaseModel):
    """Update a scan's boxes and/or review status."""

    boxes: list[dict] | None = None
    status: str | None = None


class ProjectExportRequest(BaseModel):
    """Request to export a project's approved scans (defaults from settings)."""

    format: str | None = None
    quality: int | None = None
    include_gps: bool | None = None


class ProjectMetadataPatch(BaseModel):
    """Partial archival metadata update; omitted fields are preserved."""

    date: str | None = None
    date_label: str | None = None
    date_precision: str | None = None
    place_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    caption: str | None = None
    people: list[str] | None = None
    event: str | None = None
    album: str | None = None


class ProjectMetadataBatchPatch(BaseModel):
    scan_ids: list[str] | None = None
    metadata: ProjectMetadataPatch


# --- Helper Functions ---


def get_session_or_404(session_id: str) -> Session:
    """Get session or raise 404."""
    session = get_session_manager().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _session_date_state(session: Session) -> tuple[str | None, bool]:
    """Return ``(date_taken, clear_date)`` overrides stored via /api/exif.

    ``date_taken`` is a user-set date to write, or ``None``. ``clear_date`` is
    True when the user explicitly cleared the date, meaning any date copied
    from the original EXIF must be dropped on export.
    """
    if not session.files:
        return None, False
    filename = next(iter(session.files.keys()))
    entry = session.exif_data.get(filename)
    if not entry:
        return None, False
    return entry.get("date_taken"), bool(entry.get("date_cleared"))


def load_page_image(session: Session, filename: str, page: int) -> Image.Image:
    """Load a specific page from an uploaded file."""
    file_info = session.files.get(filename)
    if file_info is None:
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    file_path = Path(file_info["path"])
    if not file_path.exists():
        raise HTTPException(status_code=410, detail="Session files no longer exist")

    if file_info.get("is_pdf"):
        page_count = int(file_info.get("page_count", 1))
        if page < 1 or page > page_count:
            raise HTTPException(status_code=400, detail=f"Invalid page number: {page}")

        # Render only the requested page; cache a few pages per session so
        # repeated detect/crop/preview calls don't re-render the PDF.
        cache_key = (filename, page)
        cached = session.page_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            image = extract_pdf_page(file_path, page, dpi=150)  # Lower DPI for preview
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        while len(session.page_cache) >= _PAGE_CACHE_MAX_ENTRIES:
            session.page_cache.pop(next(iter(session.page_cache)))
        session.page_cache[cache_key] = image
        return image
    else:
        # Load image directly
        return Image.open(file_path).convert("RGB")


def image_to_base64(image: Image.Image, format: str = "JPEG", quality: int = 85) -> str:
    """Convert PIL Image to base64 string."""
    buffer = io.BytesIO()
    if format.upper() == "JPEG":
        image.save(buffer, format="JPEG", quality=quality)
    else:
        image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def box_to_detected_region(box: BoundingBox, image: Image.Image) -> DetectedRegion:
    """Convert BoundingBox to DetectedRegion for cropping."""
    # Calculate axis-aligned bounding box from rotated rect
    import math

    import numpy as np

    cx, cy = box.center_x, box.center_y
    w, h = box.width, box.height
    angle_rad = math.radians(box.angle)

    # Get corners of rotated rectangle
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    corners = []
    for dx, dy in [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]:
        x = cx + dx * cos_a - dy * sin_a
        y = cy + dx * sin_a + dy * cos_a
        corners.append((x, y))

    corners = np.array(corners)
    x_min, y_min = corners.min(axis=0)
    x_max, y_max = corners.max(axis=0)

    return DetectedRegion(
        center=(cx, cy),
        size=(w, h),
        angle=box.angle,
        area=w * h,
        area_ratio=(w * h) / (image.width * image.height),
        x=int(max(0, x_min)),
        y=int(max(0, y_min)),
        width=int(min(image.width, x_max) - max(0, x_min)),
        height=int(min(image.height, y_max) - max(0, y_min)),
    )


def normalize_initial_directory(initial_directory: str | None) -> str | None:
    """Resolve an initial directory or fall back to its nearest existing parent."""
    if not initial_directory:
        return None

    candidate = Path(initial_directory).expanduser()
    if candidate.exists() and candidate.is_dir():
        return str(candidate.resolve())

    for parent in candidate.parents:
        if parent.exists() and parent.is_dir():
            return str(parent.resolve())

    return None


def choose_directory(initial_directory: str | None = None) -> str | None:
    """Open a native directory picker and return the selected absolute path."""
    resolved_initial_directory = normalize_initial_directory(initial_directory)

    if sys.platform == "darwin":
        default_location = resolved_initial_directory or str(Path.home())
        script = [
            'set selectedFolder to choose folder with prompt "Select output directory" default location POSIX file "'
            + default_location.replace('\\', '\\\\').replace('"', '\\"')
            + '"',
            "POSIX path of selectedFolder",
        ]
        args: list[str] = []
        for line in script:
            args.extend(["-e", line])

        result = subprocess.run(
            ["osascript", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "User canceled" in stderr:
                return None
            raise RuntimeError(f"Directory picker unavailable: {stderr or result.stdout.strip()}")

        selected = result.stdout.strip()
        return str(Path(selected).expanduser().resolve()) if selected else None

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        selected = filedialog.askdirectory(
            parent=root,
            title="Select output directory",
            initialdir=resolved_initial_directory or str(Path.home()),
            mustexist=True,
        )
        root.destroy()

        if not selected:
            return None

        return str(Path(selected).expanduser().resolve())
    except Exception as error:
        raise RuntimeError(f"Directory picker unavailable: {error}") from error


# --- API Endpoints ---


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/upload", response_model=UploadResponse)
def upload_file(file: UploadFile = File(...)):
    """Upload a file and create a session.

    Sync endpoint on purpose: FastAPI runs it in a worker thread so the
    streaming copy and image probing never block the event loop.
    """
    if file.filename is None:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate the extension against an allowlist before touching the content.
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type: {ext or 'no extension'}. "
                f"Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
            ),
        )

    # Create session
    session = get_session_manager().create_session()

    # Sanitize the client-supplied filename before using it on the filesystem.
    fallback_name = f"upload_{uuid.uuid4().hex[:8]}{ext}"
    safe_filename = sanitize_name(file.filename, default=fallback_name)
    file_path = session.directory / safe_filename

    try:
        # Stream to disk with a size cap (never buffer the whole file in RAM).
        size = 0
        with open(file_path, "wb") as out:
            while True:
                chunk = file.file.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
                    )
                out.write(chunk)

        # Determine page count and dimensions
        is_pdf_file = ext == ".pdf"
        if is_pdf_file:
            page_count = get_pdf_page_count(file_path)  # No rendering needed
            if page_count < 1:
                raise HTTPException(status_code=400, detail="PDF contains no pages")
            if page_count > MAX_PDF_PAGES:
                raise HTTPException(
                    status_code=400,
                    detail=f"PDF has too many pages ({page_count}, max {MAX_PDF_PAGES})",
                )
            # Render only the first page for dimensions and cache it for reuse.
            first_page = extract_pdf_page(file_path, 1, dpi=150)
            width, height = first_page.width, first_page.height
            session.page_cache[(safe_filename, 1)] = first_page
        else:
            page_count = 1
            with Image.open(file_path) as image:
                width, height = image.size

            # Extract EXIF from non-PDF files
            exif = extract_exif(file_path.read_bytes())
            if exif:
                session.exif_data[safe_filename] = exif
    except HTTPException:
        get_session_manager().delete_session(session.id)
        raise
    except Exception as e:
        # Corrupt/unreadable file (includes PIL decompression-bomb errors)
        get_session_manager().delete_session(session.id)
        logger.warning("Rejected upload %r: %s", safe_filename, e)
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}") from e

    # Store file info
    session.files[safe_filename] = {
        "path": str(file_path),
        "is_pdf": is_pdf_file,
        "page_count": page_count,
    }

    return UploadResponse(
        session_id=session.id,
        filename=safe_filename,
        page_count=page_count,
        image_width=width,
        image_height=height,
    )


@app.get("/api/image/{session_id}/{filename}")
def get_image(session_id: str, filename: str, page: int = 1):
    """Get an uploaded image or PDF page. Sync: runs in a worker thread."""
    session = get_session_or_404(session_id)
    image = load_page_image(session, filename, page)

    # Convert to JPEG for serving
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)

    return Response(content=buffer.getvalue(), media_type="image/jpeg")


@app.get("/api/models/status")
async def models_status():
    """Get the current status of downloadable models."""
    return get_model_statuses()


@app.post("/api/models/download")
async def models_download(request: ModelDownloadRequest):
    """Start downloading a model in the background (if missing)."""
    try:
        return start_model_download(request.model)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def run_detect(
    request: DetectRequest,
    progress_cb: ProgressCallback = _noop_progress,
    is_cancelled: CancelCheck = _never_cancelled,
) -> DetectResponse:
    """Run detection for both synchronous requests and background jobs."""
    session = get_session_or_404(request.session_id)

    # Get first file (we only support one at a time for now)
    if not session.files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    filename = list(session.files.keys())[0]
    progress_cb(5, "rendering page")
    _check_cancelled(is_cancelled)
    image = load_page_image(session, filename, request.page)
    progress_cb(20, "preprocessing")
    _check_cancelled(is_cancelled)

    detection_mode = request.detection_mode
    if detection_mode in ("classic", "ScanSplitterv2", "v2"):
        detection_mode = "scansplitterv2"
    elif detection_mode in ("ScanSplitterv1", "v1", "legacy"):
        detection_mode = "scansplitterv1"

    # Run detection based on mode
    if detection_mode == "u2net":
        # Use U2-Net deep learning detection
        progress_cb(35, "running model")
        regions = detect_photos_u2net(
            image,
            min_area_ratio=request.min_area / 100,
            max_area_ratio=request.max_area / 100,
            lite=request.u2net_lite,
        )
    elif detection_mode == "scansplitterv1":
        progress_cb(45, "detecting")
        regions = detect_photos_v1(
            image,
            min_area_ratio=request.min_area / 100,
            max_area_ratio=request.max_area / 100,
        )
    else:
        # Use ScanSplitterv2 contour-based detection with enhancements
        progress_cb(45, "detecting")
        regions = detect_photos_v2(
            image,
            min_area_ratio=request.min_area / 100,
            max_area_ratio=request.max_area / 100,
            enhance_contrast=request.enhance_contrast,
            adaptive_morphology=request.adaptive_morphology,
            min_solidity=request.min_solidity,
            max_aspect_ratio=request.max_aspect_ratio,
            min_extent=request.min_extent,
            border_mode=request.border_mode,  # type: ignore
            border_padding=request.border_padding,
        )

    _check_cancelled(is_cancelled)
    progress_cb(85, "scoring rotations")
    # Convert to BoundingBox format
    boxes = []
    for region in regions:
        boxes.append(
            BoundingBox(
                id=uuid.uuid4().hex[:8],
                center_x=region.center[0],
                center_y=region.center[1],
                width=region.size[0],
                height=region.size[1],
                angle=region.angle,
            )
        )

    # Build image URL
    image_url = f"/api/image/{request.session_id}/{filename}?page={request.page}"

    return DetectResponse(boxes=boxes, image_url=image_url)


@app.post("/api/detect", response_model=DetectResponse)
def detect_boxes(request: DetectRequest):
    """Detect bounding boxes in an image. Sync: runs in a worker thread."""
    return run_detect(request)


def run_crop(
    request: CropRequest,
    progress_cb: ProgressCallback = _noop_progress,
    is_cancelled: CancelCheck = _never_cancelled,
) -> CropResponse:
    """Crop images for both synchronous requests and background jobs."""
    import cv2
    import numpy as np

    session = get_session_or_404(request.session_id)

    if not session.files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    filename = list(session.files.keys())[0]
    progress_cb(5, "rendering page")
    image = load_page_image(session, filename, request.page)

    # Drop results from previous crop calls so legacy exports can't mix
    # stale crops with the current ones (and disk usage stays bounded).
    for old_path in session.cropped_images:
        old_path.unlink(missing_ok=True)
    session.cropped_images.clear()

    # Convert to OpenCV format
    cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    cropped_images = []
    total = len(request.boxes)
    for index, box in enumerate(request.boxes, 1):
        _check_cancelled(is_cancelled)
        progress_cb(10 + int(85 * (index - 1) / max(total, 1)), f"cropping image {index}/{total}")
        # Convert box to DetectedRegion
        region = box_to_detected_region(box, image)

        # Crop the region
        cropped_cv = crop_rotated_region(cv_image, region)

        # Convert back to PIL
        cropped_rgb = cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB)
        cropped_pil = Image.fromarray(cropped_rgb)

        # Auto-rotate if enabled
        rotation_applied = 0
        if request.auto_rotate:
            cropped_pil, rotation_applied = auto_rotate(cropped_pil)

        # Convert to base64
        data = image_to_base64(cropped_pil)

        cropped_images.append(
            CroppedImage(
                id=box.id,
                data=data,
                width=cropped_pil.width,
                height=cropped_pil.height,
                rotation_applied=rotation_applied,
            )
        )

        # Save to session for export (sanitize the client-supplied box id)
        safe_id = sanitize_name(box.id, default=uuid.uuid4().hex[:8], allow_dot=False)
        cropped_path = session.directory / f"cropped_{safe_id}.jpg"
        cropped_pil.save(cropped_path, "JPEG", quality=95)
        session.cropped_images.append(cropped_path)

    return CropResponse(images=cropped_images)


@app.post("/api/crop", response_model=CropResponse)
def crop_images(request: CropRequest):
    """Crop images using user-adjusted bounding boxes. Sync: worker thread."""
    return run_crop(request)


def run_export_zip(
    request: ExportRequest,
    progress_cb: ProgressCallback = _noop_progress,
    is_cancelled: CancelCheck = _never_cancelled,
) -> bytes:
    """Build an export ZIP for both synchronous requests and background jobs."""
    session = get_session_or_404(request.session_id)

    # Get original EXIF data for potential reuse
    original_exif_raw = None
    if request.format.lower() != "png" and session.exif_data:
        first_filename = list(session.files.keys())[0] if session.files else None
        if first_filename and first_filename in session.exif_data:
            original_exif_raw = session.exif_data[first_filename].get("_raw")

    # Use provided image data if available (includes client-side rotations)
    if request.images:
        zip_path = session.directory / "export.zip"
        ext = "png" if request.format.lower() == "png" else "jpg"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            total = len(request.images)
            for index, img_data in enumerate(request.images, 1):
                _check_cancelled(is_cancelled)
                progress_cb(int(90 * (index - 1) / max(total, 1)), f"encoding image {index}/{total}")
                # Decode base64 and re-encode in requested format
                img_bytes = base64.b64decode(img_data.data)
                img = Image.open(io.BytesIO(img_bytes))

                buffer = io.BytesIO()
                if request.format.lower() == "png":
                    img.save(buffer, "PNG", optimize=True)
                else:
                    img.save(buffer, "JPEG", quality=request.quality)
                    # Apply per-image EXIF if date is set
                    if img_data.date_taken:
                        exif_bytes = create_exif_bytes(
                            date_taken=img_data.date_taken,
                            original_exif=original_exif_raw,
                            include_gps=request.include_gps,
                        )
                        if exif_bytes:
                            buffer = io.BytesIO(apply_exif_to_jpeg(buffer.getvalue(), exif_bytes))

                # Sanitize client-supplied name to prevent zip-slip.
                filename = f"{sanitize_name(img_data.name, default='photo')}.{ext}"
                zf.writestr(filename, buffer.getvalue())

        return zip_path.read_bytes()

    # Legacy fallback: use cached images from session
    if not session.cropped_images:
        raise HTTPException(status_code=400, detail="No cropped images to export")

    # Build EXIF once for the legacy path. Honor any date set/cleared via
    # /api/exif and the GPS privacy flag.
    session_date, clear_date = _session_date_state(session)
    exif_bytes = create_exif_bytes(
        date_taken=session_date,
        original_exif=original_exif_raw,
        include_gps=request.include_gps,
        clear_date=clear_date,
    )

    zip_path = session.directory / "export.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        total = len(session.cropped_images)
        for i, img_path in enumerate(session.cropped_images, 1):
            _check_cancelled(is_cancelled)
            progress_cb(int(90 * (i - 1) / max(total, 1)), f"encoding image {i}/{total}")
            if img_path.exists():
                # Re-encode in requested format
                img = Image.open(img_path)

                buffer = io.BytesIO()
                if request.format.lower() == "png":
                    img.save(buffer, "PNG", optimize=True)
                    ext = "png"
                else:
                    img.save(buffer, "JPEG", quality=request.quality)
                    # Apply EXIF to JPEG if available
                    if exif_bytes:
                        buffer = io.BytesIO(apply_exif_to_jpeg(buffer.getvalue(), exif_bytes))
                    ext = "jpg"

                # Get custom name if provided, otherwise use default
                img_id = img_path.stem.replace("cropped_", "")
                if request.names and img_id in request.names:
                    # Sanitize client-supplied name to prevent zip-slip.
                    filename = f"{sanitize_name(request.names[img_id], default='photo')}.{ext}"
                else:
                    filename = f"photo_{i:03d}.{ext}"

                zf.writestr(filename, buffer.getvalue())

    return zip_path.read_bytes()


@app.post("/api/export")
def export_zip(request: ExportRequest):
    """Export cropped images as a ZIP file. Sync: runs in a worker thread."""
    return Response(
        content=run_export_zip(request),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="scansplitter_export.zip"'},
    )


def run_export_local(
    request: ExportLocalRequest,
    progress_cb: ProgressCallback = _noop_progress,
    is_cancelled: CancelCheck = _never_cancelled,
) -> dict:
    """Export locally for both synchronous requests and background jobs."""
    if not _local_features_enabled():
        raise HTTPException(
            status_code=403,
            detail="Local filesystem export is disabled when the server is not bound to localhost",
        )

    session = get_session_or_404(request.session_id)

    # Get original EXIF data for potential reuse
    original_exif_raw = None
    if request.format.lower() != "png" and session.exif_data:
        first_filename = list(session.files.keys())[0] if session.files else None
        if first_filename and first_filename in session.exif_data:
            original_exif_raw = session.exif_data[first_filename].get("_raw")

    # Validate output directory
    output_path = Path(request.output_directory).expanduser().resolve()

    if not output_path.exists():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {output_path}")
    if not output_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {output_path}")

    ext = "png" if request.format.lower() == "png" else "jpg"

    def safe_output_file(name: str) -> Path:
        """Resolve a sanitized output path and enforce containment in output_path."""
        filename = f"{sanitize_name(name, default='photo')}.{ext}"
        candidate = output_path / filename
        if not candidate.resolve().is_relative_to(output_path):
            raise HTTPException(status_code=400, detail=f"Invalid output filename: {name}")
        return candidate

    # Build list of filenames that would be created (sanitized to basenames)
    filenames: list[str] = []
    if request.images:
        filenames = [safe_output_file(img_data.name).name for img_data in request.images]
    elif session.cropped_images:
        for i, img_path in enumerate(session.cropped_images, 1):
            if img_path.exists():
                img_id = img_path.stem.replace("cropped_", "")
                if request.names and img_id in request.names:
                    filenames.append(safe_output_file(request.names[img_id]).name)
                else:
                    filenames.append(f"photo_{i:03d}.{ext}")

    # Check for existing files if overwrite is not enabled
    if not request.overwrite:
        existing_files = [f for f in filenames if (output_path / f).exists()]
        if existing_files:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Files already exist",
                    "existing_files": existing_files,
                    "count": len(existing_files),
                },
            )

    exported_files = []

    try:
        # Use provided image data if available (includes client-side rotations)
        if request.images:
            total = len(request.images)
            for index, img_data in enumerate(request.images, 1):
                _check_cancelled(is_cancelled)
                progress_cb(int(90 * (index - 1) / max(total, 1)), f"encoding image {index}/{total}")
                # Decode base64 and re-encode in requested format
                img_bytes = base64.b64decode(img_data.data)
                img = Image.open(io.BytesIO(img_bytes))

                output_file = safe_output_file(img_data.name)

                if request.format.lower() == "png":
                    img.save(output_file, "PNG", optimize=True)
                else:
                    # Save to buffer first, apply per-image EXIF if date is set, then write
                    buffer = io.BytesIO()
                    img.save(buffer, "JPEG", quality=request.quality)
                    output_bytes = buffer.getvalue()
                    if img_data.date_taken:
                        exif_bytes = create_exif_bytes(
                            date_taken=img_data.date_taken,
                            original_exif=original_exif_raw,
                            include_gps=request.include_gps,
                        )
                        if exif_bytes:
                            output_bytes = apply_exif_to_jpeg(output_bytes, exif_bytes)
                    output_file.write_bytes(output_bytes)

                exported_files.append(str(output_file))
        else:
            # Legacy fallback: use cached images from session
            if not session.cropped_images:
                raise HTTPException(status_code=400, detail="No cropped images to export")

            # Build EXIF once for the legacy path. Honor any date set/cleared
            # via /api/exif and the GPS privacy flag.
            session_date, clear_date = _session_date_state(session)
            exif_bytes = create_exif_bytes(
                date_taken=session_date,
                original_exif=original_exif_raw,
                include_gps=request.include_gps,
                clear_date=clear_date,
            )

            total = len(session.cropped_images)
            for i, img_path in enumerate(session.cropped_images, 1):
                _check_cancelled(is_cancelled)
                progress_cb(int(90 * (i - 1) / max(total, 1)), f"encoding image {i}/{total}")
                if img_path.exists():
                    img = Image.open(img_path)

                    img_id = img_path.stem.replace("cropped_", "")
                    if request.names and img_id in request.names:
                        output_file = safe_output_file(request.names[img_id])
                    else:
                        output_file = output_path / f"photo_{i:03d}.{ext}"

                    if request.format.lower() == "png":
                        img.save(output_file, "PNG", optimize=True)
                    else:
                        # Save to buffer first, apply EXIF, then write to file
                        buffer = io.BytesIO()
                        img.save(buffer, "JPEG", quality=request.quality)
                        output_bytes = buffer.getvalue()
                        if exif_bytes:
                            output_bytes = apply_exif_to_jpeg(output_bytes, exif_bytes)
                        output_file.write_bytes(output_bytes)

                    exported_files.append(str(output_file))

    except HTTPException:
        raise
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied writing to: {output_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}") from e

    return {"status": "success", "files": exported_files, "count": len(exported_files)}


@app.post("/api/export-local")
def export_local(request: ExportLocalRequest):
    """Export cropped images to a local directory. Sync: worker thread."""
    return run_export_local(request)


def _job_payload(job) -> dict:
    """Return the stable public polling representation of a job."""
    return {
        "job_id": job.job_id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "result": job.result,
        "error": job.error,
        "error_status": job.error_status,
        "error_detail": job.error_detail,
    }


@app.post("/api/jobs/detect", status_code=202)
def create_detect_job(request: DetectRequest):
    get_session_or_404(request.session_id)

    def worker(progress: ProgressCallback, cancelled: CancelCheck) -> dict:
        response = run_detect(request, progress, cancelled)
        return {"boxes": [box.model_dump() for box in response.boxes]}

    return {"job_id": submit_job("detect", request.session_id, worker).job_id}


@app.post("/api/jobs/crop", status_code=202)
def create_crop_job(request: CropRequest):
    get_session_or_404(request.session_id)

    def worker(progress: ProgressCallback, cancelled: CancelCheck) -> dict:
        response = run_crop(request, progress, cancelled)
        return {"images": [image.model_dump() for image in response.images]}

    return {"job_id": submit_job("crop", request.session_id, worker).job_id}


@app.post("/api/jobs/export", status_code=202)
def create_export_job(request: ExportRequest):
    get_session_or_404(request.session_id)

    def worker(progress: ProgressCallback, cancelled: CancelCheck) -> dict:
        data = run_export_zip(request, progress, cancelled)
        return {"__download_bytes": data}

    job = submit_job("export", request.session_id, worker)
    return {"job_id": job.job_id}


@app.post("/api/jobs/export-local", status_code=202)
def create_export_local_job(request: ExportLocalRequest):
    if not _local_features_enabled():
        raise HTTPException(
            status_code=403,
            detail="Local filesystem export is disabled when the server is not bound to localhost",
        )
    get_session_or_404(request.session_id)

    def worker(progress: ProgressCallback, cancelled: CancelCheck) -> dict:
        response = run_export_local(request, progress, cancelled)
        return {"files": response["files"], "count": response["count"]}

    return {"job_id": submit_job("export-local", request.session_id, worker).job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_payload(job)


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str):
    job = registry.get(job_id)
    if (
        job is None
        or job.kind != "export"
        or job.status != "succeeded"
        or job.download_bytes is None
    ):
        raise HTTPException(status_code=404, detail="Job download not ready or expired")
    return Response(
        content=job.download_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="scansplitter_export.zip"'},
    )


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in {"succeeded", "failed", "cancelled"}:
        return {"status": "cancelled" if job.status == "cancelled" else "already done"}
    job.cancel_flag.set()
    if job.status == "queued":
        registry.update(job_id, status="cancelled", stage="cancelled")
        return {"status": "cancelled"}
    return {"status": "cancelling"}


@app.post("/api/select-directory", response_model=SelectDirectoryResponse)
def select_directory(request: SelectDirectoryRequest):
    """Open a native directory picker on the host machine. Sync: worker thread."""
    if not _local_features_enabled():
        raise HTTPException(
            status_code=403,
            detail="Directory picker is disabled when the server is not bound to localhost",
        )

    try:
        directory = choose_directory(request.initial_directory)
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return SelectDirectoryResponse(directory=directory)


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its files."""
    success = get_session_manager().delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


@app.get("/api/exif/{session_id}", response_model=ExifResponse)
async def get_exif(session_id: str):
    """Get EXIF data for a session's uploaded file."""
    session = get_session_or_404(session_id)

    if not session.files:
        return ExifResponse(exif=None)

    filename = list(session.files.keys())[0]
    exif = session.exif_data.get(filename)

    if not exif:
        return ExifResponse(exif=None)

    return ExifResponse(
        exif=ExifData(
            date_taken=exif.get("date_taken"),
            make=exif.get("make"),
            model=exif.get("model"),
            has_gps=exif.get("has_gps", False),
        )
    )


@app.post("/api/exif")
async def update_exif(request: UpdateExifRequest):
    """Update EXIF date for a session."""
    session = get_session_or_404(request.session_id)

    if not session.files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    filename = list(session.files.keys())[0]

    if filename not in session.exif_data:
        session.exif_data[filename] = {}

    entry = session.exif_data[filename]

    # Distinguish an explicit JSON `null` (clear the date) from an omitted
    # field (keep the current value) using pydantic's set-fields tracking.
    date_provided = "date_taken" in request.model_fields_set

    if request.date_taken:
        entry["date_taken"] = request.date_taken
        entry["date_modified"] = True
        entry["date_cleared"] = False
    elif date_provided:
        # Explicit null / empty -> clear so exports write no DateTimeOriginal,
        # even when the original EXIF is being copied.
        entry.pop("date_taken", None)
        entry["date_modified"] = True
        entry["date_cleared"] = True
    # Field omitted entirely: leave existing date state untouched.

    return {"status": "ok"}


# --- Persistent project endpoints ---


@app.get("/api/projects")
def list_projects():
    """List all persistent projects with per-status counts."""
    return {"projects": get_project_store().list_projects()}


@app.post("/api/projects")
def create_project(request: ProjectCreateRequest):
    """Create a new project. Returns the full project JSON."""
    return get_project_store().create_project(request.name)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    """Return a project's full JSON (scans included)."""
    return get_project_store().get_project(pid)


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, request: ProjectPatchRequest):
    """Update a project's name and/or settings (partial)."""
    return get_project_store().update_project(pid, name=request.name, settings=request.settings)


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    """Delete a project and all of its scans."""
    get_project_store().delete_project(pid)
    return {"status": "deleted"}


@app.post("/api/projects/{pid}/scans")
def add_project_scans(pid: str, files: list[UploadFile] = File(...), detect: bool = True):
    """Upload one or more scans (PDFs expand to one scan per page).

    Sync endpoint on purpose: FastAPI runs it in a worker thread so the
    streaming reads and image decoding never block the event loop.
    """
    store = get_project_store()
    store.get_project(pid)  # validate id / existence before reading uploads

    uploaded: list[tuple[str, bytes]] = []
    for upload in files:
        if upload.filename is None:
            raise HTTPException(status_code=400, detail="No filename provided")
        ext = Path(upload.filename).suffix.lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type: {ext or 'no extension'}. "
                    f"Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
                ),
            )

        size = 0
        chunks: list[bytes] = []
        while True:
            chunk = upload.file.read(_UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
                )
            chunks.append(chunk)
        uploaded.append((upload.filename, b"".join(chunks)))

    scans = store.add_scans(pid, uploaded)

    jobs = []
    if detect:
        for scan in scans:
            job_id = store.submit_detect_job(pid, scan["id"])
            scan["status"] = "detecting"
            jobs.append({"scan_id": scan["id"], "job_id": job_id})

    return {"scans": scans, "jobs": jobs}


@app.get("/api/projects/{pid}/scans/{sid}/image")
def get_project_scan_image(pid: str, sid: str, thumb: bool = False):
    """Serve a stored scan image (or its cached 320px thumbnail)."""
    payload, media_type = get_project_store().scan_image_bytes(pid, sid, thumb=thumb)
    return Response(content=payload, media_type=media_type)


@app.patch("/api/projects/{pid}/scans/{sid}")
def patch_project_scan(pid: str, sid: str, request: ScanPatchRequest):
    """Update a scan's boxes (re-runs confidence) and/or review status."""
    return get_project_store().update_scan(
        pid, sid, boxes=request.boxes, status=request.status
    )


@app.patch("/api/projects/{pid}/scans/{sid}/metadata")
def patch_project_scan_metadata(pid: str, sid: str, request: ProjectMetadataPatch):
    """Partially update archival metadata for one scan."""
    patch = request.model_dump(exclude_unset=True)
    return get_project_store().update_metadata(pid, [sid], patch)[0]


@app.patch("/api/projects/{pid}/metadata")
def patch_project_metadata(pid: str, request: ProjectMetadataBatchPatch):
    """Atomically apply archival metadata to selected scans or the whole project."""
    patch = request.metadata.model_dump(exclude_unset=True)
    scans = get_project_store().update_metadata(pid, request.scan_ids, patch)
    return {"scans": scans}


@app.delete("/api/projects/{pid}/scans/{sid}")
def delete_project_scan(pid: str, sid: str):
    """Delete a single scan and its on-disk artifacts."""
    get_project_store().delete_scan(pid, sid)
    return {"status": "deleted"}


@app.post("/api/projects/{pid}/scans/{sid}/detect", status_code=202)
def redetect_project_scan(pid: str, sid: str):
    """Re-run detection for a single scan (result persisted into the project)."""
    store = get_project_store()
    store.get_scan(pid, sid)  # validate before queueing
    return {"job_id": store.submit_detect_job(pid, sid)}


@app.post("/api/projects/{pid}/detect-pending", status_code=202)
def detect_pending_scans(pid: str):
    """Queue detection for every pending or failed scan in the project."""
    store = get_project_store()
    store.get_project(pid)
    return {"jobs": store.submit_detect_pending(pid)}


@app.post("/api/projects/{pid}/export", status_code=202)
def export_project(pid: str, request: ProjectExportRequest):
    """Crop and zip every approved + auto-approved scan as a background job."""
    store = get_project_store()
    store.get_project(pid)
    job_id = store.submit_export_job(
        pid, fmt=request.format, quality=request.quality, include_gps=request.include_gps
    )
    return {"job_id": job_id}


def create_app() -> FastAPI:
    """Create the FastAPI app."""
    return app
