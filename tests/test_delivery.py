import io
import urllib.error
import zipfile

import pytest
from fastapi import HTTPException

from scansplitter.delivery import (
    archive_files,
    upload_immich,
    upload_nextcloud,
    write_watched_folder,
)


def _archive() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("photo.jpg", b"jpeg")
        archive.writestr("digitization-manifest.json", b"[]")
    return output.getvalue()


def _png_archive() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("photo.png", b"png")
    return output.getvalue()


def test_archive_files_and_delivery_url_validation():
    assert next(archive_files(_archive())) == ("photo.jpg", b"jpeg")
    with pytest.raises(HTTPException):
        upload_immich(_archive(), "file:///tmp", "secret")
    with pytest.raises(HTTPException):
        upload_nextcloud(_archive(), "ftp://cloud", "user", "pass", "folder")


def test_immich_and_nextcloud_requests_are_explicit_and_authenticated(monkeypatch):
    requests = []

    class Response:
        status = 201
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None

    def open_request(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    assert upload_immich(_archive(), "https://photos.example", "immich-secret") == 1
    immich = requests[0][0]
    assert immich.full_url == "https://photos.example/api/assets"
    assert immich.headers["X-api-key"] == "immich-secret"
    assert b'name="assetData"' in immich.data
    assert b'name="fileCreatedAt"' in immich.data
    assert b'name="fileModifiedAt"' in immich.data
    assert b'name="deviceAssetId"' not in immich.data
    assert b'name="deviceId"' not in immich.data
    assert b"Content-Type: image/jpeg" in immich.data

    requests.clear()
    assert upload_immich(_png_archive(), "https://photos.example/api", "immich-secret") == 1
    assert requests[0][0].full_url == "https://photos.example/api/assets"
    assert b"Content-Type: image/png" in requests[0][0].data

    requests.clear()
    assert upload_nextcloud(
        _archive(), "https://cloud.example/remote.php/dav/files/ada", "ada", "app-pass", "Photos"
    ) == 2
    assert requests[0][0].get_method() == "PUT"
    assert requests[0][0].headers["Authorization"].startswith("Basic ")
    assert requests[0][0].headers["X-nc-webdav-auto-mkcol"] == "1"
    assert requests[0][0].headers["X-nc-webdav-automkcol"] == "1"
    assert requests[0][0].full_url.endswith("/Photos/photo.jpg")


def test_nextcloud_409_creates_collections_and_retries(monkeypatch):
    requests = []

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    put_attempts = 0

    def open_request(request, timeout):
        nonlocal put_attempts
        requests.append(request)
        if request.get_method() == "PUT":
            put_attempts += 1
            if put_attempts == 1:
                raise urllib.error.HTTPError(request.full_url, 409, "Conflict", {}, None)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    assert upload_nextcloud(
        _archive(), "https://cloud.example/dav", "ada", "pass", "Photos/Scans"
    ) == 2
    methods = [request.get_method() for request in requests]
    assert methods[:4] == ["PUT", "MKCOL", "MKCOL", "PUT"]


def test_watched_folder_conflicts_require_overwrite(tmp_path):
    destination = tmp_path / "watched"
    destination.mkdir()
    (destination / "photo.jpg").write_bytes(b"old")
    with pytest.raises(HTTPException) as exc:
        write_watched_folder(_archive(), destination)
    assert exc.value.status_code == 409
    assert "photo.jpg" in exc.value.detail
    assert write_watched_folder(_archive(), destination, overwrite=True) == 2
    assert (destination / "photo.jpg").read_bytes() == b"jpeg"
