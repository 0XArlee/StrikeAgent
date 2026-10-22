// Inside the News Tower: one floor per kind of news (tower.ts), drawn on a canvas with the screens writing the live
// news on them, and your agent walking by itself to whatever you choose to look at (it takes the lift between floors).
// What it looks at opens beside the scene. Only on this page: the agent keeps trading on Strike as usual, and the
// rest of the city does not see it here.
import { useEffect, useRef, useState } from "react";
import type { Lang } from "../i18n";
import type { AgentView } from "./agents";
import { countdown, forMarket, type NewsDoc, type NewsItem } from "./news";
import { EventsList, Headline, MARKETS, ReadingBlock, ScoreBox, signed, sideOf } from "./NewsView";
import { drawFrame, lookFor, onSheet, sheetOf, type Anim, type Dir } from "./sprites";
import { ticker, type CityText } from "./text";
import {
  EXCHANGES, FLOORS, ROOMS, ROOM_H, ROOM_W, TILE, alarmOf, byRegion, exchangeNow, floor, pushOf, roomArt, roomPath, storiesOf,
  type RoomId, type SpotDef,
} from "./tower";

type Doc = NewsDoc | null | "none" | "error";
const ART_W = ROOM_W * TILE, ART_H = ROOM_H * TILE;
const SPEED = 96;                       // art px per second (a brisk walk: a floor is crossed in 3 s)
const UP = "#4ade80", DOWN = "#f87171", AMBER = "#fbbf24", CYAN = "#5eead4", CREAM = "#f3e3c2", DIM = "#7c8599";
const FIRST = 8;
const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const tone = (v: number | null | undefined) => (v == null || Math.abs(v) < 0.5 ? DIM : v > 0 ? UP : DOWN);

interface Walker { x: number; y: number; dir: Dir; path: [number, number][]; then?: () => void }
interface Ride { to: RoomId; t0: number; switched: boolean }

// ------------------------------------------------------------------ LED boards: text as dots, cached per string
const LED_FONT = `600 8px "IBM Plex Mono", monospace`;
const bitmaps = new Map<string, { w: number; bits: Uint8Array }>();
const boards = new Map<string, HTMLCanvasElement>();
if (typeof document !== "undefined") void document.fonts?.ready.then(() => { bitmaps.clear(); boards.clear(); });

function bitmap(text: string) {
  let b = bitmaps.get(text);
  if (b) return b;
  const c = document.createElement("canvas");
  let g = c.getContext("2d")!;
  g.font = LED_FONT;
  c.width = Math.max(1, Math.ceil(g.measureText(text).width) + 1); c.height = 8;
  g = c.getContext("2d")!;
  g.font = LED_FONT; g.fillStyle = "#fff"; g.fillText(text, 0, 7);
  const d = g.getImageData(0, 0, c.width, 8).data, bits = new Uint8Array(c.width * 8);
  for (let i = 0; i < bits.length; i++) bits[i] = d[i * 4 + 3] > 110 ? 1 : 0;
  b = { w: c.width, bits };
  bitmaps.set(text, b);
  return b;
}

export type Seg = { t: string; c: string };
/** One line of LED text (segments in their colours), drawn once at the screen's scale with its glow. */
function board(segs: Seg[], k: number, pitch = 1): { im: HTMLCanvasElement; w: number; h: number } {
  const key = `${segs.map((s) => `${s.c}|${s.t}`).join("§")}@${k.toFixed(2)}/${pitch}`;
  const w = segs.reduce((n, s) => n + bitmap(s.t).w, 0) * pitch, h = 8 * pitch;
  let im = boards.get(key);
  if (!im) {
    if (boards.size > 90) boards.clear();
    const pad = Math.ceil(2 * k);
    const dots = document.createElement("canvas");
    dots.width = Math.ceil(w * k) + pad * 2; dots.height = Math.ceil(h * k) + pad * 2;
    const g = dots.getContext("2d")!;
    let x0 = 0;
    const s = Math.max(1, pitch * k * 0.78);
    for (const seg of segs) {
      const b = bitmap(seg.t);
      g.fillStyle = seg.c;
      for (let y = 0; y < 8; y++) for (let x = 0; x < b.w; x++) {
        if (b.bits[y * b.w + x]) g.fillRect(pad + (x0 + x) * pitch * k, pad + y * pitch * k, s, s);
      }
      x0 += b.w;
    }
    im = document.createElement("canvas");
    im.width = dots.width; im.height = dots.height;
    const f = im.getContext("2d")!;
    f.shadowColor = segs[0]?.c ?? AMBER; f.shadowBlur = 1.6 * k;
    f.globalAlpha = 0.4; f.drawImage(dots, 0, 0);
    f.shadowBlur = 0; f.globalAlpha = 1; f.drawImage(dots, 0, 0);
    boards.set(key, im);
  }
  return { im, w, h };
}

/** Draw a LED line at (x, y) in art px; with `scroll`, it runs right to left inside the box [x, x + boxW). */
export function led(g: CanvasRenderingContext2D, k: number, segs: Seg[], x: number, y: number, opt: { pitch?: number; boxW?: number; t?: number; align?: "left" | "center" | "right" } = {}) {
  if (!segs.length || !segs.some((s) => s.t)) return;
  const { im, w } = board(segs, k, opt.pitch ?? 1);
  const pad = Math.ceil(2 * k) / k;
  const dw = im.width / k, dh = im.height / k;
  if (opt.boxW != null && w > opt.boxW && opt.t != null) {
    const gap = 24, span = w + gap, off = (opt.t * 22) % span;
    g.save(); g.beginPath(); g.rect(x, y - 2, opt.boxW, dh); g.clip();
    g.drawImage(im, x - off - pad, y - pad, dw, dh);
    g.drawImage(im, x - off + span - pad, y - pad, dw, dh);
    g.restore();
    return;
  }
  const bx = opt.boxW != null && opt.align === "center" ? x + (opt.boxW - w) / 2 : opt.boxW != null && opt.align === "right" ? x + opt.boxW - w : x;
  g.drawImage(im, bx - pad, y - pad, dw, dh);
}

