"""FastAPI backend for ScanSplitter."""

import base64
import io
import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from .detector import (
    DetectedRegion,
    crop_rotated_region,
    detect_photos_u2net,
    detect_photos_v1,
    detect_photos_v2,
)
from .exif_handler import apply_exif_to_jpeg, create_exif_bytes, extract_exif
from .pdf_handler import extract_images_from_pdf, is_pdf
from .rotator import auto_rotate
from .session import Session, get_session_manager
from .models import get_model_statuses, start_model_download

app = FastAPI(title="ScanSplitter API", version="0.1.0")

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


class ExportLocalRequest(BaseModel):
    """Request for local export."""

    session_id: str
    output_directory: str
    format: str = "jpeg"  # jpeg or png
    quality: int = 85
    names: dict[str, str] | None = None  # id -> custom name (legacy)
    images: list[ImageData] | None = None  # Direct image data with rotations applied
    overwrite: bool = False  # Whether to overwrite existing files


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


# --- Helper Functions ---


def get_session_or_404(session_id: str) -> Session:
    """Get session or raise 404."""
    session = get_session_manager().get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def load_page_image(session: Session, filename: str, page: int) -> Image.Image:
    """Load a specific page from an uploaded file."""
    file_info = session.files.get(filename)
    if file_info is None:
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    file_path = Path(file_info["path"])

    if file_info.get("is_pdf"):
        # Extract specific page from PDF
        images = extract_images_from_pdf(file_path, dpi=150)  # Lower DPI for preview
        if page < 1 or page > len(images):
            raise HTTPException(status_code=400, detail=f"Invalid page number: {page}")
        return images[page - 1]
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


# --- API Endpoints ---


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/api/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """Upload a file and create a session."""
    if file.filename is None:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Create session
    session = get_session_manager().create_session()

    # Save file
    file_path = session.directory / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    # Determine page count and dimensions
    is_pdf_file = is_pdf(file_path)
    if is_pdf_file:
        images = extract_images_from_pdf(file_path, dpi=72)  # Low DPI just for count
        page_count = len(images)
        # Get dimensions from first page at full res
        first_page = extract_images_from_pdf(file_path, dpi=150)[0]
        width, height = first_page.width, first_page.height
    else:
        page_count = 1
        image = Image.open(file_path)
        width, height = image.size
        image.close()

        # Extract EXIF from non-PDF files
        exif = extract_exif(content)
        if exif:
            session.exif_data[file.filename] = exif

    # Store file info
    session.files[file.filename] = {
        "path": str(file_path),
        "is_pdf": is_pdf_file,
        "page_count": page_count,
    }

    return UploadResponse(
        session_id=session.id,
        filename=file.filename,
        page_count=page_count,
        image_width=width,
        image_height=height,
    )


@app.get("/api/image/{session_id}/{filename}")
async def get_image(session_id: str, filename: str, page: int = 1):
    """Get an uploaded image or PDF page."""
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


@app.post("/api/detect", response_model=DetectResponse)
async def detect_boxes(request: DetectRequest):
    """Detect bounding boxes in an image."""
    session = get_session_or_404(request.session_id)

    # Get first file (we only support one at a time for now)
    if not session.files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    filename = list(session.files.keys())[0]
    image = load_page_image(session, filename, request.page)

    detection_mode = request.detection_mode
    if detection_mode in ("classic", "ScanSplitterv2", "v2"):
        detection_mode = "scansplitterv2"
    elif detection_mode in ("ScanSplitterv1", "v1", "legacy"):
        detection_mode = "scansplitterv1"

    # Run detection based on mode
    if detection_mode == "u2net":
        # Use U2-Net deep learning detection
        regions = detect_photos_u2net(
            image,
            min_area_ratio=request.min_area / 100,
            max_area_ratio=request.max_area / 100,
            lite=request.u2net_lite,
        )
    elif detection_mode == "scansplitterv1":
        regions = detect_photos_v1(
            image,
            min_area_ratio=request.min_area / 100,
            max_area_ratio=request.max_area / 100,
        )
    else:
        # Use ScanSplitterv2 contour-based detection with enhancements
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


