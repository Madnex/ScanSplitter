"""Secure persistence for external delivery credentials.

Credentials are stored as a small JSON document in the operating system's
credential vault through ``keyring``.  They are never written to project data
or returned to the frontend with secret fields intact.
"""

from __future__ import annotations

import json
from typing import Any

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE_NAME = "ScanSplitter delivery"

DELIVERY_CREDENTIAL_FIELDS: dict[str, tuple[str, ...]] = {
    "immich": ("server_url", "api_key"),
    "nextcloud": ("base_url", "username", "password", "folder"),
}

DELIVERY_SECRET_FIELDS: dict[str, frozenset[str]] = {
    "immich": frozenset({"api_key"}),
    "nextcloud": frozenset({"password"}),
}


class CredentialStoreError(RuntimeError):
    """The operating system credential store could not complete an operation."""


def _ensure_available() -> None:
    try:
        priority = keyring.get_keyring().priority
    except (KeyringError, RuntimeError) as exc:
        raise CredentialStoreError("The system credential store is unavailable") from exc
    if priority <= 0:
        raise CredentialStoreError("The system credential store is unavailable")


def _validate_target(target: str) -> None:
    if target not in DELIVERY_CREDENTIAL_FIELDS:
        raise ValueError("Credential storage is only available for Immich and Nextcloud")


def _clean_config(target: str, config: dict[str, Any]) -> dict[str, str]:
    fields = DELIVERY_CREDENTIAL_FIELDS[target]
    return {
        field: value.strip()
        for field in fields
        if isinstance((value := config.get(field)), str) and value.strip()
    }


def save_delivery_credentials(target: str, config: dict[str, Any]) -> None:
    """Store one delivery connection in the current user's system vault."""
    _validate_target(target)
    _ensure_available()
    cleaned = _clean_config(target, config)
    missing_secrets = DELIVERY_SECRET_FIELDS[target] - cleaned.keys()
    if missing_secrets:
        raise ValueError(f"Missing secret fields: {', '.join(sorted(missing_secrets))}")
    payload = json.dumps({"version": 1, "config": cleaned}, separators=(",", ":"))
    try:
        keyring.set_password(SERVICE_NAME, target, payload)
    except (KeyringError, RuntimeError) as exc:
        raise CredentialStoreError("The system credential store is unavailable") from exc


def load_delivery_credentials(target: str) -> dict[str, str] | None:
    """Load a delivery connection, returning ``None`` when none is stored."""
    _validate_target(target)
    _ensure_available()
    try:
        payload = keyring.get_password(SERVICE_NAME, target)
    except (KeyringError, RuntimeError) as exc:
        raise CredentialStoreError("The system credential store is unavailable") from exc
    if payload is None:
        return None
    try:
        decoded = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CredentialStoreError("The stored delivery credential is invalid") from exc
    if not isinstance(decoded, dict) or not isinstance(decoded.get("config"), dict):
        raise CredentialStoreError("The stored delivery credential is invalid")
    return _clean_config(target, decoded["config"])


def delete_delivery_credentials(target: str) -> bool:
    """Delete a stored connection, returning whether one previously existed."""
    _validate_target(target)
    if load_delivery_credentials(target) is None:
        return False
    try:
        keyring.delete_password(SERVICE_NAME, target)
    except PasswordDeleteError as exc:
        raise CredentialStoreError("The stored delivery credential could not be removed") from exc
    except (KeyringError, RuntimeError) as exc:
        raise CredentialStoreError("The system credential store is unavailable") from exc
    return True


def public_delivery_credentials(target: str, config: dict[str, str]) -> dict[str, Any]:
    """Return saved connection metadata without exposing a secret value."""
    secret_fields = DELIVERY_SECRET_FIELDS[target]
    return {
        "target": target,
        "saved": True,
        "storage_available": True,
        **{key: value for key, value in config.items() if key not in secret_fields},
    }
