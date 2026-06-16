"""Encrypt and decrypt application auth_config at rest (SPEC §23.1, Day 12)."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

ENC_VERSION = "v1"
ENV_KEY = "ENCRYPTION_KEY"


class EncryptionKeyError(RuntimeError):
    """Raised when encryption is required but ENCRYPTION_KEY is missing or invalid."""


def encryption_key_configured() -> bool:
    return bool(os.getenv(ENV_KEY, "").strip())


def _load_key() -> bytes:
    raw = os.getenv(ENV_KEY, "").strip()
    if not raw:
        raise EncryptionKeyError(f"{ENV_KEY} is not set")
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise EncryptionKeyError(f"{ENV_KEY} must be a 64-character hex string") from exc
    if len(key) != 32:
        raise EncryptionKeyError(f"{ENV_KEY} must decode to 32 bytes (AES-256)")
    return key


def encrypt_auth_config(plain: dict[str, Any]) -> dict[str, Any]:
    """Return encrypted envelope with public `type` for API sanitization."""
    if not plain:
        return {}

    key = _load_key()
    nonce = os.urandom(12)
    payload = json.dumps(plain, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, payload, None)

    return {
        "_enc": ENC_VERSION,
        "type": plain.get("type", "form"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_auth_config(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Decrypt auth_config for worker use only — never expose via API."""
    if not stored:
        return {}
    if stored.get("_enc") != ENC_VERSION:
        return dict(stored)

    key = _load_key()
    nonce = base64.b64decode(stored["nonce"])
    ciphertext = base64.b64decode(stored["ciphertext"])
    plain_bytes = AESGCM(key).decrypt(nonce, ciphertext, None)
    return json.loads(plain_bytes.decode("utf-8"))


def is_encrypted_auth_config(stored: dict[str, Any] | None) -> bool:
    return bool(stored and stored.get("_enc") == ENC_VERSION)


def prepare_auth_config_for_storage(
    plain: dict[str, Any],
    *,
    allow_plaintext: bool,
) -> dict[str, Any]:
    if not plain:
        return {}
    if encryption_key_configured():
        return encrypt_auth_config(plain)
    if not allow_plaintext:
        raise EncryptionKeyError(f"{ENV_KEY} is required to store auth_config")
    logger.warning("Storing auth_config without encryption (development only)")
    return plain
