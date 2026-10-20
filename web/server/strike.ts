// Strike builder connect (docs.strikefinance.org/api/builder-codes): request-signature and verify-signature, called
// from the site so the browser never handles the API-wallet key. Strike creates the account if the address has none.
/// <reference path="./env.d.ts" />

export const STRIKE_API: Record<string, string> = {
  testnet: "https://api-v2-testnet.strikefinance.org",
  mainnet: "https://api.strikefinance.org",
};

export class StrikeError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function post<T>(env: string, path: string, body: unknown): Promise<T> {
  const base = STRIKE_API[env];
  if (!base) throw new StrikeError(500, `unknown Strike environment ${env}`);
  const r = await fetch(base + path, {
    method: "POST", body: JSON.stringify(body), signal: AbortSignal.timeout(15_000),
    headers: { "Content-Type": "application/json", "User-Agent": "smartflow-city/1.0" },   // Cloudflare blocks default agents
  });
  const text = await r.text();
  let data: Record<string, unknown> = {};
  try { data = text ? JSON.parse(text) : {}; } catch { /* not JSON */ }
  if (!r.ok) throw new StrikeError(r.status, String(data.error ?? data.msg ?? data.message ?? text.slice(0, 160) ?? r.statusText));
  return data as T;
}

/** Markets listed on this Strike environment (testnet lists fewer than mainnet). */
export async function listedMarkets(env: string): Promise<string[]> {
  const base = STRIKE_API[env];
  if (!base) throw new StrikeError(500, `unknown Strike environment ${env}`);
  const r = await fetch(`${base}/v2/markets`, { signal: AbortSignal.timeout(10_000), headers: { "User-Agent": "smartflow-city/1.0" } });
  if (!r.ok) throw new StrikeError(r.status, "markets unavailable");
  const data = await r.json() as { markets?: Record<string, unknown> };
  return Object.keys(data.markets ?? {});
}

export interface SignatureChallenge { nonce: string; message_to_sign: string }
export interface Linked {
  account_id: string; builder_code: string; fee_share_bps: number; api_wallet_id?: number;
  api_wallet_public_key: string; api_wallet_created_at?: string; api_wallet_expired_at?: string;
}

export const requestSignature = (env: string, b: { address: string; code: string; fee_share_bps: number; public_key: string }) =>
  post<SignatureChallenge>(env, "/auth/builder/request-signature", { address: b.address, chain: "cardano", code: b.code, fee_share_bps: b.fee_share_bps, public_key: b.public_key });

export const verifySignature = (env: string, b: { address: string; nonce: string; wallet_signature: string }) =>
  post<Linked>(env, "/auth/builder/verify-signature", { address: b.address, chain: "cardano", nonce: b.nonce, wallet_signature: b.wallet_signature });
