// Real trading for users' agents (builder connect). The site reserves a public key generated on the agents' host, asks
// Strike to authorise it as the user's API wallet for the Smart Flow builder code, and records the link. The host
// pulls the links and trades with the matching private key, which never leaves it.
/// <reference path="./env.d.ts" />
import { parseAddress } from "./cardano";
import { addEvent, audit, auditNow, userById } from "./store";
import { StrikeError, listedMarkets, requestSignature, verifySignature } from "./strike";
import { CHALLENGE_TTL, body, fail, hmacHex, json, readToken, sameText } from "./util";

/** The site's network: wallets and Strike. Production is mainnet; only the QA site sets LIVE_ENV=testnet. */
export const liveEnv = (env: Env) => (env.LIVE_ENV === "testnet" ? "testnet" : "mainnet");
export const walletNetwork = (env: Env) => (liveEnv(env) === "mainnet" ? 1 : 0);   // Cardano address network id
export const liveFee = (env: Env) => Math.min(100, Math.max(0, Math.round(Number(env.BUILDER_FEE_BPS ?? 20)))) || 20;
const PUB = /^[0-9a-f]{64}$/;

interface LinkRow { user_id: string; env: string; pub: string; account_id: string; fee_bps: number; status: string; created_at: number; updated_at: number }
interface SessionRow { id: string; user_id: string; pub: string; env: string; nonce: string; address: string; message: string; expires_at: number; used: number }

export async function linkFor(db: D1Database, userId: string): Promise<LinkRow | null> {
  return db.prepare("SELECT * FROM live_links WHERE user_id = ?1").bind(userId).first<LinkRow>();
}

/** Invite-only phase: real trading only for the wallets in LIVE_ALLOW (everyone else stays on paper). */
export const inviteOnly = (env: Env) => !!env.BUILDER_CODE && !!env.LIVE_ALLOW?.trim();
/** Real trading open to everyone: users' agents are always real (no paper agents for users any more). */
export const liveForAll = (env: Env) => !!env.BUILDER_CODE && !inviteOnly(env);
export function liveAllowed(env: Env, address: string): boolean {
  if (!env.BUILDER_CODE) return false;
  if (!inviteOnly(env)) return true;
  return (env.LIVE_ALLOW ?? "").split(",").map((a) => a.trim()).includes(address);
}

export function liveView(env: Env, link: LinkRow | null, allowed = liveForAll(env)) {
  return {
    env: liveEnv(env), enabled: allowed, feeBps: liveFee(env),
    status: link && link.env === liveEnv(env) ? link.status : "none",
    accountId: link ? `${link.account_id.slice(0, 8)}…` : null, since: link?.created_at ?? null,
  };
}

/** Requests from the agents' host: HMAC-SHA256 of "{ms}.{payload}" with PUSH_SECRET, 2-minute window. */
export async function fromHost(env: Env, req: Request, payload: string): Promise<boolean> {
  const ts = req.headers.get("X-SF-Time") ?? "", sig = req.headers.get("X-SF-Signature") ?? "";
  if (!/^\d{13}$/.test(ts) || Math.abs(Date.now() - Number(ts)) > 120_000 || !env.PUSH_SECRET) return false;
  return sameText(await hmacHex(env.PUSH_SECRET, `${ts}.${payload}`), sig);
}

export const strikeFail = (e: unknown) => e instanceof StrikeError
  ? fail(e.status >= 500 ? 502 : 400, `Strike: ${e.message}`) : fail(502, "Strike did not answer, try again in a minute");

/** The agent trades only the markets this Strike environment lists: refuse before anything is signed if none is. */
async function unlisted(e: string, markets: string[]): Promise<Response | null> {
  let listed: string[];
  try { listed = await listedMarkets(e); } catch (err) { return strikeFail(err); }
  if (markets.some((m) => listed.includes(m))) return null;
  return fail(400, `none of your markets trades on Strike ${e} (${listed.map((m) => m.replace("-USD", "")).join(", ")})`);
}

