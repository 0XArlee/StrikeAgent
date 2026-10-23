// Shared helpers for the Pages Functions: JSON responses, limits, HMAC, session tokens and input validation.
/// <reference path="./env.d.ts" />
import registry from "../../config/strategies.json";

export const MARKETS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "ADA-USD", "NEAR-USD", "ZEC-USD"];
// risk per trade of each preset, % (smartflow/live/fleet.py RISK); each strategy caps it (config/strategies.json
// max_risk: Smart Flow Pyramid stacks up to 3 entries per market and goes up to the standard preset, docs/STRATEGY.md)
export const RISK: Record<string, number> = { conservative: 0.5, standard: 1.0, assertive: 2.0 };
/** Whether this risk preset is allowed with this strategy. */
export const riskAllowed = (strategy: string, risk: string) => (RISK[risk] ?? Infinity) <= RISK[STRATEGIES[strategyOf(strategy)].maxRisk];
export const CHALLENGE_TTL = 5 * 60_000;
export const SESSION_TTL = 7 * 86400_000;

const HEADERS = { "Content-Type": "application/json; charset=utf-8", "X-Content-Type-Options": "nosniff" };

export function json(data: unknown, status = 200, cache = "no-store"): Response {
  return new Response(JSON.stringify(data), { status, headers: { ...HEADERS, "Cache-Control": cache } });
}
export const fail = (status: number, error: string) => json({ error }, status);

/** Request body as JSON, refusing anything bigger than `max` bytes or not an object. */
export async function body<T>(req: Request, max = 16_384): Promise<T | null> {
  const n = Number(req.headers.get("Content-Length") ?? 0);
  if (n > max) return null;
  const text = await req.text();
  if (text.length > max) return null;
  try {
    const v = JSON.parse(text);
    return v && typeof v === "object" && !Array.isArray(v) ? (v as T) : null;
  } catch { return null; }
}

const enc = new TextEncoder();
const hex = (b: ArrayBuffer) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");

export async function hmacHex(secret: string, msg: string | Uint8Array): Promise<string> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", key, typeof msg === "string" ? enc.encode(msg) : msg));
}

export function sameText(a: string, b: string): boolean {   // constant time for equal lengths
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

export async function sha256Hex(s: string): Promise<string> { return hex(await crypto.subtle.digest("SHA-256", enc.encode(s))); }

/** "{agentId}.{expiresMs}.{hmac}" — proves the bearer signed in with the wallet of that agent recently. */
export async function issueToken(secret: string, id: string, now: number): Promise<{ token: string; exp: number }> {
  const exp = now + SESSION_TTL;
  return { token: `${id}.${exp}.${await hmacHex(secret, `session.${id}.${exp}`)}`, exp };
}
export async function readToken(secret: string, req: Request, now: number): Promise<string | null> {
  const m = /^Bearer ([\w-]+)\.(\d+)\.([0-9a-f]{64})$/.exec(req.headers.get("Authorization") ?? "");
  if (!m || Number(m[2]) < now) return null;
  return sameText(await hmacHex(secret, `session.${m[1]}.${m[2]}`), m[3]) ? m[1] : null;
}

/** Display name for the city: 2-24 letters, digits, spaces and . _ - ·, not posing as the official agents. */
export function cleanName(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const s = v.normalize("NFC").replace(/\s+/g, " ").trim();
  if (!/^[\p{L}\p{N} ._·-]{2,24}$/u.test(s)) return null;
  if (/smart\s*flow|smartflow|strike|official|oficial|admin/i.test(s)) return null;
  return s;
}

export function cleanMarkets(v: unknown): string[] | null {
  if (!Array.isArray(v) || !v.length || v.length > MARKETS.length) return null;
  const set = new Set(v);
  if ([...set].some((m) => typeof m !== "string" || !MARKETS.includes(m))) return null;
  return MARKETS.filter((m) => set.has(m));
}

export const ip = (req: Request) => req.headers.get("CF-Connecting-IP") ?? "local";

export interface UserRow {
  id: string; address: string; name: string; risk: string; markets: string; public: number; status: string;
  created_at: number; updated_at: number; look: string | null; strategy?: string; persona?: string | null;
}

/** The strategies a user can pick: the live ones of the registry the agents' host also reads (config/strategies.json).
 *  ref: its official paper agent in the city; maxRisk: the highest preset allowed with it. */
export const STRATEGIES: Record<string, { ref: string; name: string; maxRisk: string }> = Object.fromEntries(
  (registry.strategies as { id: string; name: string; status: string; max_risk: string; paper?: { city_id?: string } }[])
    .filter((s) => s.status === "live").map((s) => [s.id, { ref: s.paper?.city_id ?? "", name: s.name, maxRisk: s.max_risk }]));
export const DEFAULT_STRATEGY: string = registry.default;
export const strategyOf = (v: unknown): string => (typeof v === "string" && v in STRATEGIES ? v : DEFAULT_STRATEGY);

export const cityCacheKey = (req: Request) => new Request(new URL("/api/city", req.url).toString());
export const edgeCache = () => (caches as unknown as { default: Cache }).default;

/** Route wrapper: an unexpected error is logged server-side and answered with a generic 500 (no internals leak). */
export const safe = (h: (c: Ctx) => Promise<Response>) => async (c: Ctx): Promise<Response> => {
  try { return await h(c); } catch (e) { console.error("api error", e); return fail(500, "internal error"); }
};
