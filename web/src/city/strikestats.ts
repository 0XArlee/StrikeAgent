// Strike Finance's own numbers, for the inside of its building: Strike's public statistics API (CORS open, read straight
// from the browser), the live positions on the exchange, its vaults and its funding against other exchanges. Read when
// someone goes in, then every minute while they stay; a part that fails leaves the rest as it is.
import { useEffect, useState } from "react";

const API = "https://api.strikefinance.org";
const DAY = 86_400_000;

type Row3 = [number, string, number];   // [day (ms), market or asset, value]

// every long on a perpetuals exchange has a short on the other side, so the open interest is one side's notional, and
// what says something is how many positions are long and how many short
export interface MarketOi { market: string; oi: number; longN: number; shortN: number }
export interface Funding { market: string; strike: number | null; binance: number | null; bybit: number | null; okx: number | null; hyperliquid?: number | null }
export interface Vault { name: string; type: string; equity: number; share: number; fee: number }

export interface StrikeStats {
  at: number;
  // all time (Strike's summary)
  users: number | null; volumeAll: number | null; depositsAll: number | null; withdrawalsAll: number | null;
  liquidatedAll: number | null; revenueAll: number | null; referredAll: number | null;
  tradesAll: number | null;                          // the sum of every day's trades
  // each day (UTC), oldest first, the last one is today so far
  days: number[]; volume: number[]; trades: number[]; revenue: number[]; liquidations: number[];
  oiDays: number[]; oi: number[];                    // open interest at each day's end, every market together (USD)
  dau: [number, number][]; newUsers: [number, number][];
  volumeByMarket30d: { market: string; volume: number }[];
  // now
  tvl: number | null; treasury: { asset: string; value: number }[];
  positions: { n: number; oi: number; longN: number; shortN: number; byMarket: MarketOi[] } | null;
  funding: Funding[]; vaults: Vault[];
}

async function get(path: string): Promise<unknown> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 12_000);
  try {
    const r = await fetch(API + path, { signal: ctl.signal });
    if (!r.ok) throw new Error(`${r.status}`);
    return await r.json();
  } finally { clearTimeout(timer); }
}
const num = (v: unknown): number | null => { const n = Number(v); return Number.isFinite(n) ? n : null; };

/** A series by market and day -> one total per day (every market together), oldest first. */
function byDay(rows: Row3[] | undefined): Map<number, number> {
  const m = new Map<number, number>();
  for (const [ts, , v] of rows ?? []) m.set(ts, (m.get(ts) ?? 0) + (Number(v) || 0));
  return m;
}

