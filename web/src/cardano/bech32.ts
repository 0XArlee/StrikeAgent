// Bech32 (BIP-173) without the 90-character limit, as Cardano Shelley addresses (CIP-19) require. Shared by the page
// and the server (web/server/cardano.ts), which decodes and checks every address it is given.
const CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";
const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];

function polymod(values: number[]): number {
  let chk = 1;
  for (const v of values) {
    const b = chk >> 25;
    chk = ((chk & 0x1ffffff) << 5) ^ v;
    for (let i = 0; i < 5; i++) if ((b >> i) & 1) chk ^= GEN[i];
  }
  return chk;
}

function hrpExpand(hrp: string): number[] {
  const out: number[] = [];
  for (let i = 0; i < hrp.length; i++) out.push(hrp.charCodeAt(i) >> 5);
  out.push(0);
  for (let i = 0; i < hrp.length; i++) out.push(hrp.charCodeAt(i) & 31);
  return out;
}

function toWords(bytes: Uint8Array): number[] {
  let acc = 0, bits = 0;
  const out: number[] = [];
  for (const b of bytes) {
    acc = (acc << 8) | b;
    bits += 8;
    while (bits >= 5) { bits -= 5; out.push((acc >> bits) & 31); }
  }
  if (bits > 0) out.push((acc << (5 - bits)) & 31);
  return out;
}

export function hexToBytes(hex: string): Uint8Array {
  const clean = hex.replace(/^0x/, "");
  if (clean.length % 2 || /[^0-9a-f]/i.test(clean)) throw new Error("invalid hex");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(clean.slice(2 * i, 2 * i + 2), 16);
  return out;
}

export function utf8ToHex(s: string): string {
  return Array.from(new TextEncoder().encode(s), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Decodes and checks a bech32 string (lowercase, valid checksum, clean padding). */
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
  if (polymod([...hrpExpand(hrp), ...data]) !== 1) throw new Error("bech32: bad checksum");
  let acc = 0, bits = 0;
  const out: number[] = [];
  for (const v of data.slice(0, -6)) {
    acc = (acc << 5) | v; bits += 5;
    while (bits >= 8) { bits -= 8; out.push((acc >> bits) & 0xff); }
  }
  if (bits >= 5 || ((acc << (8 - bits)) & 0xff)) throw new Error("bech32: bad padding");
  return { hrp, bytes: new Uint8Array(out) };
}

export function bech32Encode(hrp: string, bytes: Uint8Array): string {
  const data = toWords(bytes);
  const values = [...hrpExpand(hrp), ...data, 0, 0, 0, 0, 0, 0];
  const mod = polymod(values) ^ 1;
  const checksum = Array.from({ length: 6 }, (_, i) => (mod >> (5 * (5 - i))) & 31);
  return hrp + "1" + [...data, ...checksum].map((d) => CHARSET[d]).join("");
}

/** CIP-30 returns addresses as hex bytes; turn one into its bech32 form (addr… / addr_test…). */
export function addressHexToBech32(hex: string): string {
  const bytes = hexToBytes(hex);
  const header = bytes[0];
  const network = header & 0x0f;           // CIP-19: 1 = mainnet, 0 = testnets
  const type = header >> 4;
  const base = type === 0x0e || type === 0x0f ? "stake" : "addr";
  return bech32Encode(network === 1 ? base : `${base}_test`, bytes);
}

/** Who an address belongs to: its stake credential for a base address (it stays the same whatever payment address an
 *  HD wallet hands out), else the whole address. Two addresses with the same key are the same wallet account. */
export function walletKey(addr: string): string {
  const b = bech32Decode(addr).bytes;
  const type = b[0] >> 4;
  const hex = (x: Uint8Array) => Array.from(x, (v) => v.toString(16).padStart(2, "0")).join("");
  return type <= 3 && b.length >= 57 ? `stake:${hex(b.slice(29, 57))}` : `addr:${hex(b)}`;
}

export function shortAddr(a: string, head = 10, tail = 6): string {
  return a.length > head + tail + 1 ? `${a.slice(0, head)}…${a.slice(-tail)}` : a;
}