export interface LiveStart { pub: string; nonce: string; env: string; message: string }

/** Reserves a free API-wallet key for `userId` and asks Strike for the builder-connect message its wallet must sign. */
export async function startLink(env: Env, userId: string, address: string, markets: string[], now: number): Promise<LiveStart | Response> {
  const e = liveEnv(env);
  const bad = await unlisted(e, markets);
  if (bad) return bad;
  let pub: string | null = null;   // two requests never get the same key
  for (let i = 0; i < 3 && !pub; i++) {
    const cand = await env.DB.prepare("SELECT pub FROM live_keys WHERE env = ?1 AND status = 'free' ORDER BY updated_at LIMIT 1").bind(e).first<{ pub: string }>();
    if (!cand) break;
    const r = await env.DB.prepare("UPDATE live_keys SET status = 'pending', user_id = ?2, updated_at = ?3 WHERE pub = ?1 AND status = 'free'")
      .bind(cand.pub, userId, now).run();
    if (r.meta.changes) pub = cand.pub;
  }
  if (!pub) return fail(503, "no API wallet is ready right now: try again in a minute");
  let ch;
  try {
    ch = await requestSignature(e, { address, code: env.BUILDER_CODE ?? "", fee_share_bps: liveFee(env), public_key: pub });
  } catch (err) {   // Strike issued nothing for this key: it can go back to the pool
    await env.DB.prepare("UPDATE live_keys SET status = 'free', user_id = NULL, updated_at = ?2 WHERE pub = ?1").bind(pub, now).run();
    return strikeFail(err);
  }
  if (!ch?.nonce || typeof ch.message_to_sign !== "string") return fail(502, "unexpected answer from Strike");
  return { pub, nonce: ch.nonce, env: e, message: ch.message_to_sign };
}

/** A key Strike was asked about is never offered again, whatever happened next. */
export const burnKey = (env: Env, pub: string, now: number) =>
  env.DB.prepare("UPDATE live_keys SET status = 'revoked', updated_at = ?2 WHERE pub = ?1").bind(pub, now).run();

/** Sends the wallet's signature to Strike and checks it authorised exactly our key, builder code and fee. On success
 *  returns the statements that record the link (run them in the same batch as anything else); on failure the key is
 *  burnt and the error response returned. */
export async function finishLink(env: Env, userId: string, s: { pub: string; nonce: string; env: string; address: string },
                                 walletSignature: string, now: number, proof: { req: Request; message: string }): Promise<D1PreparedStatement[] | Response> {
  // the audit row: Strike's own message that the wallet signed (the builder code and fee it approves) and its answer
  const row = (ok: boolean, detail: Record<string, unknown>) => ({ user: userId, address: s.address, action: "live_connect", ok,
    detail: { env: s.env, pub: s.pub, builderCode: env.BUILDER_CODE ?? "", feeBps: liveFee(env), ...detail },
    message: proof.message, signature: walletSignature });
  let res;
  try {
    res = await verifySignature(s.env, { address: s.address, nonce: s.nonce, wallet_signature: walletSignature });
  } catch (err) {
    await burnKey(env, s.pub, now);
    await auditNow(env.DB, proof.req, s.env, row(false, { error: `Strike refused: ${err instanceof Error ? err.message : String(err)}` }), now);
    return strikeFail(err);
  }
  const fee = liveFee(env);
  const strike = { accountId: res.account_id ?? null, apiWallet: res.api_wallet_public_key ?? null, builderCode: res.builder_code ?? null,
    feeBps: res.fee_share_bps ?? null };
  if (String(res.api_wallet_public_key ?? "").toLowerCase() !== s.pub || res.builder_code !== env.BUILDER_CODE
      || Number(res.fee_share_bps) !== fee || !res.account_id) {
    await burnKey(env, s.pub, now);
    await auditNow(env.DB, proof.req, s.env, row(false, { error: "Strike linked a different key, builder code or fee", strike }), now);
    return fail(502, "Strike linked a different key, builder code or fee: nothing was saved");
  }
  const prev = await linkFor(env.DB, userId);
  return [
    audit(env.DB, proof.req, s.env, row(true, { accountId: res.account_id, strike, replaced: prev && prev.pub !== s.pub ? prev.pub : null }), now),
    // Strike revokes the previous API wallet of this account for our builder: retire ours too
    ...(prev && prev.pub !== s.pub ? [env.DB.prepare("UPDATE live_keys SET status = 'revoked', updated_at = ?2 WHERE pub = ?1").bind(prev.pub, now)] : []),
    env.DB.prepare("UPDATE live_keys SET status = 'active', account_id = ?2, updated_at = ?3 WHERE pub = ?1").bind(s.pub, res.account_id, now),
    env.DB.prepare("INSERT INTO live_links (user_id, env, pub, account_id, fee_bps, status, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, 'active', ?6, ?6) "
      + "ON CONFLICT(user_id) DO UPDATE SET env = excluded.env, pub = excluded.pub, account_id = excluded.account_id, fee_bps = excluded.fee_bps, "
      + "status = 'active', updated_at = excluded.updated_at").bind(userId, s.env, s.pub, res.account_id, fee, now),
    addEvent(env.DB, userId, "live", now),
  ];
}

