"""API-wallet key pairs for users' builder connect, kept only on the agents' host.

The site never sees a private key. It is given the public keys of unused pairs, sends one to Strike in
``POST /auth/builder/request-signature`` when a user connects, and Strike authorises that public key as the user's
API wallet for the Smart Flow builder code. The private key stays here, encrypted at rest with AES-256-GCM (master
key in ``/etc/smartflow/keys.key``, root:smartflow 0640); only the fleet process loads it, to sign that user's orders.
A key that was ever handed out is never offered again.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..strike.auth import ApiWalletSigner, generate_keypair

ENVS = ("testnet", "mainnet")


class KeyPool:
    def __init__(self, root: Path, master_key: bytes, env: str):
        if len(master_key) != 32:
            raise ValueError("the master key must be 32 bytes")
        if env not in ENVS:
            raise ValueError(f"env must be one of {ENVS}")
        self.root, self.env = Path(root), env
        self._aes = AESGCM(master_key)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

    @classmethod
    def from_files(cls, root: Path, key_file: Path, env: str) -> "KeyPool":
        return cls(root, bytes.fromhex(Path(key_file).read_text(encoding="utf-8").strip()), env)

    @staticmethod
    def new_master_key(path: Path) -> None:
        """Writes a new random master key (hex) if none exists; never overwrites one (that would lock every key)."""
        path = Path(path)
        if path.exists():
            return
        path.write_text(os.urandom(32).hex() + "\n", encoding="utf-8")

    def _path(self, pub: str) -> Path:
        return self.root / f"{self.env}-{pub}.json"

    def generate(self) -> str:
        priv, pub = generate_keypair()
        nonce = os.urandom(12)
        ct = self._aes.encrypt(nonce, bytes.fromhex(priv), f"{self.env}:{pub}".encode())
        p = self._path(pub)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"pub": pub, "env": self.env, "created": int(time.time()), "nonce": nonce.hex(),
                                   "ct": ct.hex()}), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(p)
        return pub

    def publics(self) -> list[str]:
        return sorted(json.loads(f.read_text(encoding="utf-8"))["pub"] for f in self.root.glob(f"{self.env}-*.json"))

    def signer(self, pub: str) -> ApiWalletSigner:
        d = json.loads(self._path(pub).read_text(encoding="utf-8"))
        raw = self._aes.decrypt(bytes.fromhex(d["nonce"]), bytes.fromhex(d["ct"]), f"{self.env}:{pub}".encode())
        return ApiWalletSigner(raw.hex(), pub)

    def free(self, used: set[str]) -> list[str]:
        """Keys never handed out (``used`` = every key the site ever assigned or reserved)."""
        return [p for p in self.publics() if p not in used]

    def ensure(self, used: set[str], minimum: int = 3) -> list[str]:
        """Tops the pool up to ``minimum`` unused keys; returns the unused public keys."""
        free = self.free(used)
        while len(free) < minimum:
            free.append(self.generate())
        return sorted(free)
