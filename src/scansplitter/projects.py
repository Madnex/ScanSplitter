"""Persistent project storage and the review-queue backend.

A *project* is a named, on-disk collection of scans that survives server
restarts. Each project lives in its own directory under the data root:

    <data_dir>/projects/<project_id>/
        project.json          # all project state (atomic-written)
        scans/<scan_id>.jpg    # stored scan images (PDF pages rendered once)
        thumbs/<scan_id>.jpg   # cached 320px-wide thumbnails

All on-disk names are server-generated ids; client-supplied ids from path
parameters are validated (hex only) before any path is constructed, so there
is no client-controlled path anywhere in this module.
"""

import io
import json
import os
import re
import shutil
import threading
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from PIL import Image

from .detector import (
    DetectedRegion,
    crop_rotated_region,
    detect_photos_u2net,
    detect_photos_v1,
    detect_photos_v2,
)
from .jobs import submit_job
from .metadata import (
    create_metadata_exif,
    create_xmp_packet,
    insert_xmp,
    metadata_defaults,
    normalize_metadata_patch,
)
from .pdf_handler import extract_pdf_page, get_pdf_page_count
from .rotator import auto_rotate

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]

# --- Limits (mirrors the single-session upload endpoint) ---
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_PDF_PAGES = 200
ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".pdf"}

# Decompression-bomb guard (kept in sync with api.py).
Image.MAX_IMAGE_PIXELS = 300_000_000

# PDF pages are rendered once, at review resolution, and stored as images.
_PDF_STORE_DPI = 150
_THUMB_WIDTH = 320

# Minimum number of detected scans before a project's modal detected-count is
# trusted enough to feed `expected_count` into confidence evaluation.
_EXPECTED_COUNT_MIN_SCANS = 5

PROJECT_STATUSES = (
    "pending",
    "detecting",
    "auto_approved",
    "needs_review",
    "approved",
    "failed",
)

# Statuses whose boxes are included in an export.
_EXPORTABLE_STATUSES = {"approved", "auto_approved"}

DEFAULT_SETTINGS: dict[str, Any] = {
    "detection_mode": "scansplitterv2",
    "min_area_ratio": 2.0,
    "max_area_ratio": 80.0,
    "auto_rotate": True,
    "auto_deskew": False,
    "restore_color": False,
    "remove_dust": False,
    "upscale_2x": False,
    "format": "jpeg",
    "quality": 85,
    "include_gps": False,
}

_ID_RE = re.compile(r"[0-9a-f]{32}\Z")


