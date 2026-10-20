// Minimal CBOR (RFC 8949) for CIP-30 signatures: decodes definite-length items (what COSE_Sign1 / COSE_Key use) and
// encodes the COSE Sig_structure. Indefinite lengths, floats and big numbers are rejected: no wallet needs them here.
export type Cbor = number | Uint8Array | string | boolean | null | undefined | Cbor[] | Map<Cbor, Cbor> | { tag: number; value: Cbor };

const MAX_ITEMS = 256;

export function decode(b: Uint8Array): Cbor {
  let i = 0;
  const need = (n: number) => { if (i + n > b.length) throw new Error("cbor: truncated"); };
  const len = (ai: number): number => {
    if (ai < 24) return ai;
    if (ai === 24) { need(1); return b[i++]; }
    if (ai === 25) { need(2); const v = (b[i] << 8) | b[i + 1]; i += 2; return v; }
    if (ai === 26) { need(4); const v = b[i] * 2 ** 24 + (b[i + 1] << 16) + (b[i + 2] << 8) + b[i + 3]; i += 4; return v; }
    if (ai === 27) { need(8); let v = 0; for (let k = 0; k < 8; k++) v = v * 256 + b[i + k]; i += 8; if (v > Number.MAX_SAFE_INTEGER) throw new Error("cbor: integer too large"); return v; }
    throw new Error("cbor: unsupported length");
  };
  const item = (depth: number): Cbor => {
    if (depth > 16) throw new Error("cbor: too deep");
    need(1);
    const ib = b[i++], mt = ib >> 5, ai = ib & 31;
    switch (mt) {
      case 0: return len(ai);
      case 1: return -1 - len(ai);
      case 2: { const n = len(ai); need(n); const v = b.slice(i, i + n); i += n; return v; }
      case 3: { const n = len(ai); need(n); const v = new TextDecoder("utf-8", { fatal: true }).decode(b.subarray(i, i + n)); i += n; return v; }
      case 4: {
        const n = len(ai);
        if (n > MAX_ITEMS) throw new Error("cbor: array too long");
        const a: Cbor[] = [];
        for (let k = 0; k < n; k++) a.push(item(depth + 1));
        return a;
      }
      case 5: {
        const n = len(ai);
        if (n > MAX_ITEMS) throw new Error("cbor: map too long");
        const m = new Map<Cbor, Cbor>();
        for (let k = 0; k < n; k++) { const key = item(depth + 1); m.set(key, item(depth + 1)); }
        return m;
      }
      case 6: { const tag = len(ai); return { tag, value: item(depth + 1) }; }
      default:
        if (ai === 20) return false;
        if (ai === 21) return true;
        if (ai === 22) return null;
        if (ai === 23) return undefined;
        throw new Error("cbor: unsupported simple value");
    }
  };
  const v = item(0);
  if (i !== b.length) throw new Error("cbor: trailing bytes");
  return v;
}

function head(major: number, n: number): number[] {
  if (n < 24) return [(major << 5) | n];
  if (n < 0x100) return [(major << 5) | 24, n];
  if (n < 0x10000) return [(major << 5) | 25, n >> 8, n & 0xff];
  return [(major << 5) | 26, (n >>> 24) & 0xff, (n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

/** COSE Sig_structure for COSE_Sign1: ["Signature1", protected, external_aad = h'', payload]. */
export function sigStructure(protectedBytes: Uint8Array, payload: Uint8Array): Uint8Array {
  const ctx = new TextEncoder().encode("Signature1");
  const parts = [
    [0x84], head(3, ctx.length), [...ctx],
    head(2, protectedBytes.length), [...protectedBytes],
    [0x40],
    head(2, payload.length), [...payload],
  ];
  return new Uint8Array(parts.flat());
}
