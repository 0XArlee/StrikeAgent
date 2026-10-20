// The audit trail for the agents' host (HMAC, like the other internal routes): it copies the site's rows every minute
// and sends the heads of its own tamper-evident logs, which the site keeps (migrations/005_audit.sql).
/// <reference path="./env.d.ts" />
import { fromHost } from "./live";
import { fail, json } from "./util";

const FILE = /^[\w.-]+(\/[\w.-]+)?$/;
const HASH = /^[0-9a-f]{64}$/;

/** GET /api/internal/audit?after=<id>: the next rows of the audit trail, oldest first. */
export async function hostAudit({ request, env }: Ctx): Promise<Response> {
  const url = new URL(request.url);
  if (!(await fromHost(env, request, `GET ${url.pathname}${url.search}`))) return fail(401, "bad signature");
  const after = Math.max(0, Math.floor(Number(url.searchParams.get("after") ?? 0)) || 0);
  const rows = (await env.DB.prepare("SELECT * FROM audit WHERE id > ?1 ORDER BY id LIMIT 500").bind(after)
    .all<Record<string, unknown>>()).results;
  return json({ rows: rows.map((r) => ({ ...r, detail: r.detail ? JSON.parse(String(r.detail)) : null })) });
}

/** POST /api/internal/anchors {"heads": {file: [seq, hash]}}: kept for good (a later rewrite on the host shows). */
export async function hostAnchors({ request, env }: Ctx): Promise<Response> {
  const raw = await request.text();
  if (raw.length > 60_000 || !(await fromHost(env, request, raw))) return fail(401, "bad signature");
  let b: { heads?: unknown };
  try { b = JSON.parse(raw); } catch { return fail(400, "not JSON"); }
  const heads = b.heads && typeof b.heads === "object" ? Object.entries(b.heads as Record<string, unknown>) : null;
  if (!heads || heads.length > 200 || heads.some(([f, v]) => !FILE.test(f) || f.length > 200 || !Array.isArray(v) || v.length !== 2
      || !Number.isInteger(v[0]) || (v[0] as number) < 0 || typeof v[1] !== "string" || !HASH.test(v[1]))) return fail(400, "invalid heads");
  const now = Date.now();
  if (heads.length) {
    await env.DB.batch(heads.map(([f, v]) => env.DB.prepare("INSERT OR IGNORE INTO audit_anchors (file, seq, hash, time) VALUES (?1, ?2, ?3, ?4)")
      .bind(f, (v as [number, string])[0], (v as [number, string])[1], now)));
  }
  return json({ ok: true, kept: heads.length });
}

/** POST /api/internal/heads {"files": [...]}: what the site kept for these files, to check the host's copy. */
export async function hostHeads({ request, env }: Ctx): Promise<Response> {
  const raw = await request.text();
  if (raw.length > 20_000 || !(await fromHost(env, request, raw))) return fail(401, "bad signature");
  let b: { files?: unknown };
  try { b = JSON.parse(raw); } catch { return fail(400, "not JSON"); }
  const files = Array.isArray(b.files) ? b.files : null;
  if (!files || !files.length || files.length > 50 || files.some((f) => typeof f !== "string" || !FILE.test(f))) return fail(400, "invalid files");
  const q = `SELECT file, seq, hash FROM audit_anchors WHERE file IN (${files.map((_, i) => `?${i + 1}`).join(",")}) ORDER BY file, seq`;
  const rows = (await env.DB.prepare(q).bind(...files).all<{ file: string; seq: number; hash: string }>()).results;
  const anchors: Record<string, [number, string][]> = {};
  for (const r of rows) (anchors[r.file] ??= []).push([r.seq, r.hash]);
  return json({ anchors });
}