def _now_iso() -> str:
    """UTC timestamp in the schema's ``...Z`` form."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return uuid.uuid4().hex


def _data_dir() -> Path:
    """Resolve the data root, honoring the ``SCANSPLITTER_DATA_DIR`` override.

    Read lazily (per call) so tests can point the store at a temp directory
    before the first request.
    """
    override = os.environ.get("SCANSPLITTER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".scansplitter"


def _box_to_region(box: dict, image_width: int, image_height: int) -> DetectedRegion:
    """Convert a stored center-based box into a croppable ``DetectedRegion``.

    Mirrors ``api.box_to_detected_region`` but works on the plain-dict box
    shape used in ``project.json`` (``{id, x, y, width, height, angle}`` where
    ``x``/``y`` are the box *center*).
    """
    import math

    import numpy as np

    cx = float(box["x"])
    cy = float(box["y"])
    w = float(box["width"])
    h = float(box["height"])
    angle = float(box.get("angle", 0.0))
    angle_rad = math.radians(angle)

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
        angle=angle,
        area=w * h,
        area_ratio=(w * h) / max(1, image_width * image_height),
        x=int(max(0, x_min)),
        y=int(max(0, y_min)),
        width=int(min(image_width, x_max) - max(0, x_min)),
        height=int(min(image_height, y_max) - max(0, y_min)),
    )


def _region_to_box(region: DetectedRegion) -> dict:
    """Convert a detector region into the stored center-based box shape."""
    return {
        "id": _new_id()[:8],
        "x": float(region.center[0]),
        "y": float(region.center[1]),
        "width": float(region.size[0]),
        "height": float(region.size[1]),
        "angle": float(region.angle),
    }


def _run_confidence(
    boxes: list[dict], width: int, height: int, expected_count: int | None
) -> list[dict]:
    """Evaluate confidence flags for a scan via the ``confidence`` module.

    Imported lazily so a spec-compliant module (possibly authored in parallel)
    is resolved at call time, and so tests can inject a placeholder.
    """
    from .confidence import evaluate_scan

    flags = evaluate_scan(boxes, width, height, expected_count)
    return [{"code": f.code, "box_id": f.box_id, "message": f.message} for f in flags]


class ProjectStore:
    """Filesystem-backed store for projects, guarded by per-project locks."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks_guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    # --- Path helpers ---

    def _lock_for(self, pid: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(pid)
            if lock is None:
                lock = threading.Lock()
                self._locks[pid] = lock
            return lock

    def _project_dir(self, pid: str, must_exist: bool = True) -> Path:
        """Validate ``pid`` (hex only) and return its directory.

        Validation happens before any path construction, so a traversal
        attempt (e.g. ``"../x"``) is rejected as a 404 without touching the
        filesystem.
        """
        if not _ID_RE.fullmatch(pid):
            raise HTTPException(status_code=404, detail="Project not found")
        pdir = self.root / pid
        if must_exist and not (pdir / "project.json").exists():
            raise HTTPException(status_code=404, detail="Project not found")
        return pdir

    def _read(self, pid: str) -> dict:
        pdir = self._project_dir(pid)
        with open(pdir / "project.json", encoding="utf-8") as fh:
            data = json.load(fh)
        data["settings"] = {**DEFAULT_SETTINGS, **data.get("settings", {})}
        for scan in data.get("scans", []):
            scan.setdefault("metadata", metadata_defaults())
            scan.setdefault("back_of", None)
            scan.setdefault("ocr_text", None)
            scan.setdefault("ocr_reviewed", False)
        return data

    def _write(self, pid: str, data: dict) -> None:
        """Atomically persist ``data`` (write tmp, then ``os.replace``)."""
        pdir = self._project_dir(pid, must_exist=False)
        tmp = pdir / "project.json.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, pdir / "project.json")

    @staticmethod
    def _find_scan(data: dict, sid: str) -> dict:
        if not _ID_RE.fullmatch(sid):
            raise HTTPException(status_code=404, detail="Scan not found")
        for scan in data["scans"]:
            if scan["id"] == sid:
                return scan
        raise HTTPException(status_code=404, detail="Scan not found")

    # --- Project CRUD ---

    def create_project(self, name: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Project name is required")

        pid = _new_id()
        pdir = self.root / pid
        (pdir / "scans").mkdir(parents=True, exist_ok=True)
        (pdir / "thumbs").mkdir(parents=True, exist_ok=True)

        now = _now_iso()
        data = {
            "version": 1,
            "id": pid,
            "name": name,
            "created_at": now,
            "updated_at": now,
            "settings": dict(DEFAULT_SETTINGS),
            "scans": [],
        }
        self._write(pid, data)
        return data

    def get_project(self, pid: str) -> dict:
        return self._read(pid)

    def list_projects(self) -> list[dict]:
        summaries = []
        for entry in sorted(self.root.glob("*")):
            if not entry.is_dir() or not _ID_RE.fullmatch(entry.name):
                continue
            manifest = entry / "project.json"
            if not manifest.exists():
                continue
            try:
                with open(manifest, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            summaries.append(
                {
                    "id": data["id"],
                    "name": data["name"],
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"],
                    "counts": _count_statuses(data["scans"]),
                }
            )
        summaries.sort(key=lambda s: s["updated_at"], reverse=True)
        return summaries

    def update_project(
        self, pid: str, name: str | None = None, settings: dict | None = None
    ) -> dict:
        with self._lock_for(pid):
            data = self._read(pid)
            if name is not None:
                clean = name.strip()
                if not clean:
                    raise HTTPException(status_code=400, detail="Project name is required")
                data["name"] = clean
            if settings:
                merged = dict(data["settings"])
                for key, value in settings.items():
                    if key in DEFAULT_SETTINGS:
                        merged[key] = value
                data["settings"] = merged
            data["updated_at"] = _now_iso()
            self._write(pid, data)
            return data

    def update_metadata(
        self, pid: str, scan_ids: list[str] | None, patch: dict[str, Any]
    ) -> list[dict]:
        """Atomically apply a validated partial metadata patch to scans."""
        with self._lock_for(pid):
            data = self._read(pid)
            if scan_ids is not None and not scan_ids:
                raise HTTPException(status_code=400, detail="scan_ids must not be empty")
            targets = data["scans"] if scan_ids is None else [self._find_scan(data, sid) for sid in scan_ids]
            try:
                updated = [
                    normalize_metadata_patch(patch, scan.get("metadata")) for scan in targets
                ]
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            for scan, metadata in zip(targets, updated, strict=True):
                scan["metadata"] = metadata
            data["updated_at"] = _now_iso()
            self._write(pid, data)
            return targets

    def pair_scans(self, pid: str, front_sid: str, back_sid: str | None) -> dict:
        """Pair one optional back scan to a front, maintaining a one-to-one relationship."""
        if back_sid == front_sid:
            raise HTTPException(status_code=400, detail="A scan cannot be its own back")
        with self._lock_for(pid):
            data = self._read(pid)
            front = self._find_scan(data, front_sid)
            if back_sid is not None:
                back = self._find_scan(data, back_sid)
                for scan in data["scans"]:
                    if scan.get("back_of") == front_sid:
                        scan["back_of"] = None
                back["back_of"] = front_sid
            else:
                for scan in data["scans"]:
                    if scan.get("back_of") == front_sid:
                        scan["back_of"] = None
            data["updated_at"] = _now_iso()
            self._write(pid, data)
            return front

    def submit_ocr_job(self, pid: str, sid: str, language: str = "eng") -> str:
        scan = self.get_scan(pid, sid)

        def worker(progress: ProgressCallback, cancelled: CancelCheck) -> dict:
            from .archival import transcribe_image
            from .jobs import JobCancelled

            progress(15, "preparing local OCR")
            if cancelled():
                raise JobCancelled
            text = transcribe_image(self._project_dir(pid) / scan["stored_file"], language)
            progress(85, "saving transcription")
            self._persist_scan_fields(pid, sid, {"ocr_text": text, "ocr_reviewed": False})
            return {"scan_id": sid, "text": text}

        return submit_job("ocr", pid, worker).job_id

    def accept_ocr(self, pid: str, back_sid: str, text: str, append_caption: bool) -> dict:
        """Review a transcription and optionally attach it to the paired front caption."""
        clean = text.strip()[:10_000]
        with self._lock_for(pid):
            data = self._read(pid)
            back = self._find_scan(data, back_sid)
            back["ocr_text"] = clean or None
            back["ocr_reviewed"] = True
            front_sid = back.get("back_of")
            if append_caption and front_sid and clean:
                front = self._find_scan(data, front_sid)
                current = (front.get("metadata") or metadata_defaults()).get("caption")
                note = f"Back inscription: {clean}"
                front["metadata"] = normalize_metadata_patch(
                    {"caption": f"{current}\n\n{note}" if current else note}, front.get("metadata")
                )
            data["updated_at"] = _now_iso()
            self._write(pid, data)
            return back

    def delete_project(self, pid: str) -> None:
        pdir = self._project_dir(pid)
        shutil.rmtree(pdir, ignore_errors=True)

    # --- Scans ---

    def add_scans(self, pid: str, files: list[tuple[str, bytes]]) -> list[dict]:
        """Ingest uploaded files, expanding PDFs to one scan per page.

        Image bytes are decoded/validated and re-encoded into the project's
        ``scans/`` directory before any project.json mutation, so a bad file
        fails the request cleanly without leaving a half-written manifest.
        """
        pdir = self._project_dir(pid)
        scans_dir = pdir / "scans"
        scans_dir.mkdir(exist_ok=True)

        new_entries: list[dict] = []
        for filename, data in files:
            display_name = Path(filename or "scan").name or "scan"
            ext = Path(display_name).suffix.lower()
            if ext not in ALLOWED_UPLOAD_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {ext or 'no extension'}",
                )

            if ext == ".pdf":
                new_entries.extend(self._store_pdf(scans_dir, display_name, data))
            else:
                new_entries.append(self._store_image(scans_dir, display_name, data))

        with self._lock_for(pid):
            manifest = self._read(pid)
            manifest["scans"].extend(new_entries)
            manifest["updated_at"] = _now_iso()
            self._write(pid, manifest)
        return new_entries

    def _store_image(self, scans_dir: Path, display_name: str, data: bytes) -> dict:
        try:
            image = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception as exc:  # includes PIL decompression-bomb errors
            raise HTTPException(
                status_code=400, detail=f"Could not read image {display_name}: {exc}"
            ) from exc

        sid = _new_id()
        ext = "png" if Path(display_name).suffix.lower() == ".png" else "jpg"
        dest = scans_dir / f"{sid}.{ext}"
        if ext == "png":
            image.save(dest, "PNG", optimize=True)
        else:
            image.save(dest, "JPEG", quality=95)
        return _new_scan_entry(sid, display_name, f"scans/{sid}.{ext}", None, image.size)

    def _store_pdf(self, scans_dir: Path, display_name: str, data: bytes) -> list[dict]:
        tmp = scans_dir / f"_incoming_{_new_id()}.pdf"
        try:
            tmp.write_bytes(data)
            try:
                page_count = get_pdf_page_count(tmp)
            except Exception as exc:
                raise HTTPException(
                    status_code=400, detail=f"Could not read PDF {display_name}: {exc}"
                ) from exc
            if page_count < 1:
                raise HTTPException(status_code=400, detail="PDF contains no pages")
            if page_count > MAX_PDF_PAGES:
                raise HTTPException(
                    status_code=400,
                    detail=f"PDF has too many pages ({page_count}, max {MAX_PDF_PAGES})",
                )

            entries = []
            for page in range(1, page_count + 1):
                image = extract_pdf_page(tmp, page, dpi=_PDF_STORE_DPI).convert("RGB")
                sid = _new_id()
                dest = scans_dir / f"{sid}.jpg"
                image.save(dest, "JPEG", quality=95)
                entries.append(
                    _new_scan_entry(sid, display_name, f"scans/{sid}.jpg", page, image.size)
                )
            return entries
        finally:
            tmp.unlink(missing_ok=True)

    def get_scan(self, pid: str, sid: str) -> dict:
        return self._find_scan(self._read(pid), sid)

    def update_scan(
        self,
        pid: str,
        sid: str,
        boxes: list[dict] | None = None,
        status: str | None = None,
    ) -> dict:
        if status is not None and status not in ("approved", "needs_review"):
            raise HTTPException(
                status_code=400,
                detail="status may only be set to 'approved' or 'needs_review'",
            )

        with self._lock_for(pid):
            data = self._read(pid)
            scan = self._find_scan(data, sid)

            if boxes is not None:
                clean_boxes = [_normalize_box(b) for b in boxes]
                scan["boxes"] = clean_boxes
                scan["detected_count"] = len(clean_boxes)
                expected = _expected_count(data)
                scan["flags"] = _run_confidence(
                    clean_boxes, scan["width"], scan["height"], expected
                )
                # Editing boxes returns the scan to the review queue unless the
                # client simultaneously supplies an explicit status.
                if status is None:
                    scan["status"] = "needs_review"

            if status is not None:
                scan["status"] = status
                scan["reviewed_at"] = _now_iso()

            data["updated_at"] = _now_iso()
            self._write(pid, data)
            return scan

    def delete_scan(self, pid: str, sid: str) -> None:
        pdir = self._project_dir(pid)
        with self._lock_for(pid):
            data = self._read(pid)
            scan = self._find_scan(data, sid)
            data["scans"] = [s for s in data["scans"] if s["id"] != sid]
            data["updated_at"] = _now_iso()
            self._write(pid, data)
        # Remove the on-disk artifacts (best effort, outside the manifest lock).
        (pdir / scan["stored_file"]).unlink(missing_ok=True)
        (pdir / "thumbs" / f"{sid}.jpg").unlink(missing_ok=True)

    def scan_image_bytes(self, pid: str, sid: str, thumb: bool = False) -> tuple[bytes, str]:
        pdir = self._project_dir(pid)
        scan = self._find_scan(self._read(pid), sid)
        stored = pdir / scan["stored_file"]
        if not stored.exists():
            raise HTTPException(status_code=410, detail="Scan image no longer exists")

        if not thumb:
            media = "image/png" if stored.suffix.lower() == ".png" else "image/jpeg"
            return stored.read_bytes(), media

        thumb_path = pdir / "thumbs" / f"{sid}.jpg"
        if not thumb_path.exists():
            image = Image.open(stored).convert("RGB")
            image.thumbnail((_THUMB_WIDTH, 10_000))
            thumb_path.parent.mkdir(exist_ok=True)
            image.save(thumb_path, "JPEG", quality=85)
        return thumb_path.read_bytes(), "image/jpeg"

    # --- Detection jobs ---

    def submit_detect_job(self, pid: str, sid: str) -> str:
        """Mark a scan detecting and queue a background detection job."""
        with self._lock_for(pid):
            data = self._read(pid)
            scan = self._find_scan(data, sid)
            scan["status"] = "detecting"
            data["updated_at"] = _now_iso()
            self._write(pid, data)

        def worker(progress: ProgressCallback, cancelled: CancelCheck) -> dict:
            return self._detect_and_persist(pid, sid, progress, cancelled)

        return submit_job("detect", pid, worker).job_id

    def _detect_and_persist(
        self, pid: str, sid: str, progress: ProgressCallback, cancelled: CancelCheck
    ) -> dict:
        data = self._read(pid)
        scan = self._find_scan(data, sid)
        settings = data["settings"]
        stored = self._project_dir(pid) / scan["stored_file"]

        progress(10, "loading scan")
        try:
            image = Image.open(stored).convert("RGB")
            regions = _detect(image, settings)
            boxes = [_region_to_box(r) for r in regions]
            progress(70, "scoring confidence")
            expected = _expected_count(data, exclude_sid=sid)
            flags = _run_confidence(boxes, image.width, image.height, expected)
            status = "auto_approved" if not flags else "needs_review"
        except Exception:
            self._persist_scan_fields(pid, sid, {"status": "failed"})
            raise

        self._persist_scan_fields(
            pid,
            sid,
            {
                "boxes": boxes,
                "flags": flags,
                "detected_count": len(boxes),
                "status": status,
            },
        )
        return {
            "boxes": boxes,
            "flags": flags,
            "detected_count": len(boxes),
            "status": status,
        }

    def _persist_scan_fields(self, pid: str, sid: str, fields: dict) -> None:
        with self._lock_for(pid):
            data = self._read(pid)
            scan = self._find_scan(data, sid)
            scan.update(fields)
            data["updated_at"] = _now_iso()
            self._write(pid, data)

    def submit_detect_pending(self, pid: str) -> list[dict]:
        data = self._read(pid)
        pending = [s["id"] for s in data["scans"] if s["status"] in ("pending", "failed")]
        return [{"scan_id": sid, "job_id": self.submit_detect_job(pid, sid)} for sid in pending]

    # --- Export ---

    def submit_export_job(
        self,
        pid: str,
        fmt: str | None = None,
        quality: int | None = None,
        include_gps: bool | None = None,
    ) -> str:
        data = self._read(pid)  # validates the project exists up front
        settings = data["settings"]
        out_format = (fmt or settings["format"]).lower()
        out_quality = quality if quality is not None else settings["quality"]
        out_include_gps = include_gps if include_gps is not None else bool(settings["include_gps"])

        def worker(progress: ProgressCallback, cancelled: CancelCheck) -> dict:
            payload = self._build_export_zip(
                pid, out_format, out_quality, out_include_gps, progress, cancelled
            )
            return {"__download_bytes": payload}

        return submit_job("export", pid, worker).job_id

    def submit_restoration_preview_job(self, pid: str, sid: str, box_id: str | None) -> str:
        """Build an ephemeral before/after JPEG for one crop."""
        data = self._read(pid)
        scan = self._find_scan(data, sid)
        boxes = scan["boxes"]
        if not boxes:
            raise HTTPException(status_code=400, detail="Scan has no photo boxes to preview")
        box = next((item for item in boxes if item["id"] == box_id), None) if box_id else boxes[0]
        if box is None:
            raise HTTPException(status_code=404, detail="Photo box not found")

        def worker(progress: ProgressCallback, cancelled: CancelCheck) -> dict:
            import cv2
            import numpy as np

            from .jobs import JobCancelled
            from .restoration import apply_restorations, comparison_image

            progress(15, "cropping photo")
            if cancelled():
                raise JobCancelled
            stored = self._project_dir(pid) / scan["stored_file"]
            source = Image.open(stored).convert("RGB")
            cv_image = cv2.cvtColor(np.array(source), cv2.COLOR_RGB2BGR)
            region = _box_to_region(box, source.width, source.height)
            cropped = crop_rotated_region(cv_image, region)
            if cropped.size == 0:
                raise HTTPException(status_code=400, detail="Photo box produced an empty crop")
            before = Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
            if data["settings"]["auto_rotate"]:
                before, _ = auto_rotate(before)
            progress(55, "applying restoration")
            effective_settings = {**data["settings"], **box.get("restoration", {})}
            after, detail = apply_restorations(before, effective_settings)
            preview = comparison_image(before, after, detail)
            output = io.BytesIO()
            preview.save(output, "JPEG", quality=88)
            return {"detail": detail, "__download_bytes": output.getvalue()}

        return submit_job("restoration-preview", pid, worker).job_id

    def _build_export_zip(
        self,
        pid: str,
        out_format: str,
        out_quality: int,
        include_gps: bool,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> bytes:
        import zipfile

        import cv2
        import numpy as np

        from .jobs import JobCancelled

        data = self._read(pid)
        pdir = self._project_dir(pid)
        auto_rotate_enabled = bool(data["settings"]["auto_rotate"])
        ext = "png" if out_format == "png" else "jpg"

        exportable = [s for s in data["scans"] if s["status"] in _EXPORTABLE_STATUSES]

        buffer = io.BytesIO()
        used_names: set[str] = set()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            total = max(1, len(exportable))
            for index, scan in enumerate(exportable):
                if cancelled():
                    raise JobCancelled
                progress(int(90 * index / total), f"exporting scan {index + 1}/{total}")

                stored = pdir / scan["stored_file"]
                if not stored.exists() or not scan["boxes"]:
                    continue
                pil = Image.open(stored).convert("RGB")
                cv_image = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
                stem = _sanitize_stem(scan["original_name"])

                for photo_index, box in enumerate(scan["boxes"], 1):
                    region = _box_to_region(box, pil.width, pil.height)
                    cropped = crop_rotated_region(cv_image, region)
                    if cropped.size == 0:
                        continue
                    crop_pil = Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
                    if auto_rotate_enabled:
                        crop_pil, _ = auto_rotate(crop_pil)
                    from .restoration import apply_restorations

                    effective_settings = {**data["settings"], **box.get("restoration", {})}
                    crop_pil, _ = apply_restorations(crop_pil, effective_settings)

                    img_buffer = io.BytesIO()
                    if ext == "png":
                        crop_pil.save(img_buffer, "PNG", optimize=True)
                    else:
                        crop_pil.save(img_buffer, "JPEG", quality=out_quality)

                    payload = img_buffer.getvalue()
                    if ext == "jpg":
                        metadata = scan.get("metadata") or metadata_defaults()
                        exif = create_metadata_exif(metadata, include_gps)
                        if exif:
                            from .exif_handler import apply_exif_to_jpeg

                            payload = apply_exif_to_jpeg(payload, exif)
                        xmp = create_xmp_packet(metadata)
                        if xmp:
                            payload = insert_xmp(payload, xmp)

                    name = _unique_name(f"{stem}_{photo_index}", ext, used_names)
                    zf.writestr(name, payload)

        return buffer.getvalue()


# --- Module-level helpers ---


def _new_scan_entry(
    sid: str, original_name: str, stored_file: str, page: int | None, size: tuple[int, int]
) -> dict:
    return {
        "id": sid,
        "original_name": original_name,
        "stored_file": stored_file,
        "page": page,
        "width": size[0],
        "height": size[1],
        "status": "pending",
        "boxes": [],
        "flags": [],
        "detected_count": None,
        "reviewed_at": None,
        "metadata": metadata_defaults(),
        "back_of": None,
        "ocr_text": None,
        "ocr_reviewed": False,
    }


def _normalize_box(box: dict) -> dict:
    """Coerce a client box into the stored center-based shape."""
    normalized = {
        "id": str(box.get("id") or _new_id()[:8]),
        "x": float(box["x"]),
        "y": float(box["y"]),
        "width": float(box["width"]),
        "height": float(box["height"]),
        "angle": float(box.get("angle", 0.0)),
    }
    overrides = box.get("restoration")
    if isinstance(overrides, dict):
        normalized["restoration"] = {
            key: bool(value)
            for key, value in overrides.items()
            if key in {"auto_deskew", "restore_color", "remove_dust", "upscale_2x"}
        }
    return normalized


def _detect(image: Image.Image, settings: dict) -> list[DetectedRegion]:
    mode = settings.get("detection_mode", "scansplitterv2")
    min_ratio = float(settings.get("min_area_ratio", 2.0)) / 100
    max_ratio = float(settings.get("max_area_ratio", 80.0)) / 100
    if mode == "u2net":
        return detect_photos_u2net(image, min_area_ratio=min_ratio, max_area_ratio=max_ratio)
    if mode == "scansplitterv1":
        return detect_photos_v1(image, min_area_ratio=min_ratio, max_area_ratio=max_ratio)
    return detect_photos_v2(image, min_area_ratio=min_ratio, max_area_ratio=max_ratio)


def _expected_count(data: dict, exclude_sid: str | None = None) -> int | None:
    """Modal detected-count across the project, or None below the threshold."""
    counts = [
        s["detected_count"]
        for s in data["scans"]
        if s["detected_count"] is not None and s["id"] != exclude_sid
    ]
    if len(counts) < _EXPECTED_COUNT_MIN_SCANS:
        return None
    return Counter(counts).most_common(1)[0][0]


def _count_statuses(scans: list[dict]) -> dict:
    counts = {status: 0 for status in PROJECT_STATUSES}
    counts["total"] = len(scans)
    for scan in scans:
        status = scan.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _sanitize_stem(name: str) -> str:
    """A filesystem-safe stem from an original filename (no extension)."""
    stem = Path(name).stem or "photo"
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", stem).strip("_") or "photo"
    return cleaned


def _unique_name(base: str, ext: str, used: set[str]) -> str:
    """Return ``base.ext`` (or a ``base_N.ext`` variant) unused in ``used``."""
    candidate = f"{base}.{ext}"
    counter = 2
    while candidate in used:
        candidate = f"{base}_{counter}.{ext}"
        counter += 1
    used.add(candidate)
    return candidate


# --- Store singleton (keyed by resolved root so tests stay isolated) ---

_store_guard = threading.Lock()
_stores: dict[str, ProjectStore] = {}


def get_project_store() -> ProjectStore:
    """Return the store for the current data root (created on first use)."""
    root = (_data_dir() / "projects").resolve()
    key = str(root)
    with _store_guard:
        store = _stores.get(key)
        if store is None:
            store = ProjectStore(root)
            _stores[key] = store
        return store
