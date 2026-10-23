// Strike City renderer: camera, input, picking and the per-frame dynamic layers over the pre-rendered city.
import type { AgentView, Prices, Status } from "./agents";
import { atWork, isActive, readingNews, step } from "./agents";
import { FEET, HEAD_TOP, drawFrame, hash, sheetFor, type Anim, type Dir } from "./sprites";
import type { Book, Trade } from "./store";
import { ART2, BUILDINGS, FOUNTAIN, H, SCREEN, TILE, TOWER_SCREENS, W, footprint, renderGlow, renderLight, renderStatic } from "./world";
import { ticker } from "./text";

export type Sel = { kind: "agent" | "building"; id: string };
type Hit = Sel | { kind: "screen"; id: string } | { kind: "car"; id: string };

/** The chart on Strike Finance's screen (world px): STRIKE, Strike Finance's own token, is laid over it (city/dexscreener.tsx). */
export const SCREEN_CHART = { x: SCREEN.x + 2, y: SCREEN.y + 2, w: Math.round(SCREEN.w * 0.64) - 2, h: SCREEN.h - 19 };
/** And the order book beside it: Strike's real BTC-USD book (the city lays its prices and sizes over it). */
export const SCREEN_BOOK = { x: SCREEN.x + Math.round(SCREEN.w * 0.66), y: SCREEN.y + 2, w: SCREEN.w - Math.round(SCREEN.w * 0.66) - 2, h: SCREEN.h - 19 };
/** The chart on each market tower's screen (world px): TradingView's live chart of that market is laid over it. */
export const TOWER_CHARTS = TOWER_SCREENS.map((s) => ({ id: s.id, market: s.market, x: s.x + 2, y: s.y + 2, w: s.w - 4, h: s.h - 4 }));
/** The news strip along the screen's foot (world px). */
const STRIP = 15;

export interface EngineOpts {
  getAgents: () => AgentView[];
  getPrices: () => Prices;
  getHistory: (market: string) => number[];
  getHeadline: () => string;
  getNewsTape?: () => string;                          // the News Tower's LED band (the latest stories)
  getJobLabel?: (a: AgentView) => string | null;       // an agent at work in its trade's building: what it reads there
  getBook?: () => Book | null;                         // Strike's order book for the exchange's screen
  getToken?: () => { price: number; change: number } | null;   // STRIKE, Strike Finance's token (its screen until its chart is in)
  getWeather: () => 0 | 1 | 2;   // calm · breezy · storm
  getAlerts?: () => Record<string, { level: "info" | "warn" | "alert"; text: string }>;   // Strike's fresh alerts, by building
  onSelect: (sel: Sel | null) => void;
  onChart?: (market: string) => void;                  // a screen was pressed: open its chart ("STRIKE" or a market)
  onScreen?: (x: number, y: number, zoom: number) => void;   // every frame: where SCREEN_CHART's corner is (CSS px)
  takeTrades?: (now: number) => Trade[];               // Strike's real trades due to drive in now (each one is a car)
  onTrade?: (t: Trade) => void;                        // a car was pressed: the trade it is
  reducedMotion: boolean;
  interactive?: boolean;                               // false: a picture of the city (landing): no input at all
  view?: { cx: number; cy: number; zoom: number };     // fixed camera for wide frames (desktop)
  viewSmall?: { cx: number; cy: number; zoom: number }; // and for frames under 700 px (phones)
}

/** The colour of Strike's copy trading in the city: the Copy Arena's neon, the leads' rings and bubbles. */
export const LEAD_COLOR = "#fb7185";
/** How many of a lead's copiers walk behind it (the rest are in its card). */
export const TRAIL_MAX = 4;
/** Copiers wear one of a few looks (a handful of sheets for every lead's copiers). */
const COPIER_LOOKS = 6;

export const STATUS_COLOR: Record<Status, string> = {
  analyzing: "#67e8f9", waiting: "#fbbf24", signal: "#4efab0", risk: "#fb923c",
  entering: "#4efab0", in_trade: "#4efab0", exiting: "#e5e7eb", paused: "#93c5fd", offline: "#9ca3af", unfunded: "#c4b5fd",
};

/** "1h32" / "12m" until a real agent's next candle check (bubble label). */
function countdown(ms: number): string {
  const m = Math.max(0, Math.round(ms / 60_000));
  return m >= 60 ? `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}` : `${m}m`;
}

