// The News Tower's floors (tower.json, drawn by web/scripts/build_tower.py) and what each one shows from the news
// document: one floor per kind of news, each spot a view of it. Only reading: nothing here reaches the agents.
import tower from "./tower.json";
import { forMarket, type Category, type NewsDoc, type NewsItem } from "./news";

export type RoomId = "lobby" | "macro" | "geo" | "rules" | "money" | "security";
export type SpotKind = "reading" | "wire" | "scores" | "topics" | "events" | "stories" | "map" | "clocks" | "lift" | "exit";
export interface SpotDef { id: string; kind: SpotKind; cats?: Category[]; label?: string }
export interface Floor { id: RoomId; n: number; cats: Category[]; color: string; first: string; spots: SpotDef[] }

export const FLOORS: Floor[] = [
  { id: "lobby", n: 0, cats: [], color: "#fbbf24", first: "screen", spots: [
    { id: "screen", kind: "reading" }, { id: "printer", kind: "wire" }, { id: "score", kind: "scores" },
    { id: "desks", kind: "topics" }, { id: "board", kind: "events" }, { id: "lift", kind: "lift" }, { id: "door", kind: "exit" }] },
  { id: "macro", n: 1, cats: ["macro"], color: "#60a5fa", first: "board", spots: [
    { id: "board", kind: "events", label: "releases" }, { id: "podium", kind: "stories", cats: ["macro"] }, { id: "lift", kind: "lift" }] },
  { id: "geo", n: 2, cats: ["geopolitics"], color: "#22d3ee", first: "map", spots: [
    { id: "map", kind: "map" }, { id: "wall", kind: "stories", cats: ["geopolitics"] }, { id: "clocks", kind: "clocks" }, { id: "lift", kind: "lift" }] },
  { id: "rules", n: 3, cats: ["regulation", "legal"], color: "#e2b04a", first: "bench", spots: [
    { id: "bench", kind: "stories", cats: ["legal"] }, { id: "rostrum", kind: "stories", cats: ["regulation"] }, { id: "lift", kind: "lift" }] },
  { id: "money", n: 4, cats: ["etf", "institutional", "flows"], color: "#4ade80", first: "etf", spots: [
    { id: "etf", kind: "stories", cats: ["etf"] }, { id: "desks", kind: "stories", cats: ["institutional"], label: "deskInst" },
    { id: "flows", kind: "stories", cats: ["flows"] }, { id: "lift", kind: "lift" }] },
  { id: "security", n: 5, cats: ["security", "exchange", "tech"], color: "#f87171", first: "alarm", spots: [
    { id: "alarm", kind: "stories", cats: ["security"] }, { id: "exchanges", kind: "stories", cats: ["exchange"] },
    { id: "servers", kind: "stories", cats: ["tech"] }, { id: "lift", kind: "lift" }] },
];
export const floor = (id: RoomId) => FLOORS.find((f) => f.id === id)!;

type Rect = [number, number, number, number];
export interface RoomData {
  spots: Record<string, { rect: Rect; stand: [number, number]; face: "up" | "down" | "left" | "right" }>;
  screens: Record<string, Rect>;
  staff: { x: number; y: number; dir: "up" | "down" | "left" | "right"; anim: "idle" | "phone" | "read"; seed: string }[];
  walk: string[];
  pins?: Record<string, [number, number]>;
  leds?: [number, number][];
}
export const TILE = tower.tile, ROOM_W = tower.w, ROOM_H = tower.h;
export const ROOMS = tower.rooms as unknown as Record<RoomId, RoomData>;
export const roomArt = (id: RoomId) => `${import.meta.env.BASE_URL ?? "/"}art/tower/${id}.webp`;

/** The tiles from (sx, sy) to (tx, ty) through the room's walkable tiles (none: unreachable). */
export function roomPath(room: RoomData, sx: number, sy: number, tx: number, ty: number): [number, number][] {
  const w = ROOM_W, h = ROOM_H, ok = (x: number, y: number) => x >= 0 && y >= 0 && x < w && y < h && room.walk[y][x] === "1";
  if (!ok(tx, ty)) return [];
  const prev = new Int32Array(w * h).fill(-1);
  const start = sy * w + sx;
  prev[start] = start;
  const q = [start];
  for (let i = 0; i < q.length; i++) {
    const c = q[i], x = c % w, y = (c / w) | 0;
    if (x === tx && y === ty) break;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = x + dx, ny = y + dy, n = ny * w + nx;
      if (ok(nx, ny) && prev[n] < 0) { prev[n] = c; q.push(n); }
    }
  }
  const end = ty * w + tx;
  if (prev[end] < 0) return [];
  const out: [number, number][] = [];
  for (let c = end; c !== start; c = prev[c]) out.push([c % w, (c / w) | 0]);
  return out.reverse();
}

