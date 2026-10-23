// Copy with your agent: the copy plan an owner signs with their wallet (whom to copy or let the agent choose, when, how),
// kept here for the agents' host, which carries it out on Strike's own copy trading in a sub-account of the owner's
// (smartflow/copytrade/pilot.py) and reports how it goes. Strike City never holds money: Strike moves it from the
// owner's account into the copy's sub-account, and the stop-loss ends the copy on Strike's side.
/// <reference path="./env.d.ts" />
import { fromHost, liveEnv } from "./live";
import { fail, json } from "./util";

export interface CopyPlan {
  mode: "off" | "manual" | "pilot";
  lead: string | null; platform: "strike" | "hyperliquid" | null;          // manual: the trader
  sizing: { kind: "ratio"; amount: number } | { kind: "fixed"; margin: number; funding: number };
  stopLoss: number;                 // $ the copy may lose before Strike ends it
  leverage: number;                 // the copy's sub-account (isolated margin)
  excluded: string[];               // markets it never opens
  until: number | null;             // the agent stops the copy then
  alarmPause: boolean;              // stopped while the News Tower's security alarm is on (a hack, an exchange going down)
  macroPause: boolean;              // and from 30 min before to an hour after the big US releases (Fed, CPI, jobs, PCE, GDP)
  account: string;                  // "auto": a free sub-account of the owner's, else a new one; "new"; or a sub-account's id
  pilot: { minScore: number; platforms: ("strike" | "hyperliquid")[]; review: number; maxSwitches: number } | null;
}

const LEAD = /^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|0x[0-9a-f]{40})$/i;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SYMBOL = /^[A-Z0-9:]{1,20}-USD$/;
const REVIEWS = [6, 12, 24, 72, 168];
const MIN_COPY = 20;   // Strike's minimum copy amount and margin per entry (GET /v2/copy/lead-traders)
const num = (v: unknown, lo: number, hi: number) => (typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi ? v : null);

/** A plan from the page, checked; a string says what is wrong. */
export function normalizePlan(v: unknown, now: number): CopyPlan | string {
  const p = (v ?? {}) as Record<string, unknown>;
  const mode = p.mode;
  if (mode !== "off" && mode !== "manual" && mode !== "pilot") return "choose manual, pilot or off";
  const s = (p.sizing ?? {}) as Record<string, unknown>;
  let sizing: CopyPlan["sizing"];
  if (s.kind === "ratio") {
    const amount = num(s.amount, MIN_COPY, 100_000);
    if (amount == null) return "the copy amount goes from 20 $ (Strike's minimum) to 100,000 $";
    sizing = { kind: "ratio", amount };
  } else if (s.kind === "fixed") {
    const margin = num(s.margin, MIN_COPY, 10_000), funding = num(s.funding, MIN_COPY, 100_000);
    if (margin == null || funding == null || funding < margin) return "the margin per entry goes from 20 $ (Strike's minimum), and what goes into the copy covers at least one entry";
    sizing = { kind: "fixed", margin, funding };
  } else return "choose fixed ratio or fixed margin";
  const budget = sizing.kind === "ratio" ? sizing.amount : sizing.funding;
  const stopLoss = num(p.stopLoss, 1, budget);
  if (stopLoss == null) return "the stop-loss goes from 1 $ to what goes into the copy";
  const leverage = num(p.leverage, 1, 20);
  if (leverage == null || !Number.isInteger(leverage)) return "the leverage goes from 1x to 20x";
  const excluded = Array.isArray(p.excluded) ? p.excluded : [];
  if (excluded.length > 30 || excluded.some((m) => typeof m !== "string" || !SYMBOL.test(m))) return "invalid markets";
  const until = p.until == null ? null : num(p.until, now + 3_600_000, now + 366 * 86_400_000);
  if (p.until != null && until == null) return "the end date goes from one hour to one year from now";
  let lead: string | null = null, platform: CopyPlan["platform"] = null, pilot: CopyPlan["pilot"] = null;
  if (mode === "manual") {
    if (typeof p.lead !== "string" || !LEAD.test(p.lead) || (p.platform !== "strike" && p.platform !== "hyperliquid")) return "choose the trader to copy";
    lead = p.platform === "hyperliquid" ? p.lead.toLowerCase() : p.lead;
    platform = p.platform;
  }
  if (mode === "pilot") {
    const q = (p.pilot ?? {}) as Record<string, unknown>;
    const minScore = num(q.minScore, 0, 100), maxSwitches = num(q.maxSwitches, 0, 7);
    const platforms = Array.isArray(q.platforms) ? [...new Set(q.platforms.filter((x) => x === "strike" || x === "hyperliquid"))] as ("strike" | "hyperliquid")[] : [];
    const review = typeof q.review === "number" && REVIEWS.includes(q.review) ? q.review : null;
    if (minScore == null || maxSwitches == null || !Number.isInteger(maxSwitches) || !platforms.length || review == null) return "invalid pilot rules";
    pilot = { minScore, platforms, review, maxSwitches };
  }
  const account = p.account == null || p.account === "auto" ? "auto" : p.account === "new" ? "new"
    : typeof p.account === "string" && UUID.test(p.account) ? p.account.toLowerCase() : null;
  if (account == null) return "choose where the copy runs";
  return { mode, lead, platform, sizing, stopLoss, leverage, excluded: [...new Set(excluded as string[])], until, alarmPause: !!p.alarmPause,
    macroPause: !!p.macroPause, account, pilot };
}

