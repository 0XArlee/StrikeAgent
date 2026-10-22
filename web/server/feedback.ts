// Suggestions and feedback from the site (the "Feedback" button): a subject, a message and an optional picture, kept in
// D1 and private: only the site's admins read them (My agent's inbox, ADMIN_IDS) and the agents' host takes the new
// ones to send them to the operator's phone (the same alert channel as its other alerts), with a signed link to the
// picture. Who wrote it is known only if they were signed in; the IP is kept as its network (/24), to limit abuse.
/// <reference path="./env.d.ts" />
import { fromHost } from "./live";
import { ipNet } from "./store";
import { body, fail, hmacHex, json, readToken, sameText } from "./util";

const MAX_SUBJECT = 120, MAX_MESSAGE = 4000, MAX_IMAGE = 1_500_000;   // chars; the page shrinks pictures well below
const PER_HOUR = 6;
const IMAGE = /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/;

export interface FeedbackRow {
  id: string; created_at: number; subject: string; message: string; image: string | null; page: string | null; lang: string | null;
  user_id: string | null; ua: string | null; ip_net: string | null; read_at: number | null; sent_at: number | null;
}

const clean = (v: unknown, max: number) => (typeof v === "string" ? v.replace(/\u0000/g, "").trim().slice(0, max) : "");

/** POST /api/feedback: anyone may send one (a few an hour per network); signed in, it says which agent wrote it. */
export async function sendFeedback({ request, env }: Ctx): Promise<Response> {
  const now = Date.now();
  const b = await body<{ subject?: unknown; message?: unknown; image?: unknown; page?: unknown; lang?: unknown }>(request, 2_200_000);
  if (!b) return fail(400, "invalid request");
  const subject = clean(b.subject, MAX_SUBJECT), message = clean(b.message, MAX_MESSAGE);
  if (subject.length < 2) return fail(400, "write a subject");
  if (message.length < 2) return fail(400, "write a message");
  let image: string | null = null;
  if (b.image != null && b.image !== "") {
    if (typeof b.image !== "string" || b.image.length > MAX_IMAGE || !IMAGE.test(b.image)) return fail(400, "the picture must be a JPEG, PNG or WebP under 1 MB");
    image = b.image;
  }
  const net = ipNet(request);
  const recent = await env.DB.prepare("SELECT COUNT(*) AS n FROM feedback WHERE ip_net IS ?1 AND created_at > ?2").bind(net, now - 3600_000).first<{ n: number }>();
  if ((recent?.n ?? 0) >= PER_HOUR) return fail(429, "you sent several in the last hour: try again later");
  const user = await readToken(env.SESSION_SECRET, request, now);
  const id = crypto.randomUUID();
  await env.DB.prepare("INSERT INTO feedback (id, created_at, subject, message, image, page, lang, user_id, ua, ip_net) "
    + "VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)")
    .bind(id, now, subject, message, image, clean(b.page, 200) || null, clean(b.lang, 5) || null, user,
      (request.headers.get("User-Agent") ?? "").slice(0, 200) || null, net).run();
  return json({ ok: true, id });
}

const admins = (env: Env) => (env.ADMIN_IDS ?? "").split(",").map((s) => s.trim()).filter(Boolean);
export const isAdmin = (env: Env, id: string) => admins(env).includes(id);

/** GET /api/feedback/inbox: the latest suggestions, for an admin signed in with their wallet (My agent). */
export async function feedbackInbox({ request, env }: Ctx): Promise<Response> {
  const now = Date.now();
  const id = await readToken(env.SESSION_SECRET, request, now);
  if (!id) return fail(401, "sign in again with your wallet");
  if (!admins(env).includes(id)) return fail(403, "only the site's admins read the suggestions");
  const rows = (await env.DB.prepare("SELECT f.*, u.name AS user_name FROM feedback f LEFT JOIN users u ON u.id = f.user_id "
    + "ORDER BY f.created_at DESC LIMIT 100").all<FeedbackRow & { user_name: string | null }>()).results;
  return json({
    unread: rows.filter((r) => !r.read_at).length,
    items: rows.map((r) => ({ id: r.id, t: r.created_at, subject: r.subject, message: r.message, image: r.image, page: r.page, lang: r.lang,
      user: r.user_id ? { id: r.user_id, name: r.user_name } : null, read: !!r.read_at })),
  });
}