// ------------------------------------------------------------------ what the floors show
/** The news of some categories for a market (the market's own, the ones about the whole market), newest first. */
export function storiesOf(doc: NewsDoc, market: string, cats: Category[]): NewsItem[] {
  return forMarket(doc.headlines, market).filter((h) => h.cat && cats.includes(h.cat)).sort((a, b) => b.t - a.t);
}

/** What some categories add to a market's reading (null: the market has no reading) and how many stories count. */
export function pushOf(doc: NewsDoc, market: string, cats: Category[]): { push: number | null; n: number } {
  const rd = doc.markets[market];
  if (!rd || rd.net == null) return { push: null, n: 0 };
  let push = 0, n = 0;
  for (const c of cats) {
    const x = rd.cats?.[c] ?? [...rd.drivers.up, ...rd.drivers.down].find((d) => d.cat === c);
    if (x) { push += x.push; n += x.n; }
  }
  return { push: Math.round(push * 10) / 10, n };
}

/** The catalysts placed on the map, by region (geopolitics apart: the bright pins). */
export function byRegion(doc: NewsDoc, market: string): { region: string; geo: NewsItem[]; other: NewsItem[] }[] {
  const out = new Map<string, { region: string; geo: NewsItem[]; other: NewsItem[] }>();
  for (const h of forMarket(doc.headlines, market)) {
    if (!h.catalyst || !h.region) continue;
    const r = out.get(h.region) ?? { region: h.region, geo: [], other: [] };
    (h.cat === "geopolitics" ? r.geo : r.other).push(h);
    out.set(h.region, r);
  }
  return [...out.values()].sort((a, b) => b.geo.length - a.geo.length || b.other.length - a.other.length);
}

/** A security story about this market in the last 24 h strong enough to sound the alarm (a hack or exploit scored
 *  -30 or worse): the one the room's panel also lists. */
export function alarmOf(doc: NewsDoc, market: string, now: number): NewsItem | null {
  return forMarket(doc.headlines, market).find((h) => h.cat === "security" && h.catalyst && (h.score ?? 0) <= -30 && now - h.t <= 86400_000) ?? null;
}

// ------------------------------------------------------------------ the markets' clocks
export interface Exchange { id: "ny" | "london" | "tokyo"; tz: string; sessions: [number, number][] }   // minutes of the local day
export const EXCHANGES: Exchange[] = [
  { id: "ny", tz: "America/New_York", sessions: [[570, 960]] },                 // 9:30-16:00
  { id: "london", tz: "Europe/London", sessions: [[480, 990]] },                // 8:00-16:30
  { id: "tokyo", tz: "Asia/Tokyo", sessions: [[540, 690], [750, 930]] },        // 9:00-11:30, 12:30-15:30
];

/** Local time, open now, and minutes to the next change (weekends closed; holidays not known). */
export function exchangeNow(x: Exchange, now: number): { time: string; open: boolean; minutes: number } {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: x.tz, weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(new Date(now));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const day = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(get("weekday"));
  const m = +get("hour") * 60 + +get("minute");
  const time = `${get("hour")}:${get("minute")}`;
  const weekday = day >= 1 && day <= 5;
  const s = weekday ? x.sessions.find(([a, b]) => m >= a && m < b) : undefined;
  if (s) return { time, open: true, minutes: s[1] - m };
  // the next opening: later today, or the first session of the next weekday
  const later = weekday ? x.sessions.find(([a]) => a > m) : undefined;
  if (later) return { time, open: false, minutes: later[0] - m };
  let d = day, add = 1440 - m;
  for (let i = 0; i < 7; i++) {
    d = (d + 1) % 7;
    if (d >= 1 && d <= 5) break;
    add += 1440;
  }
  return { time, open: false, minutes: add + x.sessions[0][0] };
}
