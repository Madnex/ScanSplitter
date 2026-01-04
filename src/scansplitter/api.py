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

from .detector import DetectedRegion, crop_rotated_region, detect_photos
from .pdf_handler import extract_images_from_pdf, is_pdf
from .rotator import auto_rotate
from .session import Session, get_session_manager

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


class ExportRequest(BaseModel):
    """Request for export."""

    session_id: str
    format: str = "jpeg"  # jpeg or png
    quality: int = 85
    names: dict[str, str] | None = None  # id -> custom name


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


@app.post("/api/detect", response_model=DetectResponse)
async def detect_boxes(request: DetectRequest):
    """Detect bounding boxes in an image."""
    session = get_session_or_404(request.session_id)

    # Get first file (we only support one at a time for now)
    if not session.files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    filename = list(session.files.keys())[0]
    image = load_page_image(session, filename, request.page)

    # Run detection
    regions = detect_photos(
        image,
        min_area_ratio=request.min_area / 100,
        max_area_ratio=request.max_area / 100,
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

    if not session.cropped_images:
        raise HTTPException(status_code=400, detail="No cropped images to export")

    # Create ZIP file
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
                    ext = "jpg"

                # Get custom name if provided, otherwise use default
                # Filename is cropped_{id}.jpg, extract the id
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


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its files."""
    success = get_session_manager().delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


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
