"""Regression coverage for export data loss found during the codebase audit."""

import base64
import io
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from PIL import Image

from scansplitter.api import (
    ExportLocalRequest,
    ExportRequest,
    ImageData,
    run_export_local,
    run_export_zip,
)
from scansplitter.session import get_session_manager


@pytest.fixture
def export_session():
    manager = get_session_manager()
    session = manager.create_session()
    yield session
    manager.delete_session(session.id)


def image_data(name):
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), "red").save(buffer, "PNG")
    return ImageData(id=name, name=name, data=base64.b64encode(buffer.getvalue()).decode())


@pytest.mark.parametrize("names", [("family holiday", "family_holiday"), ("Photo", "photo")])
@pytest.mark.parametrize("local", [False, True])
def test_export_rejects_sanitized_collisions_before_writing(export_session, tmp_path, names, local):
    images = [image_data(name) for name in names]
    with pytest.raises(HTTPException, match="Duplicate export filename") as error:
        if local:
            run_export_local(ExportLocalRequest(
                session_id=export_session.id, images=images,
                output_directory=str(tmp_path), overwrite=True,
            ))
        else:
            run_export_zip(ExportRequest(session_id=export_session.id, images=images))
    assert error.value.status_code == 400
    assert not list(tmp_path.iterdir())


def test_simultaneous_zip_exports_keep_their_own_images(export_session):
    barrier = threading.Barrier(2)

    def export(name):
        payload = run_export_zip(
            ExportRequest(session_id=export_session.id, images=[image_data(name)]),
            progress_cb=lambda *_: barrier.wait(timeout=5),
        )
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            assert archive.namelist() == [f"{name}.jpg"]
            assert archive.testzip() is None

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(export, ["first", "second"]))


def test_legacy_export_rejects_sanitized_collisions(export_session):
    for name in ("a", "b"):
        path = export_session.directory / f"cropped_{name}.jpg"
        Image.new("RGB", (12, 12)).save(path)
        export_session.cropped_images.append(path)
    with pytest.raises(HTTPException, match="Duplicate export filename"):
        run_export_zip(ExportRequest(
            session_id=export_session.id, names={"a": "photo 1", "b": "photo_1"},
        ))


def test_quick_canonical_exports_keep_pixels_across_rotation_and_paths(tmp_path):
    from fastapi.testclient import TestClient

    from scansplitter.api import app
    client = TestClient(app)
    source = Image.new("RGB", (60, 40), "#bd6c38")
    buffer = io.BytesIO()
    source.save(buffer, "PNG")
    session = client.post("/api/upload", files={"file": ("original.png", buffer.getvalue(), "image/png")}).json()["session_id"]
    crop = client.post("/api/crop", json={"session_id": session, "auto_rotate": False, "edge_cleanup_mode": "off",
        "boxes": [{"id": "full", "center_x": 30, "center_y": 20, "width": 60, "height": 40, "angle": 0}]}).json()["images"][0]
    request = {"session_id": session, "format": "png", "images": [{"id": "full", "name": "photo", "session_id": session, "crop_id": crop["crop_id"], "rotation": 90, "date_taken": "1980-03-04"}]}
    individual = client.post("/api/export/photo", json=request)
    assert individual.status_code == 200
    decoded = Image.open(io.BytesIO(individual.content))
    assert decoded.size == (40, 60)
    assert decoded.getpixel((20, 20)) == (189, 108, 56)
    zipped = client.post("/api/export", json=request)
    with zipfile.ZipFile(io.BytesIO(zipped.content)) as archive:
        assert archive.read("photo.png") == individual.content
    local = client.post("/api/export-local", json={**request, "output_directory": str(tmp_path)})
    assert local.status_code == 200
    assert (tmp_path / "photo.png").read_bytes() == individual.content
