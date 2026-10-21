// Users' paper agents. They run the same Smart Flow engine with the published parameters, so their signals are those
// of the reference paper agent on the host; each user's agent applies them to the markets it chose, from the moment it
// started, never while paused, and sized at its own risk per trade. Results in R are the reference fills' (net of
// fees); the paper account compounds them at the user's risk.
/// <reference path="./env.d.ts" />
import { normalizeLook, type Look } from "../src/city/look";
import { accountResult, pointResult, type Portfolio } from "../src/city/portfolio-types";
import { RISK, strategyOf, type UserRow } from "./util";

export interface Decision { time: number; market: string; kind: string; code: string; args?: Record<string, unknown>; text?: string }
// stop/trail are null for a position the agent did not open (a live account can hold one opened by hand)
export interface Position { market: string; side: "long" | "short"; entry: number; stop: number | null; trail: number | null; qty: number | null;
  openedAt?: number | null; id?: string; upnl?: number | null }
export interface Trade { market: string; side: "long" | "short"; entry: number; exit: number; stop?: number; r: number; reason: string; openedAt: number; time: number;
  test?: boolean; qty?: number | null; pnl?: number | null; pnlPct?: number | null }
export interface Agent {
  id: string; name: string; owner?: string; kind?: string; env?: string; tf?: string; variant?: string; changes?: string[];
  markets: string[]; riskPct?: number; feeBps?: number; equity0?: number | null; cash?: number | null; since?: number | null;
  lastCheck?: number | null; nextCheck?: number; status: string; alerts?: unknown[];
  positions: Position[]; trades: Trade[]; checks: Record<string, { time: number; args: Record<string, unknown>; text: string }>;
  decisions: Decision[]; look?: Look | null; error?: string;
  portfolio?: Portfolio;   // a user's live agent: its Strike account (amounts only for the owner, see publicPortfolio)
  strategy?: string;       // smartflow | pyramid
  result?: number | null;  // a live account's result since it started, deposits left out (owner only)
  tally?: { n: number; wins: number; won: number; lost: number; best: number };   // counts over every trade
}
/** A strategy on its safety hold (smartflow/live/health.py): users' agents open no new trades until it is lifted. */
export interface Hold { since: number; why: string[] }
export interface CityDoc { generated: number; engine: string; agents: Agent[]; holds?: Record<string, Hold> }

export const REFERENCE_ID = "sf-reference";
export const PAPER_EQUITY = 10_000;
const STALE_MS = 15 * 60_000;   // the agents' host pushes every 30 s and at least every 10 min

export interface UserEvent { time: number; code: "start" | "pause" | "resume" | "show" | "hide" | "live" | "live_off" | "settings" | "test" }

/** The host stopped pushing: whatever its last snapshot said, nobody is checking the market any more. */
export function freshen(doc: CityDoc, now: number): CityDoc {
  if (now - doc.generated <= STALE_MS) return doc;
  return { ...doc, agents: doc.agents.map((a) => ({ ...a, status: "offline" })) };
}

function pausedAt(events: UserEvent[]): (t: number) => boolean {
  const spans: [number, number][] = [];
  let start: number | null = null;
  for (const e of [...events].sort((a, b) => a.time - b.time)) {
    if (e.code === "pause" && start === null) start = e.time;
    if (e.code === "resume" && start !== null) { spans.push([start, e.time]); start = null; }
  }
  if (start !== null) spans.push([start, Infinity]);
  return (t) => spans.some(([a, b]) => t >= a && t < b);
}