export function txt(g: CanvasRenderingContext2D, s: string, x: number, y: number, size: number, color: string, align: CanvasTextAlign = "left", weight = 700) {
  g.font = `${weight} ${size}px "IBM Plex Mono", monospace`;
  g.fillStyle = color; g.textAlign = align; g.textBaseline = "alphabetic";
  g.fillText(s, x, y);
}

const up = (s: string) => s.toLocaleUpperCase();
const lower = (s: string, lang: Lang) => s.charAt(0).toLocaleLowerCase(lang === "es" ? "es-ES" : "en-US") + s.slice(1);
export const plain = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "");   // the LED font has no accents to spare

// ------------------------------------------------------------------ the component
export function TowerView({ T, lang, doc, agent, market0, onExit }:
  { T: CityText; lang: Lang; doc: Doc; agent: AgentView | null; market0: string; onExit: () => void }) {
  const W = T.tower, N = T.news;
  const [room, setRoom] = useState<RoomId>("lobby");
  const [spot, setSpot] = useState<string>(floor("lobby").first);
  const [market, setMarket] = useState(MARKETS.includes(market0) ? market0 : "BTC-USD");
  const [arrived, setArrived] = useState(!agent);
  const [riding, setRiding] = useState(false);
  const [now, setNow] = useState(Date.now);
  const canvas = useRef<HTMLCanvasElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const exitBtn = useRef<HTMLButtonElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLElement>(null);
  const toPanel = () => {
    const r = root.current, p = panel.current, s = stage.current;
    if (!r || !p || !s || window.innerWidth > 1000) return;
    requestAnimationFrame(() => r.scrollTo({ top: Math.max(0, p.offsetTop - s.offsetHeight - 8), behavior: reduced ? "auto" : "smooth" }));
  };
  const me = useRef<Walker | null>(null);
  const ride = useRef<Ride | null>(null);
  const hover = useRef<string | null>(null);
  const live = useRef({ room, spot, market, doc, arrived, lang });
  live.current = { room, spot, market, doc, arrived, lang };
  const fl = floor(room), data = ROOMS[room];
  const def = fl.spots.find((s) => s.id === spot) ?? fl.spots[0];
  const d = doc && typeof doc === "object" ? doc : null;
  const name = agent?.name ?? "";

  useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 15_000); return () => window.clearInterval(id); }, []);
  useEffect(() => { exitBtn.current?.focus({ preventScroll: true }); }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onExit(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onExit]);

  // ---- the agent comes in through the door and goes to the video wall
  useEffect(() => {
    if (!agent) return;
    const first = ROOMS.lobby.spots[floor("lobby").first];
    me.current = { x: 13 * TILE + 8, y: ROOM_H * TILE + 6, dir: "up", path: [] };
    walkTo(first.stand[0], first.stand[1], first.face, () => setArrived(true), [13, ROOM_H - 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function walkTo(tx: number, ty: number, face: Dir, then?: () => void, from?: [number, number]) {
    const w = me.current;
    if (!w) { then?.(); return; }
    const sx = from?.[0] ?? Math.floor(w.x / TILE), sy = from?.[1] ?? Math.min(ROOM_H - 1, Math.floor((w.y - 1) / TILE));
    const path = roomPath(ROOMS[live.current.room], sx, sy, tx, ty);
    if (from) path.unshift(from);
    if (reduced || (!path.length && (sx !== tx || sy !== ty))) {
      w.x = tx * TILE + 8; w.y = ty * TILE + 15; w.dir = face; w.path = []; then?.();
      return;
    }
    w.path = path;
    w.then = () => { w.dir = face; then?.(); };
  }

  /** Choose what to look at: the panel shows it at once, the agent walks there. */
  function choose(s: SpotDef) {
    if (ride.current) return;
    if (s.kind === "exit") {
      const st = data.spots[s.id];
      if (!me.current) { onExit(); return; }
      setSpot(s.id); setArrived(false);
      walkTo(st.stand[0], st.stand[1], "down", () => { me.current!.path = [[13, ROOM_H - 1]]; me.current!.then = onExit; });
      return;
    }
    setSpot(s.id);
    setArrived(!me.current);
    if (s.kind !== "lift") toPanel();
    const st = data.spots[s.id];
    walkTo(st.stand[0], st.stand[1], st.face, () => setArrived(true));
  }

  /** To another floor: walk to the lift, the doors close, the floor changes, the doors open. */
  function goFloor(to: RoomId) {
    if (ride.current || to === room) return;
    setRiding(true); setArrived(false); setSpot("lift");
    toPanel();
    const start = () => {
      if (reduced) { arrive(to); return; }
      ride.current = { to, t0: performance.now(), switched: false };
    };
    const lift = data.spots.lift;
    if (me.current) walkTo(lift.stand[0], lift.stand[1], "up", start); else start();
  }
  function arrive(to: RoomId) {
    const f = floor(to), lift = ROOMS[to].spots.lift, first = ROOMS[to].spots[f.first];
    live.current.room = to;
    setRoom(to); setSpot(f.first); setRiding(false);
    if (me.current) {
      me.current.x = lift.stand[0] * TILE + 8; me.current.y = lift.stand[1] * TILE + 15; me.current.dir = "down"; me.current.path = [];
      walkTo(first.stand[0], first.stand[1], first.face, () => setArrived(true));
    } else setArrived(true);
  }

  // ---- the scene: size, input and the drawing loop
  useEffect(() => {
    const c = canvas.current, box = stage.current;
    if (!c || !box) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    let k = 1;
    const fit = () => {
      // desktop: the scene fits the space beside the panel; phones and narrow windows: the width, the page scrolls
      const maxW = box.clientWidth, maxH = window.innerWidth > 1000 ? box.clientHeight : Infinity;
      k = Math.max(0.5, Math.min(maxW, maxH * 2) * dpr / ART_W);
      c.width = Math.round(ART_W * k); c.height = Math.round(ART_H * k);
      c.style.width = `${c.width / dpr}px`; c.style.height = `${c.height / dpr}px`;
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(box);

    const images = new Map<RoomId, HTMLImageElement>();
    for (const f of FLOORS) { const im = new Image(); im.decoding = "async"; im.src = roomArt(f.id); images.set(f.id, im); }
    // the room at a whole number of pixels per art pixel (crisp), drawn down smoothly to the canvas' size: a pixel art
    // picture at any size without uneven pixels
    let bg: { room: RoomId; k: number; c: HTMLCanvasElement } | null = null;
    const backdrop = (room: RoomId): HTMLCanvasElement | null => {
      const im = images.get(room);
      if (!im?.complete || !im.naturalWidth) return null;
      const whole = Math.max(1, Math.ceil(k - 0.01));
      if (bg && bg.room === room && bg.k === whole) return bg.c;
      const off = document.createElement("canvas");
      off.width = ART_W * whole; off.height = ART_H * whole;
      const og = off.getContext("2d")!;
      og.imageSmoothingEnabled = false;
      og.drawImage(im, 0, 0, off.width, off.height);
      bg = { room, k: whole, c: off };
      return off;
    };
    const toArt = (e: PointerEvent) => { const r = c.getBoundingClientRect(); return { x: ((e.clientX - r.left) / r.width) * ART_W, y: ((e.clientY - r.top) / r.height) * ART_H }; };
    const hit = (x: number, y: number) => {
      const rd = ROOMS[live.current.room];
      for (const s of floor(live.current.room).spots) {
        const sp = rd.spots[s.id];
        const [rx, ry, rw, rh] = sp.rect;
        const inRect = x >= rx - 3 && x <= rx + rw + 3 && y >= ry - 3 && y <= ry + rh + 3;
        const onStand = Math.floor(x / TILE) === sp.stand[0] && Math.floor(y / TILE) === sp.stand[1];
        if (inRect || onStand) return s;
      }
      return null;
    };
    const move = (e: PointerEvent) => { const p = toArt(e), s = hit(p.x, p.y); hover.current = s?.id ?? null; c.style.cursor = s ? "pointer" : "default"; };
    const click = (e: PointerEvent) => { const p = toArt(e), s = hit(p.x, p.y); if (s) pick.current(s); };
    const leave = () => { hover.current = null; };
    c.addEventListener("pointermove", move);
    c.addEventListener("pointerup", click);
    c.addEventListener("pointerleave", leave);

    const g = c.getContext("2d")!;
    let raf = 0, last = performance.now();
    const t0 = last;
    const phase = (s: string) => (s.split("").reduce((a, ch) => a + ch.charCodeAt(0), 0) % 97) / 9.7;
    const frame = (ms: number) => {
      raf = requestAnimationFrame(frame);
      if (document.hidden) return;
      const dt = Math.min(0.05, (ms - last) / 1000); last = ms;
      const t = reduced ? 0 : (ms - t0) / 1000;
      const L = live.current;
      // the lift ride: the doors close, dark, the new floor, the doors open
      const rr = ride.current;
      let dark = 0, doors = 0;
      if (rr) {
        const e = ms - rr.t0;
        doors = Math.min(1, e / 420);
        dark = e < 420 ? 0 : e < 760 ? (e - 420) / 340 : e < 1100 ? 1 - (e - 760) / 340 : 0;
        if (e >= 760 && !rr.switched) { rr.switched = true; arriveRef.current(rr.to); }
        if (e >= 760) doors = Math.max(0, 1 - (e - 760) / 380);
        if (e >= 1140) ride.current = null;
      }
      // the agent walks
      const w = me.current;
      if (w && w.path.length) {
        const [tx, ty] = w.path[0];
        const gx = tx * TILE + 8, gy = ty * TILE + 15;
        const dx = gx - w.x, dy = gy - w.y, dist = Math.hypot(dx, dy), step = SPEED * dt;
        w.dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
        if (dist <= step) { w.x = gx; w.y = gy; w.path.shift(); if (!w.path.length) { const f = w.then; w.then = undefined; f?.(); } }
        else { w.x += (dx / dist) * step; w.y += (dy / dist) * step; }
      }

      g.setTransform(1, 0, 0, 1, 0, 0);
      g.fillStyle = "#05060a"; g.fillRect(0, 0, c.width, c.height);
      const back = backdrop(L.room);
      if (back) { g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high"; g.drawImage(back, 0, 0, c.width, c.height); }
      g.setTransform(k, 0, 0, k, 0, 0);
      g.imageSmoothingEnabled = false;
      const rd = ROOMS[L.room];
      overlay(g, k, L.room, rd, L.doc, L.market, t, Date.now(), T, L.lang);
      // the lift's floor indicator, on every floor
      const li = rd.screens.lift;
      if (li) led(g, k, [{ t: W.floorShort(floor(L.room).n), c: "#ff5a4f" }], li[0], li[1] + 0.5, { pitch: 0.55, boxW: li[2], align: "center" });

      // what can be looked at: a marker above each thing, the hovered one outlined
      const col = floor(L.room).color;
      for (const s of floor(L.room).spots) {
        const sp = rd.spots[s.id];
        const [rx, ry, rw, rh] = sp.rect;
        const on = s.id === hover.current, sel = s.id === L.spot;
        if (on || sel) {
          g.save();
          g.globalAlpha = sel ? 0.55 + 0.25 * Math.sin(t * 4) : 0.9;
          g.strokeStyle = col; g.lineWidth = 1;
          g.strokeRect(rx - 1.5, ry - 1.5, rw + 3, rh + 3);
          g.restore();
        }
        if (!sel) {
          const mx = rx + rw / 2, my = Math.max(5, ry - 4) + Math.sin(t * 3 + rx) * 1.2;
          g.fillStyle = col; g.globalAlpha = on ? 1 : 0.85;
          g.beginPath(); g.moveTo(mx, my - 3); g.lineTo(mx + 2.5, my); g.lineTo(mx, my + 3); g.lineTo(mx - 2.5, my); g.closePath(); g.fill();
          g.globalAlpha = 1;
        }
        if (on) {
          const label = W.spots[s.label ?? s.id] ?? s.id;
          g.font = `600 6px "IBM Plex Sans", sans-serif`;
          const tw = g.measureText(label).width + 8, lx = Math.min(ART_W - tw - 2, Math.max(2, rx + rw / 2 - tw / 2)), ly = Math.min(ART_H - 12, ry + rh + 4);
          g.fillStyle = "rgba(5,6,10,.88)"; g.fillRect(lx, ly, tw, 10);
          g.fillStyle = "#fff"; g.textAlign = "left"; g.fillText(label, lx + 4, ly + 7.3);
        }
      }

      // people, back to front: the staff and your agent
      const people: { x: number; y: number; draw: () => void }[] = rd.staff.map((p) => ({
        x: p.x * TILE + 8, y: p.y * TILE + 15,
        draw: () => { const sh = sheetOf(lookFor(p.seed)); if (sh) drawFrame(g, sh, p.anim as Anim, p.dir, t + phase(p.seed), p.x * TILE + 8, p.y * TILE + 15); },
      }));
      if (w && w.y <= ART_H + 8) {
        const sh = sheetOf(agentLook.current!);
        people.push({ x: w.x, y: w.y, draw: () => {
          g.fillStyle = "rgba(0,0,0,.35)"; g.beginPath(); g.ellipse(w.x, w.y, 5, 1.8, 0, 0, Math.PI * 2); g.fill();
          if (sh) drawFrame(g, sh, w.path.length ? "walk" : "idle", w.dir, t, w.x, w.y);
          else { g.fillStyle = col; g.beginPath(); g.arc(w.x, w.y - 8, 4, 0, Math.PI * 2); g.fill(); }
        } });
      }
      people.sort((a, b) => a.y - b.y).forEach((p) => p.draw());
      if (w && L.arrived && !rr) bubble(g, w.x, w.y - 26, sayRef.current);
      if (w) {   // its name, small, under its feet
        g.font = `700 5px "IBM Plex Mono", monospace`; g.textAlign = "center";
        const nw = g.measureText(nameRef.current).width + 6;
        g.fillStyle = "rgba(5,6,10,.75)"; g.fillRect(w.x - nw / 2, w.y + 2, nw, 7);
        g.fillStyle = col; g.fillText(nameRef.current, w.x, w.y + 7.4);
      }
      // the ride: the lift doors close over the scene's lift, then dark
      if (doors > 0) {
        const lr = rd.spots.lift.rect;
        g.fillStyle = "#9aa3b5";
        const half = (lr[2] / 2) * doors;
        g.fillRect(lr[0], lr[1] + 2, half, lr[3] - 2); g.fillRect(lr[0] + lr[2] - half, lr[1] + 2, half, lr[3] - 2);
      }
      if (dark > 0) { g.fillStyle = `rgba(3,4,8,${dark})`; g.fillRect(0, 0, ART_W, ART_H); }
    };
    raf = requestAnimationFrame(frame);
    const off = onSheet(() => { /* the next frame draws it */ });
    return () => {
      cancelAnimationFrame(raf); ro.disconnect(); off();
      c.removeEventListener("pointermove", move); c.removeEventListener("pointerup", click); c.removeEventListener("pointerleave", leave);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // the loop reads the latest handlers and texts through refs
  const pick = useRef(choose); pick.current = choose;
  const arriveRef = useRef(arrive); arriveRef.current = arrive;
  const agentLook = useRef(agent ? agent.look ?? lookFor(agent.id) : null); agentLook.current = agent ? agent.look ?? lookFor(agent.id) : null;
  const nameRef = useRef(name); nameRef.current = name;
  const sayRef = useRef(""); sayRef.current = say(def, d, market, now, T, lang);

  const pushTxt = (v: number | null) => (v == null ? "—" : signed(v, lang));
  return (
    <div ref={root} className="tw" role="dialog" aria-modal="true" aria-labelledby="tw-title" style={{ ["--room" as string]: fl.color }}>
      <header className="tw-top">
        <div className="tw-head">
          <h2 id="tw-title"><span className="tw-badge num">{W.floorShort(fl.n)}</span>{W.floors[room].name}</h2>
          <p className="tw-about">{W.title} · {W.floors[room].about}</p>
        </div>
        <div className="tw-markets" role="group" aria-label={W.market}>
          {MARKETS.map((m) => {
            const v = d?.markets[m]?.net ?? null;
            return <button key={m} type="button" aria-pressed={m === market} onClick={() => setMarket(m)}>
              {ticker(m)}{v != null && <span className={`num ${sideOf(v)}`}>{signed(v, lang)}</span>}</button>;
          })}
        </div>
        <button ref={exitBtn} type="button" className="btn btn-ghost tw-exit" onClick={onExit}><span aria-hidden="true">←</span> {W.exit}</button>
      </header>

      <div className="tw-main">
        <div className="tw-scene">
          <div className="tw-stage" ref={stage}>
            <canvas ref={canvas} aria-hidden="true" />
            {riding && <p className="sr-only" role="status">{W.goFloor(W.floors[room].name)}</p>}
          </div>
          <div className="tw-spots" role="group" aria-label={W.floors[room].name}>
            {fl.spots.map((s) => (
              <button key={s.id} type="button" aria-pressed={s.id === spot} disabled={riding} onClick={() => choose(s)}>{W.spots[s.label ?? s.id]}</button>
            ))}
          </div>
          <nav className="tw-floors" aria-label={W.floorsTitle}>
            {FLOORS.map((f) => {
              const p = d && f.cats.length ? pushOf(d, market, f.cats) : null;
              return (
                <button key={f.id} type="button" aria-current={f.id === room ? "location" : undefined} disabled={riding} onClick={() => goFloor(f.id)}
                        style={{ ["--fc" as string]: f.color }}>
                  <span className="tw-fn num">{W.floorShort(f.n)}</span>
                  <span className="tw-fname">{W.floors[f.id].name}</span>
                  {p && p.push != null && p.n > 0 && <span className={`tw-fpush num ${sideOf(p.push * 4)}`}>{pushTxt(p.push)}</span>}
                </button>
              );
            })}
          </nav>
          <p className="tw-note small faint">{agent ? W.onlyYou : W.visitor}</p>
        </div>

        <section ref={panel} className="tw-panel" aria-labelledby="tw-spot-title">
          <h3 id="tw-spot-title">{W.spots[def.label ?? def.id]}</h3>
          {agent && !arrived && !riding && def.kind !== "exit" && <p className="tw-going small" role="status">{W.going(name, lower(W.spots[def.label ?? def.id], lang))}</p>}
          {!d ? <p className="news-state" role="status">{doc === null ? N.loading : doc === "none" ? N.empty : N.error}</p>
            : <SpotBody key={`${room}:${def.id}`} T={T} lang={lang} doc={d} def={def} room={room} market={market} now={now}
                        onMarket={setMarket} onFloor={goFloor} onExit={onExit} />}
        </section>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ what a spot shows beside the scene
function SpotBody({ T, lang, doc, def, room, market, now, onMarket, onFloor, onExit }:
  { T: CityText; lang: Lang; doc: NewsDoc; def: SpotDef; room: RoomId; market: string; now: number; onMarket: (m: string) => void;
    onFloor: (r: RoomId) => void; onExit: () => void }) {
  const W = T.tower, N = T.news;
  const [all, setAll] = useState(false);
  const [region, setRegion] = useState<string | null>(null);
  const list = (items: NewsItem[]) => (
    <>
      {items.length ? <ul className="tw-list">{(all ? items : items.slice(0, FIRST)).map((h) => <Headline key={h.id} T={T} lang={lang} h={h} now={now} />)}</ul>
        : <p className="small muted">{W.noStories}</p>}
      {!all && items.length > FIRST && <button type="button" className="btn btn-ghost btn-block" onClick={() => setAll(true)}>{W.more} ({items.length - FIRST})</button>}
    </>
  );
  const floorsList = (
    <ul className="tw-floorlist">
      {FLOORS.filter((f) => f.cats.length).map((f) => {
        const p = pushOf(doc, market, f.cats);
        return (
          <li key={f.id} style={{ ["--fc" as string]: f.color }}>
            <div className="grow">
              <p className="tw-fl-name"><span className="num">{W.floorShort(f.n)}</span> {W.floors[f.id].name}</p>
              <p className="small muted">{W.floors[f.id].about}</p>
              <p className="small"><span className="faint">{W.push(ticker(market))}: </span>
                <b className={`num ${p.push == null ? "" : sideOf(p.push * 4)}`}>{p.push == null || !p.n ? W.pushNone : signed(p.push, lang)}</b>
                {p.n > 0 && <span className="faint"> · {W.stories(p.n)}</span>}</p>
            </div>
            {f.id === room ? <span className="tw-here small">{W.here}</span>
              : <button type="button" className="btn btn-ghost" aria-label={W.goFloor(W.floors[f.id].name)} onClick={() => onFloor(f.id)}>{W.go}</button>}
          </li>
        );
      })}
    </ul>
  );

  switch (def.kind) {
    case "reading":
      return <><p className="tw-hint">{W.hints.reading}</p><div className="news-read"><ReadingBlock T={T} lang={lang} doc={doc} market={market} /></div></>;
    case "wire":
      return <><p className="tw-hint">{W.hints.wire}</p>{list(forMarket(doc.headlines, market))}</>;
    case "scores":
      return (
        <>
          <p className="tw-hint">{W.hints.scores}</p>
          <div className="news-box"><ScoreBox T={T} doc={doc} market={market} /></div>
          <table className="tw-table">
            <caption className="sr-only">{W.scoreAll}</caption>
            <thead><tr><th scope="col">{W.market}</th><th scope="col">{W.hit}</th><th scope="col">{W.calls}</th></tr></thead>
            <tbody>{MARKETS.map((m) => {
              const b = doc.scoreboard[m];
              return <tr key={m} aria-current={m === market || undefined}><th scope="row"><button type="button" className="tw-linkbtn" onClick={() => onMarket(m)}>{ticker(m)}</button></th>
                <td className="num">{b?.called ? `${Math.round((b.hits / b.called) * 100)} %` : "—"}</td><td className="num">{b?.called ?? 0}</td></tr>;
            })}</tbody>
          </table>
        </>
      );
    case "topics":
      return <><p className="tw-hint">{W.hints.topics}</p>{floorsList}</>;
    case "lift":
      return <><p className="tw-hint">{W.hints.lift}</p>{floorsList}<button type="button" className="btn btn-ghost btn-block" onClick={() => onFloor("lobby")} disabled={room === "lobby"}>{W.floorShort(0)} · {W.floors.lobby.name}</button></>;
    case "events":
      return (
        <>
          <p className="tw-hint">{W.hints.events}</p>
          <div className="news-box"><EventsList T={T} lang={lang} doc={doc} now={now} max={room === "macro" ? 12 : 4} /></div>
          {room === "macro" && (
            <dl className="tw-evabout">{Object.keys(W.evAbout).map((k) => <div key={k}><dt className="num">{W.codes[k] ?? k}</dt><dd>{W.evAbout[k]}</dd></div>)}</dl>
          )}
          {room === "lobby" && <button type="button" className="btn btn-ghost btn-block" onClick={() => onFloor("macro")}>{W.goFloor(W.floors.macro.name)}</button>}
        </>
      );
    case "stories": {
      const cats = def.cats ?? [];
      const p = pushOf(doc, market, cats);
      return (
        <>
          <p className="tw-hint">{cats.map((c) => W.storyHints[c]).join(" ")}</p>
          <div className="tw-push">
            <span className="small faint">{W.push(ticker(market))}</span>
            <b className={`num ${p.push == null ? "" : sideOf(p.push * 4)}`}>{p.push == null || !p.n ? W.pushNone : signed(p.push, lang)}</b>
            {p.n > 0 && <span className="small faint">{W.stories(p.n)}</span>}
            <p className="small faint tw-push-note">{W.pushNote}</p>
          </div>
          <div className="tw-bymarket" role="group" aria-label={W.byMarket}>
            {MARKETS.map((m) => { const q = pushOf(doc, m, cats); return (
              <button key={m} type="button" aria-pressed={m === market} onClick={() => onMarket(m)}>
                <span>{ticker(m)}</span><span className={`num ${q.push == null ? "faint" : sideOf(q.push * 4)}`}>{q.push == null || !q.n ? "·" : signed(q.push, lang)}</span>
              </button>); })}
          </div>
          {list(storiesOf(doc, market, cats))}
        </>
      );
    }
    case "map": {
      const regions = byRegion(doc, market);
      const shown = region ? regions.find((r) => r.region === region) : null;
      const items = shown ? [...shown.geo, ...shown.other].sort((a, b) => b.t - a.t) : storiesOf(doc, market, ["geopolitics"]);
      return (
        <>
          <p className="tw-hint">{W.hints.map}</p>
          {regions.length ? (
            <div className="tw-regions" role="group" aria-label={W.allRegions}>
              <button type="button" aria-pressed={!region} onClick={() => { setRegion(null); setAll(false); }}>{W.allRegions}</button>
              {regions.map((r) => (
                <button key={r.region} type="button" aria-pressed={region === r.region} onClick={() => { setRegion(r.region); setAll(false); }}>
                  {W.regions[r.region] ?? r.region} <span className="num">{r.geo.length + r.other.length}</span>
                </button>
              ))}
            </div>
          ) : <p className="small muted">{W.mapEmpty}</p>}
          {list(items)}
        </>
      );
    }
    case "clocks":
      return (
        <>
          <p className="tw-hint">{W.hints.clocks}</p>
          <ul className="tw-clocks">{EXCHANGES.map((x) => {
            const s = exchangeNow(x, now);
            const left = countdown(s.minutes * 60_000, N.units);
            return <li key={x.id}><div className="grow"><p className="tw-fl-name">{W.clockCities[x.id]}</p><p className="small faint">{W.exchangesNames[x.id]}</p></div>
              <div className="tw-clock-r"><p className="num tw-clock-t">{s.time}</p><p className={`small ${s.open ? "pos" : "faint"}`}>{s.open ? W.open : W.closed} · {s.open ? W.closesIn(left) : W.opensIn(left)}</p></div></li>;
          })}</ul>
          <p className="small faint">{W.clockNote}</p>
        </>
      );
    case "exit":
      return <><p className="tw-hint">{W.hints.exit}</p><button type="button" className="btn btn-primary btn-block" onClick={onExit}>{W.exit}</button></>;
  }
  return null;
}

/** What the agent says once it is there: one short line from what it is looking at. */
function say(def: SpotDef, doc: NewsDoc | null, market: string, now: number, T: CityText, lang: Lang): string {
  const S = T.tower.say, N = T.news, tk = ticker(market);
  if (!doc) return "";
  switch (def.kind) {
    case "reading": { const rd = doc.markets[market]; return rd?.net != null && rd.label ? S.reading(tk, N.labels[rd.label], signed(rd.net, lang)) : S.readingNone(tk); }
    case "wire": return S.wire(forMarket(doc.headlines, market).length);
    case "scores": { const b = doc.scoreboard[market]; return b?.called ? S.scores(`${Math.round((b.hits / b.called) * 100)} %`) : S.scoresNone; }
    case "events": { const e = doc.events.next.find((x) => x.t > now); return e ? S.events(N.evShort[e.kind] ?? e.kind, N.inTime(countdown(e.t - now, N.units))) : S.eventsNone; }
    case "stories": { const p = pushOf(doc, market, def.cats ?? []); return S.stories(storiesOf(doc, market, def.cats ?? []).length, p.push == null ? "—" : `${tk} ${signed(p.push, lang)}`); }
    case "map": { const r = byRegion(doc, market)[0]; return r ? S.map(T.tower.regions[r.region] ?? r.region, r.geo.length + r.other.length) : S.mapNone; }
    case "clocks": return S.clocks(exchangeNow(EXCHANGES[0], now).open);
    case "topics": case "lift": return S.topics;
    default: return "";
  }
}

export function bubble(g: CanvasRenderingContext2D, x: number, y: number, s: string) {
  if (!s) return;
  g.font = `600 6px "IBM Plex Sans", sans-serif`;
  const w = Math.min(150, g.measureText(s).width + 8), h = 10;
  const bx = Math.max(2, Math.min(ART_W - w - 2, x - w / 2)), by = Math.max(2, y - h);
  g.fillStyle = "rgba(255,255,255,.96)";
  g.beginPath(); g.roundRect?.(bx, by, w, h, 3); if (!g.roundRect) g.rect(bx, by, w, h); g.fill();
  g.beginPath(); g.moveTo(x - 2, by + h); g.lineTo(x + 2, by + h); g.lineTo(x, by + h + 3); g.fill();
  g.fillStyle = "#0b0d12"; g.textAlign = "left"; g.textBaseline = "alphabetic";
  g.save(); g.beginPath(); g.rect(bx, by, w, h); g.clip(); g.fillText(s, bx + 4, by + 7.3); g.restore();
}

// ------------------------------------------------------------------ the screens of each floor
function overlay(g: CanvasRenderingContext2D, k: number, room: RoomId, rd: (typeof ROOMS)[RoomId], doc: Doc, market: string, t: number, now: number, T: CityText, lang: Lang) {
  const W = T.tower, N = T.news, S = rd.screens;
  const d = doc && typeof doc === "object" ? doc : null;
  const tk = ticker(market);
  const title = (h: NewsItem) => plain(lang === "es" && h.es ? h.es : h.title);
  const wire = (items: NewsItem[], n = 6): Seg[] => items.slice(0, n).flatMap((h) => [
    { t: h.score != null && h.catalyst !== false ? (h.score > 0 ? "+ " : h.score < 0 ? "- " : "· ") : "· ", c: tone(h.catalyst === false ? null : h.score) },
    { t: `${title(h)}    `, c: CYAN }]);
  const none = (r: [number, number, number, number], c = DIM) => led(g, k, [{ t: plain(W.noData), c }], r[0] + 2, r[1] + r[3] / 2 - 4, { boxW: r[2] - 4, align: "center" });

  if (room === "lobby") {
    const rdm = d?.markets[market];
    const [x, y, w] = S.wall;
    if (rdm?.net != null) {
      const c = tone(Math.abs(rdm.net) < 15 ? 0 : rdm.net);
      led(g, k, [{ t: tk, c: AMBER }], x + 1, y + 1, { boxW: w - 2, align: "center", pitch: 0.75 });
      txt(g, signed(rdm.net, lang), x + w / 2, y + 15.5, 9, c, "center");
    } else led(g, k, [{ t: tk, c: AMBER }], x + 1, y + 5, { boxW: w - 2, align: "center" });
    const ups = rdm?.drivers.up.length ?? 0, downs = rdm?.drivers.down.length ?? 0;
    const arrow = (r: number[], n: number, c: string, dir: 1 | -1) => {
      for (let i = 0; i < 3; i++) {
        g.globalAlpha = i < n ? 0.95 : 0.18; g.fillStyle = c;
        const cx = r[0] + r[2] / 2, cy = r[1] + 4 + i * 5;
        g.beginPath(); g.moveTo(cx, cy - 2 * dir); g.lineTo(cx + 3, cy + 2 * dir); g.lineTo(cx - 3, cy + 2 * dir); g.closePath(); g.fill();
      }
      g.globalAlpha = 1;
    };
    arrow(S.wallL, ups, UP, 1); arrow(S.wallR, downs, DOWN, -1);
    const b = d?.scoreboard[market];
    const [sx, sy, sw] = S.score1;
    if (b?.called) { led(g, k, [{ t: `${Math.round((b.hits / b.called) * 100)}%`, c: UP }], sx + 1, sy + 2, { boxW: sw - 2, align: "center" }); txt(g, plain(up(W.hit)), sx + sw / 2, sy + 15, 4, DIM, "center"); }
    else led(g, k, [{ t: "--", c: DIM }], sx + 1, sy + 4, { boxW: sw - 2, align: "center" });
    const e = d?.events.next.find((x2) => x2.t > now);
    const [ex, ey, ew] = S.score2;
    if (e) {
      led(g, k, [{ t: W.codes[e.kind] ?? e.kind, c: AMBER }], ex + 1, ey + 1.5, { boxW: ew - 2, align: "center", pitch: 0.7 });
      txt(g, countdown(e.t - now, N.units), ex + ew / 2, ey + 14.5, 4.2, CREAM, "center");
    }
    const [bx, by, bw] = S.board;
    if (e) txt(g, W.codes[e.kind] ?? e.kind, bx + bw / 2, by + 8.5, 5, "#3b2414", "center", 700);
    // the teleprinter's paper rolls out
    const [px, py, pw, ph] = S.paper;
    g.save(); g.beginPath(); g.rect(px, py, pw, ph); g.clip();
    g.fillStyle = "#f4f1e8"; g.fillRect(px, py, pw, ph);
    g.fillStyle = "#8b8f99";
    const off = (t * 4) % 2;
    for (let i = -1; i < ph / 2; i++) g.fillRect(px + 1.5, py + i * 2 + off, (pw - 3) * (0.4 + ((i * 37) % 6) / 10), 0.7);
    g.restore();
  }

  if (room === "macro") {
    const [x, y, w, h] = S.board;
    if (!d) { none(S.board, AMBER); return; }
    const loc = lang === "es" ? "es-ES" : "en-US";
    const fmt = (ts: number) => {
      const dt = new Date(ts);
      return plain(`${dt.toLocaleDateString(loc, { day: "2-digit" })} ${dt.toLocaleDateString(loc, { month: "short" }).replace(".", "")} ${dt.toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" })}`).toUpperCase();
    };
    const rows: Seg[][] = [];
    for (const e of d.events.just.filter((x2) => now - x2.t <= 2 * 3600_000)) rows.push([{ t: (W.codes[e.kind] ?? e.kind).padEnd(8), c: UP }, { t: plain(up(N.eventJust)), c: UP }]);
    for (const e of d.events.next.filter((x2) => x2.t > now)) {
      if (rows.length >= 3) break;
      rows.push([{ t: (W.codes[e.kind] ?? e.kind).padEnd(8), c: AMBER }, { t: `${fmt(e.t)}  `, c: "#ffd27a" },
        { t: plain(up(countdown(e.t - now, N.units))), c: AMBER }]);
    }
    rows.forEach((r, i) => led(g, k, r, x + 3, y + 1.5 + i * 8.6, { boxW: w - 6 }));
    if (!rows.length) none([x, y, w, h], AMBER);
    // the room's push on the market, on the lectern's screen
  }

  if (room === "geo") {
    const pins = rd.pins ?? {};
    const [mx, my, mw, mh] = S.map;
    if (d) {
      const regions = byRegion(d, market);
      for (const r of regions) {
        const p = pins[r.region];
        if (!p) continue;
        const items = [...r.geo, ...r.other];
        const avg = items.reduce((s, h) => s + (h.score ?? 0), 0) / Math.max(1, items.length);
        const c = r.geo.length ? (Math.abs(avg) < 10 ? AMBER : avg > 0 ? UP : DOWN) : "#a5b4fc";
        const pulse = (t * 0.8 + p[0] / 50) % 1;
        if (r.geo.length) {
          g.strokeStyle = c; g.globalAlpha = 1 - pulse; g.lineWidth = 0.8;
          g.beginPath(); g.arc(p[0], p[1], 2 + pulse * (4 + Math.min(4, r.geo.length) * 1.5), 0, Math.PI * 2); g.stroke();
        }
        g.globalAlpha = r.geo.length ? 1 : 0.9; g.fillStyle = c;
        g.beginPath(); g.arc(p[0], p[1], r.geo.length ? 1.8 + Math.min(3, r.geo.length) * 0.4 : 1.6, 0, Math.PI * 2); g.fill();
        if (!r.geo.length) { g.strokeStyle = c; g.globalAlpha = 0.45; g.lineWidth = 0.6; g.beginPath(); g.arc(p[0], p[1], 3, 0, Math.PI * 2); g.stroke(); }
        g.globalAlpha = 1;
        txt(g, String(r.geo.length + r.other.length), p[0] + 3.5, p[1] - 2.5, 4.5, r.geo.length ? "#fff" : "#c7d2fe", "left");
      }
      const glob = regions.find((r) => r.region === "global");
      if (glob) led(g, k, [{ t: `${plain(up(W.regions.global))} ${glob.geo.length + glob.other.length}`, c: "#a5b4fc" }], mx + 2, my + mh - 7, { pitch: 0.7 });
    }
    // the wall screen: the push, then the headlines running
    const [wx, wy, ww] = S.wall;
    const geo = d ? storiesOf(d, market, ["geopolitics"]) : [];
    const p = d ? pushOf(d, market, ["geopolitics"]) : { push: null, n: 0 };
    led(g, k, [{ t: `${W.short.geo} `, c: AMBER }, { t: `${tk} ${p.push == null || !p.n ? "·" : signed(p.push, lang)}`, c: tone(p.n ? p.push : null) }], wx + 2, wy + 2, { boxW: ww - 4 });
    if (geo.length) led(g, k, wire(geo), wx + 2, wy + 13, { boxW: ww - 4, t });
    else led(g, k, [{ t: plain(up(T.tower.say.mapNone)), c: DIM }], wx + 2, wy + 13, { boxW: ww - 4 });
    // the clocks
    EXCHANGES.forEach((x2, i) => {
      const r = S[`clock${i}`];
      if (!r) return;
      const s = exchangeNow(x2, now);
      led(g, k, [{ t: ({ ny: "NY", london: "LDN", tokyo: "TYO" } as Record<string, string>)[x2.id], c: DIM }], r[0] + 1, r[1] + 1.5, { boxW: r[2] - 2, align: "center", pitch: 0.7 });
      led(g, k, [{ t: s.time, c: s.open ? UP : AMBER }], r[0] + 1, r[1] + 9.5, { boxW: r[2] - 2, align: "center", pitch: 0.8 });
      g.fillStyle = s.open ? UP : "#3a3f4f"; g.fillRect(r[0] + r[2] - 3, r[1] + 1, 1.5, 1.5);
    });
    void mw;
  }

  if (room === "rules") {
    const [x, y, w] = S.docket;
    const items = d ? storiesOf(d, market, ["legal", "regulation"]) : [];
    const p = d ? pushOf(d, market, ["legal", "regulation"]) : { push: null, n: 0 };
    led(g, k, [{ t: `${W.short.rules} `, c: CREAM }, { t: `${tk} ${p.push == null || !p.n ? "·" : signed(p.push, lang)}`, c: tone(p.n ? p.push : null) }], x + 2, y + 2, { boxW: w - 4 });
    if (items.length) led(g, k, wire(items).map((s) => (s.c === CYAN ? { ...s, c: CREAM } : s)), x + 2, y + 13, { boxW: w - 4, t });
  }

  if (room === "money") {
    const [x, y, w] = S.ticker;
    if (!d) { none(S.ticker, UP); return; }
    const head: Seg[] = (["etf", "institutional", "flows"] as const).flatMap((c) => {
      const p = pushOf(d, market, [c]);
      return [{ t: `${plain(up(N.cats[c] ?? c)).split(" ")[0]} `, c: DIM }, { t: `${p.push == null || !p.n ? "·" : signed(p.push, lang)}   `, c: tone(p.n ? p.push : null) }];
    });
    led(g, k, [{ t: `${tk}  `, c: AMBER }, ...head], x + 2, y + 2, { boxW: w - 4, t });
    const items = storiesOf(d, market, ["etf", "institutional", "flows"]);
    if (items.length) led(g, k, wire(items).map((s) => (s.c === CYAN ? { ...s, c: "#bbf7d0" } : s)), x + 2, y + 13, { boxW: w - 4, t: t + 3 });
  }

  if (room === "security") {
    const [x, y, w] = S.alarm;
    const alarm = d ? alarmOf(d, market, now) : null;
    const blink = reduced || Math.floor(t * 2) % 2 === 0;
    if (alarm) {
      if (blink) led(g, k, [{ t: plain(W.alarmOn), c: "#ff4d4d" }], x + 2, y + 2, { boxW: w - 4, align: "center" });
      led(g, k, [{ t: title(alarm), c: "#ffb4b4" }], x + 2, y + 13, { boxW: w - 4, t });
    } else if (d) {
      led(g, k, [{ t: plain(W.alarmOk), c: UP }], x + 2, y + 2, { boxW: w - 4, align: "center", pitch: 0.85 });
      const sec = storiesOf(d, market, ["security"]);
      if (sec.length) led(g, k, wire(sec, 3).map((s) => (s.c === CYAN ? { ...s, c: "#9ca3af" } : s)), x + 2, y + 13, { boxW: w - 4, t });
    } else none(S.alarm);
    // the beacons on the wall
    for (const bx of [12.25 * TILE + 8, 22.25 * TILE + 8]) {
      const on = alarm ? 0.5 + 0.5 * Math.sin(t * 6) : 0.12;
      const gr = g.createRadialGradient(bx, 1.25 * TILE + 8, 0, bx, 1.25 * TILE + 8, 18);
      gr.addColorStop(0, `rgba(255,60,60,${on * 0.55})`); gr.addColorStop(1, "rgba(255,60,60,0)");
      g.fillStyle = gr; g.fillRect(bx - 18, 1.25 * TILE - 10, 36, 36);
    }
    const [ex, ey, ew] = S.exchanges;
    const xs = d ? storiesOf(d, market, ["exchange", "tech"]) : [];
    const p = d ? pushOf(d, market, ["exchange"]) : { push: null, n: 0 };
    led(g, k, [{ t: `${W.short.security} `, c: AMBER }, { t: `${tk} ${p.push == null || !p.n ? "·" : signed(p.push, lang)}`, c: tone(p.n ? p.push : null) }], ex + 2, ey + 2, { boxW: ew - 4 });
    if (xs.length) led(g, k, wire(xs), ex + 2, ey + 13, { boxW: ew - 4, t: t + 5 });
    // the servers blink
    (rd.leds ?? []).forEach(([lx, ly], i) => {
      for (let j = 0; j < 3; j++) {
        const on = reduced ? j === 0 : Math.sin(t * (2 + ((i + j) % 3)) + i * 1.7 + j) > 0.2;
        g.fillStyle = on ? (j === 2 && i % 4 === 1 ? AMBER : UP) : "#1f2a24";
        g.fillRect(lx + j * 2.2, ly, 1.2, 1.2);
      }
    });
  }
}
