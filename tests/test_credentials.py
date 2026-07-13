"""Tests for system-vault delivery credential persistence."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from scansplitter import api as api_module
from scansplitter import credentials

client = TestClient(api_module.app)


def test_credential_store_round_trip_never_exposes_secret(monkeypatch):
    vault: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(credentials.keyring, "get_keyring", lambda: SimpleNamespace(priority=1))
    monkeypatch.setattr(
        credentials.keyring,
        "set_password",
        lambda service, account, value: vault.__setitem__((service, account), value),
    )
    monkeypatch.setattr(
        credentials.keyring,
        "get_password",
        lambda service, account: vault.get((service, account)),
    )
    monkeypatch.setattr(
        credentials.keyring,
        "delete_password",
        lambda service, account: vault.pop((service, account)),
    )

    config = {"server_url": " https://photos.example/api ", "api_key": " secret "}
    credentials.save_delivery_credentials("immich", config)
    loaded = credentials.load_delivery_credentials("immich")

    assert loaded == {"server_url": "https://photos.example/api", "api_key": "secret"}
    assert credentials.public_delivery_credentials("immich", loaded) == {
        "target": "immich",
        "saved": True,
        "storage_available": True,
        "server_url": "https://photos.example/api",
    }
    assert credentials.delete_delivery_credentials("immich") is True
    assert credentials.load_delivery_credentials("immich") is None


def test_null_keyring_is_reported_as_unavailable(monkeypatch):
    monkeypatch.setattr(credentials.keyring, "get_keyring", lambda: SimpleNamespace(priority=0))
    with pytest.raises(credentials.CredentialStoreError, match="unavailable"):
        credentials.load_delivery_credentials("immich")


def test_saved_credentials_are_merged_server_side(monkeypatch):
    captured: dict = {}

    def submit_delivery_job(pid, target, config):
        captured.update({"pid": pid, "target": target, "config": config})
        return "job-1"

    monkeypatch.setenv("SCANSPLITTER_LOCAL_MODE", "1")
    monkeypatch.setattr(
        credentials,
        "load_delivery_credentials",
        lambda target: {"server_url": "https://old.example", "api_key": "saved-secret"},
    )
    monkeypatch.setattr(
        api_module,
        "get_project_store",
        lambda: SimpleNamespace(submit_delivery_job=submit_delivery_job),
    )

    response = client.post(
        "/api/projects/project-1/deliver",
        json={
            "target": "immich",
            "server_url": "https://new.example",
            "use_saved_credentials": True,
        },
    )

    assert response.status_code == 202
    assert response.json() == {"job_id": "job-1"}
    assert captured == {
        "pid": "project-1",
        "target": "immich",
        "config": {
            "server_url": "https://new.example",
            "api_key": "saved-secret",
            "include_gps": False,
            "organize_folders": True,
            "manifest_format": "both",
            "overwrite": False,
        },
    }


def test_credential_api_returns_public_fields_and_handles_unavailable_store(monkeypatch):
    monkeypatch.setenv("SCANSPLITTER_LOCAL_MODE", "1")
    monkeypatch.setattr(
        credentials,
        "load_delivery_credentials",
        lambda target: {
            "base_url": "https://cloud.example/dav",
            "username": "jan",
            "password": "never-return-this",
            "folder": "Photos",
        },
    )
    response = client.get("/api/delivery-credentials/nextcloud")
    assert response.status_code == 200
    assert response.json() == {
        "target": "nextcloud",
        "saved": True,
        "storage_available": True,
        "base_url": "https://cloud.example/dav",
        "username": "jan",
        "folder": "Photos",
    }
    assert "never-return-this" not in response.text

    def unavailable(target):
        raise credentials.CredentialStoreError("The system credential store is unavailable")

    monkeypatch.setattr(credentials, "load_delivery_credentials", unavailable)
    response = client.get("/api/delivery-credentials/immich")
    assert response.status_code == 200
    assert response.json() == {
        "target": "immich",
        "saved": False,
        "storage_available": False,
        "error": "The system credential store is unavailable",
    }


@pytest.mark.parametrize("flag", ["use_saved_credentials", "remember_credentials"])
def test_saved_credentials_are_disabled_outside_local_mode(monkeypatch, flag):
    monkeypatch.setenv("SCANSPLITTER_LOCAL_MODE", "0")
    response = client.post(
        "/api/projects/project-1/deliver",
        json={
            "target": "immich",
            "server_url": "https://photos.example",
            "api_key": "one-time-secret",
            flag: True,
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Saved credentials require local mode"