// The city's three pre-rendered layers (deterministic: the same for every engine), made once per page. Drawing them in
// one go blocks the page ~100 ms on a phone: prepareLayers() makes them one at a time in the browser's idle moments.
type Layers = { ground: HTMLCanvasElement; light: HTMLCanvasElement; glow: HTMLCanvasElement };
let layers: Layers | null = null;
/** A moment the browser has nothing else to do (or the next turn, where it cannot say). */
export const idleMoment = () => new Promise<void>((r) => {
  const ric = (window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback;
  if (ric) ric(() => r(), { timeout: 1000 }); else setTimeout(r, 0);
});
const layersNow = (): Layers => (layers ??= (() => { const ground = renderStatic(); return { ground, light: renderLight(), glow: renderGlow() }; })());

export async function prepareLayers(wait: () => Promise<void> = idleMoment): Promise<void> {
  if (layers) return;
  await wait(); const ground = renderStatic();      // the light sources the other two use are found here
  await wait(); const light = renderLight();
  await wait(); const glow = renderGlow();
  layers ??= { ground, light, glow };
}

export class CityEngine {
  private ctx: CanvasRenderingContext2D;
  private staticLayer = layersNow().ground;
  private lightLayer = layersNow().light;
  private glowLayer = layersNow().glow;
  private raf = 0;
  private last = performance.now();
  private dpr = Math.min(2, window.devicePixelRatio || 1);
  private cx = FOUNTAIN.x; private cy = FOUNTAIN.y - 40; private zoom = 1.5;
  private inset = { left: 0, right: 0, bottom: 0 };   // screen px covered by panels / cards
  // preview a time of day with #/city?night=1 (read once: the page rewrites the hash afterwards)
  private forcedNight = ((m) => (m ? +m[1] : null))(/[?&]night=([01](?:\.\d+)?)/.exec(location.hash));
  private follow: string | null = null;
  selected: Sel | null = null;
  private hovered: string | null = null;
  private heldCar: string | null = null;   // the car under the pointer stops, so it can be pressed
  private mouse: { x: number; y: number } | null = null;   // where the mouse rests (a car may drive under it)
  private pointers = new Map<number, { x: number; y: number }>();
  private drag: { x: number; y: number; cx: number; cy: number; moved: boolean } | null = null;
  private pinch: { d: number; zoom: number } | null = null;
  // every car is a real trade on Strike mainnet: it drives in when the trade comes in and leaves at the end of its road
  private cars: { lane: number; t: number; speed: number; trade: Trade; x: number; y: number; until: number }[] = [];
  private rain = Array.from({ length: 140 }, () => ({ x: Math.random(), y: Math.random(), v: 0.6 + Math.random() * 0.6 }));
  private t0 = performance.now();
  private placed: { x: number; y: number; w: number; h: number }[] = [];   // bubbles already drawn this frame
  private few = true;
  private bookW = new Array<number>(10).fill(0);
  private phases = new Map<string, number>();     // each agent's animation offset (seconds), stable   // the book's bars (5 asks, 5 bids), easing to each new reading
  private trails = new Map<string, { x: number; y: number }[]>();   // each lead's latest steps, newest first: its copiers walk on them

  constructor(private canvas: HTMLCanvasElement, private o: EngineOpts) {
    this.ctx = canvas.getContext("2d", { alpha: false })!;
    this.resize();
    this.home();
    if (o.interactive === false) this.on(window, "resize", () => { this.resize(); this.home(); });
    else this.bind();
  }

  start() {
    cancelAnimationFrame(this.raf);
    this.last = performance.now();
    const loop = (t: number) => { this.frame(t); this.raf = requestAnimationFrame(loop); };
    this.raf = requestAnimationFrame(loop);
  }
  /** Stops drawing (off-screen) without releasing the engine; start() resumes. */
  pause() { cancelAnimationFrame(this.raf); }
  stop() { cancelAnimationFrame(this.raf); this.unbind(); }

  resize() {
    const r = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(1, Math.round(r.width * this.dpr));
    this.canvas.height = Math.max(1, Math.round(r.height * this.dpr));
    this.clamp();
  }

  // ------------------------------------------------------------- camera
  private get vw() { return this.canvas.width / this.dpr; }
  private get vh() { return this.canvas.height / this.dpr; }
  private toWorld(sx: number, sy: number) { return { x: this.cx + (sx - this.vw / 2) / this.zoom, y: this.cy + (sy - this.vh / 2) / this.zoom }; }
  private toScreen(wx: number, wy: number) { return { x: (wx - this.cx) * this.zoom + this.vw / 2, y: (wy - this.cy) * this.zoom + this.vh / 2 }; }
  private clamp() {
    const minZoom = Math.max(this.vw / W, this.vh / H);
    this.zoom = Math.min(4, Math.max(minZoom, this.zoom));
    const hw = this.vw / 2 / this.zoom, hh = this.vh / 2 / this.zoom;
    // a side panel or a bottom card covers part of the map: the camera may go that far past the edge, so whoever stands
    // by the map's edge (the Copy Arena's door) can still be shown beside the panel, above the card
    this.cx = Math.min(W - hw + this.inset.right / this.zoom, Math.max(hw - this.inset.left / this.zoom, this.cx));
    this.cy = Math.min(H - hh + this.inset.bottom / this.zoom, Math.max(hh, this.cy));
  }
  zoomBy(f: number, sx = this.vw / 2, sy = this.vh / 2) {
    const before = this.toWorld(sx, sy);
    this.zoom *= f;
    this.clamp();
    const after = this.toWorld(sx, sy);
    this.cx += before.x - after.x; this.cy += before.y - after.y;
    this.clamp();
  }
  /** Default view: market towers, the exchange and the plaza, where most agents are. */
  private home() {
    const small = this.vw < 700;
    const v = small ? this.o.viewSmall : this.o.view;
    if (v) { ({ cx: this.cx, cy: this.cy, zoom: this.zoom } = v); this.clamp(); return; }
    this.zoom = small ? 1.2 : 1.55;
    this.cx = small ? 700 : FOUNTAIN.x;   // phones: BTC tower door, exchange door and the plaza in one view
    this.cy = small ? 405 : 395;
    this.clamp();
  }
  recenter() { this.follow = null; this.home(); }
  setInsets(right: number, bottom: number, left = 0) {
    if (left === this.inset.left && right === this.inset.right && bottom === this.inset.bottom) return;
    this.inset = { left, right, bottom };
    this.clamp();   // the panel or the card closed: back inside the map
  }
  /** Select from the UI (lists, cards) or from a click on the map; agents are followed, buildings centred. */
  select(sel: Sel | null, notify = true) {
    this.selected = sel;
    this.follow = sel?.kind === "agent" ? sel.id : null;
    if (sel?.kind === "agent") this.zoom = Math.max(this.zoom, 2.2);
    if (sel?.kind === "building") {
      const b = BUILDINGS.find((x) => x.id === sel.id);
      if (b) { const f = footprint(b); this.cx = ((f.x0 + f.x1) / 2) * TILE; this.cy = ((f.y0 + f.y1) / 2) * TILE + 20; this.clamp(); }
    }
    if (notify) this.o.onSelect(sel);
  }
  setFollow(on: boolean) { this.follow = on && this.selected?.kind === "agent" ? this.selected.id : null; }
  get following() { return this.follow; }
  pan(dx: number, dy: number) { this.follow = null; this.cx += dx / this.zoom; this.cy += dy / this.zoom; this.clamp(); }

  // ------------------------------------------------------------- input
  private handlers: [EventTarget, string, EventListener][] = [];
  private on(t: EventTarget, e: string, f: EventListener, opt?: AddEventListenerOptions) { t.addEventListener(e, f, opt); this.handlers.push([t, e, f]); }
  private bind() {
    const c = this.canvas;
    this.on(window, "resize", () => this.resize());
    this.on(c, "pointerdown", ((e: PointerEvent) => {
      c.setPointerCapture(e.pointerId);
      this.pointers.set(e.pointerId, { x: e.offsetX, y: e.offsetY });
      if (this.pointers.size === 2) {
        const [a, b] = [...this.pointers.values()];
        this.pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, zoom: this.zoom };
        this.drag = null;
      } else this.drag = { x: e.offsetX, y: e.offsetY, cx: this.cx, cy: this.cy, moved: false };
      const hit = this.pick(e.offsetX, e.offsetY);   // a finger on a car stops it too
      if (hit?.kind === "car") this.heldCar = hit.id;
    }) as EventListener);
    this.on(c, "pointerleave", (() => { this.hovered = null; this.heldCar = null; this.mouse = null; }) as EventListener);
    this.on(c, "pointermove", ((e: PointerEvent) => {
      if (this.pointers.has(e.pointerId)) this.pointers.set(e.pointerId, { x: e.offsetX, y: e.offsetY });
      if (this.pinch && this.pointers.size === 2) {
        const [a, b] = [...this.pointers.values()];
        this.zoom = this.pinch.zoom * (Math.hypot(a.x - b.x, a.y - b.y) / this.pinch.d);
        this.clamp();
        return;
      }
      if (this.drag) {
        const dx = e.offsetX - this.drag.x, dy = e.offsetY - this.drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 5) this.drag.moved = true;
        if (this.drag.moved) { this.follow = null; this.cx = this.drag.cx - dx / this.zoom; this.cy = this.drag.cy - dy / this.zoom; this.clamp(); c.style.cursor = "grabbing"; }
      } else if (e.pointerType === "mouse") {
        this.mouse = { x: e.offsetX, y: e.offsetY };
        const hit = this.pick(e.offsetX, e.offsetY);
        this.hovered = hit?.kind === "agent" ? hit.id : null;
        this.heldCar = hit?.kind === "car" ? hit.id : null;
        c.style.cursor = hit ? "pointer" : "grab";
      }
    }) as EventListener);
    const up = ((e: PointerEvent) => {
      this.pointers.delete(e.pointerId);
      if (this.pointers.size < 2) this.pinch = null;
      if (this.drag && !this.drag.moved) {
        const hit = this.pick(e.offsetX, e.offsetY);
        if (hit?.kind === "screen") this.o.onChart?.(hit.id);
        else if (hit?.kind === "car") { const car = this.cars.find((x) => String(x.trade.id) === hit.id); if (car) this.o.onTrade?.(car.trade); }
        else this.select(hit);
      }
      this.drag = null;
      if (e.pointerType !== "mouse") this.heldCar = null;
      c.style.cursor = "grab";
    }) as EventListener;
    this.on(c, "pointerup", up);
    this.on(c, "pointercancel", up);
    this.on(c, "wheel", ((e: WheelEvent) => { e.preventDefault(); this.zoomBy(Math.exp(-e.deltaY * 0.0015), e.offsetX, e.offsetY); }) as EventListener, { passive: false });
    this.on(c, "keydown", ((e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      const s = 80;
      if (k === "arrowleft" || k === "a") this.pan(-s, 0);
      else if (k === "arrowright" || k === "d") this.pan(s, 0);
      else if (k === "arrowup" || k === "w") this.pan(0, -s);
      else if (k === "arrowdown" || k === "s") this.pan(0, s);
      else if (k === "+" || k === "=") this.zoomBy(1.25);
      else if (k === "-" || k === "_") this.zoomBy(1 / 1.25);
      else if (k === "escape" && this.selected) this.select(null);
      else return;
      e.preventDefault();
    }) as EventListener);
  }
  private unbind() { for (const [t, e, f] of this.handlers) t.removeEventListener(e, f); this.handlers = []; }

  private pick(sx: number, sy: number): Hit | null {
    const w = this.toWorld(sx, sy);
    let best: string | null = null, bd = 22 / this.zoom + 6;   // generous hit area, at least ~22 screen px
    for (const a of this.o.getAgents()) {
      const d = Math.hypot(a.x - w.x, a.y - (FEET - HEAD_TOP) / 2 - w.y);   // the middle of the character
      if (d < bd) { bd = d; best = a.id; }
    }
    if (best) return { kind: "agent", id: best };
    if (this.o.onTrade) {   // a car: the trade it is
      let car: string | null = null, cd = 20 / this.zoom + 9;   // generous: a moving car is hard to tap
      for (const x of this.cars) { const d = Math.hypot(x.x - w.x, x.y - w.y); if (d < cd) { cd = d; car = String(x.trade.id); } }
      if (car) return { kind: "car", id: car };
    }
    if (this.o.onChart && w.x >= SCREEN.x && w.x < SCREEN.x + SCREEN.w && w.y >= SCREEN.y && w.y < SCREEN.y + SCREEN.h) return { kind: "screen", id: "STRIKE" };
    if (this.o.onChart) for (const s of TOWER_SCREENS) {
      if (w.x >= s.x && w.x < s.x + s.w && w.y >= s.y && w.y < s.y + s.h) return { kind: "screen", id: s.market };
    }
    for (const b of BUILDINGS) {
      const f = footprint(b);
      if (w.x >= f.x0 * TILE && w.x < f.x1 * TILE && w.y >= f.y0 * TILE && w.y < f.y1 * TILE) return { kind: "building", id: b.id };
    }
    return null;
  }

  // ------------------------------------------------------------- frame
  private night(): number {
    if (this.forcedNight !== null) return this.forcedNight;
    const d = new Date();
    const h = d.getHours() + d.getMinutes() / 60;   // the viewer's local time
    if (h >= 20 || h < 6) return 1;
    if (h >= 18) return 0.5 + (h - 18) / 4;
    if (h < 8) return 1 - (h - 6) / 4;
    return 0.4;   // daylight keeps a dim, neon-friendly tone
  }

  private frame(now: number) {
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    const agents = this.o.getAgents();
    for (const a of agents) {
      if (!this.o.reducedMotion) step(a, dt);
      else if (a.path.length) { const end = a.path[a.path.length - 1]; a.x = end.x; a.y = end.y; a.path = []; }
    }
    if (this.follow) {
      const a = agents.find((x) => x.id === this.follow);
      if (a) {
        const k = this.o.reducedMotion ? 1 : Math.min(1, dt * 4);
        // keep the followed agent in the middle of the part of the map that panels do not cover
        const tx = a.x + (this.inset.right - this.inset.left) / 2 / this.zoom, ty = a.y - 20 + this.inset.bottom / 2 / this.zoom;
        this.cx += (tx - this.cx) * k; this.cy += (ty - this.cy) * k; this.clamp();
      }
    }
    const g = this.ctx;
    const z = this.zoom * this.dpr;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.fillStyle = "#05070a";
    g.fillRect(0, 0, this.canvas.width, this.canvas.height);
    g.setTransform(z, 0, 0, z, this.canvas.width / 2 - this.cx * z, this.canvas.height / 2 - this.cy * z);
    g.imageSmoothingEnabled = false;
    g.drawImage(this.staticLayer, 0, 0);
    const time = this.o.reducedMotion ? 0 : (now - this.t0) / 1000;
    this.drawFountain(g, time);
    this.drawScreen(g, time, dt);
    this.drawTowerScreens(g);
    this.drawNewsTower(g, time);
    if (this.o.onScreen) { const p = this.toScreen(SCREEN_CHART.x, SCREEN_CHART.y); this.o.onScreen(p.x, p.y, this.zoom); }
    this.drawCars(g, dt);
    if (this.selected?.kind === "building") this.drawBuildingFocus(g, this.selected.id, time);
    const sorted = [...agents].sort((a, b) => a.y - b.y);
    for (const a of sorted) this.drawAgent(g, a);
    const n = this.night();
    g.globalAlpha = n;
    g.drawImage(this.lightLayer, 0, 0);
    g.drawImage(this.glowLayer, 0, 0);   // windows, neon and lamps shine through the night
    g.globalAlpha = 1;
    // screen-space overlays
    g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.drawSigns(g, time, n);
    if (this.o.getWeather() === 2 && !this.o.reducedMotion) this.drawRain(g, dt);
    // bubbles: the selected agent first, then front to back. While the city is small every agent keeps its name and
    // overlapping bubbles stack; in a crowd they stack or shrink to a dot
    this.placed = [];
    this.few = agents.filter((a) => a.kind !== "lead").length <= 12;   // leads give way to the city's own agents
    const sel = this.selected?.kind === "agent" ? this.selected.id : null;
    const rank = (a: AgentView) => (a.id === sel ? 0 : 1);
    const order = [...sorted].reverse().sort((p, q) => rank(p) - rank(q));
    for (const a of order) this.drawBubble(g, a, time);
  }

  private drawFountain(g: CanvasRenderingContext2D, t: number) {
    const fr = this.o.getPrices()["BTC-USD"]?.funding ?? 0;
    // water tint follows the sign of BTC funding: mint when longs pay, rose when shorts pay
    const col = fr >= 0 ? "78,250,176" : "244,63,94";
    const drop = fr >= 0 ? "#c9fde6" : "#ffd0d8";
    const fx = FOUNTAIN.x, fy = FOUNTAIN.y + 6;
    g.fillStyle = `rgba(${col},0.22)`;
    g.beginPath(); g.ellipse(fx, fy, 27, 15, 0, 0, Math.PI * 2); g.fill();
    for (let i = 0; i < 3; i++) {
      const k = (t * 0.4 + i / 3) % 1;
      g.strokeStyle = `rgba(${col},${0.55 * (1 - k)})`;
      g.lineWidth = 1;
      g.beginPath(); g.ellipse(fx, fy, 7 + k * 19, 4 + k * 10, 0, 0, Math.PI * 2); g.stroke();
    }
    // eight arcing jets from the pedestal into the basin
    g.fillStyle = drop;
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2;
      const ex = fx + Math.cos(a) * 21, ey = fy + Math.sin(a) * 11;
      for (let k = 0; k < 4; k++) {
        const u = (t * 0.9 + k / 4 + i * 0.13) % 1;
        const x = fx + (ex - fx) * u, y = fy - 10 + (ey - fy + 10) * u - 16 * u * (1 - u) * 2;
        g.globalAlpha = 0.9 - u * 0.4;
        g.fillRect(x - 0.75, y - 0.75, 1.5, 1.5);
      }
    }
    g.globalAlpha = 1;
    // central jet: a column fading upwards, with spray falling back from its crown
    const jet = 16 + Math.sin(t * 3.2) * 3, top = fy - 10 - jet;
    const grad = g.createLinearGradient(0, fy - 10, 0, top);
    grad.addColorStop(0, `rgba(${col},0.75)`); grad.addColorStop(1, `rgba(${col},0)`);
    g.fillStyle = grad; g.fillRect(fx - 2, top, 4, jet);
    g.fillStyle = drop;
    for (let k = 0; k < 6; k++) {
      const u = (t * 1.3 + k / 6) % 1, side = k % 2 ? 1 : -1;
      g.globalAlpha = 1 - u;
      g.fillRect(fx + side * (1 + u * 6) - 0.5, top + 2 + u * u * 14, 1, 1);
    }
    g.globalAlpha = 1;
  }

  private drawScreen(g: CanvasRenderingContext2D, t: number, dt: number) {
    const { x, y, w, h } = SCREEN;
    g.fillStyle = "#020806"; g.fillRect(x, y, w, h);
    g.strokeStyle = "rgba(78,250,176,0.6)"; g.lineWidth = 1; g.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    const chartH = h - STRIP - 2;
    g.fillStyle = "rgba(78,250,176,0.08)";
    for (let gx = x + 8; gx < x + w * 0.62; gx += 16) g.fillRect(gx, y + 3, 1, chartH - 4);
    // STRIKE, Strike Finance's token: its name and price until its chart (DEX Screener) is drawn over this part
    const tok = this.o.getToken?.();
    g.textAlign = "left"; g.textBaseline = "top";
    g.font = `700 13px "IBM Plex Mono", monospace`;
    g.fillStyle = "#4efab0";
    g.fillText("STRIKE", x + 10, y + 10);
    g.font = `600 7px "IBM Plex Mono", monospace`;
    g.fillStyle = "rgba(199,253,228,0.7)";
    g.fillText("STRIKE FINANCE · STRIKE/ADA · SUNDAESWAP", x + 10, y + 27);
    if (tok) {
      g.font = `700 11px "IBM Plex Mono", monospace`;
      g.fillStyle = tok.change >= 0 ? "#4efab0" : "#f43f5e";
      g.fillText(`$${tok.price.toFixed(4)}  ${tok.change >= 0 ? "▲" : "▼"}${Math.abs(tok.change).toFixed(2)}%`, x + 10, y + 40);
    }
    // order book (right third): Strike's real one, asks above and bids below, the best ones in the middle; each bar is
    // a level's size against the biggest shown, and eases to every new reading (store.refreshBook, every 2.5 s)
    const bx = x + w * 0.66, bw = w * 0.32;
    const book = this.o.getBook?.();
    const want = new Array<number>(10).fill(0);
    if (book?.asks.length && book.bids.length) {
      const top = Math.max(...book.asks.slice(0, 5).map((l) => l[1]), ...book.bids.slice(0, 5).map((l) => l[1]));
      for (let i = 0; i < 5; i++) { want[i] = (book.asks[i]?.[1] ?? 0) / top; want[5 + i] = (book.bids[i]?.[1] ?? 0) / top; }
    }
    const k = this.o.reducedMotion ? 1 : Math.min(1, dt * 5);
    for (let i = 0; i < 10; i++) this.bookW[i] += (want[i] - this.bookW[i]) * k;
    for (let i = 0; i < 5; i++) {
      const a = this.bookW[i] * bw * 0.9, b = this.bookW[5 + i] * bw * 0.9;
      g.fillStyle = "rgba(244,63,94,0.75)"; g.fillRect(bx + bw - a, y + 4 + (4 - i) * 4, a, 3);
      g.fillStyle = "rgba(78,250,176,0.75)"; g.fillRect(bx + bw - b, y + chartH - 3 - (4 - i) * 4, b, 3);
    }
    // news strip
    const ny = y + h - STRIP;
    g.fillStyle = "#041510"; g.fillRect(x + 1, ny, w - 2, STRIP - 1);
    g.save();
    g.beginPath(); g.rect(x + 1, ny, w - 2, STRIP - 1); g.clip();
    const txt = this.o.getHeadline();
    g.font = `600 9px "IBM Plex Mono", monospace`;
    g.textBaseline = "middle"; g.textAlign = "left";
    const tw = g.measureText(txt).width + 40;
    const off = this.o.reducedMotion ? 0 : (t * 22) % tw;
    g.fillStyle = "#c7fde4";
    for (let k = -1; k < 3; k++) g.fillText(txt, x + 4 - off + k * tw, ny + STRIP / 2);
    g.restore();
  }

  /** Each market tower's screen: glass, a rim in the tower's colour, and the market's last 48 hours (Strike's prices)
   *  until TradingView's live chart of it is drawn over it. */
  private drawTowerScreens(g: CanvasRenderingContext2D) {
    for (const s of TOWER_SCREENS) {
      const b = BUILDINGS.find((x) => x.id === s.id)!;
      g.fillStyle = "#020806"; g.fillRect(s.x, s.y, s.w, s.h);
      g.strokeStyle = b.neon; g.globalAlpha = 0.75; g.lineWidth = 1; g.strokeRect(s.x + 0.5, s.y + 0.5, s.w - 1, s.h - 1);
      g.globalAlpha = 1;
      const hist = this.o.getHistory(s.market);
      if (hist.length < 3) continue;
      const min = Math.min(...hist), max = Math.max(...hist), up = hist[hist.length - 1] >= hist[0];
      g.strokeStyle = up ? "#4efab0" : "#f43f5e"; g.lineWidth = 1.2;
      g.beginPath();
      hist.forEach((v, i) => {
        const px = s.x + 6 + (i / (hist.length - 1)) * (s.w - 12);
        const py = s.y + s.h - 8 - ((v - min) / (max - min || 1)) * (s.h - 26);
        if (i) g.lineTo(px, py); else g.moveTo(px, py);
      });
      g.stroke();
      g.font = `700 7px "IBM Plex Mono", monospace`;
      g.fillStyle = b.neon; g.textAlign = "left"; g.textBaseline = "top";
      g.fillText(`${s.market} · 48H`, s.x + 6, s.y + 5);
    }
  }

  /** The News Tower's LED band over its entrance (the new art only; its name is drawn at the top). */
  private drawNewsTower(g: CanvasRenderingContext2D, t: number) {
    const tape = ART2 ? this.o.getNewsTape?.() : "";
    if (!tape) return;
    const x = 4 * TILE + 5, y = 37 * TILE + 3, w = 16 * TILE - 10, h = 10;
    g.fillStyle = "#0c0802"; g.fillRect(x, y, w, h);
    g.strokeStyle = "rgba(251,191,36,0.55)"; g.lineWidth = 1; g.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    g.save();
    g.beginPath(); g.rect(x + 1, y + 1, w - 2, h - 2); g.clip();
    g.font = `700 7px "IBM Plex Mono", monospace`;
    g.textBaseline = "middle"; g.textAlign = "left";
    const tw = g.measureText(tape).width + 48;
    const off = this.o.reducedMotion ? 0 : (t * 20) % tw;
    g.fillStyle = "#fbbf24";
    for (let k = 0; k < 3; k++) g.fillText(tape, x + 4 - off + k * tw, y + h / 2 + 0.5);
    g.fillStyle = "rgba(0,0,0,0.28)";   // the dots of the board
    for (let gx = x + 1; gx < x + w - 1; gx += 2) g.fillRect(gx, y + 1, 0.6, h - 2);
    g.restore();
  }

  private drawCars(g: CanvasRenderingContext2D, dt: number) {
    const lanes = [
      { h: true, y: 18 * TILE + 8, dir: 1 }, { h: true, y: 19 * TILE + 8, dir: -1 },
      { h: true, y: 42 * TILE + 8, dir: 1 }, { h: true, y: 43 * TILE + 8, dir: -1 },
      { h: false, x: 24 * TILE + 8, dir: 1 }, { h: false, x: 25 * TILE + 8, dir: -1 },
      { h: false, x: 72 * TILE + 8, dir: 1 }, { h: false, x: 73 * TILE + 8, dir: -1 },
      { h: false, x: 48 * TILE + 8, dir: 1, top: true }, { h: false, x: 49 * TILE + 8, dir: -1, top: true },
    ];
    const now = performance.now();
    for (const trade of this.o.takeTrades?.(now) ?? []) {
      // a road per trade (spread over the city's ten lanes); with reduced motion it parks along its road for a while
      const lane = (hash(trade.market) + trade.id) % lanes.length;
      this.cars.push({ lane, t: this.o.reducedMotion ? 0.15 + ((trade.id % 70) / 100) : 0, speed: 0.032 + ((trade.id % 7) / 7) * 0.016,
        trade, x: -999, y: -999, until: now + 20_000 });
    }
    if (this.mouse && !this.drag) {   // a car that drives under the resting mouse stops as well
      const hit = this.pick(this.mouse.x, this.mouse.y);
      this.heldCar = hit?.kind === "car" ? hit.id : null;
      if (hit?.kind === "car") this.canvas.style.cursor = "pointer";
    }
    if (this.cars.length > 60) this.cars.splice(0, this.cars.length - 60);
    this.cars = this.cars.filter((car) => (this.o.reducedMotion ? now < car.until : car.t < 1));
    for (const car of this.cars) {
      const held = String(car.trade.id) === this.heldCar;
      if (!this.o.reducedMotion && !held) car.t += car.speed * dt;
      const L = lanes[car.lane] as { h: boolean; x?: number; y?: number; dir: number; top?: boolean };
      const span = L.h ? W : L.top ? 18 * TILE : H;
      const p = L.dir > 0 ? car.t * span : (1 - car.t) * span;
      const cx = L.h ? p : L.x!, cy = L.h ? L.y! : p;
      car.x = cx; car.y = cy;
      // bought green, sold red; the bigger the trade, the bigger the car (a truck from 5,000 $)
      const usd = car.trade.usd, truck = usd >= 5000;
      const len = truck ? 19 : usd >= 100 ? 13 : 11, wid = truck ? 8 : usd >= 100 ? 7 : 6, front = L.dir > 0 ? 1 : -1;
      g.fillStyle = "rgba(0,0,0,0.35)";
      if (L.h) g.fillRect(cx - len / 2 + 1, cy - wid / 2 + 2, len, wid); else g.fillRect(cx - wid / 2 + 1, cy - len / 2 + 2, wid, len);
      if (held) {   // a light outline: this one can be pressed
        g.fillStyle = "#fff7d6";
        if (L.h) g.fillRect(cx - len / 2 - 1.5, cy - wid / 2 - 1.5, len + 3, wid + 3); else g.fillRect(cx - wid / 2 - 1.5, cy - len / 2 - 1.5, wid + 3, len + 3);
      }
      g.fillStyle = car.trade.side === "buy" ? "#1d7a55" : "#9b2c3b";
      if (L.h) g.fillRect(cx - len / 2, cy - wid / 2, len, wid); else g.fillRect(cx - wid / 2, cy - len / 2, wid, len);
      if (truck) {   // the cargo box
        g.fillStyle = car.trade.side === "buy" ? "#4efab0" : "#fb7185";
        const bl = len - 7;
        if (L.h) g.fillRect(front > 0 ? cx - len / 2 + 1 : cx - len / 2 + 6, cy - wid / 2 + 1, bl, wid - 2);
        else g.fillRect(cx - wid / 2 + 1, front > 0 ? cy - len / 2 + 1 : cy - len / 2 + 6, wid - 2, bl);
      }
      g.fillStyle = "rgba(160,200,220,0.35)";   // windscreen
      if (L.h) g.fillRect(cx + front * 2 - 1, cy - 2.5, 2, 5); else g.fillRect(cx - 2.5, cy + front * 2 - 1, 5, 2);
      g.fillStyle = "#fff7d6";
      const fx = front > 0 ? len / 2 - 1 : -len / 2;
      if (L.h) { g.fillRect(cx + fx, cy - 3, 1, 2); g.fillRect(cx + fx, cy + 1, 1, 2); }
      else { g.fillRect(cx - 3, cy + fx, 2, 1); g.fillRect(cx + 1, cy + fx, 2, 1); }
      g.fillStyle = "#ef4444";
      const bx = front > 0 ? -len / 2 : len / 2 - 1;
      if (L.h) g.fillRect(cx + bx, cy - 3, 1, 6); else g.fillRect(cx - 3, cy + bx, 6, 1);
    }
  }

  private drawBuildingFocus(g: CanvasRenderingContext2D, id: string, t: number) {
    const b = BUILDINGS.find((x) => x.id === id);
    if (!b) return;
    const f = footprint(b);
    g.strokeStyle = b.neon;
    g.globalAlpha = 0.6 + 0.4 * Math.sin(t * 3);
    g.lineWidth = 2;
    g.strokeRect(f.x0 * TILE - 2, f.y0 * TILE - 2, (f.x1 - f.x0) * TILE + 4, (f.y1 - f.y0) * TILE + 4);
    g.globalAlpha = 1;
  }

  private drawAgent(g: CanvasRenderingContext2D, a: AgentView) {
    const sheet = sheetFor(a.id, a.look);   // null until its pieces have loaded: its ring shows meanwhile
    const walking = a.path.length > 0;
    if (a.lead) this.drawCopiers(g, a, walking);
    g.fillStyle = "rgba(0,0,0,0.45)";
    g.beginPath(); g.ellipse(a.x, a.y, 5, 2, 0, 0, Math.PI * 2); g.fill();
    if (a.lead) {   // a lead of Strike's copy trading: a rose ring, pulsing while it walks to do something on Strike
      const k = this.o.reducedMotion || !walking ? 0.3 : (performance.now() / 1400) % 1;
      g.strokeStyle = `rgba(251,113,133,${0.85 - 0.6 * k})`; g.lineWidth = 1;
      g.beginPath(); g.ellipse(a.x, a.y, 6 + k * 5, 2.5 + k * 2, 0, 0, Math.PI * 2); g.stroke();
      g.fillStyle = "rgba(251,113,133,0.2)";
      g.beginPath(); g.ellipse(a.x, a.y, 7, 3, 0, 0, Math.PI * 2); g.fill();
    } else {   // a ring: every agent here is a real one. It pulses only while the agent is doing something; one that waits
        // for its setup has a still ring, and a paused or offline one a faint ring
      const busy = isActive(a), resting = a.status === "paused" || a.status === "offline" || a.status === "unfunded";
      const k = this.o.reducedMotion || !busy ? 0.3 : (performance.now() / 1400) % 1;
      g.strokeStyle = `rgba(78,250,176,${(0.85 - 0.6 * k) * (resting ? 0.4 : 1)})`; g.lineWidth = 1;
      g.beginPath(); g.ellipse(a.x, a.y, 6 + k * 5, 2.5 + k * 2, 0, 0, Math.PI * 2); g.stroke();
      g.fillStyle = `rgba(78,250,176,${resting ? 0.08 : 0.22})`;
      g.beginPath(); g.ellipse(a.x, a.y, 7, 3, 0, 0, Math.PI * 2); g.fill();
    }
    if (this.selected?.kind === "agent" && a.id === this.selected.id) {
      g.strokeStyle = a.lead ? LEAD_COLOR : "#4efab0"; g.lineWidth = 1;
      g.beginPath(); g.ellipse(a.x, a.y, 8, 3.5, 0, 0, Math.PI * 2); g.stroke();
    }
    if (!sheet) return;
    // walking, its 6 frames in the way it goes; analysing a candle, it checks its phone; otherwise it stands (and
    // breathes). Each agent's animation starts at its own moment, so a crowd does not move in step
    const anim: Anim = walking ? "walk" : a.status === "analyzing" ? "phone" : "idle";
    let ph = this.phases.get(a.id);
    if (ph === undefined) { ph = (hash(a.id) % 1000) / 250; this.phases.set(a.id, ph); }
    const t = this.o.reducedMotion ? 0 : performance.now() / 1000 + ph;
    drawFrame(g, sheet, anim, anim === "phone" ? "down" : a.dir, t, a.x, a.y);
  }

  /** The people copying a lead on Strike right now (up to TRAIL_MAX), walking in its steps a little smaller than it:
   *  copying is following. Standing, they wait in a short line behind it. */
  private drawCopiers(g: CanvasRenderingContext2D, a: AgentView, walking: boolean) {
    const n = Math.min(TRAIL_MAX, a.lead?.copiers.active ?? 0);
    let trail = this.trails.get(a.id);
    if (!trail) { trail = [{ x: a.x, y: a.y }]; this.trails.set(a.id, trail); }
    const moved = Math.hypot(a.x - trail[0].x, a.y - trail[0].y);
    if (moved > 40) { trail.length = 0; trail.push({ x: a.x, y: a.y }); }   // it jumped (reduced motion): start again
    else if (moved >= 3) { trail.unshift({ x: a.x, y: a.y }); if (trail.length > 24) trail.length = 24; }
    const t = this.o.reducedMotion ? 0 : performance.now() / 1000;
    for (let i = 0; i < n; i++) {
      const k = (i + 1) * 4;   // ~12 px apart along the lead's steps
      let x: number, y: number, dir: Dir = a.dir;
      if (trail.length > k) {
        x = trail[k].x; y = trail[k].y;
        const f = trail[k - 1], dx = f.x - x, dy = f.y - y;
        if (dx || dy) dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
      } else {   // not enough steps yet: in a row beside it, one each side in turn
        const end = trail[trail.length - 1];
        x = end.x + (i % 2 ? 1 : -1) * 11 * (1 + Math.floor(i / 2)); y = end.y - 2;
        dir = walking ? a.dir : "down";
      }
      g.fillStyle = "rgba(0,0,0,0.35)";
      g.beginPath(); g.ellipse(x, y, 4, 1.6, 0, 0, Math.PI * 2); g.fill();
      g.strokeStyle = "rgba(251,113,133,0.45)"; g.lineWidth = 0.75;
      g.beginPath(); g.ellipse(x, y, 4.5, 1.9, 0, 0, Math.PI * 2); g.stroke();
      const sheet = sheetFor(`copier:${(hash(a.id) + i) % COPIER_LOOKS}`);
      if (!sheet) continue;
      g.globalAlpha = 0.92;
      drawFrame(g, sheet, walking ? "walk" : "idle", dir, t + i * 0.37, x, y, 0.75);
      g.globalAlpha = 1;
    }
  }

  /** Each building's name on a lit plate at its front (the exchange's under its screen), drawn on the screen so it
   *  reads at any zoom: 12-20 CSS px, never the size of a speck when zoomed out nor of a poster when zoomed in. A market
   *  tower adds its live price under its name. */
  private drawSigns(g: CanvasRenderingContext2D, t: number, night: number) {
    const prices = this.o.getPrices();
    const alerts = this.o.getAlerts?.() ?? {};
    const font = `"IBM Plex Mono", monospace`;
    g.save();
    g.textAlign = "center";
    g.textBaseline = "middle";
    for (const b of BUILDINGS) {
      const ts = TOWER_SCREENS.find((x) => x.id === b.id);
      const wy = b.kind === "exchange" ? Math.max((b.y + b.d) * TILE + 7, SCREEN.y + SCREEN.h + 9) : ts ? ts.y + ts.h + 9 : (b.y + b.d) * TILE + 7;
      const s = this.toScreen((b.x + b.w / 2) * TILE, wy);
      if (s.x < -200 || s.x > this.vw + 200 || s.y < -40 || s.y > this.vh + 60) continue;
      const big = b.kind === "exchange" || b.kind === "news";
      const size = Math.round(Math.min(big ? 20 : 17, Math.max(big ? 13 : 12, (big ? 10 : 8.5) * this.zoom)));
      const flicker = b.kind === "alley" && t ? 0.7 + 0.3 * Math.max(0, Math.sin(t * 13) * Math.sin(t * 3.1)) : 1;
      g.font = `700 ${size}px ${font}`;
      const tw = g.measureText(b.label).width, padX = Math.round(size * 0.6), h = Math.round(size * 1.6);
      roundRect(g, s.x - tw / 2 - padX, s.y - h / 2, tw + padX * 2, h, 4);
      g.fillStyle = "rgba(3,6,8,0.86)"; g.fill();
      g.strokeStyle = b.neon; g.globalAlpha = 0.6; g.lineWidth = 1; g.stroke();
      g.globalAlpha = flicker;
      g.shadowColor = b.neon;
      g.shadowBlur = 6 * (0.4 + night);
      g.fillStyle = b.neon;
      g.fillText(b.label, s.x, s.y + 1);
      g.globalAlpha = 1;
      g.shadowBlur = 0;
      let below = s.y + h / 2 + 4;   // where an alert goes: under the plate (and the price), never over a tower's screen
      if (b.market && prices[b.market]) {
        const p = prices[b.market];
        const ps = Math.max(11, Math.round(size * 0.78));
        g.font = `600 ${ps}px ${font}`;
        const txt = `${p.price >= 1000 ? Math.round(p.price).toLocaleString("en-US") : p.price.toFixed(2)} ${p.change >= 0 ? "▲" : "▼"}${Math.abs(p.change).toFixed(2)}%`;
        const pw = g.measureText(txt).width + ps, ph = Math.round(ps * 1.5), py = s.y + h / 2 + 3;
        roundRect(g, s.x - pw / 2, py, pw, ph, 3);
        g.fillStyle = "rgba(2,6,6,0.92)"; g.fill();
        g.strokeStyle = p.change >= 0 ? "rgba(78,250,176,0.55)" : "rgba(244,63,94,0.55)";
        g.lineWidth = 1; g.stroke();
        g.fillStyle = p.change >= 0 ? "#4efab0" : "#f43f5e";
        g.fillText(txt, s.x, py + ph / 2 + 0.5);
        below = py + ph + 4;
      }
      const al = alerts[b.id];
      if (al) this.drawAlert(g, al, s.x, below, size, t);
    }
    g.restore();
  }

  /** One of Strike's fresh alerts over the building it concerns (a move over its tower, funding at the Funding Cafe,
   *  a position near liquidation over Liquidation Alley...): a badge that breathes, red, amber or blue by how serious. */
  private drawAlert(g: CanvasRenderingContext2D, al: { level: string; text: string }, x: number, top: number, size: number, t: number) {
    const color = al.level === "alert" ? "#f43f5e" : al.level === "warn" ? "#fbbf24" : "#60a5fa";
    const fs = Math.max(11, Math.round(size * 0.8));
    g.font = `700 ${fs}px "IBM Plex Mono", monospace`;
    const text = al.text.length > 34 ? al.text.slice(0, 33) + "…" : al.text;
    const label = `▲ ${text}`;
    const w = g.measureText(label).width + fs * 1.2, h = Math.round(fs * 1.7), y = top;
    // never cut by the map's edge or under an open panel (Alt Row stands at the right edge)
    x = Math.min(this.vw - this.inset.right - w / 2 - 60, Math.max(this.inset.left + w / 2 + 8, x));   // 60: the zoom buttons
    const pulse = this.o.reducedMotion ? 1 : 0.55 + 0.45 * Math.sin(t * 4);
    g.save();
    g.shadowColor = color;
    g.shadowBlur = 10 * pulse;
    roundRect(g, x - w / 2, y, w, h, h / 2);
    g.fillStyle = "rgba(8,6,8,0.92)"; g.fill();
    g.lineWidth = 1.5; g.strokeStyle = color; g.globalAlpha = 0.5 + 0.5 * pulse; g.stroke();
    g.globalAlpha = 1; g.shadowBlur = 0;
    g.fillStyle = color;
    g.fillText(label, x, y + h / 2 + 0.5);
    g.restore();
  }

  private drawRain(g: CanvasRenderingContext2D, dt: number) {
    g.strokeStyle = "rgba(170,200,255,0.25)";
    g.lineWidth = 1;
    g.beginPath();
    for (const d of this.rain) {
      d.y = (d.y + d.v * dt * 1.4) % 1;
      const x = d.x * this.vw, y = d.y * this.vh;
      g.moveTo(x, y); g.lineTo(x - 3, y + 10);
    }
    g.stroke();
  }

  private drawBubble(g: CanvasRenderingContext2D, a: AgentView, t: number) {
    const s = this.toScreen(a.x, a.y - (FEET - HEAD_TOP) - 3);   // just over its head
    if (s.x < -40 || s.y < -40 || s.x > this.vw + 40 || s.y > this.vh + 40) return;
    const scale = Math.min(1.1, Math.max(0.8, this.zoom / 2));
    const bob = isActive(a) ? Math.sin(t * 2 + a.x) * 1.5 : 0;   // a waiting agent's bubble stays still too
    let label = "";
    let color = STATUS_COLOR[a.status];
    let text = color;   // the label's colour (a lead keeps its rose border and says its side in green or red)
    if (a.lead) {
      color = LEAD_COLOR;
      const p = a.position;
      label = p ? `${p.side === "long" ? "LONG" : "SHORT"} ${ticker(p.market)}` : `${Math.round(a.lead.city ?? a.lead.score ?? 0)}`;   // the star is its icon
      text = p ? (p.side === "long" ? "#4efab0" : "#f43f5e") : LEAD_COLOR;
    } else if (a.status === "in_trade" && a.position) {
      const r = a.position.rOpen;
      // positions in several markets: it stands at one tower, so the bubble says which one it shows
      const many = new Set((a.real?.positions ?? []).map((p) => p.market)).size > 1;
      label = `${many ? `${a.position.market.replace("-USD", "")} ` : ""}${r >= 0 ? "+" : "−"}${Math.abs(r).toFixed(1)}R`;
      color = r >= 0 ? "#4efab0" : "#f43f5e";
    } else if (a.status === "exiting" && a.trades[0]) {
      const r = a.trades[0].r;
      label = `${r > 0 ? "+" : "−"}${Math.abs(r).toFixed(1)}R`;
      color = r > 0 ? "#4efab0" : "#f43f5e";
    } else if (a.real && (readingNews(a) || (a.status === "waiting" && atWork(a))) && this.o.getJobLabel?.(a)) {
      label = this.o.getJobLabel(a)!;                     // at work, or at the News Tower: the real data it reads there
    } else if (a.real && a.status === "waiting") {
      label = countdown(a.real.nextCheck - Date.now());   // real schedule: next 4h candle close
    } else if (a.real && a.status === "analyzing") {
      // it checks every market it trades: the bubble goes through them (one at a time, n of N)
      const ms = a.markets, n = ms.length;
      const i = n > 1 && !this.o.reducedMotion ? Math.floor(performance.now() / 1300) % n : Math.max(0, ms.indexOf(a.focus));
      label = `${(ms[i] ?? a.focus).replace("-USD", "")}${n > 1 ? ` ${i + 1}/${n}` : ""}`;
    }
    const iw = 16 * scale, h = 17 * scale;
    g.font = `700 ${Math.round(10 * scale)}px "IBM Plex Mono", monospace`;
    const tw = label ? g.measureText(label).width + 4 * scale : 0;
    const w = iw + tw + 4 * scale;
    const x = s.x - w / 2;
    const isSel = this.selected?.kind === "agent" && this.selected.id === a.id;
    const isReal = this.few && !a.lead;   // small city: names always on, bubbles never reduced to a dot
    // the name tag (selected, real, hovered or close zoom) is measured first so bubble + tag are placed as one block
    // a lead carries its name (with a LEAD mark) when selected, hovered or zoomed in: the city's own agents keep theirs on
    const named = isSel || isReal || a.id === this.hovered || this.zoom >= 2.8;
    const tag = a.lead ? "LEAD" : "";
    const tagFont = `700 ${Math.round(8 * scale)}px "IBM Plex Mono", monospace`, nameFont = `600 ${Math.round(10 * scale)}px "IBM Plex Sans", sans-serif`;
    g.font = tagFont;
    const tagW = tag ? g.measureText(tag).width + 6 : 0;
    g.font = nameFont;
    const nw = named ? g.measureText(a.name).width + 10 + tagW : 0, nh = named ? 13 * scale : 0, nx = s.x - nw / 2;
    const rects = (yy: number) => named ? [{ x, y: yy, w, h }, { x: nx, y: yy - nh - 3, w: nw, h: nh }] : [{ x, y: yy, w, h }];
    const hit = (yy: number) => rects(yy).some((q) => this.placed.some((r) => q.x < r.x + r.w && q.x + q.w > r.x && q.y < r.y + r.h && q.y + q.h > r.y));
    const y0 = s.y - h + bob;
    let y = y0;
    if (!isSel && hit(y)) {
      if (isReal) {   // a real agent is never reduced to a dot: its block climbs until it is free
        for (let k = 0; k < 4 && hit(y); k++) y -= h + nh + 6;
      } else {
        const up = y - h - 3;
        if (!hit(up) && this.zoom >= 1.8) y = up;
        else {   // no room: a small status dot keeps the agent readable
          g.fillStyle = color;
          g.beginPath(); g.arc(s.x, s.y - 3, 2.5, 0, Math.PI * 2); g.fill();
          return;
        }
      }
    }
    for (const q of rects(y)) this.placed.push(q);
    if (y < y0 - 1) {   // lifted: a leader line keeps it tied to its agent
      g.strokeStyle = color; g.globalAlpha = 0.55; g.lineWidth = 1;
      g.beginPath(); g.moveTo(s.x, y + h + 4 * scale); g.lineTo(s.x, s.y - 1); g.stroke();
      g.globalAlpha = 1;
    }
    g.fillStyle = "rgba(8,12,14,0.9)";
    g.strokeStyle = color;
    g.lineWidth = 1;
    roundRect(g, x, y, w, h, 5 * scale);
    g.fill(); g.stroke();
    g.beginPath(); g.moveTo(s.x - 3 * scale, y + h - 0.5); g.lineTo(s.x, y + h + 4 * scale); g.lineTo(s.x + 3 * scale, y + h - 0.5); g.closePath();
    g.fillStyle = "rgba(8,12,14,0.9)"; g.fill();
    if (a.lead && !a.position) drawStar(g, x + 2 * scale, y, iw, h, color);
    else drawIcon(g, a, x + 2 * scale, y, iw, h, text);
    if (label) { g.fillStyle = text; g.textBaseline = "middle"; g.textAlign = "left"; g.fillText(label, x + iw + 2 * scale, y + h / 2 + 0.5); }
    if (named) {
      // real agents always carry their name, with a LIVE mark
      const ny = y - nh - 3;
      g.fillStyle = isSel ? (a.lead ? LEAD_COLOR : "#4efab0") : "rgba(8,12,14,0.92)";
      roundRect(g, nx, ny, nw, nh, 4); g.fill();
      if (isReal && !isSel) { g.strokeStyle = "rgba(78,250,176,0.7)"; g.lineWidth = 1; roundRect(g, nx + 0.5, ny + 0.5, nw - 1, nh - 1, 4); g.stroke(); }
      g.textBaseline = "middle";
      if (tag) {
        g.fillStyle = isSel ? "#000" : a.lead ? LEAD_COLOR : "#4efab0";
        g.font = tagFont;
        g.textAlign = "left";
        g.fillText(tag, nx + 5, ny + nh / 2 + 0.5);
      }
      g.font = nameFont;
      g.fillStyle = isSel ? "#000" : "#fff";
      g.textAlign = "left";
      g.fillText(a.name, nx + 5 + tagW, ny + nh / 2 + 0.5);
    }
  }
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath();
  g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

