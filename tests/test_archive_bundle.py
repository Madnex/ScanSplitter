import hashlib
import io
import json
import zipfile

import pytest
from fastapi import HTTPException
from PIL import Image

from scansplitter.archive_bundle import build_archive_bundle
from scansplitter.projects import ProjectStore


def make_store(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    project = store.create_project("Test album")
    image = io.BytesIO()
    Image.new("RGB", (100, 80), "red").save(image, "PNG")
    scan = store.add_scans(project["id"], [("page.png", image.getvalue())])[0]
    store.update_scan(
        project["id"],
        scan["id"],
        boxes=[
            {
                "id": "crop/../../evil",
                "x": 50,
                "y": 40,
                "width": 40,
                "height": 30,
                "angle": 0,
            }
        ],
        status="approved",
    )
    return store, project, scan, image.getvalue()


def export(store, project, path, originals=True):
    return build_archive_bundle(
        store,
        project["id"],
        "png",
        85,
        False,
        "png",
        originals,
        lambda *args: None,
        lambda: False,
        path,
    )


def test_bundle_provenance_safe_names_originals_and_stable_identity(tmp_path):
    store, project, scan, original = make_store(tmp_path)
    manifests = []
    for name in ("one.zip", "two.zip"):
        with zipfile.ZipFile(export(store, project, tmp_path / name)) as archive:
            manifest = json.loads(archive.read("archive-manifest.json"))
            manifests.append(manifest)
            assert manifest["schema"] == "scansplitter.archive-bundle"
            assert manifest["scans"][0]["coordinate_size"] == [100, 80]
            assert manifest["photos"][0]["geometry"]["center"] == [0.5, 0.5]
            for file in manifest["files"]:
                assert ".." not in file["path"].split("/")
                assert hashlib.sha256(archive.read(file["path"])).hexdigest() == file["sha256"]
                if file["role"] == "source_original":
                    assert archive.read(file["path"]) == original
    assert manifests[0] == manifests[1]


def test_originals_opt_in_and_unreviewed_scans_excluded(tmp_path):
    store, project, scan, original = make_store(tmp_path)
    store.add_scans(project["id"], [("unreviewed.png", original)])
    with zipfile.ZipFile(export(store, project, tmp_path / "bundle.zip", False)) as archive:
        manifest = json.loads(archive.read("archive-manifest.json"))
        assert len(manifest["scans"]) == 1
        assert manifest["scans"][0]["source_file_id"] is None
        assert not any(f["role"] == "source_original" for f in manifest["files"])


def test_changed_original_rejected(tmp_path):
    store, project, scan, _ = make_store(tmp_path)
    (store._project_dir(project["id"]) / scan["source_file"]).write_bytes(b"corrupt")
    with pytest.raises(HTTPException, match="checksum mismatch"):
        export(store, project, tmp_path / "bundle.zip")


def test_legacy_original_not_invented(tmp_path):
    store, project, scan, _ = make_store(tmp_path)
    data = store._read(project["id"])
    data["scans"][0]["source_integrity"] = "legacy_derivative"
    store._write(project["id"], data)
    with pytest.raises(HTTPException, match="Original source unavailable"):
        export(store, project, tmp_path / "bundle.zip")


def test_gps_gate_and_effective_processing_settings(tmp_path):
    store, project, scan, _ = make_store(tmp_path)
    data = store._read(project["id"])
    data["scans"][0]["metadata"].update(latitude=50.8, longitude=4.3)
    data["scans"][0]["boxes"][0]["restoration"] = {"manual_rotation": 90}
    store._write(project["id"], data)
    with zipfile.ZipFile(export(store, project, tmp_path / "bundle.zip")) as archive:
        manifest = json.loads(archive.read("archive-manifest.json"))
        assert "latitude" not in manifest["scans"][0]["metadata"]
        assert "longitude" not in manifest["photos"][0]["metadata"]
        assert manifest["photos"][0]["transformations"]["manual_rotation"] == 90


def test_project_http_export_downloads_generic_bundle(tmp_path, monkeypatch):
    import time

    from fastapi.testclient import TestClient

    from scansplitter import api

    store, project, scan, _ = make_store(tmp_path)
    monkeypatch.setattr(api, "get_project_store", lambda: store)
    client = TestClient(api.app)
    response = client.post(
        f"/api/projects/{project['id']}/export",
        json={"archive_bundle": True, "include_originals": True},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.01)
    assert job["status"] == "succeeded", job
    response = client.get(job["result"]["download_url"])
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert (
            json.loads(archive.read("archive-manifest.json"))["schema"]
            == "scansplitter.archive-bundle"
        )
    assert (
        client.post(
            f"/api/projects/{project['id']}/scans/{scan['id']}/export",
            json={"archive_bundle": True},
        ).status_code
        == 400
    )
