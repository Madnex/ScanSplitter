"""Regression tests for ScanSplitter API security fixes.

These tests avoid any detection / model-download code paths: crops are driven
by explicit bounding boxes and exports use in-memory image data.
"""

import base64
import io
from importlib.metadata import version

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


def _upload(filename="scan.png") -> dict:
    response = client.post(
        "/api/upload",
        files={"file": (filename, _png_bytes(), "image/png")},
    )
    assert response.status_code == 200, response.text
    return response.json()


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


def test_version_matches_installed_metadata():
    assert scansplitter.__version__ == version("scansplitter")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