const usd = (v: number) => `${v.toLocaleString("en-US", { maximumFractionDigits: 2 })} $`;
const iso = (t: number) => new Date(t).toISOString().slice(0, 16).replace("T", " ") + " UTC";

/** What the owner signs: the whole plan, in plain words. */
export function planLines(p: CopyPlan): string[] {
  if (p.mode === "off") return ["My agent stops copying: Strike stops the copy and closes its copied positions.",
    "What is left in the copy's sub-account goes back to my main account from Strike's app."];
  const who = p.mode === "manual"
    ? `My agent copies ${p.platform === "hyperliquid" ? "the Hyperliquid wallet" : "the Strike trader"} ${p.lead} on Strike's copy trading.`
    : `My agent chooses whom to copy on Strike's copy trading: Strike City's score ${p.pilot!.minScore} or more, on ${p.pilot!.platforms.join(" and ")}, `
      + `reviewed every ${p.pilot!.review} h, at most ${p.pilot!.maxSwitches} changes a week.`;
  const how = p.sizing.kind === "ratio"
    ? `Fixed ratio: ${usd(p.sizing.amount)} (every order of the trader scaled to it).`
    : `Fixed margin: ${usd(p.sizing.margin)} per entry, ${usd(p.sizing.funding)} in all.`;
  const where = p.account === "new" ? "It runs in a new sub-account that Strike creates and funds from my main account."
    : p.account === "auto" ? "It runs in a sub-account of mine that copies nobody and has the money; only if none does, Strike creates a new one funded from my main account."
    : `It runs in my sub-account ${p.account}, with the money that is in it.`;
  return [who,
    `${where} ${how}`,
    `Strike ends the copy if it loses ${usd(p.stopLoss)}. Leverage in the copy's sub-account: ${p.leverage}x, isolated margin.`,
    p.excluded.length ? `It never opens: ${p.excluded.join(", ")}.` : "It may open every market the trader trades on Strike.",
    p.until ? `It stops on ${iso(p.until)}.` : "No end date.",
    p.alarmPause ? "It stops while the News Tower's security alarm is on (a hack, an exchange going down) and starts again after it." : "The News Tower's security alarm does not stop it.",
    ...(p.macroPause ? ["It also stops from 30 minutes before to an hour after the big US releases (Fed decisions, CPI, jobs, PCE, GDP)."] : []),
    "Money moves between my main account and my sub-accounts in Strike's app."];
}

/** The upsert of a signed plan: each change is a new version the host carries out once. */
export const savePlan = (db: D1Database, userId: string, env: string, p: CopyPlan, now: number) =>
  db.prepare("INSERT INTO copy_plans (user_id, env, plan, version, updated_at) VALUES (?1, ?2, ?3, 1, ?4) "
    + "ON CONFLICT(user_id) DO UPDATE SET env = excluded.env, plan = excluded.plan, version = copy_plans.version + 1, updated_at = excluded.updated_at")
    .bind(userId, env, JSON.stringify(p), now);

export interface CopyView { plan: CopyPlan | null; version: number | null; status: Record<string, unknown> | null }

