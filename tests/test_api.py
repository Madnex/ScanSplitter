"""Regression tests for ScanSplitter API security fixes.

These tests avoid any detection / model-download code paths: crops are driven
by explicit bounding boxes and exports use in-memory image data.
"""

import base64
import io
import zipfile
from importlib.metadata import version

import piexif
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import scansplitter
from scansplitter.api import app
from scansplitter.session import get_session_manager

# No context manager -> the startup event (static mount) is not triggered.
client = TestClient(app)


def _png_bytes(color=(200, 100, 50), size=(64, 48)) -> bytes:
    """Return bytes of a small in-memory PNG image."""
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _png_base64() -> str:
    return base64.b64encode(_png_bytes()).decode("utf-8")


def _jpeg_with_exif(
    date_taken: str = "2015:05:05 10:00:00",
    with_gps: bool = True,
    size=(64, 48),
) -> bytes:
    """Return a small in-memory JPEG carrying GPS + DateTimeOriginal EXIF."""
    exif_dict: dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    if date_taken:
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_taken.encode("utf-8")
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_taken.encode("utf-8")
    if with_gps:
        exif_dict["GPS"] = {
            piexif.GPSIFD.GPSVersionID: (2, 3, 0, 0),
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: [(51, 1), (30, 1), (0, 1)],
            piexif.GPSIFD.GPSLongitudeRef: b"W",
            piexif.GPSIFD.GPSLongitude: [(0, 1), (7, 1), (0, 1)],
        }
    exif_bytes = piexif.dump(exif_dict)
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(buffer, format="JPEG", exif=exif_bytes)
    return buffer.getvalue()


def _load_exif(jpeg_bytes: bytes) -> dict:
    return piexif.load(jpeg_bytes)


def _date_original(jpeg_bytes: bytes) -> str | None:
    exif = _load_exif(jpeg_bytes)
    dt = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
    return dt.decode("utf-8") if isinstance(dt, bytes) else dt


def _first_zip_jpeg(zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".jpg"))
        return zf.read(name)


