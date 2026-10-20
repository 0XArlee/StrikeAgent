// City state outside React: prices (Strike public market data, Binance as fallback), the agents and their feed.
// React reads it through useSyncExternalStore; the canvas engine reads it every frame.
// Every agent is real and comes from the Smart Flow API (/api/city, built from the agents' journals): no simulated
// population. If the API cannot be reached the city says so instead of inventing agents.
import { freePost, fromApi, liveTick, mulberry, type AgentView, type ApiAgent, type Decision, type FeedItem, type Prices } from "./agents";

export const CITY_MARKETS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "ADA-USD"];
const STRIKE = "https://api.strikefinance.org/price/v2";
const BINANCE = "https://fapi.binance.com/fapi/v1";
const CITY_API = (import.meta.env.VITE_CITY_API as string | undefined) ?? "";   // "" = same origin (/api proxied)
const toBinance = (m: string) => m.replace("-USD", "USDT");

export type PriceSource = "strike" | "binance" | "offline";

async function getJson(url: string, ms = 8000): Promise<unknown> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { signal: ctl.signal });
    if (!r.ok) throw new Error(`${r.status}`);
    return await r.json();
  } finally { clearTimeout(timer); }
}

type Row = Record<string, string | number>;

async function strikePrices(): Promise<Prices> {
  const [tick, prem] = (await Promise.all([getJson(`${STRIKE}/ticker/24hr`), getJson(`${STRIKE}/premiumIndex`)])) as [Row[], Row[]];
  const out: Prices = {};
  for (const t of tick) {
    const m = String(t.symbol);
    if (!m.endsWith("-USD")) continue;
    const p = prem.find((x) => x.symbol === m);
    out[m] = { price: +(p?.markPrice ?? t.lastPrice), change: +t.priceChangePercent, funding: +(p?.fundingRate ?? 0) };
  }
  return out;
}

async function binancePrices(): Promise<Prices> {
  const [tick, prem] = (await Promise.all([getJson(`${BINANCE}/ticker/24hr`), getJson(`${BINANCE}/premiumIndex`)])) as [Row[], Row[]];
  const out: Prices = {};
  for (const m of [...CITY_MARKETS, "NEAR-USD", "ZEC-USD"]) {
    const t = tick.find((x) => x.symbol === toBinance(m));
    if (!t) continue;
    const p = prem.find((x) => x.symbol === toBinance(m));
    // Binance funds every 8 h; shown per hour like Strike
    out[m] = { price: +(p?.markPrice ?? t.lastPrice), change: +t.priceChangePercent, funding: +(p?.lastFundingRate ?? 0) / 8 };
  }
  return out;
}

async function history(source: PriceSource, m: string): Promise<number[]> {
  const url = source === "strike" ? `${STRIKE}/klines?symbol=${m}&interval=1h&limit=48`
    : `${BINANCE}/klines?symbol=${toBinance(m)}&interval=1h&limit=48`;
  const rows = (await getJson(url)) as (string | number)[][];
  return rows.map((k) => +k[4]).filter((v) => Number.isFinite(v) && v > 0);
}

function tone(d: Decision): FeedItem["tone"] {
  if (d.kind === "order") return d.args?.side === "short" ? "neg" : "pos";
  if (d.kind === "exit") return Number(d.args?.r) > 0 ? "pos" : "neg";
  if (d.kind === "risk" || d.kind === "alert") return "warn";
  return "info";
}

/** The owner's agent with its amounts (null when the session expired or the request failed: the public one stays). */
async function ownAgent(token: string): Promise<ApiAgent | null> {
  try {
    const r = await fetch(`${CITY_API}/api/me`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(6000) });
    if (!r.ok) return null;
    const me = (await r.json()) as { agent?: ApiAgent };
    return me.agent ?? null;
  } catch { return null; }
}

export class CityStore {
  agents: AgentView[] = [];
  feed: FeedItem[] = [];             // the agents' journal events, newest first
  apiOk = false;                     // the API answered at least once
  prices: Prices = {};
  hist: Record<string, number[]> = {};
  source: PriceSource = "offline";
  updatedAt = 0;
  cityAt = 0;                        // when the API built the last snapshot
  ready = false;
  /** The signed-in owner: their own agent is drawn from /api/me, with the amounts only they may see. */
  owner: { id: string; token: string } | null = null;
  private R = mulberry((Date.now() & 0xffff) + 7);
  private version = 0;
  private listeners = new Set<() => void>();
  private timers: number[] = [];
  private dirty = false;