/** POST /api/feedback/read: an admin marks them read. */
export async function feedbackRead({ request, env }: Ctx): Promise<Response> {
  const now = Date.now();
  const id = await readToken(env.SESSION_SECRET, request, now);
  if (!id || !admins(env).includes(id)) return fail(403, "only the site's admins read the suggestions");
  const b = await body<{ ids?: unknown }>(request);
  const ids = Array.isArray(b?.ids) ? b!.ids.filter((x): x is string => typeof x === "string").slice(0, 100) : [];
  if (ids.length) await env.DB.batch(ids.map((x) => env.DB.prepare("UPDATE feedback SET read_at = ?2 WHERE id = ?1 AND read_at IS NULL").bind(x, now)));
  return json({ ok: true });
}

/** The signature of a picture's link (the agents' host builds the same one to send it to the operator). */
const imageSig = (env: Env, id: string) => hmacHex(env.PUSH_SECRET, `feedback-image.${id}`);

/** GET /api/feedback/image?id=&sig=: one picture, for whoever has its signed link. */
export async function feedbackImage({ request, env }: Ctx): Promise<Response> {
  const u = new URL(request.url);
  const id = u.searchParams.get("id") ?? "", sig = u.searchParams.get("sig") ?? "";
  if (!/^[0-9a-f-]{36}$/.test(id) || !env.PUSH_SECRET || !sameText(await imageSig(env, id), sig)) return fail(404, "not found");
  const r = await env.DB.prepare("SELECT image FROM feedback WHERE id = ?1").bind(id).first<{ image: string | null }>();
  const m = r?.image ? /^data:(image\/(?:jpeg|png|webp));base64,(.+)$/.exec(r.image) : null;
  if (!m) return fail(404, "not found");
  const bin = Uint8Array.from(atob(m[2]), (c) => c.charCodeAt(0));
  return new Response(bin, { headers: { "Content-Type": m[1], "Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'" } });
}

/** GET /api/internal/feedback: the ones not yet sent to the operator (HMAC, the agents' host); POST: they were sent. */
export async function hostFeedback({ request, env }: Ctx): Promise<Response> {
  if (request.method === "POST") {
    const raw = await request.text();
    if (raw.length > 10_000 || !(await fromHost(env, request, raw))) return fail(401, "bad signature");
    let b: { ids?: unknown };
    try { b = JSON.parse(raw); } catch { return fail(400, "not JSON"); }
    const ids = Array.isArray(b.ids) ? b.ids.filter((x): x is string => typeof x === "string").slice(0, 50) : [];
    const now = Date.now();
    if (ids.length) await env.DB.batch(ids.map((x) => env.DB.prepare("UPDATE feedback SET sent_at = ?2 WHERE id = ?1").bind(x, now)));
    return json({ ok: true });
  }
  if (!(await fromHost(env, request, "GET /api/internal/feedback"))) return fail(401, "bad signature");
  const origin = new URL(request.url).origin;
  const rows = (await env.DB.prepare("SELECT f.id, f.created_at, f.subject, f.message, f.page, f.lang, f.user_id, u.name AS user_name, "
    + "f.image IS NOT NULL AS has_image FROM feedback f LEFT JOIN users u ON u.id = f.user_id WHERE f.sent_at IS NULL ORDER BY f.created_at LIMIT 20")
    .all<{ id: string; created_at: number; subject: string; message: string; page: string | null; lang: string | null; user_id: string | null;
      user_name: string | null; has_image: number }>()).results;
  return json({ items: await Promise.all(rows.map(async (r) => ({
    id: r.id, t: r.created_at, subject: r.subject, message: r.message, page: r.page, lang: r.lang, user: r.user_name ?? r.user_id,
    image: r.has_image ? `${origin}/api/feedback/image?id=${r.id}&sig=${await imageSig(env, r.id)}` : null,
  }))) });
}
