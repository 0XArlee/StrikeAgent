"""Strike API-wallet request signing (docs: api/getting-started "API Wallet Authentication", snapshot 2026-10-19).

Message: ``{METHOD}:{PATH}:{TIMESTAMP}:{NONCE}:{BODY_HASH}`` where PATH includes the query string, TIMESTAMP is Unix
seconds (server accepts +-3 min), NONCE is a fresh UUID v4 and BODY_HASH is the SHA-256 hex of the exact body bytes
sent (empty string for GET). Ed25519 over the UTF-8 message; signature as hex.

Keys: raw Ed25519, public 64 hex chars; private 64 hex (seed) or 128 hex (seed + public). The private key never
leaves this object: it is not logged, not repr'd, not serialised.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def serialize_body(body: dict | None) -> str:
    """Serialise once; the signed bytes must be the sent bytes (compact JSON, like the official Python example)."""
    return "" if body is None else json.dumps(body, separators=(",", ":"), ensure_ascii=False)


def generate_keypair() -> tuple[str, str]:
    """New API-wallet key pair ``(private_hex_64, public_hex_64)``. Register the public key on app.strikefinance.org
    (API Wallets page) or pass it to the builder-connect flow."""
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                           serialization.NoEncryption()).hex()
    pub = k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    return priv, pub


class ApiWalletSigner:
    def __init__(self, private_key_hex: str, public_key_hex: str | None = None):
        raw = bytes.fromhex(private_key_hex.strip())
        if len(raw) == 64:
            raw = raw[:32]
        if len(raw) != 32:
            raise ValueError("Ed25519 private key must be 32 bytes (64 hex) or 64 bytes (128 hex)")
        self._key = Ed25519PrivateKey.from_private_bytes(raw)
        derived = self._key.public_key().public_bytes(serialization.Encoding.Raw,
                                                      serialization.PublicFormat.Raw).hex()
        if public_key_hex and public_key_hex.strip().lower() != derived:
            raise ValueError("public key does not match the private key")
        self.public_key = derived

    def __repr__(self) -> str:  # never leak the key
        return f"ApiWalletSigner(public_key={self.public_key[:8]}…)"

    @classmethod
    def from_env(cls, prefix: str = "STRIKE_API") -> "ApiWalletSigner":
        priv = os.environ.get(f"{prefix}_PRIVATE_KEY")
        if not priv:
            raise RuntimeError(f"{prefix}_PRIVATE_KEY is not set")
        return cls(priv, os.environ.get(f"{prefix}_PUBLIC_KEY"))

    @staticmethod
    def message(method: str, path: str, timestamp: int, nonce: str, body: str) -> str:
        body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return f"{method.upper()}:{path}:{timestamp}:{nonce}:{body_hash}"

    def headers(self, method: str, path: str, body: str = "", timestamp: int | None = None,
                nonce: str | None = None) -> dict[str, str]:
        ts = int(time.time()) if timestamp is None else timestamp
        nc = str(uuid.uuid4()) if nonce is None else nonce
        sig = self._key.sign(self.message(method, path, ts, nc, body).encode("utf-8")).hex()
        return {
            "X-API-Wallet-Public-Key": self.public_key,
            "X-API-Wallet-Signature": sig,
            "X-API-Wallet-Timestamp": str(ts),
            "X-API-Wallet-Nonce": nc,
        }

    def ws_logon(self, timestamp_ms: int | None = None) -> dict:
        """``session.logon`` payload for the user-api WebSocket (strike-builder-reference ws/userStream.ts):
        message ``session.logon:{timestamp_ms}:{publicKey}``. Not yet verified against a live server."""
        ts = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
        sig = self._key.sign(f"session.logon:{ts}:{self.public_key}".encode()).hex()
        return {"method": "session.logon", "id": 1,
                "params": {"apiKey": self.public_key, "signature": sig, "timestamp": ts}}


def verify(public_key_hex: str, message: str, signature_hex: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(bytes.fromhex(signature_hex),
                                                                                 message.encode("utf-8"))
        return True
    except Exception:
        return False