export async function liveChallenge({ request, env }: Ctx): Promise<Response> {
  const now = Date.now();
  const id = await readToken(env.SESSION_SECRET, request, now);
  if (!id) return fail(401, "sign in again with your wallet");
  if (!env.BUILDER_CODE) return fail(501, "real trading is not enabled yet");
  const u = await userById(env.DB, id);
  if (!u) return fail(404, "this agent no longer exists");
  if (!liveAllowed(env, u.address)) return fail(403, "real trading is by invitation for now: your agent stays on paper");
  const e = liveEnv(env);
  if (parseAddress(u.address).network !== walletNetwork(env)) return fail(400, `this agent's wallet is not on Strike ${e}`);
  const link = await linkFor(env.DB, id);
  if (link && link.env === e && link.status === "active") return fail(409, "your agent is already connected to Strike");
  const st = await startLink(env, id, u.address, JSON.parse(u.markets), now);
  if (st instanceof Response) return st;
  const sid = crypto.randomUUID();
  await env.DB.prepare("INSERT INTO live_sessions (id, user_id, pub, env, nonce, address, message, created_at, expires_at, used) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, 0)")
    .bind(sid, id, st.pub, e, st.nonce, u.address, st.message, now, now + CHALLENGE_TTL).run();
  return json({ sessionId: sid, messageToSign: st.message, expiresAt: now + CHALLENGE_TTL, feeBps: liveFee(env), env: e });
}

export async function liveVerify({ request, env }: Ctx): Promise<Response> {
  const now = Date.now();
  const id = await readToken(env.SESSION_SECRET, request, now);
  if (!id) return fail(401, "sign in again with your wallet");
  const b = await body<{ sessionId?: unknown; walletSignature?: unknown }>(request);
  if (!b || typeof b.sessionId !== "string" || typeof b.walletSignature !== "string" || b.walletSignature.length > 8192) return fail(400, "invalid request");
  const used = await env.DB.prepare("UPDATE live_sessions SET used = 1 WHERE id = ?1 AND user_id = ?2 AND used = 0 AND expires_at > ?3").bind(b.sessionId, id, now).run();
  if (!used.meta.changes) return fail(410, "this request expired or was already used: start again");
  const s = await env.DB.prepare("SELECT * FROM live_sessions WHERE id = ?1").bind(b.sessionId).first<SessionRow>();
  if (!s) return fail(410, "start again");
  const done = await finishLink(env, id, s, b.walletSignature, now, { req: request, message: s.message });
  if (done instanceof Response) return done;
  await env.DB.batch(done);
  return json(liveView(env, await linkFor(env.DB, id), true));
}

