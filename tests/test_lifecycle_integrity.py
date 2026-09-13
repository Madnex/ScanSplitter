"""Audit regressions for archival fidelity, transactional writes and races."""
import hashlib
import io
import json
import threading
import time
import zipfile

import pytest
from fastapi import HTTPException
from PIL import Image

from scansplitter import projects
from scansplitter.jobs import JobCancelled, registry
from scansplitter.projects import ProjectStore


def png(color="red"):
    output = io.BytesIO()
    Image.new("RGB", (120, 100), color).save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects")


def add(store):
    pid = store.create_project("Audit")["id"]
    scan = store.add_scans(pid, [("source.png", png())])[0]
    return pid, scan


def box():
    return {"id": "crop", "x": 60, "y": 50, "width": 80, "height": 60, "angle": 0}


def test_original_bytes_checksum_and_failed_batch_rollback(store):
    pid, scan = add(store)
    source = store.root / pid / scan["source_file"]
    assert source.read_bytes() == png()
    assert scan["source_sha256"] == hashlib.sha256(png()).hexdigest()
    before = sorted(str(p.relative_to(store.root)) for p in store.root.rglob("*") if p.is_file())
    with pytest.raises(HTTPException):
        store.add_scans(pid, [("ok.png", png("blue")), ("bad.png", b"not an image")])
    after = sorted(str(p.relative_to(store.root)) for p in store.root.rglob("*") if p.is_file())
    assert before == after
    assert len(store.get_project(pid)["scans"]) == 1


def test_restart_recovers_without_replaying_jobs(store):
    pid, scan = add(store)
    store._persist_scan_fields(pid, scan["id"], {"status": "detecting"})
    reopened = ProjectStore(store.root)
    recovered = reopened.get_scan(pid, scan["id"])
    assert recovered["status"] == "pending"
    assert "interrupted" in recovered["interruption"]


def test_stale_detection_cannot_overwrite_edit(store, monkeypatch):
    pid, scan = add(store)
    started, release = threading.Event(), threading.Event()
    def detector(*args):
        started.set()
        assert release.wait(5)
        return []
    monkeypatch.setattr(projects, "_detect", detector)
    job_id = store.submit_detect_job(pid, scan["id"])
    assert started.wait(5)
    assert store.submit_detect_job(pid, scan["id"]) == job_id
    store.update_scan(pid, scan["id"], [box()], "approved")
    release.set()
    deadline = time.monotonic() + 5
    while registry.get(job_id).status in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(.01)
    saved = store.get_scan(pid, scan["id"])
    assert saved["boxes"][0]["id"] == "crop"
    assert saved["status"] == "approved"


def test_cancel_at_first_progress_recovers_scan(store):
    pid, scan = add(store)
    store._persist_scan_fields(pid, scan["id"], {"status": "detecting"})
    def cancel(*args):
        raise JobCancelled
    with pytest.raises(JobCancelled):
        store._detect_and_persist(pid, scan["id"], cancel, lambda: True)
    assert store.get_scan(pid, scan["id"])["status"] == "pending"


@pytest.mark.parametrize("settings", [{"quality": -3}, {"auto_rotate": "false"}, {"min_area_ratio": "invalid"}, {"min_area_ratio": 90, "max_area_ratio": 80}, {"unknown": True}])
def test_settings_reject_invalid_values_atomically(store, settings):
    pid, _ = add(store)
    before = store.get_project(pid)
    with pytest.raises(HTTPException):
        store.update_project(pid, settings=settings)
    assert store.get_project(pid) == before


@pytest.mark.parametrize("boxes", [[{**box(), "width": 0}], [box(), box()], [{**box(), "x": float("nan")}], [{**box(), "height": 99999}]])
def test_geometry_validation(store, boxes):
    pid, scan = add(store)
    with pytest.raises(HTTPException):
        store.update_scan(pid, scan["id"], boxes)
    assert store.get_scan(pid, scan["id"])["boxes"] == []


def test_single_and_zip_exports_share_pixels_metadata_and_rotation(store):
    pid, scan = add(store)
    store.update_project(pid, settings={"auto_rotate": False, "edge_cleanup_mode": "off"})
    store.update_scan(pid, scan["id"], [{**box(), "restoration": {"manual_rotation": 90}}], "approved")
    store.update_metadata(pid, None, {"caption": "Keepsake", "date": "1980-03-04"})
    single = store.export_photo(pid, scan["id"], "crop", "png")
    archive = store._build_export_zip(pid, "png", 85, False, lambda *args: None, lambda: False)
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        assert single == zf.read(zf.namelist()[0])
    assert Image.open(io.BytesIO(single)).size == (60, 80)


def test_pairing_rejects_chains_and_cycles(store):
    pid, a = add(store)
    b, c = store.add_scans(pid, [("b.png", png()), ("c.png", png())])
    store.pair_scans(pid, a["id"], b["id"])
    for front, back in [(b, a), (b, c), (c, a)]:
        with pytest.raises(HTTPException):
            store.pair_scans(pid, front["id"], back["id"])
    store.pair_scans(pid, a["id"], None)
    store.pair_scans(pid, b["id"], c["id"])


