// Strike's copy trading in the city (GET /api/copy): the traders you can copy on Strike (Strike accounts and the
// Hyperliquid wallets Strike can copy), what the people who already copy them made, Strike's copy-trading totals, and
// the open positions of the leads that walk the city. Collected and kept on the agents' host (smartflow/copytrade);
// here only read. Strike City never copies anyone: the button opens the trader on Strike, where you copy.
import { useEffect, useState } from "react";

export interface Trader {
  id: string; platform: "strike" | "hyperliquid"; url: string;
  name?: string | null;                      // its name on Strike, when it has one
  subOf?: string | null;                     // a sub-account: the name of the main account it belongs to ("?" unknown)
  score: number | null; scores: Record<string, string>; direction: string | null;
  city: number | null;                       // Strike City's score to choose whom to copy (0-100)
  style: string | null; bias: string | null; value: number | null;
  pnl: Record<string, number | null>; roi: Record<string, number | null>; volume: Record<string, number | null>;
  assets: string[]; recommended: number | null;
  copiers: { active: number; ever: number; pnl: number; volume: number; won: number; n: number };
  metrics: { days: number; dd: number | null; upDays: number | null };
  parts?: Record<Part, number | null>;       // the parts of the city score, each 0-100 (null: not known yet)
  curve?: [number, number][];                // its PnL, every day kept (deposits and withdrawals move equity, not this)
  equity?: [number, number][];               // documents written before the curve was its PnL
  lastTrade: number | null; since: number | null; walks: boolean;
  positions?: { market: string; side: "long" | "short"; size: number; entry: number | null; upnl: number | null; leverage: number | null }[];
  events?: { t: number; market: string; kind: "open" | "close" | "flip" | "add" | "reduce"; side: string; size: number; price: number | null }[];
}
export interface CopyDoc {
  v: 1; generated: number; pushedAt: number; stale: boolean; historyDays: number;
  strike: { allocated: number | null; openInterest: number | null; volume30d: number; subscriptions30d: number; profits30d: number;
    daily: { volume: [number, number][]; subscriptions: [number, number][]; profits: [number, number][] } };
  counts: { traders: number; active: number; subs: number; inProfit: number };
  traders: Trader[];
  copiers: { lead: string; follower: string; platform: string; mode: string; status: string; pnl: number; volume: number; since: number }[];
  /** Strike traders left out because they copy others: Strike never passes a copier's copied orders on. */
  copyingOthers?: { id: string; name: string | null; copies: string[] }[];
  /** The score tested on every copy seen (each scored only with what came before it): smartflow/copytrade evidence(). */
  evidence?: { copies: number; leads: number; base: number; auc: { strike: number; city: number }; top: { strike: number; city: number }; at: number } | null;
}
export type CopyState = CopyDoc | null | "none" | "error";
export type Part = "strike" | "copiers" | "fall" | "record" | "size";
/** The weight of each part of the city score (smartflow/copytrade/service.py SCORE_WEIGHTS). */
export const PART_WEIGHTS: Record<Part, number> = { strike: 30, copiers: 30, fall: 0, record: 20, size: 20 };

/** Its PnL day by day (its equity in documents written before). */
export const curveOf = (t: Trader): [number, number][] => t.curve ?? t.equity ?? [];

const URL_COPY = `${(import.meta.env.VITE_CITY_API as string | undefined) ?? ""}/api/copy`;

/** The document, refreshed every minute while something shows it. */
export function useCopy(on: boolean): CopyState {
  const [doc, setDoc] = useState<CopyState>(null);
  useEffect(() => {
    if (!on) return;
    let alive = true;
    const load = async () => {
      if (document.hidden) return;
      try {
        const r = await fetch(URL_COPY, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(8000) });
        const j = r.ok ? await r.json() : null;
        if (!alive) return;
        if (!j) setDoc((d) => (d && typeof d === "object" ? d : "error"));
        else setDoc(j.none ? "none" : (j as CopyDoc));
      } catch { if (alive) setDoc((d) => (d && typeof d === "object" ? d : "error")); }
    };
    void load();
    const id = window.setInterval(load, 60_000);
    return () => { alive = false; window.clearInterval(id); };
  }, [on]);
  return doc;
}

/** Its name on Strike when it has one; else "#019D8B" for a Strike account, "0x0526…63FE" for a Hyperliquid wallet. */
export function traderName(t: Pick<Trader, "id" | "platform"> & { name?: string | null }): string {
  if (t.name) return t.name.length > 18 ? `${t.name.slice(0, 17)}…` : t.name;
  return t.platform === "hyperliquid" ? `${t.id.slice(0, 6)}…${t.id.slice(-4)}` : `#${t.id.replace(/-/g, "").slice(0, 6).toUpperCase()}`;
}

/** The share of the copies of this trader that ended (or are) in profit, once there are a few. */
export const copiersWon = (t: Trader) => (t.copiers.n >= 3 ? t.copiers.won / t.copiers.n : null);

/** Its biggest open position (the market tower it walks to). */
export function mainPosition(t: Trader) {
  return positionsBySize(t)[0];
}

/** Its open positions, the largest first. */
export function positionsBySize(t: Trader) {
  return [...(t.positions ?? [])].sort((a, b) => Math.abs(b.size * (b.entry ?? 1)) - Math.abs(a.size * (a.entry ?? 1)));
}

/** What can go wrong copying it, said plainly (the chooser shows these next to the numbers). */
export function warnings(t: Trader): ("copiersLost" | "short" | "deep" | "noCopiers" | "fresh")[] {
  const w: ("copiersLost" | "short" | "deep" | "noCopiers" | "fresh")[] = [];
  if (t.copiers.n >= 3 && t.copiers.pnl < 0) w.push("copiersLost");
  if (t.metrics.days < 14) w.push("short");
  if ((t.metrics.dd ?? 0) >= 0.25) w.push("deep");
  if (!t.copiers.n) w.push("noCopiers");
  if ((t.roi["30d"] ?? 0) > 5) w.push("fresh");   // a 500 %+ month: often a small account that got lucky
  return w;
}
