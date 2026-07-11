"""Tests for the persistent-projects backend.

Detection runs in-process using the contour-based ``scansplitterv2`` mode
(never u2net, so no network / model download). Confidence evaluation is
provided by a spec-faithful in-test placeholder injected into ``sys.modules``
so the review-status logic is exercised deterministically and independently of
the parallel ``confidence`` module.
"""

import io
import json
import sys
import time
import types
import zipfile
from dataclasses import dataclass

import fitz
import piexif
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from scansplitter import projects
from scansplitter.api import app

client = TestClient(app)


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Point the project store at an isolated temp data directory."""
    monkeypatch.setenv("SCANSPLITTER_DATA_DIR", str(tmp_path))
    # Drop any cached store so the new root takes effect.
    projects._stores.clear()
    yield tmp_path
    projects._stores.clear()


@dataclass(frozen=True)
class _Flag:
    code: str
    box_id: str | None
    message: str


def _install_confidence(monkeypatch, evaluate):
    """Inject a placeholder ``scansplitter.confidence`` module."""
    module = types.ModuleType("scansplitter.confidence")
    module.Flag = _Flag
    module.evaluate_scan = evaluate
    monkeypatch.setitem(sys.modules, "scansplitter.confidence", module)


def _spec_evaluate(boxes, image_width, image_height, expected_count=None):
    """A minimal, spec-faithful confidence evaluation used by most tests."""
    flags = []
    if not boxes:
        flags.append(_Flag("no_boxes", None, "No boxes detected"))
    margin = 0.005 * min(image_width, image_height)
    for box in boxes:
        left = box["x"] - box["width"] / 2
        right = box["x"] + box["width"] / 2
        top = box["y"] - box["height"] / 2
        bottom = box["y"] + box["height"] / 2
        if (
            left <= margin
            or top <= margin
            or right >= image_width - margin
            or bottom >= image_height - margin
        ):
            flags.append(_Flag("touches_edge", box["id"], "Box touches an edge"))
    if expected_count is not None and len(boxes) != expected_count:
        flags.append(_Flag("count_mismatch", None, "Unexpected number of photos"))
    return flags


# --- Image helpers ----------------------------------------------------------


def _solid_png(color=(240, 240, 240), size=(200, 160)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _photo_png(size=(800, 600)) -> bytes:
    """A white page with one clearly separated dark rectangle."""
    img = Image.new("RGB", size, (255, 255, 255))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    draw.rectangle([200, 150, 600, 450], fill=(30, 30, 30))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _two_page_pdf() -> bytes:
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page(width=300, height=240)
        page.draw_rect(fitz.Rect(60, 60, 240, 180), fill=(0.1, 0.1, 0.1))
    return doc.tobytes()


def _wait_for_job(job_id: str) -> dict:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    pytest.fail(f"job {job_id} did not finish")


def _create_project(name="Shoebox 1975") -> dict:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


# --- CRUD -------------------------------------------------------------------


def test_project_crud():
    created = _create_project("My Project")
    pid = created["id"]
    assert created["version"] == 1
    assert created["name"] == "My Project"
    assert created["settings"]["detection_mode"] == "scansplitterv2"
    assert created["scans"] == []

    # List
    listing = client.get("/api/projects").json()["projects"]
    assert any(p["id"] == pid for p in listing)
    summary = next(p for p in listing if p["id"] == pid)
    assert summary["counts"]["total"] == 0

    # Get
    fetched = client.get(f"/api/projects/{pid}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == pid

    # Patch name + settings
    patched = client.patch(
        f"/api/projects/{pid}",
        json={"name": "Renamed", "settings": {"quality": 70, "bogus": "ignored"}},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["name"] == "Renamed"
    assert body["settings"]["quality"] == 70
    assert "bogus" not in body["settings"]

    # Delete
    assert client.delete(f"/api/projects/{pid}").json() == {"status": "deleted"}
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_old_manifest_gets_restoration_defaults(data_dir):
    created = _create_project("Legacy")
    pid = created["id"]
    manifest = data_dir / "projects" / pid / "project.json"
    payload = json.loads(manifest.read_text())
    payload["settings"].pop("auto_deskew")
    manifest.write_text(json.dumps(payload))

    fetched = client.get(f"/api/projects/{pid}")
    assert fetched.status_code == 200
    assert fetched.json()["settings"]["auto_deskew"] is False
    assert fetched.json()["settings"]["restore_color"] is False


def test_create_project_requires_name():
    assert client.post("/api/projects", json={"name": "   "}).status_code == 400


# --- Upload -----------------------------------------------------------------


def test_upload_image_and_pdf_expands_pages(monkeypatch):
    _install_confidence(monkeypatch, _spec_evaluate)
    pid = _create_project()["id"]

    response = client.post(
        f"/api/projects/{pid}/scans?detect=false",
        files=[
            ("files", ("holiday.jpg", _photo_png(), "image/jpeg")),
            ("files", ("album.pdf", _two_page_pdf(), "application/pdf")),
        ],
    )
    assert response.status_code == 200, response.text
    scans = response.json()["scans"]
    # 1 image + 2 PDF pages == 3 scans.
    assert len(scans) == 3

    pages = sorted(s["page"] for s in scans if s["page"] is not None)
    assert pages == [1, 2]
    image_scans = [s for s in scans if s["page"] is None]
    assert len(image_scans) == 1
    assert image_scans[0]["original_name"] == "holiday.jpg"
    assert all(s["status"] == "pending" for s in scans)

    # Stored image is retrievable, and a thumbnail is generated on demand.
    sid = scans[0]["id"]
    full = client.get(f"/api/projects/{pid}/scans/{sid}/image")
    assert full.status_code == 200
    assert full.headers["content-type"] in ("image/jpeg", "image/png")

    thumb = client.get(f"/api/projects/{pid}/scans/{sid}/image?thumb=true")
    assert thumb.status_code == 200
    assert Image.open(io.BytesIO(thumb.content)).width <= 320


def test_upload_rejects_unsupported_extension():
    pid = _create_project()["id"]
    response = client.post(
        f"/api/projects/{pid}/scans?detect=false",
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert response.status_code == 400


# --- Detection jobs ---------------------------------------------------------


def test_detect_job_persists_boxes_and_auto_approves(monkeypatch):
    # No flags -> auto_approved, regardless of how many boxes are detected.
    _install_confidence(monkeypatch, lambda *a, **k: [])
    pid = _create_project()["id"]

    upload = client.post(
        f"/api/projects/{pid}/scans",
        files=[("files", ("photo.png", _photo_png(), "image/png"))],
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert len(body["jobs"]) == 1
    assert body["scans"][0]["status"] == "detecting"

    job = _wait_for_job(body["jobs"][0]["job_id"])
    assert job["status"] == "succeeded", job

    scan = client.get(f"/api/projects/{pid}").json()["scans"][0]
    assert scan["status"] == "auto_approved"
    assert scan["flags"] == []
    assert scan["detected_count"] == len(scan["boxes"])
    # The rectangle should be found by scansplitterv2.
    assert scan["detected_count"] >= 1


def test_detect_job_flags_route_to_needs_review(monkeypatch):
    # A solid image yields zero boxes -> the spec placeholder flags no_boxes.
    _install_confidence(monkeypatch, _spec_evaluate)
    pid = _create_project()["id"]

    upload = client.post(
        f"/api/projects/{pid}/scans",
        files=[("files", ("blank.png", _solid_png(), "image/png"))],
    )
    job = _wait_for_job(upload.json()["jobs"][0]["job_id"])
    assert job["status"] == "succeeded", job

    scan = client.get(f"/api/projects/{pid}").json()["scans"][0]
    assert scan["status"] == "needs_review"
    assert any(f["code"] == "no_boxes" for f in scan["flags"])
    assert scan["detected_count"] == 0


# --- PATCH scan re-evaluates flags + approve flow ---------------------------


def test_patch_boxes_reevaluates_flags_and_approve_flow(monkeypatch):
    _install_confidence(monkeypatch, _spec_evaluate)
    pid = _create_project()["id"]
    upload = client.post(
        f"/api/projects/{pid}/scans?detect=false",
        files=[("files", ("photo.png", _photo_png(), "image/png"))],
    )
    sid = upload.json()["scans"][0]["id"]

    # A centered box (well away from edges) -> no flags, but editing returns
    # the scan to needs_review.
    centered = {"id": "b1", "x": 400, "y": 300, "width": 300, "height": 200, "angle": 0}
    resp = client.patch(f"/api/projects/{pid}/scans/{sid}", json={"boxes": [centered]})
    assert resp.status_code == 200, resp.text
    scan = resp.json()
    assert scan["flags"] == []
    assert scan["status"] == "needs_review"
    assert scan["detected_count"] == 1

    # A box touching the left edge -> touches_edge flag appears.
    edge = {"id": "b2", "x": 5, "y": 300, "width": 40, "height": 200, "angle": 0}
    resp = client.patch(f"/api/projects/{pid}/scans/{sid}", json={"boxes": [edge]})
    assert resp.status_code == 200, resp.text
    assert any(f["code"] == "touches_edge" for f in resp.json()["flags"])

    # Approve the scan.
    resp = client.patch(f"/api/projects/{pid}/scans/{sid}", json={"status": "approved"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert resp.json()["reviewed_at"] is not None

    # Client may not set an arbitrary status.
    bad = client.patch(f"/api/projects/{pid}/scans/{sid}", json={"status": "auto_approved"})
    assert bad.status_code == 400


# --- Archival metadata ------------------------------------------------------


def test_single_and_batch_metadata_updates_are_persistent_and_atomic():
    pid = _create_project()["id"]
    upload = client.post(
        f"/api/projects/{pid}/scans?detect=false",
        files=[
            ("files", ("one.png", _photo_png(), "image/png")),
            ("files", ("two.png", _photo_png(), "image/png")),
        ],
    )
    first, second = upload.json()["scans"]
    updated = client.patch(
        f"/api/projects/{pid}/scans/{first['id']}/metadata",
        json={"caption": "  Family picnic  ", "people": ["Ada", "ada", " Bob "]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["metadata"]["people"] == ["Ada", "Bob"]

    batch = client.patch(
        f"/api/projects/{pid}/metadata",
        json={"scan_ids": None, "metadata": {"album": "Shoebox 2"}},
    )
    assert batch.status_code == 200, batch.text
    assert all(scan["metadata"]["album"] == "Shoebox 2" for scan in batch.json()["scans"])
    assert batch.json()["scans"][0]["metadata"]["caption"] == "Family picnic"

    bad = client.patch(
        f"/api/projects/{pid}/metadata",
        json={"scan_ids": [first["id"], "0" * 32], "metadata": {"event": "Changed"}},
    )
    assert bad.status_code == 404
    project = client.get(f"/api/projects/{pid}").json()
    assert all(scan["metadata"]["event"] is None for scan in project["scans"])
    assert project["scans"][1]["id"] == second["id"]


def test_front_back_pairing_ocr_and_acceptance(monkeypatch):
    pid = _create_project()["id"]
    upload = client.post(
        f"/api/projects/{pid}/scans?detect=false",
        files=[
            ("files", ("front.png", _photo_png(), "image/png")),
            ("files", ("back.png", _photo_png(), "image/png")),
        ],
    ).json()["scans"]
    front, back = upload
    paired = client.post(
        f"/api/projects/{pid}/scans/{front['id']}/pair", json={"back_scan_id": back["id"]}
    )
    assert paired.status_code == 200
    assert client.get(f"/api/projects/{pid}").json()["scans"][1]["back_of"] == front["id"]

    monkeypatch.setattr("scansplitter.archival.transcribe_image", lambda path, language: "June 1975")
    started = client.post(f"/api/projects/{pid}/scans/{back['id']}/ocr", json={"language": "eng"})
    job = _wait_for_job(started.json()["job_id"])
    assert job["result"]["text"] == "June 1975"
    accepted = client.post(
        f"/api/projects/{pid}/scans/{back['id']}/ocr/accept",
        json={"text": "June 1975", "append_to_front_caption": True},
    )
    assert accepted.json()["ocr_reviewed"] is True
    project = client.get(f"/api/projects/{pid}").json()
    assert project["scans"][0]["metadata"]["caption"] == "Back inscription: June 1975"


def test_geocode_is_explicit_and_names_provider(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self): return b'[{"display_name":"Antwerp, Belgium","lat":"51.2","lon":"4.4"}]'

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Response())
    response = client.post("/api/geocode", json={"query": "Antwerp"})
    assert response.status_code == 200
    assert response.json()["provider"] == "OpenStreetMap Nominatim"
    assert response.json()["results"][0]["latitude"] == 51.2


def test_project_jpeg_export_embeds_exif_xmp_and_gates_gps(monkeypatch):
    _install_confidence(monkeypatch, lambda *a, **k: [])
    pid = _create_project()["id"]
    upload = client.post(
        f"/api/projects/{pid}/scans?detect=false",
        files=[("files", ("archive.png", _photo_png(), "image/png"))],
    )
    sid = upload.json()["scans"][0]["id"]
    box = {"id": "b1", "x": 400, "y": 300, "width": 300, "height": 200, "angle": 0}
    client.patch(f"/api/projects/{pid}/scans/{sid}", json={"boxes": [box]})
    client.patch(f"/api/projects/{pid}/scans/{sid}", json={"status": "approved"})
    metadata = {
        "date": "1975-06-01", "date_label": "summer 1975", "date_precision": "season",
        "place_name": "Antwerp", "latitude": 51.2194, "longitude": 4.4025,
        "caption": "At the station", "people": ["Ada"], "event": "Visit", "album": "Roll 2",
    }
    assert client.patch(f"/api/projects/{pid}/scans/{sid}/metadata", json=metadata).status_code == 200

    def exported(include_gps):
        started = client.post(f"/api/projects/{pid}/export", json={"format": "jpeg", "include_gps": include_gps})
        job = _wait_for_job(started.json()["job_id"])
        archive = zipfile.ZipFile(io.BytesIO(client.get(job["result"]["download_url"]).content))
        return archive.read(archive.namelist()[0])

    without_gps = exported(False)
    exif = piexif.load(without_gps)
    assert exif["Exif"][piexif.ExifIFD.DateTimeOriginal] == b"1975:06:01 00:00:00"
    assert not exif["GPS"]
    assert b"summer 1975" in without_gps
    assert b"At the station" in without_gps
    assert b"Person: Ada" in without_gps

    with_gps = piexif.load(exported(True))
    assert with_gps["GPS"][piexif.GPSIFD.GPSLatitudeRef] == b"N"
    assert with_gps["GPS"][piexif.GPSIFD.GPSLongitudeRef] == b"E"


# --- Export -----------------------------------------------------------------


def test_export_job_produces_zip_with_expected_names(monkeypatch):
    _install_confidence(monkeypatch, lambda *a, **k: [])
    pid = _create_project()["id"]
    upload = client.post(
        f"/api/projects/{pid}/scans?detect=false",
        files=[("files", ("Vacation.png", _photo_png(), "image/png"))],
    )
    sid = upload.json()["scans"][0]["id"]

    # Two boxes, both approved via auto-approve path -> both exported.
    boxes = [
        {"id": "b1", "x": 250, "y": 200, "width": 200, "height": 150, "angle": 0},
        {"id": "b2", "x": 550, "y": 400, "width": 200, "height": 150, "angle": 0},
    ]
    client.patch(f"/api/projects/{pid}/scans/{sid}", json={"boxes": boxes})
    client.patch(f"/api/projects/{pid}/scans/{sid}", json={"status": "approved"})

    started = client.post(f"/api/projects/{pid}/export", json={"format": "jpeg"})
    assert started.status_code == 202, started.text
    job = _wait_for_job(started.json()["job_id"])
    assert job["status"] == "succeeded", job

    download = client.get(job["result"]["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = sorted(archive.namelist())
        assert names == ["Vacation_1.jpg", "Vacation_2.jpg"]
        for name in names:
            assert archive.read(name)


def test_restoration_preview_job_returns_inline_jpeg(monkeypatch):
    _install_confidence(monkeypatch, lambda *a, **k: [])
    pid = _create_project()["id"]
    upload = client.post(
        f"/api/projects/{pid}/scans?detect=false",
        files=[("files", ("tilted.png", _photo_png(), "image/png"))],
    )
    sid = upload.json()["scans"][0]["id"]
    box = {"id": "photo-1", "x": 400, "y": 300, "width": 400, "height": 300, "angle": 0}
    client.patch(f"/api/projects/{pid}/scans/{sid}", json={"boxes": [box]})

    started = client.post(
        f"/api/projects/{pid}/scans/{sid}/restoration-preview",
        json={"box_id": "photo-1"},
    )
    assert started.status_code == 202
    job = _wait_for_job(started.json()["job_id"])
    assert job["status"] == "succeeded", job
    assert "detail" in job["result"]
    download = client.get(job["result"]["download_url"])
    assert download.headers["content-type"] == "image/jpeg"
    assert download.headers["content-disposition"].startswith("inline;")
    assert Image.open(io.BytesIO(download.content)).format == "JPEG"


def test_phase4_export_adds_master_folders_and_manifests(monkeypatch):
    _install_confidence(monkeypatch, lambda *a, **k: [])
    pid = _create_project()["id"]
    scan = client.post(
        f"/api/projects/{pid}/scans?detect=false",
        files=[("files", ("archive.png", _photo_png(), "image/png"))],
    ).json()["scans"][0]
    box = {"id": "b1", "x": 400, "y": 300, "width": 300, "height": 200, "angle": 0}
    client.patch(f"/api/projects/{pid}/scans/{scan['id']}", json={"boxes": [box]})
    client.patch(f"/api/projects/{pid}/scans/{scan['id']}", json={"status": "approved"})
    client.patch(
        f"/api/projects/{pid}/scans/{scan['id']}/metadata",
        json={"date": "1975-01-01", "date_precision": "year", "album": "Family", "event": "Picnic"},
    )
    started = client.post(
        f"/api/projects/{pid}/export",
        json={"master_format": "tiff", "organize_folders": True, "manifest_format": "both"},
    )
    job = _wait_for_job(started.json()["job_id"])
    archive = zipfile.ZipFile(io.BytesIO(client.get(job["result"]["download_url"]).content))
    names = archive.namelist()
    assert "Family/1975/Picnic/archive_1.jpg" in names
    assert "masters/Family/1975/Picnic/archive_1.tif" in names
    assert "digitization-manifest.json" in names
    assert "digitization-manifest.csv" in names
    manifest = json.loads(archive.read("digitization-manifest.json"))
    assert manifest[0]["box_id"] == "b1"
    assert len(manifest[0]["sha256"]) == 64


def test_watched_folder_delivery_writes_canonical_artifacts(monkeypatch, tmp_path):
    _install_confidence(monkeypatch, lambda *a, **k: [])
    pid = _create_project()["id"]
    scan = client.post(
        f"/api/projects/{pid}/scans?detect=false",
        files=[("files", ("one.png", _photo_png(), "image/png"))],
    ).json()["scans"][0]
    box = {"id": "b1", "x": 400, "y": 300, "width": 300, "height": 200, "angle": 0}
    client.patch(f"/api/projects/{pid}/scans/{scan['id']}", json={"boxes": [box]})
    client.patch(f"/api/projects/{pid}/scans/{scan['id']}", json={"status": "approved"})
    destination = tmp_path / "watched"
    started = client.post(
        f"/api/projects/{pid}/deliver",
        json={"target": "folder", "destination": str(destination)},
    )
    job = _wait_for_job(started.json()["job_id"])
    assert job["status"] == "succeeded", job
    assert (destination / "Unsorted" / "one_1.jpg").exists()
    assert (destination / "digitization-manifest.json").exists()


# --- Path safety ------------------------------------------------------------


def test_project_id_traversal_is_rejected(data_dir):
    # A traversal attempt must 404 without touching the filesystem outside the
    # data dir. Starlette percent-decodes "%2e%2e%2fx" into "../x" only after
    # routing, so the id validator (hex only) rejects it before any path is
    # built. Uploading to such an id must likewise 404.
    for pid in ("%2e%2e%2fx", "not-hex-id", "0" * 31):
        assert client.get(f"/api/projects/{pid}").status_code == 404
        assert (
            client.post(
                f"/api/projects/{pid}/scans?detect=false",
                files=[("files", ("x.png", _solid_png(), "image/png"))],
            ).status_code
            == 404
        )

    # No stray files/dirs escaped the projects root (which stays empty).
    assert list((data_dir / "projects").glob("*")) == []
    assert not (data_dir.parent / "x").exists()


def test_unknown_project_returns_404():
    assert client.get(f"/api/projects/{'0' * 32}").status_code == 404
    assert client.delete(f"/api/projects/{'0' * 32}").status_code in (200, 404)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
