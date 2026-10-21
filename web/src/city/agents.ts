// City agents: data model (mirrors the agent journal), A* paths on the walk grid, and how a real agent moves.
// Every agent comes from the Smart Flow API (/api/city), built from real agent journals: the Smart Flow paper agents
// and the users' agents their owners chose to show.
import type { Portfolio } from "./portfolio-types";
import { BUILDINGS, COLS, ROWS, TILE, canWalk, plazaSpot, type Building } from "./world";
import type { Dir } from "./sprites";
import { normalizeLook, type Look } from "./look";

export type Status = "analyzing" | "waiting" | "signal" | "risk" | "entering" | "in_trade" | "exiting" | "paused" | "offline"
  | "unfunded";   // connected to Strike, its account has no balance yet

export type ExitReason = "trail" | "stop" | "chandelier" | "target" | "time" | "flow" | "test" | "other";
export interface Trade {
  market: string; side: "long" | "short"; entry: number; exit: number; r: number; reason: ExitReason; time: number; test?: boolean;
  pnl?: number | null;      // net result in the account's money (its owner, and paper agents)
  pnlPct?: number | null;   // the same as a share of the account (a live agent in the public city)
}

/** One journal entry. `code` + `args` are rendered to text per language by ./text.ts; `text` is the engine's own
 *  English sentence (live agents), used when a code is unknown to this page. */
export interface Decision { time: number; market: string; kind: "analysis" | "signal" | "risk" | "order" | "exit" | "pause" | "alert";
  code: Code; args?: Record<string, string | number | null>; text?: string }
export type Code = "no_range" | "no_body" | "low_volume" | "against_trend" | "signal" | "risk_spread" | "risk_daily" | "risk_open"
  | "open" | "close" | "pause" | "resume" | "live" | "live_off" | "held" | "settings" | "test" | "test_open" | "test_close" | "account_fill"
  // live journals (smartflow/api/city.py)
  | "check" | "not_traded" | "risk_weekly" | "risk_other" | "risk_min" | "not_filled" | "alert" | "start"
  | "risk_balance" | "risk_hold" | "test_funds" | "test_busy";

export interface Position { market: string; side: "long" | "short"; entry: number; stop: number; trail: number; size: number; rOpen: number;
  stopKnown: boolean; upnl: number | null }   // a live account can hold a position the agent did not open (no stop)

/** What only a real agent has: its schedule, account and latest check per market, straight from /api/city. */
export interface RealInfo {
  env: string; tf: string; variant: "reference" | "official" | "experimental"; changes: string[]; feeBps: number;
  equity0: number | null; cash: number | null; since: number | null; lastCheck: number | null; nextCheck: number;
  result: number | null;   // a live account's result, deposits left out (its owner only)
  checks: Record<string, { time: number; args: Record<string, string | number | null>; text: string }>;
  positions: Position[];
}

export interface AgentView {
  id: string;
  kind: "paper" | "live";            // simulated execution on Strike's real book / real orders
  name: string;
  owner: string;          // "Smart Flow" or "Strike user" (wallet addresses are never shown)
  risk: number;           // % of equity per trade
  markets: string[];
  status: Status;
  focus: string;          // market currently looked at
  position: null | Position;
  trades: Trade[];
  decisions: Decision[];
  rToday: number;
  // motion (art px)
  x: number; y: number; dir: Dir; path: { x: number; y: number }[]; frame: number; target: string;
  nextAt: number;         // time of its next move (performance.now clock)
  real?: RealInfo;
  portfolio?: Portfolio;  // a user's live agent: its Strike account (shares of it in the public city)
  testTrades?: Trade[];   // the test trades its owner asked for: in its trades list, never in any count
  tally?: Tally;          // counts over every one of its trades (the list above is the latest ones only)
  strategy?: string;
  look?: Look;            // chosen by the owner (character creator); otherwise derived from the id
  tour?: number;          // live: the market its card shows first while it waits (two agents never show the same one)
  post?: { x: number; y: number };     // its own spot in the plaza: where it stands still while it waits
  trip?: { to: string; until: number }; // a real event just happened (order, exit, risk check): it goes there
  seen?: number;          // time of the latest journal entry already acted on
}