def _upload(filename="scan.png", content: bytes | None = None, content_type="image/png") -> dict:
    if content is None:
        content = _png_bytes()
    response = client.post(
        "/api/upload",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _upload_jpeg_with_exif(**kwargs) -> dict:
    return _upload("scan.jpg", content=_jpeg_with_exif(**kwargs), content_type="image/jpeg")


def _session_dir(session_id: str):
    session = get_session_manager().get_session(session_id)
    assert session is not None
    return session.directory.resolve()


def _crop(session_id: str, box_id="box1") -> dict:
    box = {
        "id": box_id,
        "center_x": 32.0,
        "center_y": 24.0,
        "width": 40.0,
        "height": 30.0,
        "angle": 0.0,
    }
    response = client.post(
        "/api/crop",
        json={"session_id": session_id, "page": 1, "boxes": [box], "auto_rotate": False},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_traversal_filename_is_sanitized():
    """Uploading a traversal filename must not write outside the session dir."""
    data = _upload("../../evil.png")
    returned = data["filename"]

    # The stored name must be a plain basename, no separators or parent refs.
    assert "/" not in returned
    assert "\\" not in returned
    assert not returned.startswith("..")

    session_dir = _session_dir(data["session_id"])
    written = (session_dir / returned).resolve()
    assert written.exists()
    assert written.is_relative_to(session_dir)

    # The traversal target must not have been created outside the session dir.
    assert not (session_dir.parent / "evil.png").exists()


def test_crop_box_id_traversal_stays_in_session_dir():
    """A malicious box id must not escape the session directory on save."""
    data = _upload()
    session_dir = _session_dir(data["session_id"])

    _crop(data["session_id"], box_id="../x")

    session = get_session_manager().get_session(data["session_id"])
    assert session.cropped_images
    for path in session.cropped_images:
        assert path.resolve().is_relative_to(session_dir)
    # No file leaked into the parent (would be cropped_../x.jpg -> ../cropped_x...).
    assert not (session_dir.parent / "cropped_x.jpg").exists()


def test_export_local_traversal_name_contained(tmp_path):
    """export-local must reject or contain a traversal image name."""
    data = _upload()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    response = client.post(
        "/api/export-local",
        json={
            "session_id": data["session_id"],
            "output_directory": str(out_dir),
            "format": "jpeg",
            "images": [{"id": "a", "data": _png_base64(), "name": "../escape"}],
        },
    )

    assert response.status_code in (200, 400), response.text
    # Nothing may be written outside the chosen output directory.
    assert not (tmp_path / "escape.jpg").exists()
    if response.status_code == 200:
        for fpath in response.json()["files"]:
            from pathlib import Path

            assert Path(fpath).resolve().is_relative_to(out_dir.resolve())


def test_legacy_jpeg_export_path_returns_200():
    """Regression: legacy export (no images field) must not NameError on exif_bytes."""
    data = _upload()
    _crop(data["session_id"])

    response = client.post(
        "/api/export",
        json={"session_id": data["session_id"], "format": "jpeg"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"


def test_export_local_empty_session_returns_400(tmp_path):
    """Regression: empty session must return 400, not a swallowed 500."""
    data = _upload()  # uploaded but never cropped -> no cropped images
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    response = client.post(
        "/api/export-local",
        json={
            "session_id": data["session_id"],
            "output_directory": str(out_dir),
            "format": "jpeg",
        },
    )
    assert response.status_code == 400, response.text


def test_export_strips_gps_by_default():
    """/api/export must drop the GPS IFD by default but keep DateTimeOriginal."""
    data = _upload_jpeg_with_exif()
    _crop(data["session_id"])

    response = client.post(
        "/api/export",
        json={"session_id": data["session_id"], "format": "jpeg"},
    )
    assert response.status_code == 200, response.text

    jpeg = _first_zip_jpeg(response.content)
    exif = _load_exif(jpeg)
    # GPS IFD must be empty (privacy default).
    assert not exif.get("GPS"), exif.get("GPS")
    # Regression: stripping GPS must not nuke the rest of the metadata.
    assert _date_original(jpeg) == "2015:05:05 10:00:00"


def test_export_includes_gps_when_opted_in():
    """/api/export with include_gps=true keeps the GPS IFD."""
    data = _upload_jpeg_with_exif()
    _crop(data["session_id"])

    response = client.post(
        "/api/export",
        json={"session_id": data["session_id"], "format": "jpeg", "include_gps": True},
    )
    assert response.status_code == 200, response.text

    exif = _load_exif(_first_zip_jpeg(response.content))
    assert exif.get("GPS"), "GPS IFD should be present when include_gps=true"
    assert piexif.GPSIFD.GPSLatitude in exif["GPS"]


def test_export_local_strips_gps_by_default(tmp_path):
    """/api/export-local must drop GPS by default and keep it when opted in."""
    data = _upload_jpeg_with_exif()
    _crop(data["session_id"])
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # Default: GPS stripped, date preserved.
    response = client.post(
        "/api/export-local",
        json={
            "session_id": data["session_id"],
            "output_directory": str(out_dir),
            "format": "jpeg",
        },
    )
    assert response.status_code == 200, response.text
    from pathlib import Path

    exported = Path(response.json()["files"][0]).read_bytes()
    assert not _load_exif(exported).get("GPS")
    assert _date_original(exported) == "2015:05:05 10:00:00"

    # Opt in: GPS retained.
    response = client.post(
        "/api/export-local",
        json={
            "session_id": data["session_id"],
            "output_directory": str(out_dir),
            "format": "jpeg",
            "include_gps": True,
            "overwrite": True,
        },
    )
    assert response.status_code == 200, response.text
    exported = Path(response.json()["files"][0]).read_bytes()
    assert _load_exif(exported).get("GPS")


def test_export_images_branch_strips_gps_by_default(tmp_path):
    """The request.images export branch must also honor include_gps."""
    data = _upload_jpeg_with_exif()
    _crop(data["session_id"])
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    from pathlib import Path

    # Per-image date set -> original EXIF (incl. GPS) is copied; default strips it.
    response = client.post(
        "/api/export-local",
        json={
            "session_id": data["session_id"],
            "output_directory": str(out_dir),
            "format": "jpeg",
            "images": [{"id": "a", "data": _png_base64(), "name": "photo1", "date_taken": "2021-03-04"}],
        },
    )
    assert response.status_code == 200, response.text
    exported = Path(response.json()["files"][0]).read_bytes()
    assert not _load_exif(exported).get("GPS")
    assert _date_original(exported) == "2021:03:04 00:00:00"

    # Opt in keeps GPS.
    response = client.post(
        "/api/export-local",
        json={
            "session_id": data["session_id"],
            "output_directory": str(out_dir),
            "format": "jpeg",
            "include_gps": True,
            "overwrite": True,
            "images": [{"id": "a", "data": _png_base64(), "name": "photo1", "date_taken": "2021-03-04"}],
        },
    )
    assert response.status_code == 200, response.text
    exported = Path(response.json()["files"][0]).read_bytes()
    assert _load_exif(exported).get("GPS")


def test_exif_date_set_then_cleared_affects_export():
    """A date set via /api/exif is written; an explicit null clears it on export."""
    data = _upload_jpeg_with_exif()
    _crop(data["session_id"])
    sid = data["session_id"]

    # Set a date (overrides the copied original 2015 date).
    resp = client.post("/api/exif", json={"session_id": sid, "date_taken": "2020-06-07"})
    assert resp.status_code == 200, resp.text

    export = client.post("/api/export", json={"session_id": sid, "format": "jpeg"})
    assert export.status_code == 200, export.text
    assert _date_original(_first_zip_jpeg(export.content)) == "2020:06:07 00:00:00"

    # Explicit null clears the date -> export writes no DateTimeOriginal,
    # even though the original EXIF carried one (explicit clear wins).
    resp = client.post("/api/exif", json={"session_id": sid, "date_taken": None})
    assert resp.status_code == 200, resp.text

    export = client.post("/api/export", json={"session_id": sid, "format": "jpeg"})
    assert export.status_code == 200, export.text
    assert _date_original(_first_zip_jpeg(export.content)) is None


def test_exif_update_omitting_date_leaves_it_unchanged():
    """Omitting date_taken keeps the previously set date (keep-unchanged)."""
    data = _upload_jpeg_with_exif()
    _crop(data["session_id"])
    sid = data["session_id"]

    resp = client.post("/api/exif", json={"session_id": sid, "date_taken": "2019-12-25"})
    assert resp.status_code == 200, resp.text

    # Request without date_taken must not clear it.
    resp = client.post("/api/exif", json={"session_id": sid})
    assert resp.status_code == 200, resp.text

    export = client.post("/api/export", json={"session_id": sid, "format": "jpeg"})
    assert export.status_code == 200, export.text
    assert _date_original(_first_zip_jpeg(export.content)) == "2019:12:25 00:00:00"


def test_version_matches_installed_metadata():
    assert scansplitter.__version__ == version("scansplitter")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
