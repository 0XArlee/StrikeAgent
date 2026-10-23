// Inside Strike Finance: the exchange's own numbers as a hall. The volume wall at the back (each day's trading volume as
// bars), the users and the treasury either side, the open interest on the console in the middle, Strike's funding against
// other exchanges at the trading desks; all of it Strike's public statistics, live. Your agent walks by itself to
// whatever you choose and what it looks at opens beside the scene. Only on this page (the city goes on for everyone else).
import { useEffect, useRef, useState } from "react";
import type { Lang } from "../i18n";
import type { AgentView } from "./agents";
import { pct, usd } from "./CopyView";
import { drawFrame, lookFor, onSheet, sheetOf, type Anim, type Dir } from "./sprites";
import { HQ, ROOM_H, ROOM_W, TILE, hqArt, roomPath } from "./tower";
import { bubble, led, plain, txt } from "./TowerView";
import type { StrikeStats } from "./strikestats";
import { ticker, type CityText } from "./text";

type Spot = "board" | "oi" | "users" | "treasury" | "funding" | "door";
const SPOTS: Spot[] = ["board", "oi", "users", "treasury", "funding", "door"];
const ART_W = ROOM_W * TILE, ART_H = ROOM_H * TILE;
const SPEED = 96;
const MINT = "#4efab0", UP = "#4ade80", DOWN = "#f87171", SKY = "#7dd3fc", CREAM = "#e7f9f0", DIM = "#6b8a80", GOLD = "#fbbf24";
const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const SHOWN = 90;   // days on the charts

interface Walker { x: number; y: number; dir: Dir; path: [number, number][]; then?: () => void }
type Stats = StrikeStats | null | "error";