def test_legacy_source_is_explicit(store):
    pid, scan = add(store)
    path = store.root / pid / "project.json"
    data = json.loads(path.read_text())
    data["version"] = 1
    data["scans"][0].pop("source_integrity")
    data["scans"][0].pop("source_file")
    path.write_text(json.dumps(data))
    assert store.get_scan(pid, scan["id"])["source_integrity"] == "legacy_derivative"


def test_revision_conflict_retains_newer_edit(store):
    pid, scan = add(store)
    updated = store.update_scan(pid, scan["id"], [box()], revision=0)
    with pytest.raises(HTTPException) as error:
        store.update_scan(pid, scan["id"], [], revision=0)
    assert error.value.status_code == 409
    assert store.get_scan(pid, scan["id"])["boxes"] == updated["boxes"]


def test_delivery_resumes_confirmed_files_and_checks_cancellation(tmp_path):
    from scansplitter.delivery import DeliveryJournal, write_watched_folder
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("one.png", png())
        archive.writestr("two.png", png("blue"))
    target = tmp_path / "out"
    target.mkdir()
    journal_path = tmp_path / "journal.json"
    journal = DeliveryJournal(journal_path, lambda: (target / "one.png").exists())
    with pytest.raises(JobCancelled):
        write_watched_folder(payload.getvalue(), target, journal=journal)
    assert json.loads(journal_path.read_text()).keys() == {"one.png"}
    retry = DeliveryJournal(journal_path, lambda: False)
    assert write_watched_folder(payload.getvalue(), target, journal=retry) == 1
    assert retry.skipped == 1
    assert (target / "two.png").read_bytes() == png("blue")


def test_pdf_retains_source_and_exports_at_300_dpi(store):
    import pymupdf
    document = pymupdf.open()
    page = document.new_page(width=72, height=72)
    page.draw_rect((0, 0, 72, 72), fill=(1, 0, 0))
    payload = document.tobytes()
    document.close()
    pid = store.create_project("PDF")["id"]
    scan = store.add_scans(pid, [("page.pdf", payload)])[0]
    assert (store.root / pid / scan["source_file"]).read_bytes() == payload
    assert scan["width"] == 150
    store.update_project(pid, settings={"auto_rotate": False, "edge_cleanup_mode": "off"})
    store.update_scan(pid, scan["id"], [{"id": "full", "x": 75, "y": 75, "width": 150, "height": 150, "angle": 0}])
    image = Image.open(io.BytesIO(store.export_photo(pid, scan["id"], "full", "png")))
    assert image.size == (300, 300)


def test_pdf_pixel_limit_is_checked_before_render(tmp_path, monkeypatch):
    import pymupdf

    from scansplitter.pdf_handler import extract_pdf_page
    document = pymupdf.open()
    document.new_page(width=10000, height=10000)
    path = tmp_path / "large.pdf"
    document.save(path)
    document.close()
    render = pytest.MonkeyPatch()
    def unexpected(*args, **kwargs):
        pytest.fail("Oversize PDF reached pixel allocation")
    render.setattr(pymupdf.Page, "get_pixmap", unexpected)
    try:
        with pytest.raises(ValueError, match="pixel"):
            extract_pdf_page(path, 1)
    finally:
        render.undo()


def test_high_bit_depth_tiff_original_is_retained(store):
    image = Image.new("I;16", (20, 20))
    image.putpixel((10, 10), 45000)
    output = io.BytesIO()
    image.save(output, "TIFF")
    pid = store.create_project("16-bit original")["id"]
    scan = store.add_scans(pid, [("original.tiff", output.getvalue())])[0]
    retained = (store.root / pid / scan["source_file"]).read_bytes()
    assert retained == output.getvalue()
    assert Image.open(io.BytesIO(retained)).getpixel((10, 10)) == 45000


def test_profiled_source_is_retained_and_rendered_in_srgb(store):
    from PIL import ImageCms
    image = Image.new("RGB", (120, 100), (160, 90, 50))
    output = io.BytesIO()
    image.save(output, "PNG", icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    pid = store.create_project("Profiled original")["id"]
    scan = store.add_scans(pid, [("profiled.png", output.getvalue())])[0]
    assert (store.root / pid / scan["source_file"]).read_bytes() == output.getvalue()
    assert store._source_image(pid, scan).getpixel((0, 0)) == (160, 90, 50)


def test_queue_saturation_does_not_leave_scan_detecting(store, monkeypatch):
    from scansplitter import jobs
    pid, scan = add(store)
    monkeypatch.setattr(jobs, "_queue_slots", threading.BoundedSemaphore(0))
    with pytest.raises(HTTPException) as error:
        store.submit_detect_job(pid, scan["id"])
    assert error.value.status_code == 429
    assert store.get_scan(pid, scan["id"])["status"] == "pending"