/** Whether the agent is doing something right now. Only then does it move, pulse or bob: one that waits for its
 *  setup, is paused or offline stands still (like Midnight City's IDLE agents). */
export function isActive(a: Pick<AgentView, "status" | "path" | "trip">): boolean {
  return a.path.length > 0 || !!a.trip || ACTIVE.has(a.status);
}
const ACTIVE = new Set<Status>(["analyzing", "signal", "risk", "entering", "in_trade", "exiting"]);

export interface Prices { [market: string]: { price: number; change: number; funding: number } }
/** Win/loss counts in R over every closed strategy trade (smartflow/api/city.py _tally). */
export interface Tally { n: number; wins: number; won: number; lost: number; best: number }   // change: % 24h · funding: per hour

// ---------------------------------------------------------------- A*
export function findPath(sx: number, sy: number, tx: number, ty: number): { x: number; y: number }[] {
  if (!canWalk(tx, ty)) return [];
  const key = (x: number, y: number) => y * COLS + x;
  const open: number[] = [key(sx, sy)];
  const g = new Map<number, number>([[key(sx, sy), 0]]);
  const came = new Map<number, number>();
  const hh = (k: number) => Math.abs((k % COLS) - tx) + Math.abs(Math.floor(k / COLS) - ty);
  const f = new Map<number, number>([[key(sx, sy), hh(key(sx, sy))]]);
  let guard = 0;
  while (open.length && guard++ < 20000) {
    let bi = 0;
    for (let i = 1; i < open.length; i++) if ((f.get(open[i]) ?? 1e9) < (f.get(open[bi]) ?? 1e9)) bi = i;
    const cur = open.splice(bi, 1)[0];
    const cx = cur % COLS, cy = Math.floor(cur / COLS);
    if (cx === tx && cy === ty) {
      const out: { x: number; y: number }[] = [];
      let k: number | undefined = cur;
      while (k !== undefined) { out.push({ x: (k % COLS) * TILE + 8, y: Math.floor(k / COLS) * TILE + 12 }); k = came.get(k); }
      return out.reverse();
    }
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = cx + dx, ny = cy + dy;
      if (nx < 0 || ny < 0 || nx >= COLS || ny >= ROWS || !canWalk(nx, ny)) continue;
      const nk = key(nx, ny);
      const ng = (g.get(cur) ?? 0) + 1;
      if (ng < (g.get(nk) ?? 1e9)) {
        came.set(nk, cur); g.set(nk, ng); f.set(nk, ng + hh(nk));
        if (!open.includes(nk)) open.push(nk);
      }
    }
  }
  return [];
}

export function building(id: string): Building { return BUILDINGS.find((b) => b.id === id)!; }

export function goTo(a: AgentView, id: string, R: () => number): void {
  const b = building(id);
  const sx = Math.floor(a.x / TILE), sy = Math.floor(a.y / TILE);
  // spread agents around the door so they do not stack on one tile
  const spread = b.kind === "tower" ? 13 : 7;
  for (let i = 0; i < 8; i++) {
    const tx = b.door.x + Math.floor(R() * spread) - Math.floor(spread / 2), ty = b.door.y + Math.floor(R() * 3);
    const p = findPath(sx, sy, tx, ty);
    if (p.length) { a.path = p; a.target = id; return; }
  }
  a.path = findPath(sx, sy, b.door.x, b.door.y);
  a.target = id;
}

/** Walk to a tile that is not a building door (the plaza); `target` names the place. */
function goToTile(a: AgentView, t: { x: number; y: number }, target: string): void {
  a.path = findPath(Math.floor(a.x / TILE), Math.floor(a.y / TILE), t.x, t.y);
  a.target = target;
}

