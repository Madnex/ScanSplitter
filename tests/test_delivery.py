import io
import zipfile

import pytest
from fastapi import HTTPException

from scansplitter.delivery import archive_files, upload_immich, upload_nextcloud


def _archive() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("photo.jpg", b"jpeg")
        archive.writestr("digitization-manifest.json", b"[]")
    return output.getvalue()


def test_archive_files_and_delivery_url_validation():
    assert archive_files(_archive())[0] == ("photo.jpg", b"jpeg")
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
    assert b'name="deviceAssetId"' in immich.data
    assert b'name="assetData"' in immich.data

    requests.clear()
    assert upload_nextcloud(
        _archive(), "https://cloud.example/remote.php/dav/files/ada", "ada", "app-pass", "Photos"
    ) == 2
    assert requests[0][0].get_method() == "PUT"
    assert requests[0][0].headers["Authorization"].startswith("Basic ")
    assert requests[0][0].full_url.endswith("/Photos/photo.jpg")
