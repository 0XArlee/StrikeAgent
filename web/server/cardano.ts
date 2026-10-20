// Cardano wallet ownership proof: CIP-30 signData (COSE_Sign1, CIP-8) verified server-side.
// The signature proves the key behind the address signed our exact message. It authorises nothing on-chain.
import { blake2b } from "./blake2b";
import { decode, sigStructure, type Cbor } from "./cbor";

const CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";
const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];

function polymod(values: number[]): number {
  let chk = 1;
  for (const v of values) {
    const top = chk >> 25;
    chk = ((chk & 0x1ffffff) << 5) ^ v;
    for (let i = 0; i < 5; i++) if ((top >> i) & 1) chk ^= GEN[i];
  }
  return chk;
}

/** Bech32 (BIP-173) decode without the 90-character limit (Cardano base addresses are 103 characters). */
export function bech32Decode(s: string): { hrp: string; bytes: Uint8Array } {
  if (s.length > 200 || s !== s.toLowerCase()) throw new Error("bech32: invalid string");
  const pos = s.lastIndexOf("1");
  if (pos < 1 || pos + 7 > s.length) throw new Error("bech32: no separator");
  const hrp = s.slice(0, pos);
  const data: number[] = [];
  for (const c of s.slice(pos + 1)) {
    const d = CHARSET.indexOf(c);
    if (d < 0) throw new Error("bech32: invalid character");
    data.push(d);
  }
  const exp = [...hrp].map((c) => c.charCodeAt(0) >> 5).concat([0], [...hrp].map((c) => c.charCodeAt(0) & 31));
  if (polymod(exp.concat(data)) !== 1) throw new Error("bech32: bad checksum");
  let acc = 0, bits = 0;
  const out: number[] = [];
  for (const v of data.slice(0, -6)) {
    acc = (acc << 5) | v; bits += 5;
    while (bits >= 8) { bits -= 8; out.push((acc >> bits) & 0xff); }
  }
  if (bits >= 5 || ((acc << (8 - bits)) & 0xff)) throw new Error("bech32: bad padding");
  return { hrp, bytes: new Uint8Array(out) };
}

export interface Address { bech32: string; bytes: Uint8Array; network: number; paymentKey?: Uint8Array; stakeKey?: Uint8Array }

/** Shelley address -> key hashes that may sign for it (payment key, or stake key for base / reward addresses). */
export function parseAddress(addr: string): Address {
  const { hrp, bytes } = bech32Decode(addr.trim());
  const type = bytes[0] >> 4, network = bytes[0] & 0x0f;
  const okHrp = network === 1 ? ["addr", "stake"] : ["addr_test", "stake_test"];
  if (!okHrp.includes(hrp)) throw new Error("address: network and prefix do not match");
  const a: Address = { bech32: addr.trim(), bytes, network };
  if ([0, 2, 4, 6].includes(type)) a.paymentKey = bytes.slice(1, 29);
  if (type === 0 || type === 1) a.stakeKey = bytes.slice(29, 57);
  if (type === 14) a.stakeKey = bytes.slice(1, 29);
  if (type > 7 && type !== 14) throw new Error("address: unsupported type");
  if ((type <= 1 && bytes.length !== 57) || (type >= 6 && bytes.length !== 29)) throw new Error("address: bad length");
  if (!a.paymentKey && !a.stakeKey) throw new Error("address: script addresses cannot sign");
  return a;
}

const eq = (a: Uint8Array, b: Uint8Array) => a.length === b.length && a.every((x, i) => x === b[i]);
const fromHex = (h: string) => {
  if (!/^(?:[0-9a-f]{2})+$/i.test(h)) throw new Error("hex: invalid");
  return new Uint8Array(h.match(/../g)!.map((x) => parseInt(x, 16)));
};
const asBytes = (v: Cbor | undefined) => (v instanceof Uint8Array ? v : null);

/** Verifies "{coseSign1Hex}:{coseKeyHex}" (CIP-30 signData) over `message` for `address`. Returns null if valid,
 *  otherwise the reason. Checks: EdDSA, the signed address is this address, the payload is our message (or its
 *  BLAKE2b-224 when hashed), the public key hashes to the address's payment or stake key, and the signature. */
export async function verifyCip30(address: string, walletSignature: string, message: Uint8Array): Promise<string | null> {
  try {
    if (walletSignature.length > 8192) return "signature too long";
    const [sigHex, keyHex, extra] = walletSignature.split(":");
    if (!sigHex || !keyHex || extra !== undefined) return "expected cose_sign1:cose_key";
    let sign1 = decode(fromHex(sigHex));
    if (sign1 && typeof sign1 === "object" && "tag" in sign1) sign1 = sign1.value;   // tag 18 is optional
    if (!Array.isArray(sign1) || sign1.length !== 4) return "not a COSE_Sign1";
    const [prot, unprot, payload, signature] = sign1;
    const protBytes = asBytes(prot), pay = asBytes(payload), sig = asBytes(signature);
    if (!protBytes || !pay || !sig || sig.length !== 64) return "malformed COSE_Sign1";
    const hdr = decode(protBytes);
    if (!(hdr instanceof Map) || hdr.get(1) !== -8) return "algorithm is not EdDSA";
    const signedAddr = asBytes(hdr.get("address"));
    const addr = parseAddress(address);
    if (!signedAddr || !eq(signedAddr, addr.bytes)) return "signed for another address";
    const hashed = unprot instanceof Map && unprot.get("hashed") === true;
    if (!eq(pay, hashed ? blake2b(message, 28) : message)) return "payload is not the issued message";
    const key = decode(fromHex(keyHex));
    if (!(key instanceof Map) || key.get(1) !== 1 || key.get(-1) !== 6) return "key is not an Ed25519 OKP key";
    const x = asBytes(key.get(-2));
    if (!x || x.length !== 32) return "bad public key";
    const kh = blake2b(x, 28);
    if (!((addr.paymentKey && eq(kh, addr.paymentKey)) || (addr.stakeKey && eq(kh, addr.stakeKey)))) return "key does not belong to the address";
    const pub = await crypto.subtle.importKey("raw", x, { name: "Ed25519" }, false, ["verify"]);
    const ok = await crypto.subtle.verify({ name: "Ed25519" }, pub, sig, sigStructure(protBytes, pay));
    return ok ? null : "invalid signature";
  } catch (e) {
    return (e as Error).message || "invalid signature";
  }
}