export function step(a: AgentView, dt: number): void {
  if (!a.path.length) return;
  const speed = 34; // art px per second
  const t = a.path[0];
  const dx = t.x - a.x, dy = t.y - a.y;
  const dist = Math.hypot(dx, dy);
  const move = speed * dt;
  a.dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
  if (dist <= move) {
    a.x = t.x; a.y = t.y; a.path.shift();
    if (!a.path.length) a.dir = "down";   // arrived: it stands facing the street
  } else { a.x += (dx / dist) * move; a.y += (dy / dist) * move; }
  a.frame += dt * 6;
}

// ---------------------------------------------------------------- places
export { mulberry } from "./rand";

export const MARKET_TOWER: Record<string, string> = { "BTC-USD": "btc", "ETH-USD": "eth", "SOL-USD": "sol",
  "XRP-USD": "alts", "BNB-USD": "alts", "ADA-USD": "alts", "NEAR-USD": "alts", "ZEC-USD": "alts" };

/** A walkable spot near a building's door (agents gather around doors, not on one tile). */
function spot(id: string, R: () => number): { x: number; y: number } {
  const b = building(id);
  const spread = b.kind === "tower" ? 13 : 9;   // towers have a long frontage: use it
  for (let i = 0; i < 20; i++) {
    const tx = b.door.x + Math.floor(R() * spread) - Math.floor(spread / 2), ty = b.door.y + Math.floor(R() * 3);
    if (canWalk(tx, ty)) return { x: tx * TILE + 8, y: ty * TILE + 12 };
  }
  return { x: b.door.x * TILE + 8, y: b.door.y * TILE + 12 };
}

export interface FeedItem { id: number; time: number; agent: string; agentId: string; d: Decision; tone: "pos" | "neg" | "info" | "warn" }

// ---------------------------------------------------------------- live agents (/api/city)
export interface ApiAgent {
  id: string; name: string; owner?: string; kind?: "paper" | "live" | "analysis"; env?: string; tf?: string;
  variant?: "reference" | "official" | "experimental"; changes?: string[]; markets?: string[]; riskPct?: number; feeBps?: number;
  equity0?: number | null; cash?: number | null; since?: number | null; lastCheck?: number | null; nextCheck?: number;
  result?: number | null;
  status: "offline" | "in_trade" | "analyzing" | "waiting" | "paused" | "unfunded";
  tally?: Tally;
  positions?: { market: string; side: "long" | "short"; entry: number; stop: number | null; trail?: number | null; qty: number | null; upnl?: number | null }[];
  trades?: { market: string; side: "long" | "short"; entry: number; exit: number; r: number; reason: ExitReason; time: number; test?: boolean;
    pnl?: number | null; pnlPct?: number | null }[];
  strategy?: string;
  checks?: RealInfo["checks"];
  decisions?: Decision[];
  look?: unknown;
  error?: string;
  portfolio?: Portfolio;
}

