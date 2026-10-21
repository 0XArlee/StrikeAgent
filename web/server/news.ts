// The News Tower's data: the agents' host collects headlines, has a model score them and measures each one's
// reaction on Strike (smartflow/news), then signs and sends the document here like the city's snapshot. The site
// keeps the last one and serves it to everyone. Information only: the agents never read it.
/// <reference path="./env.d.ts" />
import { fromHost } from "./live";
import { edgeCache, fail, json } from "./util";

const MAX = 1_000_000;
const STALE_MS = 20 * 60_000;   // the host sends it every 5 minutes: older than this, the page says so
const cacheKey = (req: Request) => new Request(new URL("/api/news", req.url).toString());

/** POST /api/internal/news: the document from the agents' host (HMAC, like the city's push). */
export async function hostNews(c: Ctx): Promise<Response> {
  const { request, env } = c;
  if (Number(request.headers.get("Content-Length") ?? 0) > MAX) return fail(413, "news too large");
  const raw = await request.text();
  if (raw.length > MAX) return fail(413, "news too large");
  if (!(await fromHost(env, request, raw))) return fail(401, "bad signature");
  let doc: { v?: unknown; generated?: unknown; markets?: unknown; headlines?: unknown };
  try { doc = JSON.parse(raw); } catch { return fail(400, "not JSON"); }
  if (!doc || doc.v !== 1 || typeof doc.generated !== "number" || !doc.markets || typeof doc.markets !== "object"
      || !Array.isArray(doc.headlines) || doc.headlines.length > 300) return fail(400, "not a news document");
  const now = Date.now();
  await env.DB.prepare("INSERT INTO snapshots (key, body, updated_at) VALUES ('news', ?1, ?2) "
    + "ON CONFLICT(key) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at").bind(raw, now).run();
  c.waitUntil(edgeCache().delete(cacheKey(request)).catch(() => false));
  return json({ ok: true, headlines: doc.headlines.length });
}

/** GET /api/news: the last document (cached 30 s at the edge), with when it arrived; {none: true} before the first. */
export async function news(c: Ctx): Promise<Response> {
  const cache = edgeCache(), key = cacheKey(c.request);
  const hit = await cache.match(key).catch(() => undefined);
  if (hit) return hit;
  const row = await c.env.DB.prepare("SELECT body, updated_at FROM snapshots WHERE key = 'news'").first<{ body: string; updated_at: number }>();
  const now = Date.now();
  const body = row
    ? `{"pushedAt":${row.updated_at},"stale":${now - row.updated_at > STALE_MS},${row.body.slice(1)}`
    : JSON.stringify({ none: true });
  const res = new Response(body, { headers: { "Content-Type": "application/json; charset=utf-8", "X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=30" } });
  c.waitUntil(cache.put(key, res.clone()).catch(() => undefined));
  return res;
}