export function userAgent(u: UserRow, ref: Agent | undefined, events: UserEvent[], now: number): Agent {
  const chosen = JSON.parse(u.markets) as string[];
  const markets = ref ? chosen.filter((m) => ref.markets.includes(m)) : chosen;
  const set = new Set(markets);
  const risk = RISK[u.risk] ?? RISK.standard;
  const paused = pausedAt(events);
  const mine = (market: string, opened: number | null | undefined) =>
    set.has(market) && opened != null && opened >= u.created_at && !paused(opened);
  const trades = (ref?.trades ?? []).filter((t) => mine(t.market, t.openedAt))          // newest first
    .map((t) => ({ ...t, qty: null, pnl: null }));   // the reference's money, not this agent's: only R
  let equity = PAPER_EQUITY;
  for (const t of [...trades].reverse()) equity *= 1 + (t.r * risk) / 100;
  const positions = (ref?.positions ?? []).filter((p) => mine(p.market, p.openedAt))
    .map((p) => ({ ...p, qty: (equity * risk) / 100 / Math.abs(p.entry - (p.stop ?? p.entry)) }));
  const own: Decision[] = events.filter((e) => e.code !== "show" && e.code !== "hide")
    .map((e) => ({ time: e.time, market: markets[0] ?? "BTC-USD", kind: "pause", code: e.code }));
  const decisions = [...(ref?.decisions ?? []).filter((d) => set.has(d.market) && d.time >= u.created_at), ...own]
    .sort((a, b) => b.time - a.time).slice(0, 60);
  const checks = Object.fromEntries(Object.entries(ref?.checks ?? {}).filter(([m]) => set.has(m)));
  const last = Math.max(0, ...Object.values(checks).map((c) => c.time));
  const status = u.status === "paused" ? "paused" : !ref || ref.status === "offline" ? "offline"
    : positions.length ? "in_trade" : ref.status === "in_trade" ? "waiting" : ref.status;
  return {
    id: u.id, name: u.name, owner: "Strike user", kind: "paper", env: ref?.env ?? "mainnet", tf: ref?.tf ?? "240",
    variant: "reference", changes: [], markets, riskPct: risk, feeBps: ref?.feeBps ?? 10, equity0: PAPER_EQUITY,
    cash: +equity.toFixed(2), since: u.created_at, lastCheck: last || null, nextCheck: ref?.nextCheck ?? now, status,
    alerts: [], positions, trades, checks, decisions, look: storedLook(u), strategy: strategyOf(u.strategy),
  };
}

/** A user connected with the builder code: the agents' host pushes its real agent (journal + Strike account) under
 *  the user's id. The site adds what it owns: name, character, pause and the owner's own events. */
export function liveAgent(u: UserRow, a: Agent, events: UserEvent[], owner = false): Agent {
  const own: Decision[] = events.filter((e) => e.code !== "show" && e.code !== "hide")
    .map((e) => ({ time: e.time, market: a.markets[0] ?? "BTC-USD", kind: "pause", code: e.code }));
  return {
    ...a, id: u.id, name: u.name, owner: "Strike user", look: storedLook(u), since: a.since ?? u.created_at,
    strategy: strategyOf(u.strategy),
    status: u.status === "paused" ? "paused" : a.status,
    decisions: [...a.decisions, ...own].sort((x, y) => y.time - x.time).slice(0, 60),
    // a real account's size is the owner's business: the public city gets results as a share of the account
    ...(owner ? {} : { cash: null, equity0: null, result: null, positions: a.positions.map((p) => ({ ...p, qty: null, upnl: null })),
      trades: a.trades.map((t) => ({ ...t, qty: null, pnl: null })) }),   // pnlPct (over the position) stays
    portfolio: a.portfolio && (owner ? a.portfolio : publicPortfolio(a.portfolio)),
  };
}

/** A closing fill's result as Strike shows it: realized P&L minus that fill's fee, over the notional closed. */
export function closePct(f: { pnl: number | null; fee: number | null; price: number; size: number | null }): number | null {
  return f.pnl && f.size && f.price ? (f.pnl - (f.fee ?? 0)) / (f.price * Math.abs(f.size)) : null;
}

/** The same account without amounts: returns and P&L as fractions of the equity, sizes as a share of it. Deposits
 *  and withdrawals never show as a result (portfolio-types accountResult). */
export function publicPortfolio(p: Portfolio): Portfolio {
  const eq = p.equity || null, st = p.start;
  const share = (v: number | null | undefined) => (v != null && eq ? v / eq : null);
  return {
    public: true, time: p.time, start: null, equity: null, balance: null, available: null, upnl: null, margin: null, realized: null, split: null,
    flows: null, inflows: null, base: null,
    ret: accountResult(p, p.equity).ret, upnlPct: share(p.upnl),
    positions: p.positions.map((x) => ({ ...x, size: null, upnl: null, margin: null, funding: null,
      weight: x.size != null && eq ? (x.size * x.entry) / eq : null, pnlPct: share(x.upnl) })),
    orders: p.orders.map((o) => ({ ...o, size: null })),
    // a closing fill's result as Strike shows it: net of its fee, over the size closed (no amount in it)
    fills: p.fills.map((f) => ({ ...f, size: null, fee: null, pnl: null, pnlPct: closePct(f) })),
    fees: { trading: null, builder: null, builderBps: p.fees.builderBps },
    history: st == null ? [] : p.history.flatMap((pt) => {
      const v = pointResult(st, pt);
      return v == null ? [] : [[pt[0], v] as [number, number]];
    }),
  };
}