/** API snapshot -> AgentView. Keeps the walker's place and path when it already exists; `post`: where a new one stands while it waits. */
export function fromApi(x: ApiAgent, prev: AgentView | undefined, R: () => number, post?: { x: number; y: number }): AgentView {
  const positions: Position[] = (x.positions ?? []).map((p) => ({ market: p.market, side: p.side, entry: p.entry, stop: p.stop ?? p.entry,
    trail: p.trail ?? p.stop ?? p.entry, size: p.qty ?? 0, rOpen: prev?.real?.positions.find((q) => q.market === p.market)?.rOpen ?? 0,
    stopKnown: p.stop != null, upnl: p.upnl ?? null }));
  // test trades are listed with the agent's trades (marked) but never counted: stats, ranks and the city's totals
  // only ever see the strategy's own trades
  const all: Trade[] = (x.trades ?? []).map((t) => ({ market: t.market, side: t.side, entry: t.entry, exit: t.exit, r: t.r, reason: t.reason, time: t.time,
    test: !!t.test, pnl: t.pnl ?? null, pnlPct: t.pnlPct ?? null }));
  const markets = x.markets?.length ? x.markets : ["BTC-USD"];
  const status: Status = x.status;
  // each real agent starts its market tour at a different market so two agents never walk in lockstep
  const tour = Math.floor(R() * markets.length);
  const a: AgentView = prev ?? {
    id: x.id, kind: x.kind === "live" ? "live" : "paper", name: x.name, owner: "", risk: 0.5, markets, status, focus: markets[tour],
    position: null, trades: [], decisions: [], rToday: 0, x: 0, y: 0, dir: "down", path: [], frame: R() * 10, target: "", nextAt: R() * 8000, tour,
  };
  if (prev && prev.status !== status) a.nextAt = 0;   // react to a new state right away
  // a real event newer than the last snapshot sends it to where that happens (history never does)
  const decisions = x.decisions ?? [];
  const latest = decisions.reduce((m, d) => Math.max(m, d.time), 0);
  if (prev?.seen !== undefined) {
    const ev = decisions.filter((d) => d.time > (prev.seen ?? 0) && TRIP[d.kind]).sort((p, q) => q.time - p.time)[0];
    if (ev) { a.trip = { to: ev.kind === "exit" && ev.args?.reason !== "stop" ? "cafe" : TRIP[ev.kind]!, until: performance.now() + TRIP_MS }; a.nextAt = 0; }
  }
  a.seen = Math.max(prev?.seen ?? 0, latest);
  a.name = x.name;
  a.portfolio = x.portfolio ?? undefined;
  a.look = normalizeLook(x.look) ?? undefined;
  a.owner = x.owner ?? "Smart Flow";
  a.kind = x.kind === "live" ? "live" : "paper";
  a.risk = x.riskPct ?? 0.5;
  a.markets = markets;
  a.status = status;
  a.trades = all.filter((t) => !t.test);
  a.testTrades = all.filter((t) => t.test);
  a.tally = x.tally ?? undefined;
  a.strategy = x.strategy || undefined;
  a.decisions = x.decisions ?? [];
  a.rToday = +a.trades.filter((t) => t.time >= Date.now() - 86400_000).reduce((s, t) => s + t.r, 0).toFixed(2);
  a.position = positions.find((p) => p.market === a.position?.market) ?? positions[0] ?? null;
  if (a.position) a.focus = a.position.market;
  a.real = { env: x.env ?? "mainnet", tf: x.tf ?? "240", variant: x.variant ?? "reference", changes: x.changes ?? [], feeBps: x.feeBps ?? 0,
    equity0: x.equity0 ?? null, cash: x.cash ?? null, result: x.result ?? null, since: x.since ?? null, lastCheck: x.lastCheck ?? null,
    nextCheck: x.nextCheck ?? 0, checks: x.checks ?? {}, positions };
  if (!prev) {   // first appearance: already where its state says (a waiting agent at its post, in the opening view)
    a.post = post ?? nearFountain(R);
    const place = placeFor(a);
    const p = place === "plaza" ? { x: a.post.x * TILE + 8, y: a.post.y * TILE + 12 } : spot(place, R);
    a.x = p.x; a.y = p.y; a.target = place;
    a.nextAt = 0;
  }
  return a;
}

/** Where a real event takes the agent, and how long it stays there before going back to its place. */
const TRIP: Partial<Record<Decision["kind"], string>> = { signal: "exchange", order: "exchange", risk: "risk", exit: "alley" };
const TRIP_MS = 75_000;

/** Where its state keeps it: paused or offline at home, analysing in the lab, in a trade at the market's tower,
 *  waiting for a setup at its own spot in the plaza. */
function placeFor(a: AgentView): string {
  switch (a.status) {
    case "offline": case "paused": case "unfunded": return "homes";
    case "analyzing": return "lab";
    case "in_trade": return a.position ? MARKET_TOWER[a.position.market] ?? "alts" : "plaza";
    default: return "plaza";
  }
}