export async function readStrikeStats(): Promise<StrikeStats> {
  const part = <T,>(p: Promise<T>) => p.catch(() => null);
  const [summary, volumes, oiS, trades, revenue, liq, users, treasury, live, funding, vaults] = await Promise.all([
    part(get("/stat/v1/dashboard/summary")), part(get("/stat/v1/dashboard/volumes")), part(get("/stat/v1/dashboard/open-interest")),
    part(get("/stat/v1/dashboard/trades")), part(get("/stat/v1/dashboard/revenue")), part(get("/stat/v1/dashboard/liquidations")),
    part(get("/stat/v1/dashboard/users")), part(get("/stat/v1/dashboard/treasury")), part(get("/stat/v1/stats/live-positions")),
    part(get("/stat/v1/stats/coin/funding-rate-comparison")), part(get("/v2/vaults")),
  ]) as [Record<string, unknown> | null, ...(Record<string, never> | null)[]];
  if (!summary && !volumes && !oiS) throw new Error("no statistics");

  const vol = byDay((volumes as { total_volume_daily?: Row3[] } | null)?.total_volume_daily);
  const tr = byDay((trades as { daily_trades?: Row3[] } | null)?.daily_trades);
  const rev = byDay((revenue as { total_revenue_daily?: Row3[] } | null)?.total_revenue_daily);
  const lq = byDay((liq as { daily_liquidations?: Row3[] } | null)?.daily_liquidations);
  const oi = byDay((oiS as { open_interest?: Row3[] } | null)?.open_interest);
  const days = [...vol.keys()].sort((a, b) => a - b);
  const oiDays = [...oi.keys()].sort((a, b) => a - b).filter((d) => (oi.get(d) ?? 0) > 0);

  // each market's volume over the last 30 days
  const since = (days[days.length - 1] ?? 0) - 30 * DAY;
  const perMarket = new Map<string, number>();
  for (const [ts, m, v] of (volumes as { total_volume_daily?: Row3[] } | null)?.total_volume_daily ?? []) {
    if (ts > since) perMarket.set(m, (perMarket.get(m) ?? 0) + (Number(v) || 0));
  }

  // the treasury on its last day, asset by asset
  const tRows = ((treasury as { data?: Row3[] } | null)?.data ?? []) as Row3[];
  const tLast = tRows.reduce((a, r) => Math.max(a, r[0]), 0);
  const tre = tRows.filter((r) => r[0] === tLast).map((r) => ({ asset: r[1], value: Number(r[2]) || 0 })).sort((a, b) => b.value - a.value);

  // every open position on Strike, market by market (no account shown): the open interest (one side's notional) and
  // how many positions are long and how many short
  let positions: StrikeStats["positions"] = null;
  const lp = (live as { positions?: { symbol: string; size: string; mark_price: string }[] } | null)?.positions;
  if (lp?.length) {
    const mk = new Map<string, MarketOi>();
    let notional = 0, longN = 0, shortN = 0;
    for (const p of lp) {
      const size = Number(p.size), mark = Number(p.mark_price);
      if (!Number.isFinite(size) || !Number.isFinite(mark) || !size) continue;
      const usd = Math.abs(size) * mark;
      const e = mk.get(p.symbol) ?? { market: p.symbol, oi: 0, longN: 0, shortN: 0 };
      e.oi += usd / 2; notional += usd;
      if (size > 0) { e.longN++; longN++; } else { e.shortN++; shortN++; }
      mk.set(p.symbol, e);
    }
    positions = { n: lp.length, oi: notional / 2, longN, shortN, byMarket: [...mk.values()].sort((a, b) => b.oi - a.oi) };
  }

  const rate = (x: unknown) => num((x as { rate?: string } | undefined)?.rate);
  const fRows = ((funding as { data?: Record<string, unknown>[] } | null)?.data ?? []).map((f) => ({
    market: String(f.symbol), strike: rate(f.strike), binance: rate(f.binance), bybit: rate(f.bybit), okx: rate(f.okx),
  }));

  const vRows = ((vaults as { vaults?: Record<string, unknown>[] } | null)?.vaults ?? []).map((v) => ({
    name: String(v.name ?? v.nickname ?? "Vault"), type: String(v.type ?? ""), equity: Number(v.equity) || 0,
    share: Number(v.share_price) || 0, fee: (Number(v.leader_commission_bps) || 0) / 100,
  })).sort((a, b) => b.equity - a.equity);

  const s = summary ?? {};
  const u = users as { daily_active_users?: [number, number][]; new_users?: [number, number][] } | null;
  return {
    at: Date.now(),
    users: num(s.total_users), volumeAll: num(s.total_volume_usd), depositsAll: num(s.total_deposits_usd),
    withdrawalsAll: num(s.total_withdrawals_usd), liquidatedAll: num(s.total_liquidated_usd), revenueAll: num(s.total_revenue_usd),
    referredAll: num(s.total_referred_volume_usd),
    tradesAll: tr.size ? [...tr.values()].reduce((a, b) => a + b, 0) : null,
    days, volume: days.map((d) => vol.get(d) ?? 0), trades: days.map((d) => tr.get(d) ?? 0),
    revenue: days.map((d) => rev.get(d) ?? 0), liquidations: days.map((d) => lq.get(d) ?? 0),
    oiDays, oi: oiDays.map((d) => oi.get(d) ?? 0),
    dau: u?.daily_active_users ?? [], newUsers: u?.new_users ?? [],
    volumeByMarket30d: [...perMarket.entries()].map(([market, volume]) => ({ market, volume })).sort((a, b) => b.volume - a.volume),
    tvl: num((treasury as { tvl_total_usd_value?: number } | null)?.tvl_total_usd_value), treasury: tre,
    positions, funding: fRows, vaults: vRows,
  };
}

/** Strike's numbers while `on` (someone is inside): read at once, then every minute. null while the first reading is
 *  on its way, "error" if it failed (and nothing was read before). */
export function useStrikeStats(on: boolean): StrikeStats | null | "error" {
  const [s, setS] = useState<StrikeStats | null | "error">(null);
  useEffect(() => {
    if (!on) return;
    let alive = true;
    const read = () => readStrikeStats().then((v) => { if (alive) setS(v); }, () => { if (alive) setS((cur) => (cur && cur !== "error" ? cur : "error")); });
    void read();
    const id = window.setInterval(() => { if (!document.hidden) void read(); }, 60_000);
    return () => { alive = false; clearInterval(id); };
  }, [on]);
  return s;
}
