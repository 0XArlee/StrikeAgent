// The News Tower's data (GET /api/news): headlines from public feeds, each scored by a model and with the price
// reaction measured on Strike, a reading per market, the official US calendar and the scoreboard. Built on the
// agents' host (smartflow/news) and pushed to the site; here only read. Information for people: the agents never use it.
import { useEffect, useState } from "react";

export type Label = "very_bullish" | "bullish" | "neutral" | "bearish" | "very_bearish";
export type Category = "macro" | "regulation" | "etf" | "institutional" | "exchange" | "security" | "legal" | "tech" | "flows" | "price" | "other";
export interface Driver { cat: Category; push: number; n: number; top: string | null }
export interface Reading {
  net: number | null; net72: number | null; netHigh: number | null; label: Label | null; n: number; own: number;
  whipsaw: boolean; upWeight: number; downWeight: number; drivers: { up: Driver[]; down: Driver[] };
  flip: { en: string[]; es: string[] } | null;
}
export interface NewsItem {
  id: string; t: number; title: string; source: string; url: string; markets: string[];
  r15: number | null; r60: number | null; rm: string | null; tier?: number;
  z15?: number | null; z60?: number | null;   // the move against the market's normal move over that time
  // scored by the model (absent until then)
  es?: string; broad?: boolean; cat?: Category; score?: number; impact?: "high" | "medium" | "low"; conf?: number;
  catalyst?: boolean;   // false: a price recap, a prediction or unclear (listed, never in the reading)
  story?: string; sources?: number; also?: string[];   // a catalyst: its event, how many outlets told it, which others
  against?: boolean | null; w?: number; skip?: boolean;
}
export interface CalEvent { t: number; kind: "fomc" | "cpi" | "nfp"; name: string }
export interface Board { readings: number; called: number; hits: number; up: number }
export interface NewsDoc {
  v: 1; generated: number; pushedAt: number; stale: boolean;
  classifier: { on: boolean; model: string | null; error: string | null };
  markets: Record<string, Reading>;
  following: { cat: Category; follow: number; n: number }[];
  headlines: NewsItem[];
  counts: { "72h": number; scored: number };
  events: { next: CalEvent[]; just: CalEvent[] };
  scoreboard: Record<string, Board>;
  feeds: { id: string; name: string; ok: boolean | null; at: number | null }[];
}

const URL_NEWS = `${(import.meta.env.VITE_CITY_API as string | undefined) ?? ""}/api/news`;   // like the city: same origin

/** The document, refreshed every minute while something shows it; null before the first answer, "none" when the
 *  site has none yet, "error" when it could not be read. */
export function useNews(on: boolean): NewsDoc | null | "none" | "error" {
  const [doc, setDoc] = useState<NewsDoc | null | "none" | "error">(null);
  useEffect(() => {
    if (!on) return;
    let alive = true;
    const load = async () => {
      if (document.hidden) return;
      try {
        const r = await fetch(URL_NEWS, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(8000) });
        const j = r.ok ? await r.json() : null;
        if (!alive) return;
        if (!j) setDoc((d) => (d && typeof d === "object" ? d : "error"));
        else setDoc(j.none ? "none" : (j as NewsDoc));
      } catch { if (alive) setDoc((d) => (d && typeof d === "object" ? d : "error")); }
    };
    void load();
    const id = window.setInterval(load, 60_000);
    return () => { alive = false; window.clearInterval(id); };
  }, [on]);
  return doc;
}

/** The headlines a market's view lists: its own, the ones about the whole market, and (for BTC) those that name no coin. */
export function forMarket(items: NewsItem[], market: string): NewsItem[] {
  return items.filter((h) => !h.skip && (h.markets.includes(market) || h.broad || (market === "BTC-USD" && !h.markets.length)));
}

/** Only links the page may open: https. */
export const safeUrl = (u: string) => (/^https:\/\//.test(u) ? u : undefined);

/** "in 6 d 4 h", "in 3 h 12 min", "in 8 min" (lang strings from text.ts). */
export function countdown(ms: number, unit: { d: string; h: string; min: string }): string {
  const m = Math.max(0, Math.round(ms / 60_000));
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
  if (d) return `${d} ${unit.d} ${h} ${unit.h}`;
  if (h) return `${h} ${unit.h} ${mm} ${unit.min}`;
  return `${mm} ${unit.min}`;
}