/** Where waiting agents stand, spread around the fountain so a still crowd stays readable: the most visible spots
 *  first, all inside the opening view on phones (tiles x 36-51, names included) and on desktop. Beyond these, a random plaza tile. */
const POSTS: [number, number][] = [[45, 31], [39, 32], [50, 31], [45, 35], [39, 36], [50, 39], [45, 39], [39, 40], [42, 29], [48, 29]];

/** The first free post (taken: "x,y" of the posts already in use, updated). */
export function freePost(taken: Set<string>, R: () => number): { x: number; y: number } {
  for (const [x, y] of POSTS) {
    const k = `${x},${y}`;
    if (!taken.has(k) && canWalk(x, y)) { taken.add(k); return { x, y }; }
  }
  return nearFountain(R);
}

/** A plaza tile around the fountain: inside the opening view on phones (x 538-862 px) and on desktop. */
function nearFountain(R: () => number): { x: number; y: number } {
  for (let i = 0; i < 40; i++) {
    const t = plazaSpot(R);
    if (t.x >= 36 && t.x <= 51) return t;
  }
  return plazaSpot(R);
}

/** A real agent's latest check on the market it is looking at (or its latest decision). */
export function nowDecision(a: AgentView): Decision | undefined {
  if (a.real && a.position) {   // in a trade: the order that opened the position it is standing at
    const p = a.position;
    const own = a.decisions.find((d) => d.kind === "order" && d.market === p.market);
    if (own) return own;
    // a position the agent did not open (its owner's account can hold one opened by hand): say so, no invented stop
    return p.stopKnown
      ? { time: Date.now(), market: p.market, kind: "order", code: "open", args: { side: p.side, price: p.entry, stop: p.stop } }
      : { time: Date.now(), market: p.market, kind: "order", code: "held", args: { side: p.side, price: p.entry } };
  }
  const c = a.real?.checks[a.focus];
  if (c && (a.status === "waiting" || a.status === "analyzing")) {
    return { time: c.time, market: a.focus, kind: "analysis", code: "check", args: c.args, text: c.text };
  }
  return a.decisions[0];
}

/** Moves a real agent only when something real happens: its state changed (a candle close sends it to the lab, a
 *  trade to the market's tower, a pause home) or an event of its journal (an order to the exchange, a closed trade,
 *  a risk check). Otherwise it stands still where it is: no strolling while it waits for a setup. Open R uses live
 *  Strike prices. */
export function liveTick(a: AgentView, now: number, prices: Prices, R: () => number): void {
  for (const p of a.real?.positions ?? []) {
    const px = prices[p.market]?.price;
    if (px && p.entry !== p.stop) p.rOpen = +(((px - p.entry) * (p.side === "long" ? 1 : -1)) / Math.abs(p.entry - p.stop)).toFixed(2);
  }
  if (a.path.length) return;
  if (a.trip) {
    if (now < a.trip.until) { if (a.target !== a.trip.to) goTo(a, a.trip.to, R); return; }
    a.trip = undefined;
  }
  if (now < a.nextAt) return;
  const place = placeFor(a);
  if (a.target === place) return;   // already there: it stays put
  if (place === "plaza") goToTile(a, a.post ?? (a.post = nearFountain(R)), "plaza");
  else goTo(a, place, R);
}

export function stats(a: AgentView) {
  // every trade it ever closed when the host sends the counts; else the trades in the list
  const t: Tally = a.tally ?? (() => {
    const wins = a.trades.filter((x) => x.r > 0);
    return { n: a.trades.length, wins: wins.length, won: wins.reduce((s, x) => s + x.r, 0),
      lost: -a.trades.filter((x) => x.r <= 0).reduce((s, x) => s + x.r, 0), best: a.trades.length ? Math.max(...a.trades.map((x) => x.r)) : 0 };
  })();
  return { n: t.n, winRate: t.n ? t.wins / t.n : 0, totalR: +(t.won - t.lost).toFixed(2), pf: t.lost ? t.won / t.lost : t.won ? Infinity : 0,
    best: t.n ? t.best : 0 };
}