/** Stops real trading at once. Needs only the session: stopping is always allowed. */
export async function liveOff({ request, env }: Ctx): Promise<Response> {
  const now = Date.now();
  const id = await readToken(env.SESSION_SECRET, request, now);
  if (!id) return fail(401, "sign in again with your wallet");
  const link = await linkFor(env.DB, id);
  const u = await userById(env.DB, id);
  // stopping needs only the session (no signature): the row says so
  const row = (changed: boolean) => ({ user: id, address: u?.address ?? null, action: "live_off", ok: true,
    detail: { changed, auth: "session", accountId: link?.account_id ?? null, pub: link?.pub ?? null } });
  if (link && link.status === "active") {
    await env.DB.batch([
      env.DB.prepare("UPDATE live_links SET status = 'off', updated_at = ?2 WHERE user_id = ?1").bind(id, now),
      addEvent(env.DB, id, "live_off", now),
      audit(env.DB, request, liveEnv(env), row(true), now),
    ]);
  } else {
    await auditNow(env.DB, request, liveEnv(env), row(false), now);
  }
  return json(liveView(env, await linkFor(env.DB, id), !!u && liveAllowed(env, u.address)));
}


/** The agents' host: which users trade, with which key, how. */
export async function hostLive({ request, env }: Ctx): Promise<Response> {
  if (!(await fromHost(env, request, "GET /api/internal/live"))) return fail(401, "bad signature");
  const e = liveEnv(env);
  const links = (await env.DB.prepare(
    "SELECT l.user_id, l.pub, l.account_id, l.fee_bps, l.status AS link_status, l.test_at, u.status AS user_status, u.name, u.risk, u.markets, u.strategy "
    + "FROM live_links l JOIN users u ON u.id = l.user_id WHERE l.env = ?1").bind(e).all<Record<string, string | number>>()).results;
  const used = (await env.DB.prepare("SELECT pub FROM live_keys WHERE env = ?1 AND status != 'free'").bind(e).all<{ pub: string }>()).results;
  return json({
    env: e, builderCode: env.BUILDER_CODE ?? "", feeBps: liveFee(env), used: used.map((r) => r.pub),
    links: links.map((l) => ({
      userId: l.user_id, name: l.name, pub: l.pub, accountId: l.account_id, feeBps: l.fee_bps, risk: l.risk, strategy: l.strategy ?? "smartflow", testAt: l.test_at ?? null,
      markets: JSON.parse(String(l.markets)), status: l.link_status === "active" && l.user_status === "active" ? "active" : "paused",
    })),
  });
}

/** The agents' host offers the public keys of fresh pairs. */
export async function hostKeys({ request, env }: Ctx): Promise<Response> {
  const raw = await request.text();
  if (raw.length > 20_000 || !(await fromHost(env, request, raw))) return fail(401, "bad signature");
  let b: { env?: unknown; free?: unknown };
  try { b = JSON.parse(raw); } catch { return fail(400, "not JSON"); }
  const e = liveEnv(env);
  if (b.env !== e || !Array.isArray(b.free) || b.free.length > 50 || b.free.some((p) => typeof p !== "string" || !PUB.test(p))) return fail(400, "invalid keys");
  const now = Date.now();
  if (b.free.length) {
    await env.DB.batch((b.free as string[]).map((p) => env.DB.prepare("INSERT OR IGNORE INTO live_keys (pub, env, status, updated_at) VALUES (?1, ?2, 'free', ?3)").bind(p, e, now)));
  }
  const free = (await env.DB.prepare("SELECT COUNT(*) AS n FROM live_keys WHERE env = ?1 AND status = 'free'").bind(e).first<{ n: number }>())?.n ?? 0;
  return json({ ok: true, free });
}