export function StrikeView({ T, lang, stats, vol24, agent, onExit }:
  { T: CityText; lang: Lang; stats: Stats; vol24: number | null; agent: AgentView | null; onExit: () => void }) {
  const H = T.hq, W = T.tower;
  const [spot, setSpot] = useState<Spot>("board");
  const [arrived, setArrived] = useState(!agent);
  const canvas = useRef<HTMLCanvasElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLElement>(null);
  const exitBtn = useRef<HTMLButtonElement>(null);
  const me = useRef<Walker | null>(null);
  const hover = useRef<Spot | null>(null);
  const s = stats && stats !== "error" ? stats : null;
  const live = useRef({ s, spot, arrived, lang, vol24 });
  live.current = { s, spot, arrived, lang, vol24 };
  const name = agent?.name ?? "";

  const toPanel = () => {
    const r = root.current, p = panel.current, st = stage.current;
    if (!r || !p || !st || window.innerWidth > 1000) return;
    requestAnimationFrame(() => r.scrollTo({ top: Math.max(0, p.offsetTop - st.offsetHeight - 8), behavior: reduced ? "auto" : "smooth" }));
  };

  useEffect(() => { exitBtn.current?.focus({ preventScroll: true }); }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onExit(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onExit]);

  // your agent comes in through the door and walks to the volume wall
  useEffect(() => {
    if (!agent) return;
    me.current = { x: 13 * TILE + 8, y: ROOM_H * TILE + 6, dir: "up", path: [] };
    const st = HQ.spots.board;
    walkTo(st.stand[0], st.stand[1], st.face, () => setArrived(true), [13, ROOM_H - 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function walkTo(tx: number, ty: number, face: Dir, then?: () => void, from?: [number, number]) {
    const w = me.current;
    if (!w) { then?.(); return; }
    const sx = from?.[0] ?? Math.floor(w.x / TILE), sy = from?.[1] ?? Math.min(ROOM_H - 1, Math.floor((w.y - 1) / TILE));
    const path = roomPath(HQ, sx, sy, tx, ty);
    if (from) path.unshift(from);
    if (reduced || (!path.length && (sx !== tx || sy !== ty))) {
      w.x = tx * TILE + 8; w.y = ty * TILE + 15; w.dir = face; w.path = []; then?.();
      return;
    }
    w.path = path;
    w.then = () => { w.dir = face; then?.(); };
  }

  /** Choose what to look at: the panel shows it at once, your agent walks there (out through the door to leave). */
  function choose(sp: Spot) {
    const st = HQ.spots[sp];
    if (sp === "door") {
      if (!me.current) { onExit(); return; }
      setSpot(sp); setArrived(false);
      walkTo(st.stand[0], st.stand[1], "down", () => { me.current!.path = [[13, ROOM_H - 1]]; me.current!.then = onExit; });
      return;
    }
    setSpot(sp);
    setArrived(!me.current);
    toPanel();
    walkTo(st.stand[0], st.stand[1], st.face, () => setArrived(true));
  }

  // ---- the scene
  useEffect(() => {
    const c = canvas.current, box = stage.current;
    if (!c || !box) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    let k = 1;
    const fit = () => {
      const maxW = box.clientWidth, maxH = window.innerWidth > 1000 ? box.clientHeight : Infinity;
      k = Math.max(0.5, Math.min(maxW, maxH * 2) * dpr / ART_W);
      c.width = Math.round(ART_W * k); c.height = Math.round(ART_H * k);
      c.style.width = `${c.width / dpr}px`; c.style.height = `${c.height / dpr}px`;
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(box);
    const im = new Image(); im.decoding = "async"; im.src = hqArt;
    let bg: { k: number; c: HTMLCanvasElement } | null = null;
    const backdrop = (): HTMLCanvasElement | null => {
      if (!im.complete || !im.naturalWidth) return null;
      const whole = Math.max(1, Math.ceil(k - 0.01));
      if (bg && bg.k === whole) return bg.c;
      const off = document.createElement("canvas");
      off.width = ART_W * whole; off.height = ART_H * whole;
      const og = off.getContext("2d")!;
      og.imageSmoothingEnabled = false;
      og.drawImage(im, 0, 0, off.width, off.height);
      bg = { k: whole, c: off };
      return off;
    };
    const toArt = (e: PointerEvent) => { const r = c.getBoundingClientRect(); return { x: ((e.clientX - r.left) / r.width) * ART_W, y: ((e.clientY - r.top) / r.height) * ART_H }; };
    const hit = (x: number, y: number): Spot | null => {
      for (const sp of SPOTS) {
        const d = HQ.spots[sp];
        const [rx, ry, rw, rh] = d.rect;
        if ((x >= rx - 3 && x <= rx + rw + 3 && y >= ry - 3 && y <= ry + rh + 3)
          || (Math.floor(x / TILE) === d.stand[0] && Math.floor(y / TILE) === d.stand[1])) return sp;
      }
      return null;
    };
    const move = (e: PointerEvent) => { const p = toArt(e), sp = hit(p.x, p.y); hover.current = sp; c.style.cursor = sp ? "pointer" : "default"; };
    const click = (e: PointerEvent) => { const p = toArt(e), sp = hit(p.x, p.y); if (sp) pick.current(sp); };
    const leave = () => { hover.current = null; };
    c.addEventListener("pointermove", move);
    c.addEventListener("pointerup", click);
    c.addEventListener("pointerleave", leave);

    const g = c.getContext("2d")!;
    let raf = 0, last = performance.now();
    const t0 = last;
    const phase = (x: string) => (x.split("").reduce((a, ch) => a + ch.charCodeAt(0), 0) % 97) / 9.7;
    const frame = (ms: number) => {
      raf = requestAnimationFrame(frame);
      if (document.hidden) return;
      const dt = Math.min(0.05, (ms - last) / 1000); last = ms;
      const t = reduced ? 0 : Math.max(0, (ms - t0) / 1000);
      const L = live.current;
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
      const back = backdrop();
      if (back) { g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high"; g.drawImage(back, 0, 0, c.width, c.height); }
      g.setTransform(k, 0, 0, k, 0, 0);
      g.imageSmoothingEnabled = false;
      screens(g, k, L.s, L.vol24, t, T, L.lang);

      // the spots you can look at: a marker over each, the hovered one outlined with its name
      for (const sp of SPOTS) {
        const [rx, ry, rw, rh] = HQ.spots[sp].rect;
        const on = sp === hover.current, sel = sp === L.spot;
        if (on || sel) {
          g.save(); g.globalAlpha = sel ? 0.55 + 0.25 * Math.sin(t * 4) : 0.9;
          g.strokeStyle = MINT; g.lineWidth = 1; g.strokeRect(rx - 1.5, ry - 1.5, rw + 3, rh + 3); g.restore();
        }
        if (!sel) {
          const mx = rx + rw / 2, my = Math.max(5, ry - 4) + Math.sin(t * 3 + rx) * 1.2;
          g.fillStyle = MINT; g.globalAlpha = on ? 1 : 0.85;
          g.beginPath(); g.moveTo(mx, my - 3); g.lineTo(mx + 2.5, my); g.lineTo(mx, my + 3); g.lineTo(mx - 2.5, my); g.closePath(); g.fill();
          g.globalAlpha = 1;
        }
        if (on) {
          const label = H.spots[sp];
          g.font = `600 6px "IBM Plex Sans", sans-serif`;
          const tw = g.measureText(label).width + 8, lx = Math.min(ART_W - tw - 2, Math.max(2, rx + rw / 2 - tw / 2)), ly = Math.min(ART_H - 12, ry + rh + 4);
          g.fillStyle = "rgba(5,6,10,.88)"; g.fillRect(lx, ly, tw, 10);
          g.fillStyle = "#fff"; g.textAlign = "left"; g.fillText(label, lx + 4, ly + 7.3);
        }
      }

      // people, back to front: the traders at their desks, your agent
      const people: { y: number; draw: () => void }[] = HQ.staff.map((p) => ({
        y: p.y * TILE + 15,
        draw: () => { const sh = sheetOf(lookFor(p.seed)); if (sh) drawFrame(g, sh, p.anim as Anim, p.dir, t + phase(p.seed), p.x * TILE + 8, p.y * TILE + 15); },
      }));
      if (w && w.y <= ART_H + 8) {
        const sh = sheetOf(agentLook.current!);
        people.push({ y: w.y, draw: () => {
          g.fillStyle = "rgba(0,0,0,.35)"; g.beginPath(); g.ellipse(w.x, w.y, 5, 1.8, 0, 0, Math.PI * 2); g.fill();
          if (sh) drawFrame(g, sh, w.path.length ? "walk" : "idle", w.dir, t, w.x, w.y);
          else { g.fillStyle = MINT; g.beginPath(); g.arc(w.x, w.y - 8, 4, 0, Math.PI * 2); g.fill(); }
        } });
      }
      people.sort((a, b) => a.y - b.y).forEach((p) => p.draw());
      if (w && L.arrived) bubble(g, w.x, w.y - 26, sayRef.current);
      if (w) {
        g.font = `700 5px "IBM Plex Mono", monospace`; g.textAlign = "center";
        const nw = g.measureText(nameRef.current).width + 6;
        g.fillStyle = "rgba(5,6,10,.75)"; g.fillRect(w.x - nw / 2, w.y + 2, nw, 7);
        g.fillStyle = MINT; g.fillText(nameRef.current, w.x, w.y + 7.4);
      }
    };
    raf = requestAnimationFrame(frame);
    const off = onSheet(() => { /* the next frame draws it */ });
    return () => {
      cancelAnimationFrame(raf); ro.disconnect(); off();
      c.removeEventListener("pointermove", move); c.removeEventListener("pointerup", click); c.removeEventListener("pointerleave", leave);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pick = useRef(choose); pick.current = choose;
  const agentLook = useRef(agent ? agent.look ?? lookFor(agent.id) : null); agentLook.current = agent ? agent.look ?? lookFor(agent.id) : null;
  const nameRef = useRef(name); nameRef.current = name;
  const sayRef = useRef(""); sayRef.current = say(spot, s, T, lang);

  return (
    <div ref={root} className="tw hq" role="dialog" aria-modal="true" aria-labelledby="hq-title" style={{ ["--room" as string]: MINT }}>
      <header className="tw-top">
        <div className="tw-head">
          <h2 id="hq-title">{H.title}</h2>
          <p className="tw-about">{H.about}</p>
        </div>
        <button ref={exitBtn} type="button" className="btn btn-ghost tw-exit" onClick={onExit}><span aria-hidden="true">←</span> {H.exit}</button>
      </header>
      <div className="tw-main">
        <div className="tw-scene">
          <div className="tw-stage" ref={stage}><canvas ref={canvas} aria-hidden="true" /></div>
          <div className="tw-spots" role="group" aria-label={H.title}>
            {SPOTS.map((sp) => <button key={sp} type="button" aria-pressed={sp === spot} onClick={() => choose(sp)}>{H.spots[sp]}</button>)}
          </div>
          <p className="tw-note small faint">{agent ? W.onlyYou : W.visitor}</p>
        </div>
        {/* it scrolls with nothing to press in it at times: focusable, so a keyboard can scroll it too */}
        <section ref={panel} className="tw-panel" aria-labelledby="hq-spot-title" tabIndex={0}>
          <h3 id="hq-spot-title">{H.spots[spot]}</h3>
          {agent && !arrived && spot !== "door" && <p className="tw-going small" role="status">{W.going(name, H.spots[spot].toLocaleLowerCase(lang === "es" ? "es-ES" : "en-US"))}</p>}
          {!s ? <p className="news-state" role="status">{stats === "error" ? H.error : H.loading}</p>
            : <SpotBody T={T} lang={lang} s={s} vol24={vol24} spot={spot} onExit={onExit} />}
          {s && <p className="small faint hq-source">{H.source}</p>}
        </section>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ what a spot shows beside the scene
const loc = (lang: Lang) => (lang === "es" ? "es-ES" : "en-US");
const day = (ts: number, lang: Lang) => new Date(ts).toLocaleDateString(loc(lang), { day: "numeric", month: "short", timeZone: "UTC" });
const count = (v: number | null | undefined, lang: Lang) => (v == null ? "—" : Math.round(v).toLocaleString(loc(lang)));
const rateFmt = (v: number | null, lang: Lang) => (v == null ? "—" : `${(v * 100).toLocaleString(loc(lang), { minimumFractionDigits: 4, maximumFractionDigits: 4 })} %`);
const tail = <X,>(a: X[], n = SHOWN) => a.slice(Math.max(0, a.length - n));
const oiNow = (s: StrikeStats) => s.positions?.oi ?? s.oi[s.oi.length - 1] ?? null;

function SpotBody({ T, lang, s, vol24, spot, onExit }: { T: CityText; lang: Lang; s: StrikeStats; vol24: number | null; spot: Spot; onExit: () => void }) {
  const H = T.hq;
  const days = tail(s.days);
  switch (spot) {
    case "board": {
      const kpis: [string, string, string?][] = [
        [H.k.volumeAll, usd(s.volumeAll, lang)], [H.k.volume24, usd(vol24, lang)], [H.k.users, count(s.users, lang)],
        [H.k.tvl, usd(s.tvl, lang)], [H.k.tradesAll, count(s.tradesAll, lang)], [H.k.oi, usd(oiNow(s), lang)],
        [H.k.revenueAll, usd(s.revenueAll, lang)], [H.k.deposits, usd(s.depositsAll, lang)],
      ];
      return (
        <>
          <p className="tw-hint">{H.hints.board}</p>
          <div className="hq-kpis">{kpis.map(([l, v]) => <div key={l} className="hq-kpi"><span>{l}</span><b className="num">{v}</b></div>)}</div>
          <Bars days={days} values={tail(s.volume)} color={MINT} lang={lang} label={H.c.volume} fmt={(v) => usd(v, lang)} today={H.today} />
          <Area days={tail(s.oiDays)} values={tail(s.oi)} color={SKY} lang={lang} label={H.c.oi} fmt={(v) => usd(v, lang)} />
          <h4 className="ar-h">{H.topMarkets}</h4>
          <MarketBars rows={s.volumeByMarket30d.slice(0, 8).map((r) => ({ label: ticker(r.market), v: r.volume }))} lang={lang} />
        </>
      );
    }
    case "oi": {
      const p = s.positions;
      return (
        <>
          <p className="tw-hint">{H.hints.oi}</p>
          <div className="hq-kpis three">
            <div className="hq-kpi"><span>{H.k.oi}</span><b className="num">{usd(oiNow(s), lang)}</b></div>
            <div className="hq-kpi"><span>{H.k.long}</span><b className="num pos">{count(p?.longN, lang)}</b></div>
            <div className="hq-kpi"><span>{H.k.short}</span><b className="num neg">{count(p?.shortN, lang)}</b></div>
          </div>
          {p && <Split long={p.longN} short={p.shortN} lang={lang} T={T} />}
          {p && <p className="small faint">{H.positions(p.n)}</p>}
          <Area days={tail(s.oiDays)} values={tail(s.oi)} color={SKY} lang={lang} label={H.c.oi} fmt={(v) => usd(v, lang)} />
          {p && <>
            <h4 className="ar-h">{H.byMarket}</h4>
            <ul className="hq-sides">
              {p.byMarket.slice(0, 10).map((m) => {
                const tot = m.longN + m.shortN || 1;
                return (
                  <li key={m.market}>
                    <span className="mono">{ticker(m.market)}</span>
                    <span className="hq-side-bar" aria-hidden="true"><i className="l" style={{ width: `${(m.longN / tot) * 100}%` }} /><i className="s" style={{ width: `${(m.shortN / tot) * 100}%` }} /></span>
                    <span className="num">{usd(m.oi, lang)}</span>
                    <span className="sr-only">{H.longShort(pct(m.longN / tot, lang, false), pct(m.shortN / tot, lang, false))}</span>
                  </li>
                );
              })}
            </ul>
          </>}
        </>
      );
    }
    case "users": {
      const dau = s.dau[s.dau.length - 1]?.[1] ?? null, nu = s.newUsers[s.newUsers.length - 1]?.[1] ?? null;
      return (
        <>
          <p className="tw-hint">{H.hints.users}</p>
          <div className="hq-kpis three">
            <div className="hq-kpi"><span>{H.k.users}</span><b className="num">{count(s.users, lang)}</b></div>
            <div className="hq-kpi"><span>{H.k.dau}</span><b className="num">{count(dau, lang)}</b></div>
            <div className="hq-kpi"><span>{H.k.newUsers}</span><b className="num">{count(nu, lang)}</b></div>
          </div>
          <Area days={tail(s.dau.map((d) => d[0]))} values={tail(s.dau.map((d) => d[1]))} color={MINT} lang={lang} label={H.c.dau} fmt={(v) => count(v, lang)} />
          <Bars days={days} values={tail(s.trades)} color={GOLD} lang={lang} label={H.c.trades} fmt={(v) => count(v, lang)} today={H.today} />
          <p className="small">{H.tradesAll(count(s.tradesAll, lang))}</p>
        </>
      );
    }
    case "treasury": {
      const tvl = s.tvl || 1;
      return (
        <>
          <p className="tw-hint">{H.hints.treasury}</p>
          <div className="hq-kpis three">
            <div className="hq-kpi"><span>{H.k.tvl}</span><b className="num">{usd(s.tvl, lang)}</b></div>
            <div className="hq-kpi"><span>{H.k.deposits}</span><b className="num">{usd(s.depositsAll, lang)}</b></div>
            <div className="hq-kpi"><span>{H.k.withdrawals}</span><b className="num">{usd(s.withdrawalsAll, lang)}</b></div>
          </div>
          <h4 className="ar-h">{H.treasury}</h4>
          <MarketBars wide rows={s.treasury.filter((x) => x.value > 0).slice(0, 6).map((x) => ({ label: x.asset, v: x.value, note: pct(x.value / tvl, lang, false) }))} lang={lang} />
          <Bars days={days} values={tail(s.revenue)} color={GOLD} lang={lang} label={H.c.revenue} fmt={(v) => usd(v, lang)} today={H.today} />
          <p className="small">{H.revenueAll(usd(s.revenueAll, lang))} · {H.liquidatedAll(usd(s.liquidatedAll, lang))}</p>
          {s.vaults.length > 0 && <>
            <h4 className="ar-h">{H.vaults}</h4>
            <ul className="hq-vaults">
              {s.vaults.map((v) => (
                <li key={v.name}><b>{v.name}</b><span className="small faint">{H.vaultLine(usd(v.equity, lang), v.share.toLocaleString(loc(lang), { maximumFractionDigits: 4 }), `${v.fee.toLocaleString(loc(lang))} %`)}</span></li>
              ))}
            </ul>
          </>}
        </>
      );
    }
    case "funding": {
      const order = new Map(s.volumeByMarket30d.map((r, i) => [r.market, i]));
      const rows = [...s.funding].sort((a, b) => (order.get(a.market) ?? 99) - (order.get(b.market) ?? 99)).slice(0, 12);
      return (
        <>
          <p className="tw-hint">{H.hints.funding}</p>
          <div className="hq-table-wrap" role="region" aria-label={H.spots.funding} tabIndex={0}>
            <table className="city-table hq-table">
              <thead><tr><th scope="col">{H.market}</th><th scope="col" className="right">Strike</th><th scope="col" className="right">Binance</th>
                <th scope="col" className="right">Bybit</th><th scope="col" className="right">OKX</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.market}><th scope="row" className="mono">{ticker(r.market)}</th>
                    {[r.strike, r.binance, r.bybit, r.okx].map((v, i) => <td key={i} className={`right num ${i === 0 ? "hq-strike" : ""}`}>{rateFmt(v, lang)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small faint">{H.fundingNote}</p>
        </>
      );
    }
    case "door":
      return <><p className="tw-hint">{T.tower.hints.exit}</p><button type="button" className="btn btn-primary btn-block" onClick={onExit}>{H.exit}</button></>;
  }
  return null;
}

/** Each day's value as a bar (the last one, today, so far: paler); the highest and both ends marked. */
function Bars({ days, values, color, lang, label, fmt, today }: { days: number[]; values: number[]; color: string; lang: Lang; label: string;
  fmt: (v: number) => string; today: string }) {
  const n = values.length;
  if (n < 2) return null;
  const Wd = 400, Hh = 110, max = Math.max(...values) || 1, bw = Wd / n;
  const total = values.slice(0, -1).reduce((a, b) => a + b, 0);
  return (
    <figure className="hq-chart">
      <figcaption><b>{label}</b><span className="faint"> · {day(days[0], lang)} – {day(days[n - 1], lang)}</span></figcaption>
      <svg viewBox={`0 0 ${Wd} ${Hh + 14}`} role="img" aria-label={`${label}: ${day(days[0], lang)} – ${day(days[n - 1], lang)}, max ${fmt(max)}`}>
        {[0.25, 0.5, 0.75].map((f) => <line key={f} x1="0" x2={Wd} y1={Hh - f * (Hh - 6)} y2={Hh - f * (Hh - 6)} className="hq-grid" />)}
        {values.map((v, i) => {
          const h = Math.max(0.5, (v / max) * (Hh - 6));
          return <rect key={i} x={i * bw + 0.4} y={Hh - h} width={Math.max(0.8, bw - 0.8)} height={h} fill={color} opacity={i === n - 1 ? 0.45 : 0.9}>
            <title>{`${day(days[i], lang)}${i === n - 1 ? ` (${today})` : ""}: ${fmt(v)}`}</title></rect>;
        })}
        <line x1="0" x2={Wd} y1={Hh} y2={Hh} className="hq-axis" />
        <text x="2" y="9" className="hq-lbl">{fmt(max)}</text>
        <text x="0" y={Hh + 11} className="hq-lbl">{day(days[0], lang)}</text>
        <text x={Wd} y={Hh + 11} className="hq-lbl" textAnchor="end">{day(days[n - 1], lang)}</text>
      </svg>
      <p className="small faint">{`Σ ${fmt(total)}`}</p>
    </figure>
  );
}

/** A value over the days as a filled line, the latest one marked. */
function Area({ days, values, color, lang, label, fmt }: { days: number[]; values: number[]; color: string; lang: Lang; label: string; fmt: (v: number) => string }) {
  const n = values.length;
  if (n < 2) return null;
  const Wd = 400, Hh = 90, max = Math.max(...values) || 1;
  const pts = values.map((v, i) => [(i / (n - 1)) * Wd, Hh - (v / max) * (Hh - 8)] as const);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const last = values[n - 1];
  return (
    <figure className="hq-chart">
      <figcaption><b>{label}</b><span className="faint"> · {fmt(last)}</span></figcaption>
      <svg viewBox={`0 0 ${Wd} ${Hh + 14}`} role="img" aria-label={`${label}: ${fmt(last)} (${day(days[n - 1], lang)}), max ${fmt(max)}`}>
        {[0.25, 0.5, 0.75].map((f) => <line key={f} x1="0" x2={Wd} y1={Hh - f * (Hh - 8)} y2={Hh - f * (Hh - 8)} className="hq-grid" />)}
        <path d={`${line} L${Wd},${Hh} L0,${Hh} Z`} fill={color} opacity="0.16" />
        <path d={line} fill="none" stroke={color} strokeWidth="1.6" />
        <circle cx={pts[n - 1][0] - 1.5} cy={pts[n - 1][1]} r="2.6" fill={color} />
        <line x1="0" x2={Wd} y1={Hh} y2={Hh} className="hq-axis" />
        <text x="2" y="9" className="hq-lbl">{fmt(max)}</text>
        <text x="0" y={Hh + 11} className="hq-lbl">{day(days[0], lang)}</text>
        <text x={Wd} y={Hh + 11} className="hq-lbl" textAnchor="end">{day(days[n - 1], lang)}</text>
      </svg>
    </figure>
  );
}

function MarketBars({ rows, lang, wide }: { rows: { label: string; v: number; note?: string }[]; lang: Lang; wide?: boolean }) {
  const max = Math.max(...rows.map((r) => r.v), 1);
  return (
    <ul className={`hq-mbars${wide ? " wide" : ""}`}>
      {rows.map((r) => (
        <li key={r.label}><span className="mono" title={r.label}>{r.label}</span><span className="hq-mbar" aria-hidden="true"><i style={{ width: `${(r.v / max) * 100}%` }} /></span>
          <span className="num">{usd(r.v, lang)}{r.note ? <span className="faint"> · {r.note}</span> : null}</span></li>
      ))}
    </ul>
  );
}

function Split({ long, short, lang, T }: { long: number; short: number; lang: Lang; T: CityText }) {
  const tot = long + short || 1;
  return (
    <div className="hq-split" role="img" aria-label={T.hq.longShort(pct(long / tot, lang, false), pct(short / tot, lang, false))}>
      <i className="l" style={{ width: `${(long / tot) * 100}%` }}><span>{pct(long / tot, lang, false)}</span></i>
      <i className="s" style={{ width: `${(short / tot) * 100}%` }}><span>{pct(short / tot, lang, false)}</span></i>
    </div>
  );
}

/** What your agent says once there. */
function say(spot: Spot, s: StrikeStats | null, T: CityText, lang: Lang): string {
  const S = T.hq.say;
  if (!s) return "";
  switch (spot) {
    case "board": return S.board(usd(s.volumeAll, lang));
    case "oi": return S.oi(usd(oiNow(s), lang));
    case "users": return S.users(count(s.users, lang));
    case "treasury": return S.treasury(usd(s.tvl, lang));
    case "funding": return S.funding;
    default: return "";
  }
}

// ------------------------------------------------------------------ the hall's screens, drawn live
function screens(g: CanvasRenderingContext2D, k: number, s: StrikeStats | null, vol24: number | null, t: number, T: CityText, lang: Lang) {
  const S = HQ.screens, L = T.hq.led;
  const short = (v: number | null | undefined) => plain(usd(v, lang)).replace(/\s/g, "");
  // the volume wall: each of the last 60 days as a bar, the all-time volume over them
  const [bx, by, bw, bh] = S.board;
  if (s?.volume.length) {
    const vals = tail(s.volume, 60), max = Math.max(...vals) || 1, w = (bw - 6) / vals.length;
    const grow = reduced ? 1 : Math.min(1, t / 1.6);
    vals.forEach((v, i) => {
      const h = Math.max(0.5, (v / max) * (bh - 12) * grow);
      g.fillStyle = i === vals.length - 1 ? "rgba(78,250,176,0.45)" : MINT;
      g.fillRect(bx + 3 + i * w, by + bh - 2 - h, Math.max(0.6, w - 0.5), h);
    });
    led(g, k, [{ t: L.volume, c: DIM }], bx + 3, by + 2, { pitch: 0.6 });
    txt(g, short(s.volumeAll), bx + bw - 3, by + 8, 6.4, CREAM, "right");
  } else led(g, k, [{ t: L.loading, c: DIM }], bx + 3, by + 9, { boxW: bw - 6, align: "center" });
  // users, then the active ones today
  const [ux, uy, uw] = S.users;
  if (s) {
    const dau = s.dau[s.dau.length - 1]?.[1];
    const items: [string, string][] = [[L.users, (s.users ?? 0).toLocaleString("en-US")], [L.dau, String(dau ?? "—")]];
    const [label, value] = items[reduced ? 0 : Math.floor(t / 4) % items.length];
    led(g, k, [{ t: label, c: DIM }], ux + 1, uy + 1.5, { boxW: uw - 2, align: "center", pitch: 0.6 });
    txt(g, value, ux + uw / 2, uy + 15.5, 8, MINT, "center");
  }
  // the treasury, then the 24 h volume
  const [tx, ty, tw] = S.treasury;
  if (s) {
    const items: [string, string][] = [[L.tvl, short(s.tvl)], [L.vol24, short(vol24)]];
    const [label, value] = items[reduced ? 0 : Math.floor(t / 4.5) % items.length];
    led(g, k, [{ t: label, c: DIM }], tx + 1, ty + 1.5, { boxW: tw - 2, align: "center", pitch: 0.6 });
    txt(g, value, tx + tw / 2, ty + 15.5, 8, GOLD, "center");
  }
  // the console: the open interest and how it splits between longs and shorts
  const [ox, oy, ow, oh] = S.oi;
  if (s) {
    const p = s.positions, tot = p ? p.longN + p.shortN : 0;
    led(g, k, [{ t: L.oi, c: DIM }], ox + 2, oy + 2, { pitch: 0.6 });
    txt(g, short(oiNow(s)), ox + ow - 3, oy + 8, 6.4, SKY, "right");
    if (p && tot) {
      const lw = ((ow - 6) * p.longN) / tot, y = oy + oh - 8;
      g.fillStyle = UP; g.fillRect(ox + 3, y, lw, 4);
      g.fillStyle = DOWN; g.fillRect(ox + 3 + lw, y, ow - 6 - lw, 4);
      txt(g, `L ${Math.round((p.longN / tot) * 100)}%`, ox + 3, y - 1.5, 4.6, UP, "left");
      txt(g, `S ${Math.round((p.shortN / tot) * 100)}%`, ox + ow - 3, y - 1.5, 4.6, DOWN, "right");
    }
  }
}
