// Node self-test of the crypto modules against Python references (web/scripts/test_server_crypto.py writes the
// fixture). Run: esbuild server/selftest.ts --bundle --platform=node --outfile=<tmp>.mjs --format=esm; node <tmp>.mjs <fixture.json>
import { readFileSync } from "node:fs";
import { blake2b } from "./blake2b";
import { verifyCip30 } from "./cardano";

interface Fixture {
  blake: { data: string; len: number; hex: string }[];
  cases: { name: string; address: string; message: string; sig: string; ok: boolean }[];
}

const hex = (b: Uint8Array) => [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
const bytes = (h: string) => new Uint8Array((h.match(/../g) ?? []).map((x) => parseInt(x, 16)));

const fx = JSON.parse(readFileSync(process.argv[2], "utf8")) as Fixture;
let fails = 0;
for (const v of fx.blake) {
  const got = hex(blake2b(bytes(v.data), v.len));
  if (got !== v.hex) { fails++; console.log(`FAIL blake2b len=${v.len} data=${v.data.length / 2}B`); }
}
console.log(`blake2b: ${fx.blake.length - fails}/${fx.blake.length} vectors match hashlib`);
let f2 = 0;
for (const c of fx.cases) {
  const why = await verifyCip30(c.address, c.sig, new TextEncoder().encode(c.message));
  const ok = why === null;
  if (ok !== c.ok) f2++;
  console.log(`${ok === c.ok ? "PASS" : "FAIL"} cip30 ${c.name}: ${ok ? "valid" : why}`);
}
console.log(`cip30: ${fx.cases.length - f2}/${fx.cases.length} cases as expected`);
process.exit(fails || f2 ? 1 : 0);