/** A lead holding nothing right now: a star (its bubble shows its Strike City score). */
function drawStar(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, color: string) {
  const cx = x + w / 2, cy = y + h / 2, k = w / 18;
  g.save();
  g.fillStyle = color;
  g.beginPath();
  for (let i = 0; i < 10; i++) {
    const r = (i % 2 ? 2.6 : 6) * k, an = -Math.PI / 2 + (i * Math.PI) / 5;
    if (i) g.lineTo(cx + Math.cos(an) * r, cy + Math.sin(an) * r); else g.moveTo(cx + Math.cos(an) * r, cy + Math.sin(an) * r);
  }
  g.closePath(); g.fill();
  g.restore();
}

/** Status glyphs, shared by the map bubbles and the legend (drawn on small canvases). */
export function drawIcon(g: CanvasRenderingContext2D, a: Pick<AgentView, "status" | "position">, x: number, y: number, w: number, h: number, color: string) {
  const cx = x + w / 2, cy = y + h / 2, k = w / 18;
  g.save();
  g.strokeStyle = color; g.fillStyle = color; g.lineWidth = 1.6 * k; g.lineCap = "round"; g.lineJoin = "round";
  g.beginPath();
  switch (a.status) {
    case "analyzing":   // chart line
      g.moveTo(cx - 6 * k, cy + 4 * k); g.lineTo(cx - 2 * k, cy); g.lineTo(cx + 1 * k, cy + 2 * k); g.lineTo(cx + 6 * k, cy - 4 * k); g.stroke(); break;
    case "waiting":     // hourglass
      g.moveTo(cx - 4 * k, cy - 5 * k); g.lineTo(cx + 4 * k, cy - 5 * k); g.lineTo(cx - 4 * k, cy + 5 * k); g.lineTo(cx + 4 * k, cy + 5 * k); g.closePath(); g.stroke(); break;
    case "signal":      // lightning
    case "entering":
      g.moveTo(cx + 1 * k, cy - 6 * k); g.lineTo(cx - 4 * k, cy + 1 * k); g.lineTo(cx, cy + 1 * k); g.lineTo(cx - 1 * k, cy + 6 * k); g.lineTo(cx + 4 * k, cy - 1 * k); g.lineTo(cx, cy - 1 * k); g.closePath(); g.fill(); break;
    case "risk":        // shield
      g.moveTo(cx, cy - 6 * k); g.lineTo(cx + 5 * k, cy - 4 * k); g.lineTo(cx + 4 * k, cy + 2 * k); g.lineTo(cx, cy + 6 * k); g.lineTo(cx - 4 * k, cy + 2 * k); g.lineTo(cx - 5 * k, cy - 4 * k); g.closePath(); g.stroke(); break;
    case "in_trade": {  // arrow up (long) or down (short)
      const up = a.position?.side !== "short";
      if (up) { g.moveTo(cx, cy - 6 * k); g.lineTo(cx + 5 * k, cy); g.lineTo(cx - 5 * k, cy); g.closePath(); g.fill(); g.fillRect(cx - 1.5 * k, cy, 3 * k, 6 * k); }
      else { g.moveTo(cx, cy + 6 * k); g.lineTo(cx + 5 * k, cy); g.lineTo(cx - 5 * k, cy); g.closePath(); g.fill(); g.fillRect(cx - 1.5 * k, cy - 6 * k, 3 * k, 6 * k); }
      break;
    }
    case "exiting":     // coin
      g.arc(cx, cy, 5 * k, 0, Math.PI * 2); g.stroke(); g.beginPath(); g.moveTo(cx, cy - 3 * k); g.lineTo(cx, cy + 3 * k); g.stroke(); break;
    case "unfunded":    // an empty wallet waiting for its deposit: a "$" sign
      g.font = `700 ${Math.round(11 * k)}px "IBM Plex Mono", monospace`; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("$", cx, cy + 0.5); break;
    case "paused":      // Zz
      g.font = `700 ${Math.round(10 * k)}px "IBM Plex Mono", monospace`; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("Zz", cx, cy + 0.5); break;
    case "offline":     // unplugged: a broken link
      g.moveTo(cx - 6 * k, cy + 2 * k); g.lineTo(cx - 2 * k, cy - 2 * k); g.moveTo(cx + 2 * k, cy + 2 * k); g.lineTo(cx + 6 * k, cy - 2 * k);
      g.moveTo(cx - 1 * k, cy - 5 * k); g.lineTo(cx + 1 * k, cy + 5 * k); g.stroke(); break;
  }
  g.restore();
}
