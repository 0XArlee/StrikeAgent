// Alerts on Telegram (@EdgeCraftStrikeCityBot) and in the city. The agents' host runs the bot (smartflow/alerts): it
// watches Strike Finance for everyone and, for owners who link it here, their agent, accounts and copies. Linking: the
// owner's session makes a one-time code (ten minutes); the Alerts tab opens t.me/<bot>?start=<code>; the bot asks this
// site (HMAC) whose code it is and claims it. The owner sees the linked chat and can unlink it. The bot's public
// Strike alerts are pushed here like the News Tower's document and served to the city.
/// <reference path="./env.d.ts" />
import { fromHost, liveEnv } from "./live";
import { edgeCache, fail, json, readToken } from "./util";

export const BOT = "EdgeCraftStrikeCityBot";
const CODE_TTL = 10 * 60_000;
const MAX = 400_000;
const STALE_MS = 15 * 60_000;   // the host sends it at least every 10 minutes
const cacheKey = (req: Request) => new Request(new URL("/api/alerts", req.url).toString());

function newCode(env: Env): string {
  const b = crypto.getRandomValues(new Uint8Array(15));
  const s = btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return (liveEnv(env) === "testnet" ? "q" : "m") + s;   // the bot asks the site of the code's network
}

async function chats(env: Env, user: string) {
  try {
    return (await env.DB.prepare("SELECT chat, label, linked_at FROM tg_chats WHERE user_id = ?1 ORDER BY linked_at")
      .bind(user).all<{ chat: string; label: string; linked_at: number }>()).results;
  } catch { return []; }   // before the migration
}

/** GET /api/me/telegram: the chats linked to the owner's agent. POST: a one-time link to the bot. DELETE: unlink. */
export async function meTelegram({ request, env }: Ctx): Promise<Response> {
  const now = Date.now();
  const user = await readToken(env.SESSION_SECRET, request, now);
  if (!user) return fail(401, "sign in again");
  if (request.method === "GET") {
    return json({ bot: BOT, chats: (await chats(env, user)).map((c) => ({ label: c.label, since: c.linked_at })) });
  }
  if (request.method === "DELETE") {
    await env.DB.prepare("DELETE FROM tg_chats WHERE user_id = ?1").bind(user).run();
    return json({ ok: true });
  }
  let lang = "en";
  try { lang = ((await request.json()) as { lang?: string }).lang === "es" ? "es" : "en"; } catch { /* no body */ }
  const recent = await env.DB.prepare("SELECT COUNT(*) AS n FROM tg_links WHERE user_id = ?1 AND created_at > ?2").bind(user, now - CODE_TTL)
    .first<{ n: number }>();
  if ((recent?.n ?? 0) >= 5) return fail(429, "too many links: wait a few minutes");
  const code = newCode(env);
  await env.DB.batch([
    env.DB.prepare("DELETE FROM tg_links WHERE expires_at < ?1").bind(now),
    env.DB.prepare("INSERT INTO tg_links (code, user_id, lang, created_at, expires_at) VALUES (?1, ?2, ?3, ?4, ?5)")
      .bind(code, user, lang, now, now + CODE_TTL),
  ]);
  return json({ url: `https://t.me/${BOT}?start=${code}`, expires: now + CODE_TTL });
}

async function owner(env: Env, user: string) {
  return env.DB.prepare("SELECT u.id, u.name, u.address, l.account_id FROM users u LEFT JOIN live_links l ON l.user_id = u.id AND l.env = ?2 "
    + "AND l.status = 'active' WHERE u.id = ?1").bind(user, liveEnv(env)).first<{ id: string; name: string; address: string; account_id: string | null }>();
}

