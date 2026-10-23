"""The operator's secrets on the development PC (``secrets/``), encrypted at rest.

On Windows each file is kept as ``<name>.dpapi``: encrypted with DPAPI for the current Windows user, so a copy of
the folder (a backup, a synced drive, another account on the PC) cannot be read. Nothing here ever prints a secret.

    smartflow secrets lock      # encrypts every plain file of secrets/ and deletes the plain copy
    smartflow secrets status    # which files are encrypted

Readers go through ``read_text(path)``: it reads ``path`` if it still exists in plain text, else ``path.dpapi``.
The agents' host does not use this: its secrets are root-owned files there.

DPAPI ties the files to this Windows user. If that account is lost, so are these copies: the Cloudflare secrets can
be put again (``wrangler pages secret put``) and Strike API wallets created again in the Strike app.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

SUFFIX = ".dpapi"
_ENTROPY = b"smartflow-secrets-v1"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def available() -> bool:
    return sys.platform == "win32"


def _call(fn_name: str, data: bytes) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buf_in = ctypes.create_string_buffer(data, len(data))
    ent = ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY))
    blob_in = _Blob(len(data), ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_char)))
    blob_ent = _Blob(len(_ENTROPY), ctypes.cast(ent, ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    # both take (data in, description, entropy, reserved, prompt, flags, data out); 0x1 = CRYPTPROTECT_UI_FORBIDDEN
    if not getattr(crypt32, fn_name)(ctypes.byref(blob_in), None, ctypes.byref(blob_ent), None, None, 0x1, ctypes.byref(out)):
        raise OSError(f"{fn_name} failed (Windows error {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(data: bytes) -> bytes:
    return _call("CryptProtectData", data)


def unprotect(data: bytes) -> bytes:
    return _call("CryptUnprotectData", data)


def enc_path(path: Path) -> Path:
    return path.with_name(path.name + SUFFIX)


def exists(path: Path) -> bool:
    path = Path(path)
    return path.exists() or enc_path(path).exists()


def read_bytes(path: Path) -> bytes:
    path = Path(path)
    if path.exists():
        return path.read_bytes()
    return unprotect(enc_path(path).read_bytes())


def read_text(path: Path) -> str:
    return read_bytes(path).decode("utf-8")


def write_text(path: Path, text: str) -> Path:
    """Writes a secret: encrypted where DPAPI exists, else plain with owner-only permissions. Returns the file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if available():
        out = enc_path(path)
        out.write_bytes(protect(text.encode("utf-8")))
        return out
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def lock(folder: Path, log=print) -> int:
    """Encrypts every plain file of the folder (checked by decrypting it back) and deletes the plain copy."""
    if not available():
        log("DPAPI is Windows-only: on this system keep secrets/ readable by its owner only (chmod 600)")
        return 0
    n = 0
    for f in sorted(Path(folder).iterdir()):
        if not f.is_file() or f.name.endswith(SUFFIX):
            continue
        raw = f.read_bytes()
        out = enc_path(f)
        out.write_bytes(protect(raw))
        if unprotect(out.read_bytes()) != raw:
            out.unlink()
            raise OSError(f"{f.name}: the encrypted copy does not read back; the plain file was kept")
        f.unlink()
        n += 1
        log(f"encrypted {f.name} -> {out.name}")
    return n


def status(folder: Path) -> list[tuple[str, bool]]:
    """(file, encrypted) for every file of the folder."""
    if not Path(folder).exists():
        return []
    return [(f.name, f.name.endswith(SUFFIX)) for f in sorted(Path(folder).iterdir()) if f.is_file()]
