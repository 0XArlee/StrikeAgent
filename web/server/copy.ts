// Strike's copy trading for the city's Copy Arena: the agents' host reads Strike's public copy-trading data and keeps
// its history (smartflow/copytrade), then signs and sends the document here like the news. The site keeps the last one
// and serves it to everyone. Public data only; nothing here copies anyone.
/// <reference path="./env.d.ts" />
import { fromHost } from "./live";
import { edgeCache, fail, json } from "./util";

const MAX = 1_500_000;
const STALE_MS = 20 * 60_000;
const cacheKey = (req: Request) => new Request(new URL("/api/copy", req.url).toString());

/** POST /api/internal/copy: the document from the agents' host (HMAC, like the city's push). */
export async function hostCopy(c: Ctx): Promise<Response> {
  const { request, env } = c;
  if (Number(request.headers.get("Content-Length") ?? 0) > MAX) return fail(413, "copy document too large");
  const raw = await request.text();
  if (raw.length > MAX) return fail(413, "copy document too large");
  if (!(await fromHost(env, request, raw))) return fail(401, "bad signature");
  let doc: { v?: unknown; generated?: unknown; traders?: unknown; strike?: unknown };
  try { doc = JSON.parse(raw); } catch { return fail(400, "not JSON"); }
  if (!doc || doc.v !== 1 || typeof doc.generated !== "number" || !Array.isArray(doc.traders) || doc.traders.length > 200
      || !doc.strike || typeof doc.strike !== "object") return fail(400, "not a copy-trading document");
  const now = Date.now();
  await env.DB.prepare("INSERT INTO snapshots (key, body, updated_at) VALUES ('copy', ?1, ?2) "
    + "ON CONFLICT(key) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at").bind(raw, now).run();
  c.waitUntil(edgeCache().delete(cacheKey(request)).catch(() => false));
  return json({ ok: true, traders: doc.traders.length });
}

/** GET /api/copy: the last document (cached 30 s at the edge), with when it arrived; {none: true} before the first. */
export async function copy(c: Ctx): Promise<Response> {
  const cache = edgeCache(), key = cacheKey(c.request);
  const hit = await cache.match(key).catch(() => undefined);
  if (hit) return hit;
  const row = await c.env.DB.prepare("SELECT body, updated_at FROM snapshots WHERE key = 'copy'").first<{ body: string; updated_at: number }>();
  const now = Date.now();
  const body = row
    ? `{"pushedAt":${row.updated_at},"stale":${now - row.updated_at > STALE_MS},${row.body.slice(1)}`
    : JSON.stringify({ none: true });
  const res = new Response(body, { headers: { "Content-Type": "application/json; charset=utf-8", "X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=30" } });
  c.waitUntil(cache.put(key, res.clone()).catch(() => undefined));
  return res;
}
