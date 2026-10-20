// The live account a user's agent reports (agents' host -> site -> page). Shared by the page and the Pages Functions.
export interface PfPosition {
  market: string; side: "long" | "short"; size: number | null; entry: number; mark: number | null; upnl: number | null;
  lev: number | null; liq: number | null; funding: number | null; margin: number | null; openedAt: number | null; stop: number | null;
  weight?: number | null; pnlPct?: number | null;   // public view: notional / equity, P&L / equity
}
export interface PfOrder { market: string; side: string; type: string; size: number | null; price: number | null; stop: number | null; reduceOnly: boolean; status: string }
export interface PfFill {
  time: number; market: string; side: string; price: number; size: number | null; fee: number | null; pnl: number | null; pnlPct?: number | null; role: string;
  agent?: boolean;   // made by the agent (false: by hand or another app on the same account)
  test?: boolean;    // part of a test trade its owner asked for
}
/** [time, equity] or, from the host since 2026-10-21, [time, equity, net money moved in by then, gross money moved in by
 *  then]; the public view sends [time, 1 + result / base]. */
export type PfPoint = [number, number] | [number, number, number, number];
export interface Portfolio {
  public?: boolean; time: number | null; start: number | null; equity: number | null; balance: number | null; available: number | null;
  upnl: number | null; margin: number | null; ret?: number | null; upnlPct?: number | null;
  // deposits, withdrawals and transfers since the agent started (owner only): net (never part of the result) and
  // gross in; base = start + gross in, what the result is measured on
  flows?: number | null; inflows?: number | null; base?: number | null;
  realized?: number | null;   // closed trades' P&L since it connected (owner only)
  // the same net of fees, split: the strategy's trades, the owner's test trades, trades made outside the agent (owner only)
  split?: { strategy: number; test: number; outside: number } | null;
  positions: PfPosition[]; orders: PfOrder[]; fills: PfFill[];
  fees: { trading: number | null; builder: number | null; builderBps: number };
  history: PfPoint[];
}

/** The account's result since its agent started, leaving deposits and withdrawals out: money (equity - start - net
 *  flows) and as a share of what it is measured on (start + money deposited since). Null while there is nothing to
 *  measure (an account still waiting for its first deposit). */
export function accountResult(p: Pick<Portfolio, "start" | "flows" | "inflows">, equity: number | null): { total: number | null; base: number | null; ret: number | null } {
  if (equity == null || p.start == null) return { total: null, base: null, ret: null };
  const total = equity - p.start - (p.flows ?? 0);
  const base = p.start + (p.inflows ?? 0);
  return { total, base: base > 0 ? base : null, ret: base > 0 ? total / base : null };
}

/** One chart point as the result's growth (1 = where it started), deposits left out. */
export function pointResult(start: number, pt: PfPoint): number | null {
  const [, eq, flows = 0, inflows = 0] = pt as [number, number, number?, number?];
  const base = start + inflows;
  return base > 0 ? 1 + (eq - start - flows) / base : null;
}
