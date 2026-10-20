"""Test-only CIP-30 wallet: an Ed25519 key, its Cardano address and signData() in the exact wallet format
(COSE_Sign1 + COSE_Key, CIP-8). Used by the API tests and the browser end-to-end check. It never holds funds."""

import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _head(major: int, n: int) -> bytes:
    if n < 24:
        return bytes([major << 5 | n])
    if n < 0x100:
        return bytes([major << 5 | 24, n])
    if n < 0x10000:
        return bytes([major << 5 | 25]) + n.to_bytes(2, "big")
    return bytes([major << 5 | 26]) + n.to_bytes(4, "big")


def cbor_int(n: int) -> bytes:
    return _head(0, n) if n >= 0 else _head(1, -1 - n)


def cbor_bytes(b: bytes) -> bytes:
    return _head(2, len(b)) + b


def cbor_text(s: str) -> bytes:
    b = s.encode()
    return _head(3, len(b)) + b


def cbor_array(items: list[bytes]) -> bytes:
    return _head(4, len(items)) + b"".join(items)


def cbor_map(pairs: list[tuple[bytes, bytes]]) -> bytes:
    return _head(5, len(pairs)) + b"".join(k + v for k, v in pairs)


FALSE = b"\xf4"


def _polymod(values):
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if (top >> i) & 1 else 0
    return chk


def bech32_encode(hrp: str, data: bytes) -> str:
    acc = bits = 0
    five = []
    for b in data:
        acc = acc << 8 | b
        bits += 8
        while bits >= 5:
            bits -= 5
            five.append(acc >> bits & 31)
    if bits:
        five.append(acc << (5 - bits) & 31)
    exp = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    pm = _polymod(exp + five + [0] * 6) ^ 1
    return hrp + "1" + "".join(CHARSET[d] for d in five + [pm >> 5 * (5 - i) & 31 for i in range(6)])


class TestWallet:
    def __init__(self, network: int = 1, seed: bytes | None = None, base: bool = False):
        self.sk = Ed25519PrivateKey.from_private_bytes(seed) if seed else Ed25519PrivateKey.generate()
        self.pk = self.sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        kh = hashlib.blake2b(self.pk, digest_size=28).digest()
        if base:   # base address: payment key + a (different) stake key
            stake = hashlib.blake2b(b"stake" + self.pk, digest_size=28).digest()
            self.addr_bytes = bytes([0x00 | network]) + kh + stake
        else:      # enterprise address
            self.addr_bytes = bytes([0x60 | network]) + kh
        self.address = bech32_encode("addr" if network == 1 else "addr_test", self.addr_bytes)

    def sign_data(self, message: bytes, addr_bytes: bytes | None = None, hashed: bool = False) -> str:
        """CIP-30 signData(address, payload) -> "{COSE_Sign1 hex}:{COSE_Key hex}"."""
        payload = hashlib.blake2b(message, digest_size=28).digest() if hashed else message
        prot = cbor_map([(cbor_int(1), cbor_int(-8)), (cbor_text("address"), cbor_bytes(addr_bytes or self.addr_bytes))])
        to_sign = cbor_array([cbor_text("Signature1"), cbor_bytes(prot), cbor_bytes(b""), cbor_bytes(payload)])
        sig = self.sk.sign(to_sign)
        unprot = cbor_map([(cbor_text("hashed"), b"\xf5" if hashed else FALSE)])
        sign1 = cbor_array([cbor_bytes(prot), unprot, cbor_bytes(payload), cbor_bytes(sig)])
        key = cbor_map([(cbor_int(1), cbor_int(1)), (cbor_int(3), cbor_int(-8)), (cbor_int(-1), cbor_int(6)),
                        (cbor_int(-2), cbor_bytes(self.pk))])
        return f"{sign1.hex()}:{key.hex()}"
