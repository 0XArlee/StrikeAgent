// D1 access for the Pages Functions: users' agents, one-time challenges, lifecycle events and the agents' snapshot.
/// <reference path="./env.d.ts" />
import { freshen, type CityDoc, type UserEvent } from "./agents";
import { CHALLENGE_TTL, type UserRow } from "./util";

export interface ChallengeRow { id: string; address: string; kind: string; payload: string; message: string; expires_at: number; used: number }

export async function snapshot(db: D1Database, now: number): Promise<CityDoc | null> {
  const row = await db.prepare("SELECT body FROM snapshots WHERE key = 'city'").first<{ body: string }>();
  return row ? freshen(JSON.parse(row.body) as CityDoc, now) : null;
}

/** When the agents' host last pushed (the watchdogs read it from /api/info), or null if it never did. */
export async function snapshotAt(db: D1Database): Promise<number | null> {
  const row = await db.prepare("SELECT updated_at FROM snapshots WHERE key = 'city'").first<{ updated_at: number }>();
  return row?.updated_at ?? null;
}

export function saveSnapshot(db: D1Database, body: string, now: number) {
  return db.prepare("INSERT INTO snapshots (key, body, updated_at) VALUES ('city', ?1, ?2) "
    + "ON CONFLICT(key) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at").bind(body, now).run();
}

export const userById = (db: D1Database, id: string) => db.prepare("SELECT * FROM users WHERE id = ?1").bind(id).first<UserRow>();

export async function publicUsers(db: D1Database): Promise<UserRow[]> {
  return (await db.prepare("SELECT * FROM users WHERE public = 1 ORDER BY created_at LIMIT 500").all<UserRow>()).results;
}

export async function eventsFor(db: D1Database, ids: string[]): Promise<Map<string, UserEvent[]>> {
  const out = new Map<string, UserEvent[]>(ids.map((i) => [i, []]));
  for (let k = 0; k < ids.length; k += 90) {   // D1 binds at most 100 parameters per query
    const part = ids.slice(k, k + 90);
    const q = `SELECT user_id, time, code FROM events WHERE user_id IN (${part.map((_, i) => `?${i + 1}`).join(",")}) ORDER BY time`;
    const rows = (await db.prepare(q).bind(...part).all<{ user_id: string; time: number; code: UserEvent["code"] }>()).results;
    for (const r of rows) out.get(r.user_id)?.push({ time: r.time, code: r.code });
  }
  return out;
}

export const addEvent = (db: D1Database, id: string, code: UserEvent["code"], now: number) =>
  db.prepare("INSERT INTO events (user_id, time, code) VALUES (?1, ?2, ?3)").bind(id, now, code);

export interface AuditEntry {
  user?: string | null; address?: string | null; action: string; ok: boolean; detail?: unknown;
  message?: string | null; signature?: string | null;
}

/** The IP shortened to its network (/24, /48): enough to tell one place from another, not a person. */
export function ipNet(req: Request): string | null {
  const a = req.headers.get("CF-Connecting-IP");
  if (!a) return null;
  if (a.includes(":")) return `${a.split(":").slice(0, 3).join(":")}::/48`;
  const p = a.split(".");
  return p.length === 4 ? `${p.slice(0, 3).join(".")}.0/24` : null;
}

/** One row of the audit trail (append-only, migrations/005_audit.sql): run it in the same batch as the change. */
export const audit = (db: D1Database, req: Request, env: string, e: AuditEntry, now: number) =>
  db.prepare("INSERT INTO audit (time, env, user_id, address, action, ok, detail, message, signature, ip, country) "
    + "VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)")
    .bind(now, env, e.user ?? null, e.address ?? null, e.action, e.ok ? 1 : 0, e.detail === undefined ? null : JSON.stringify(e.detail),
      e.message ?? null, e.signature ?? null, ipNet(req), req.headers.get("CF-IPCountry"));

/** The same, on its own (a refusal: nothing else to write). Never fails the request it records. */
export async function auditNow(db: D1Database, req: Request, env: string, e: AuditEntry, now: number): Promise<void> {
  try { await audit(db, req, env, e, now).run(); } catch { /* the answer to the user matters more than its record */ }
}

// challenges allowed per 10 minutes: sign-ins are rare, owner actions (pause, show...) can come in a row
const LIMITS: Record<string, { ip: number; address: number }> = { connect: { ip: 10, address: 5 }, action: { ip: 30, address: 20 } };

/** Throttle per IP and per wallet over the last 10 minutes, separately for sign-ins and owner actions. */
export async function tooMany(db: D1Database, ip: string, address: string, kind: "connect" | "action", now: number): Promise<boolean> {
  const since = now - 10 * 60_000, lim = LIMITS[kind];
  const r = await db.prepare("SELECT (SELECT COUNT(*) FROM challenges WHERE ip = ?1 AND kind = ?3 AND created_at > ?4) AS a, "
    + "(SELECT COUNT(*) FROM challenges WHERE address = ?2 AND kind = ?3 AND created_at > ?4) AS b").bind(ip, address, kind, since).first<{ a: number; b: number }>();
  return !!r && (r.a >= lim.ip || r.b >= lim.address);
}

export async function newChallenge(db: D1Database, c: { address: string; kind: string; payload: unknown; message: string; ip: string }, id: string, now: number) {
  await db.batch([
    db.prepare("DELETE FROM challenges WHERE created_at < ?1").bind(now - 86400_000),
    db.prepare("INSERT INTO challenges (id, address, kind, payload, message, ip, created_at, expires_at, used) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 0)")
      .bind(id, c.address, c.kind, JSON.stringify(c.payload), c.message, c.ip, now, now + CHALLENGE_TTL),
  ]);
}

/** Marks the challenge used exactly once (concurrent replays lose) and returns it if it was valid. */
export async function consumeChallenge(db: D1Database, id: string, kind: string, now: number): Promise<ChallengeRow | null> {
  const r = await db.prepare("UPDATE challenges SET used = 1 WHERE id = ?1 AND kind = ?2 AND used = 0 AND expires_at > ?3").bind(id, kind, now).run();
  if (!r.meta.changes) return null;
  return db.prepare("SELECT * FROM challenges WHERE id = ?1").bind(id).first<ChallengeRow>();
}
