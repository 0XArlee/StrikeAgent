"""Cross-checks web/server crypto (TypeScript, runs on Cloudflare) against Python references:
BLAKE2b vs hashlib, and CIP-30 signature verification on valid and tampered wallet signatures.

    python web/scripts/test_server_crypto.py      (needs node + the web dependencies installed)
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cip30_test_wallet import TestWallet  # noqa: E402

WEB = Path(__file__).resolve().parents[1]
blake = []
for n in (0, 1, 3, 64, 127, 128, 129, 255, 256, 257, 1000):
    data = bytes((i * 7 + 3) % 256 for i in range(n))
    for ln in (28, 32, 64):
        blake.append({"data": data.hex(), "len": ln, "hex": hashlib.blake2b(data, digest_size=ln).hexdigest()})

msg = "Smart Flow · start my paper agent\nNonce: 1234"
w, other, basew = TestWallet(), TestWallet(), TestWallet(base=True)
good = w.sign_data(msg.encode())
sig_hex, key_hex = good.split(":")
cases = [
    {"name": "valid enterprise address", "address": w.address, "message": msg, "sig": good, "ok": True},
    {"name": "valid base address", "address": basew.address, "message": msg, "sig": basew.sign_data(msg.encode()), "ok": True},
    {"name": "valid hashed payload", "address": w.address, "message": msg, "sig": w.sign_data(msg.encode(), hashed=True), "ok": True},
    {"name": "another message", "address": w.address, "message": msg + "x", "sig": good, "ok": False},
    {"name": "claims another address", "address": other.address, "message": msg, "sig": good, "ok": False},
    {"name": "signed for another address", "address": w.address, "message": msg,
     "sig": w.sign_data(msg.encode(), addr_bytes=other.addr_bytes), "ok": False},
    {"name": "someone else's key", "address": w.address, "message": msg,
     "sig": f"{sig_hex}:{other.sign_data(msg.encode()).split(':')[1]}", "ok": False},
    {"name": "tampered signature", "address": w.address, "message": msg,
     "sig": f"{sig_hex[:-2]}{'00' if sig_hex[-2:] != '00' else '01'}:{key_hex}", "ok": False},
    {"name": "garbage", "address": w.address, "message": msg, "sig": "zz:zz", "ok": False},
    {"name": "testnet address on mainnet prefix", "address": TestWallet(network=0).address.replace("addr_test", "addr"),
     "message": msg, "sig": good, "ok": False},
]
with tempfile.TemporaryDirectory() as d:
    fx = Path(d) / "fx.json"
    fx.write_text(json.dumps({"blake": blake, "cases": cases}), encoding="utf-8")
    out = Path(d) / "selftest.mjs"
    esbuild = WEB / "node_modules" / ".bin" / ("esbuild.cmd" if os.name == "nt" else "esbuild")
    subprocess.run([str(esbuild), str(WEB / "server" / "selftest.ts"), "--bundle", "--platform=node", "--format=esm",
                    f"--outfile={out}", "--log-level=warning"], check=True)
    r = subprocess.run(["node", str(out), str(fx)], capture_output=True, text=True, encoding="utf-8")
    print(r.stdout + r.stderr)
    sys.exit(r.returncode)