/** GET /api/internal/telegram?code=… (HMAC): whose code it is, if still valid. ?sync=1: every owner with linked chats. */
export async function hostTelegram({ request, env }: Ctx): Promise<Response> {
  const url = new URL(request.url), now = Date.now();
  if (request.method === "GET") {
    if (!(await fromHost(env, request, `GET ${url.pathname}${url.search}`))) return fail(401, "bad signature");
    const code = url.searchParams.get("code");
    if (code) {
      const r = await env.DB.prepare("SELECT user_id, lang FROM tg_links WHERE code = ?1 AND claimed_at IS NULL AND expires_at > ?2")
        .bind(code, now).first<{ user_id: string; lang: string }>();
      const u = r ? await owner(env, r.user_id) : null;
      return json(u ? { userId: u.id, name: u.name, address: u.address, accountId: u.account_id, lang: r!.lang, env: liveEnv(env) } : {});
    }
    const rows = (await env.DB.prepare("SELECT c.user_id, c.chat, u.name, l.account_id FROM tg_chats c JOIN users u ON u.id = c.user_id "
      + "LEFT JOIN live_links l ON l.user_id = c.user_id AND l.env = ?1 AND l.status = 'active'").bind(liveEnv(env))
      .all<{ user_id: string; chat: string; name: string; account_id: string | null }>()).results;
    const users = new Map<string, { userId: string; name: string; accountId: string | null; chats: string[] }>();
    for (const r of rows) {
      const u = users.get(r.user_id) ?? { userId: r.user_id, name: r.name, accountId: r.account_id, chats: [] };
      u.chats.push(r.chat);
      users.set(r.user_id, u);
    }
    return json({ env: liveEnv(env), users: [...users.values()] });
  }
  const raw = await request.text();
  if (raw.length > 4_000 || !(await fromHost(env, request, raw))) return fail(401, "bad signature");
  let b: { claim?: { code?: string; chat?: string; label?: string }; unlink?: { userId?: string; chat?: string } };
  try { b = JSON.parse(raw); } catch { return fail(400, "not JSON"); }
  if (b.claim?.code && b.claim.chat) {
    const r = await env.DB.prepare("UPDATE tg_links SET claimed_at = ?2 WHERE code = ?1 AND claimed_at IS NULL AND expires_at > ?2 RETURNING user_id")
      .bind(b.claim.code, now).first<{ user_id: string }>();
    if (!r) return fail(410, "link expired or used");
    await env.DB.prepare("INSERT INTO tg_chats (user_id, chat, label, linked_at) VALUES (?1, ?2, ?3, ?4) "
      + "ON CONFLICT(user_id, chat) DO UPDATE SET label = excluded.label, linked_at = excluded.linked_at")
      .bind(r.user_id, String(b.claim.chat).slice(0, 32), String(b.claim.label ?? "Telegram").slice(0, 60), now).run();
    return json({ ok: true, userId: r.user_id });
  }
  if (b.unlink?.userId && b.unlink.chat) {
    await env.DB.prepare("DELETE FROM tg_chats WHERE user_id = ?1 AND chat = ?2").bind(b.unlink.userId, String(b.unlink.chat)).run();
    return json({ ok: true });
  }
  return fail(400, "nothing to do");
}

/** POST /api/internal/alerts: the bot's public Strike alerts (HMAC, like the News Tower's document). */
export async function hostAlerts(c: Ctx): Promise<Response> {
  const { request, env } = c;
  const raw = await request.text();
  if (raw.length > MAX) return fail(413, "alerts too large");
  if (!(await fromHost(env, request, raw))) return fail(401, "bad signature");
  let doc: { v?: unknown; generated?: unknown; alerts?: unknown };
  try { doc = JSON.parse(raw); } catch { return fail(400, "not JSON"); }
  if (!doc || doc.v !== 1 || typeof doc.generated !== "number" || !Array.isArray(doc.alerts) || doc.alerts.length > 200) return fail(400, "not an alerts document");
  const now = Date.now();
  await env.DB.prepare("INSERT INTO snapshots (key, body, updated_at) VALUES ('alerts', ?1, ?2) "
    + "ON CONFLICT(key) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at").bind(raw, now).run();
  c.waitUntil(edgeCache().delete(cacheKey(request)).catch(() => false));
  return json({ ok: true, alerts: doc.alerts.length });
}

/** GET /api/alerts: Strike Finance's latest moments (cached 30 s at the edge); {none: true} before the first. */
export async function alerts(c: Ctx): Promise<Response> {
  const cache = edgeCache(), key = cacheKey(c.request);
  const hit = await cache.match(key).catch(() => undefined);
  if (hit) return hit;
  const row = await c.env.DB.prepare("SELECT body, updated_at FROM snapshots WHERE key = 'alerts'").first<{ body: string; updated_at: number }>();
  const now = Date.now();
  const body = row ? `{"bot":"${BOT}","pushedAt":${row.updated_at},"stale":${now - row.updated_at > STALE_MS},${row.body.slice(1)}`
    : JSON.stringify({ bot: BOT, none: true });
  const res = new Response(body, { headers: { "Content-Type": "application/json; charset=utf-8", "X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=30" } });
  c.waitUntil(cache.put(key, res.clone()).catch(() => undefined));
  return res;
}