@app.post("/api/crop", response_model=CropResponse)
async def crop_images(request: CropRequest):
    """Crop images using user-adjusted bounding boxes."""
    import cv2
    import numpy as np

    session = get_session_or_404(request.session_id)

    if not session.files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    filename = list(session.files.keys())[0]
    image = load_page_image(session, filename, request.page)

    # Convert to OpenCV format
    cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    cropped_images = []
    for box in request.boxes:
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

        # Save to session for export
        cropped_path = session.directory / f"cropped_{box.id}.jpg"
        cropped_pil.save(cropped_path, "JPEG", quality=95)
        session.cropped_images.append(cropped_path)

    return CropResponse(images=cropped_images)


@app.post("/api/export")
async def export_zip(request: ExportRequest):
    """Export cropped images as a ZIP file."""
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
            for img_data in request.images:
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
                        )
                        if exif_bytes:
                            buffer = io.BytesIO(apply_exif_to_jpeg(buffer.getvalue(), exif_bytes))

                filename = f"{img_data.name}.{ext}"
                zf.writestr(filename, buffer.getvalue())

        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename="scansplitter_export.zip",
        )

    # Legacy fallback: use cached images from session
    if not session.cropped_images:
        raise HTTPException(status_code=400, detail="No cropped images to export")

    zip_path = session.directory / "export.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, img_path in enumerate(session.cropped_images, 1):
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
                    filename = f"{request.names[img_id]}.{ext}"
                else:
                    filename = f"photo_{i:03d}.{ext}"

                zf.writestr(filename, buffer.getvalue())

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="scansplitter_export.zip",
    )


@app.post("/api/export-local")
async def export_local(request: ExportLocalRequest):
    """Export cropped images to a local directory."""
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

    # Build list of filenames that would be created
    filenames: list[str] = []
    if request.images:
        filenames = [f"{img_data.name}.{ext}" for img_data in request.images]
    elif session.cropped_images:
        for i, img_path in enumerate(session.cropped_images, 1):
            if img_path.exists():
                img_id = img_path.stem.replace("cropped_", "")
                if request.names and img_id in request.names:
                    filenames.append(f"{request.names[img_id]}.{ext}")
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
            for img_data in request.images:
                # Decode base64 and re-encode in requested format
                img_bytes = base64.b64decode(img_data.data)
                img = Image.open(io.BytesIO(img_bytes))

                filename = f"{img_data.name}.{ext}"
                output_file = output_path / filename

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
                        )
                        if exif_bytes:
                            output_bytes = apply_exif_to_jpeg(output_bytes, exif_bytes)
                    output_file.write_bytes(output_bytes)

                exported_files.append(str(output_file))
        else:
            # Legacy fallback: use cached images from session
            if not session.cropped_images:
                raise HTTPException(status_code=400, detail="No cropped images to export")

            for i, img_path in enumerate(session.cropped_images, 1):
                if img_path.exists():
                    img = Image.open(img_path)

                    img_id = img_path.stem.replace("cropped_", "")
                    if request.names and img_id in request.names:
                        filename = f"{request.names[img_id]}.{ext}"
                    else:
                        filename = f"photo_{i:03d}.{ext}"

                    output_file = output_path / filename

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

    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied writing to: {output_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

    return {"status": "success", "files": exported_files, "count": len(exported_files)}


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

    if request.date_taken:
        session.exif_data[filename]["date_taken"] = request.date_taken
        session.exif_data[filename]["date_modified"] = True

    return {"status": "ok"}


# --- Static Files (for production) ---

# Get the static directory path relative to this file
STATIC_DIR = Path(__file__).parent / "static"


@app.on_event("startup")
async def mount_static_files():
    """Mount static files for serving the frontend if available."""
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
        print(f"Serving frontend from {STATIC_DIR}")
    else:
        print(f"No frontend found at {STATIC_DIR}, running API only")


def create_app() -> FastAPI:
    """Create the FastAPI app."""
    return app