/** Connected to Strike, but the host has not pushed its real agent yet (it starts within a minute): never shown
 *  as a paper agent in the meantime. */
export function startingAgent(u: UserRow, env: string, events: UserEvent[], now: number): Agent {
  const markets = JSON.parse(u.markets) as string[];
  const empty: Agent = {
    id: u.id, name: u.name, owner: "Strike user", kind: "live", env, tf: "240", variant: "reference", changes: [], markets,
    riskPct: RISK[u.risk] ?? RISK.standard, feeBps: 20, equity0: null, cash: null, since: u.created_at, lastCheck: null, nextCheck: now,
    status: "analyzing", alerts: [], positions: [], trades: [], checks: {}, decisions: [],
  };
  return liveAgent(u, empty, events, true);
}

/** Its owner stopped real trading where users' agents are always real: shown stopped, never as paper. */
export function stoppedAgent(u: UserRow, env: string, events: UserEvent[], now: number): Agent {
  return { ...startingAgent(u, env, events, now), status: "paused" };
}

/** The owner's character, if they made one (always re-validated: the column is only written by this API). */
export function storedLook(u: UserRow): Look | null {
  try { return u.look ? normalizeLook(JSON.parse(u.look)) : null; } catch { return null; }
}

export interface Me {
  accountId: string; address: string; name: string; public: boolean; status: "active" | "paused"; agentStatus: string;
  risk: string; markets: string[]; equity: number | null; equity0: number | null; trades: number; mode: "paper" | "live"; createdAt: number;
  openPositions: { market: string; side: "long" | "short"; size: number; entry: number; stop: number | null; upnl: number | null }[];
  decisions: Decision[]; feesPaid: null; look: Look | null; portfolio: Portfolio | null; strategy: string;
}

export function meView(u: UserRow, a: Agent, prices: Record<string, number>): Me {
  return {
    accountId: u.id, address: u.address, name: u.name, public: !!u.public, status: u.status === "paused" ? "paused" : "active",
    agentStatus: a.status, risk: u.risk, markets: a.markets, equity: a.cash ?? null, equity0: a.equity0 ?? PAPER_EQUITY, trades: a.trades.filter((t) => !t.test).length,   // tests never count
    mode: a.kind === "live" ? "live" : "paper", createdAt: u.created_at, feesPaid: null, decisions: a.decisions.slice(0, 20), look: storedLook(u),
    portfolio: a.portfolio ?? null, strategy: strategyOf(u.strategy),
    openPositions: a.positions.map((p) => {
      const px = prices[p.market], dir = p.side === "long" ? 1 : -1, size = p.qty ?? 0;
      const upnl = p.upnl != null ? +p.upnl.toFixed(2) : px ? +((px - p.entry) * dir * size).toFixed(2) : null;   // a live account reports its own
      return { market: p.market, side: p.side, size, entry: p.entry, stop: p.stop, upnl };
    }),
  };
}

/** Strike mark prices for the dashboard's open P&L (cached 15 s at the edge). */
export async function strikePrices(): Promise<Record<string, number>> {
  const key = new Request("https://smartflow-city.internal/strike-prices");
  const cache = (caches as unknown as { default: Cache }).default;
  const hit = await cache.match(key);
  if (hit) return hit.json();
  try {
    const r = await fetch("https://api.strikefinance.org/price/v2/premiumIndex", { headers: { "User-Agent": "smartflow-city/1.0" } });
    if (!r.ok) return {};
    const rows = (await r.json()) as { symbol: string; markPrice: string }[];
    const out = Object.fromEntries(rows.map((x) => [x.symbol, +x.markPrice]).filter(([, v]) => Number.isFinite(v as number)));
    await cache.put(key, new Response(JSON.stringify(out), { headers: { "Cache-Control": "max-age=15" } }));
    return out;
  } catch { return {}; }
}