/** The owner's plan and what the host last reported (My agent). */
export async function copyView(db: D1Database, userId: string, env: string): Promise<CopyView> {
  const [plan, status] = await Promise.all([
    db.prepare("SELECT plan, version FROM copy_plans WHERE user_id = ?1 AND env = ?2").bind(userId, env).first<{ plan: string; version: number }>(),
    db.prepare("SELECT body FROM copy_status WHERE user_id = ?1").bind(userId).first<{ body: string }>(),
  ]).catch(() => [null, null] as const);   // before the migration: no copy yet
  const st = status ? JSON.parse(status.body) as Record<string, unknown> : null;
  return { plan: plan ? JSON.parse(plan.plan) as CopyPlan : null, version: plan?.version ?? null, status: st && st.env === env ? st : null };
}

/** Whom each of these users' agents copies now (the city walks them behind their trader). */
export async function copying(db: D1Database, ids: string[], env: string): Promise<Map<string, { lead: string; platform: string; since: number | null }>> {
  const out = new Map<string, { lead: string; platform: string; since: number | null }>();
  if (!ids.length) return out;
  try {
    const rows = (await db.prepare(`SELECT user_id, body FROM copy_status WHERE user_id IN (${ids.map((_, i) => `?${i + 1}`).join(",")})`)
      .bind(...ids).all<{ user_id: string; body: string }>()).results;
    for (const r of rows) {
      const b = JSON.parse(r.body) as { state?: string; lead?: string; platform?: string; since?: number; env?: string };
      if (b.env === env && b.state === "copying" && b.lead && b.platform) out.set(r.user_id, { lead: b.lead, platform: b.platform, since: b.since ?? null });
    }
  } catch { /* before the migration */ }
  return out;
}

/** GET /api/internal/copyplans (HMAC): the plans of the owners connected to Strike on this site's network. An agent
 *  deleted or disconnected from Strike has its plan served as "off" (so the host stops a copy still running) until
 *  the host reports nothing left to stop. */
export async function hostCopyPlans({ request, env }: { request: Request; env: Env }): Promise<Response> {
  if (!(await fromHost(env, request, "GET /api/internal/copyplans"))) return fail(401, "bad signature");
  const e = liveEnv(env);
  const rows = (await env.DB.prepare("SELECT c.user_id, c.plan, c.version, l.pub, l.account_id, l.status AS link, u.id AS uid, s.body AS status "
    + "FROM copy_plans c JOIN live_links l ON l.user_id = c.user_id AND l.env = ?1 LEFT JOIN users u ON u.id = c.user_id "
    + "LEFT JOIN copy_status s ON s.user_id = c.user_id WHERE c.env = ?1").bind(e)
    .all<{ user_id: string; plan: string; version: number; pub: string; account_id: string; link: string; uid: string | null; status: string | null }>()).results;
  const plans = [];
  for (const r of rows) {
    const gone = r.link !== "active" || !r.uid;
    const plan = JSON.parse(r.plan) as CopyPlan;
    if (gone) {
      const st = r.status ? JSON.parse(r.status) as { state?: string; env?: string } : null;
      if (st?.env === e && st.state === "off") continue;   // stopped and reported: nothing left to do
      plan.mode = "off";
    }
    plans.push({ userId: r.user_id, pub: r.pub, accountId: r.account_id, version: r.version, plan });
  }
  return json({ env: e, plans });
}

/** POST /api/internal/copystatus (HMAC): how each plan goes, as the host saw it. */
export async function hostCopyStatus({ request, env }: { request: Request; env: Env }): Promise<Response> {
  const raw = await request.text();
  if (raw.length > 2_000_000) return fail(413, "too large");
  if (!(await fromHost(env, request, raw))) return fail(401, "bad signature");
  let b: { env?: unknown; status?: unknown };
  try { b = JSON.parse(raw); } catch { return fail(400, "not JSON"); }
  const e = liveEnv(env);
  if (b.env !== e || !Array.isArray(b.status) || b.status.length > 500) return fail(400, "not a copy status");
  const now = Date.now();
  // each owner's status, with their sub-accounts' equity over time (a week of points each): up to 40 kB
  const rows = (b.status as Record<string, unknown>[]).filter((s) => typeof s?.userId === "string" && JSON.stringify(s).length < 40_000);
  if (rows.length) {
    await env.DB.batch(rows.map((s) => env.DB.prepare("INSERT INTO copy_status (user_id, body, updated_at) VALUES (?1, ?2, ?3) "
      + "ON CONFLICT(user_id) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at")
      .bind(s.userId as string, JSON.stringify({ ...s, env: e }), now)));
  }
  return json({ ok: true, saved: rows.length });
}