  subscribe = (f: () => void) => { this.listeners.add(f); return () => this.listeners.delete(f); };
  getVersion = () => this.version;
  private emit() { this.version++; for (const f of this.listeners) f(); }

  get live() { return this.agents.length > 0; }

  async load(progress: (k: number) => void): Promise<void> {
    progress(0.1);
    await Promise.all([this.refreshPrices(), this.refreshCity()]);
    progress(0.55);
    await Promise.all(["BTC-USD", "ETH-USD", "SOL-USD"].map(async (m) => {
      try { this.hist[m] = await history(this.source === "offline" ? "strike" : this.source, m); } catch { this.hist[m] = []; }
    }));
    progress(1);
    this.ready = true;
    this.emit();
  }

  async refreshPrices(): Promise<void> {
    for (const [src, fn] of [["strike", strikePrices], ["binance", binancePrices]] as const) {
      try {
        const p = await fn();
        if (Object.keys(p).length) {
          this.prices = p; this.source = src; this.updatedAt = Date.now();
          for (const [m, v] of Object.entries(p)) if (this.hist[m]?.length) { this.hist[m] = [...this.hist[m].slice(-47), v.price]; }
          this.dirty = true;
          return;
        }
      } catch { /* try the next source */ }
    }
    this.source = "offline";
    this.dirty = true;
  }

  /** Agents from /api/city. A failure keeps the last snapshot. */
  async refreshCity(): Promise<void> {
    let doc: { generated: number; agents: ApiAgent[] };
    try {
      doc = (await getJson(`${CITY_API}/api/city`, 6000)) as typeof doc;
      if (!doc || !Array.isArray(doc.agents)) throw new Error("not a city document");
    } catch { this.dirty = true; return; }
    this.apiOk = true;
    const own = this.owner ? await ownAgent(this.owner.token) : null;
    const list = doc.agents.filter((x) => !x.error && x.markets?.length)
      .map((x) => (own && x.id === this.owner?.id && own.id === x.id ? { ...x, ...own } : x));
    // a new agent gets the first free post around the fountain (agents that wait stand still: they must not pile up)
    const taken = new Set(this.agents.filter((a) => a.post && list.some((x) => x.id === a.id)).map((a) => `${a.post!.x},${a.post!.y}`));
    this.agents = list.map((x) => {
      const prev = this.agents.find((a) => a.id === x.id);
      return fromApi(x, prev, this.R, prev ? undefined : freePost(taken, this.R));
    });
    this.cityAt = doc.generated;
    this.feed = this.agents.flatMap((a, i) => a.decisions.map((d, k) => ({
      id: i * 1e4 + k, time: d.time, agent: a.name, agentId: a.id, d, tone: tone(d),
    }))).sort((x, y) => y.time - x.time).slice(0, 60);
    this.dirty = true;
  }

  start(): void {
    this.timers.push(window.setInterval(() => {
      const now = performance.now();
      for (const a of this.agents) liveTick(a, now, this.prices, this.R);
      if (this.agents.some((a) => a.position)) this.dirty = true;
    }, 400));
    this.timers.push(window.setInterval(() => { void this.refreshPrices(); }, 15_000));
    this.timers.push(window.setInterval(() => { void this.refreshCity(); }, 10_000));   // the host pushes within ~10 s
    // the UI re-renders at most once per second
    this.timers.push(window.setInterval(() => { if (this.dirty) { this.dirty = false; this.emit(); } }, 1000));
  }

  stop(): void { for (const t of this.timers) clearInterval(t); this.timers = []; }

  agent(id: string | null): AgentView | undefined { return id ? this.agents.find((a) => a.id === id) : undefined; }

  totals() {
    const live = this.agents.filter((a) => a.status !== "paused" && a.status !== "offline" && a.status !== "unfunded").length;
    const inTrade = this.agents.filter((a) => a.position).length;
    const today = Date.now() - 24 * 3600_000;
    const trades = this.agents.reduce((s, a) => s + a.trades.filter((x) => x.time >= today).length, 0);
    const rToday = this.agents.reduce((s, a) => s + a.trades.filter((x) => x.time >= today).reduce((q, x) => q + x.r, 0), 0);
    return { total: this.agents.length, live, inTrade, trades, rToday };
  }

  /** Long / short count per market, over every open position of every agent. */
  positioning(m: string) {
    let long = 0, short = 0;
    for (const a of this.agents) {
      for (const p of a.real?.positions ?? (a.position ? [a.position] : [])) if (p.market === m) p.side === "long" ? long++ : short++;
    }
    return { long, short };
  }
}
