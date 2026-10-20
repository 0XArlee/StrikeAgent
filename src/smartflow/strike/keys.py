"""Generate a Strike API-wallet key pair locally.

    python -m smartflow.strike.keys testnet        (or: mainnet)

Writes ``secrets/strike_<env>.env`` (git-ignored; encrypted at rest on Windows, ``.dpapi``: smartflow.secretstore) with STRIKE_API_PRIVATE_KEY / STRIKE_API_PUBLIC_KEY and prints
ONLY the public key, which you register on the Strike "API Wallets" page. The API wallet can trade but cannot
withdraw (docs: api/getting-started, Permissions). Never paste the private key into a chat, a ticket or a commit;
the wallet's seed phrase is never needed by this project.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .. import secretstore
from .auth import ApiWalletSigner, generate_keypair

APP = {"testnet": "https://testnet.strikefinance.org", "mainnet": "https://app.strikefinance.org"}


def _find_hex(obj, words: tuple[str, ...], lengths: tuple[int, ...], path: str = "") -> str | None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            r = _find_hex(v, words, lengths, f"{path}.{k}".lower())
            if r:
                return r
    elif isinstance(obj, str):
        s = obj.strip().lower().removeprefix("0x")
        if len(s) in lengths and all(c in "0123456789abcdef" for c in s) and any(w in path for w in words):
            return s
    return None


def import_file(src: str, env: str) -> int:
    """Import an API-wallet key file downloaded from Strike's API Wallets page into ``secrets/strike_<env>.env`` and
    move the original into ``secrets/``. Prints only the start of the public key."""
    import json
    p = Path(src)
    if env not in APP:
        print("env must be testnet or mainnet")
        return 2
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"cannot read {p}: {e}")
        return 2
    priv = _find_hex(data, ("priv", "secret", "seed"), (64, 128))
    pub = _find_hex(data, ("pub", "api_key", "apikey", "wallet"), (64,))
    if not priv:
        print("no Ed25519 private key (64/128 hex) found in the file; fields present: "
              + ", ".join(sorted(data) if isinstance(data, dict) else []))
        return 2
    try:
        signer = ApiWalletSigner(priv, pub)
    except ValueError as e:
        print(f"invalid key pair: {e}")
        return 2
    out = Path("secrets") / f"strike_{env}.env"
    if secretstore.exists(out):
        print(f"{out} already exists; delete it first if you want to replace it")
        return 1
    saved = secretstore.write_text(out, f"# Strike {env} API wallet (imported from {p.name}) - SECRET, never share or commit\n"
                                        f"STRIKE_ENV={env}\nSTRIKE_API_PRIVATE_KEY={priv}\nSTRIKE_API_PUBLIC_KEY={signer.public_key}\n")
    # the downloaded file holds the private key too: kept only encrypted (on Windows), next to the imported key
    dest = secretstore.write_text(out.parent / p.name, p.read_text(encoding="utf-8"))
    if p.resolve() != dest.resolve():
        p.unlink()
    print(f"OK: key imported to {saved} and the original kept as {dest}")
    print(f"public key {signer.public_key[:10]}... (must match the one shown on {APP[env]}/api-keys)")
    print(f"next: smartflow auth-check --env {env}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 2 and argv[1] == "import":
        env = argv[3] if len(argv) > 3 else "testnet"
        return import_file(argv[2], env.lower())
    env = (argv[1] if len(argv) > 1 else "testnet").lower()
    if env not in APP:
        print("usage: python -m smartflow.strike.keys [testnet|mainnet]")
        return 2
    path = Path("secrets") / f"strike_{env}.env"
    if secretstore.exists(path):
        pub = next((ln.split("=", 1)[1].strip() for ln in secretstore.read_text(path).splitlines()
                    if ln.startswith("STRIKE_API_PUBLIC_KEY=")), "?")
        print(f"{path} already exists (not overwritten). Public key: {pub}")
        return 1
    priv, pub = generate_keypair()
    ApiWalletSigner(priv, pub)  # self-check
    saved = secretstore.write_text(path, f"# Strike {env} API wallet - SECRET, never share or commit\n"
                                         f"STRIKE_ENV={env}\nSTRIKE_API_PRIVATE_KEY={priv}\nSTRIKE_API_PUBLIC_KEY={pub}\n")
    print(f"Private key saved to {saved.resolve()} (keep it secret).")
    print(f"\nPUBLIC KEY (register this one):\n{pub}\n")
    print(f"Register it at {APP[env]}/api-keys  (connect your wallet, open 'API Wallets', add the public key).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
