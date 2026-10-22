// Inside the Copy Arena: Strike's copy trading as a hall. The leaderboard over the stage, the three best standing on the
// podium (the real traders, with their scores), the copiers' wall, Strike's totals, all live; your agent walks by itself
// to whatever you choose and what it looks at opens beside the scene. Choosing a trader opens it on Strike, where you
// copy: Strike City never copies anyone. Only on this page (the city goes on for everyone else).
import { useEffect, useRef, useState } from "react";
import type { Lang } from "../i18n";
import { Icon } from "../components/ui";
import type { AgentView } from "./agents";
import { copiersWon, curveOf, traderName, type CopyDoc, type CopyState, type Trader } from "./copy";
import { CopyChooser, Evidence, Spark, StrikeStats, pct, usd } from "./CopyView";
import { drawFrame, lookFor, onSheet, sheetOf, type Anim, type Dir } from "./sprites";
import { ARENA, ROOM_H, ROOM_W, TILE, arenaArt, roomPath } from "./tower";
import { bubble, led, plain, txt } from "./TowerView";
import { ticker, type CityText } from "./text";

type Spot = "board" | "podium" | "copiers" | "stats" | "door";
const SPOTS: Spot[] = ["board", "podium", "copiers", "stats", "door"];
const ART_W = ROOM_W * TILE, ART_H = ROOM_H * TILE;
const SPEED = 96;
const ROSE = "#fb7185", UP = "#4ade80", DOWN = "#f87171", AMBER = "#fbbf24", CREAM = "#f3e3c2", DIM = "#7c8599";
const PLACE_C: Record<string, string> = { 1: "#5b3d0a", 2: "#2e3442", 3: "#4a2610" };
const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

interface Walker { x: number; y: number; dir: Dir; path: [number, number][]; then?: () => void }

export function ArenaView({ T, lang, doc, agent, onExit, onFollow }:
  { T: CityText; lang: Lang; doc: CopyState; agent: AgentView | null; onExit: () => void; onFollow: (id: string) => void }) {
  const C = T.copy, W = T.tower;
  const [spot, setSpot] = useState<Spot>("board");
  const [open, setOpen] = useState<string | null>(null);   // a trader's profile open on the board
  const [arrived, setArrived] = useState(!agent);
  const canvas = useRef<HTMLCanvasElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLElement>(null);
  const exitBtn = useRef<HTMLButtonElement>(null);
  const me = useRef<Walker | null>(null);
  const hover = useRef<Spot | null>(null);
  const d = doc && typeof doc === "object" ? doc : null;
  const live = useRef({ d, spot, arrived, lang });
  live.current = { d, spot, arrived, lang };
  const name = agent?.name ?? "";

  const toPanel = () => {
    const r = root.current, p = panel.current, s = stage.current;
    if (!r || !p || !s || window.innerWidth > 1000) return;
    requestAnimationFrame(() => r.scrollTo({ top: Math.max(0, p.offsetTop - s.offsetHeight - 8), behavior: reduced ? "auto" : "smooth" }));
  };

  useEffect(() => { exitBtn.current?.focus({ preventScroll: true }); }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onExit(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onExit]);

  // your agent comes in through the door and walks to the leaderboard
  useEffect(() => {
    if (!agent) return;
    me.current = { x: 13 * TILE + 8, y: ROOM_H * TILE + 6, dir: "up", path: [] };
    const s = ARENA.spots.board;
    walkTo(s.stand[0], s.stand[1], s.face, () => setArrived(true), [13, ROOM_H - 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function walkTo(tx: number, ty: number, face: Dir, then?: () => void, from?: [number, number]) {
    const w = me.current;
    if (!w) { then?.(); return; }
    const sx = from?.[0] ?? Math.floor(w.x / TILE), sy = from?.[1] ?? Math.min(ROOM_H - 1, Math.floor((w.y - 1) / TILE));
    const path = roomPath(ARENA, sx, sy, tx, ty);
    if (from) path.unshift(from);
    if (reduced || (!path.length && (sx !== tx || sy !== ty))) {
      w.x = tx * TILE + 8; w.y = ty * TILE + 15; w.dir = face; w.path = []; then?.();
      return;
    }
    w.path = path;
    w.then = () => { w.dir = face; then?.(); };
  }

  /** Choose what to look at: the panel shows it at once, your agent walks there (out through the door to leave). */
  function choose(s: Spot) {
    const st = ARENA.spots[s];
    if (s === "door") {
      if (!me.current) { onExit(); return; }
      setSpot(s); setArrived(false);
      walkTo(st.stand[0], st.stand[1], "down", () => { me.current!.path = [[13, ROOM_H - 1]]; me.current!.then = onExit; });
      return;
    }
    setSpot(s);
    setArrived(!me.current);
    toPanel();
    walkTo(st.stand[0], st.stand[1], st.face, () => setArrived(true));
  }
  const profile = (id: string) => { setOpen(id); choose("board"); };

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
    const im = new Image(); im.decoding = "async"; im.src = arenaArt;
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
      for (const s of SPOTS) {
        const sp = ARENA.spots[s];
        const [rx, ry, rw, rh] = sp.rect;
        if ((x >= rx - 3 && x <= rx + rw + 3 && y >= ry - 3 && y <= ry + rh + 3)
          || (Math.floor(x / TILE) === sp.stand[0] && Math.floor(y / TILE) === sp.stand[1])) return s;
      }
      return null;
    };
    const move = (e: PointerEvent) => { const p = toArt(e), s = hit(p.x, p.y); hover.current = s; c.style.cursor = s ? "pointer" : "default"; };
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
      const t = reduced ? 0 : Math.max(0, (ms - t0) / 1000);   // a frame's time can come just before t0: never negative
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
      screens(g, k, L.d, t, T, L.lang);

      // the spots you can look at: a marker over each, the hovered one outlined with its name
      for (const s of SPOTS) {
        const [rx, ry, rw, rh] = ARENA.spots[s].rect;
        const on = s === hover.current, sel = s === L.spot;
        if (on || sel) {
          g.save(); g.globalAlpha = sel ? 0.55 + 0.25 * Math.sin(t * 4) : 0.9;
          g.strokeStyle = ROSE; g.lineWidth = 1; g.strokeRect(rx - 1.5, ry - 1.5, rw + 3, rh + 3); g.restore();
        }
        if (!sel) {
          const mx = rx + rw / 2, my = Math.max(5, ry - 4) + Math.sin(t * 3 + rx) * 1.2;
          g.fillStyle = ROSE; g.globalAlpha = on ? 1 : 0.85;
          g.beginPath(); g.moveTo(mx, my - 3); g.lineTo(mx + 2.5, my); g.lineTo(mx, my + 3); g.lineTo(mx - 2.5, my); g.closePath(); g.fill();
          g.globalAlpha = 1;
        }
        if (on) {
          const label = C.spots[s];
          g.font = `600 6px "IBM Plex Sans", sans-serif`;
          const tw = g.measureText(label).width + 8, lx = Math.min(ART_W - tw - 2, Math.max(2, rx + rw / 2 - tw / 2)), ly = Math.min(ART_H - 12, ry + rh + 4);
          g.fillStyle = "rgba(5,6,10,.88)"; g.fillRect(lx, ly, tw, 10);
          g.fillStyle = "#fff"; g.textAlign = "left"; g.fillText(label, lx + 4, ly + 7.3);
        }
      }

      // people, back to front: the three on the podium, the public, your agent
      const people: { y: number; draw: () => void }[] = ARENA.staff.map((p) => ({
        y: p.y * TILE + 15,
        draw: () => { const sh = sheetOf(lookFor(p.seed)); if (sh) drawFrame(g, sh, p.anim as Anim, p.dir, t + phase(p.seed), p.x * TILE + 8, p.y * TILE + 15); },
      }));
      const top = L.d?.traders.slice(0, 3) ?? [];
      top.forEach((tr, i) => {
        const at = ARENA.podium?.[String(i + 1)];
        if (!at) return;
        people.push({ y: at[1], draw: () => {
          const sh = sheetOf(lookFor(`lead:${tr.id}`));
          if (sh) drawFrame(g, sh, "idle", "down", t + i * 0.7, at[0], at[1]);
        } });
      });
      if (w && w.y <= ART_H + 8) {
        const sh = sheetOf(agentLook.current!);
        people.push({ y: w.y, draw: () => {
          g.fillStyle = "rgba(0,0,0,.35)"; g.beginPath(); g.ellipse(w.x, w.y, 5, 1.8, 0, 0, Math.PI * 2); g.fill();
          if (sh) drawFrame(g, sh, w.path.length ? "walk" : "idle", w.dir, t, w.x, w.y);
          else { g.fillStyle = ROSE; g.beginPath(); g.arc(w.x, w.y - 8, 4, 0, Math.PI * 2); g.fill(); }
        } });
      }
      people.sort((a, b) => a.y - b.y).forEach((p) => p.draw());
      podium(g, top, t);
      if (w && L.arrived) bubble(g, w.x, w.y - 26, sayRef.current);
      if (w) {
        g.font = `700 5px "IBM Plex Mono", monospace`; g.textAlign = "center";
        const nw = g.measureText(nameRef.current).width + 6;
        g.fillStyle = "rgba(5,6,10,.75)"; g.fillRect(w.x - nw / 2, w.y + 2, nw, 7);
        g.fillStyle = ROSE; g.fillText(nameRef.current, w.x, w.y + 7.4);
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
  const sayRef = useRef(""); sayRef.current = say(spot, d, T, lang);

  return (
    <div ref={root} className="tw arena" role="dialog" aria-modal="true" aria-labelledby="ar-title" style={{ ["--room" as string]: ROSE }}>
      <header className="tw-top">
        <div className="tw-head">
          <h2 id="ar-title">{C.title}</h2>
          <p className="tw-about">{C.floorAbout}</p>
        </div>
        <button ref={exitBtn} type="button" className="btn btn-ghost tw-exit" onClick={onExit}><span aria-hidden="true">←</span> {C.exit}</button>
      </header>
      <div className="tw-main">
        <div className="tw-scene">
          <div className="tw-stage" ref={stage}><canvas ref={canvas} aria-hidden="true" /></div>
          <div className="tw-spots" role="group" aria-label={C.title}>
            {SPOTS.map((s) => <button key={s} type="button" aria-pressed={s === spot} onClick={() => choose(s)}>{C.spots[s]}</button>)}
          </div>
          <p className="tw-note small faint">{agent ? W.onlyYou : W.visitor}</p>
        </div>
        <section ref={panel} className="tw-panel" aria-labelledby="ar-spot-title">
          <h3 id="ar-spot-title">{C.spots[spot]}</h3>
          {agent && !arrived && spot !== "door" && <p className="tw-going small" role="status">{W.going(name, C.spots[spot].toLocaleLowerCase(lang === "es" ? "es-ES" : "en-US"))}</p>}
          {!d ? <p className="news-state" role="status">{doc === null ? C.loading : doc === "none" ? C.none : C.error}</p>
            : <SpotBody T={T} lang={lang} doc={d} spot={spot} open={open} onProfile={profile} onFollow={onFollow} onExit={onExit} />}
        </section>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ what a spot shows beside the scene
function SpotBody({ T, lang, doc, spot, open, onProfile, onFollow, onExit }: { T: CityText; lang: Lang; doc: CopyDoc; spot: Spot;
  open: string | null; onProfile: (id: string) => void; onFollow: (id: string) => void; onExit: () => void }) {
  const C = T.copy;
  switch (spot) {
    case "board":
      return <><p className="tw-hint">{C.hints.board}</p>
        <CopyChooser key={open ?? "list"} T={T} lang={lang} doc={doc} initial={open} onFollow={onFollow} compact /></>;
    case "podium": {
      const top = doc.traders.slice(0, 3);
      return (
        <>
          <p className="tw-hint">{C.hints.podium}</p>
          {!top.length ? <p className="small muted">{C.podiumEmpty}</p> : (
            <ol className="ar-podium">
              {top.map((t, i) => <PodiumCard key={t.id} T={T} lang={lang} t={t} place={i + 1} onProfile={() => onProfile(t.id)} />)}
            </ol>
          )}
          <p className="small faint">{C.cityHow}</p>
        </>
      );
    }
    case "copiers": {
      const share = doc.counts.subs ? doc.counts.inProfit / doc.counts.subs : null;
      const known = new Map(doc.traders.map((t) => [t.id, t]));
      return (
        <>
          <p className="tw-hint">{C.hints.copiers}</p>
          {share != null && <p className="ar-big"><b className="num">{pct(share, lang, false)}</b><span>{C.copiesWon(doc.counts.inProfit, doc.counts.subs, pct(share, lang, false))}</span></p>}
          {doc.evidence && <Evidence T={T} lang={lang} ev={doc.evidence} />}
          {!!doc.copyingOthers?.length && <p className="small faint">{C.leftOut(doc.copyingOthers.length)}</p>}
          <h4 className="ar-h">{C.bestCopiers}</h4>
          <ul className="ar-copies">
            {doc.copiers.map((x, i) => {
              const lead = known.get(x.lead);
              const leadName = traderName({ id: x.lead, platform: x.platform === "hyperliquid" ? "hyperliquid" : "strike" });
              return (
                <li key={`${x.lead}${x.follower}${i}`}>
                  <div className="grow">
                    <p><span className="mono">{x.follower.slice(0, 6)}…</span> <span className="faint">→</span>{" "}
                      {lead ? <button type="button" className="tw-linkbtn mono" onClick={() => onProfile(lead.id)}>{leadName}</button> : <span className="mono">{leadName}</span>}
                      <span className={`cp-plat ${x.platform}`}>{x.platform === "hyperliquid" ? "Hyperliquid" : "Strike"}</span></p>
                    <p className="small faint">{C.modes[x.mode] ?? x.mode} · {C.states[x.status] ?? x.status} · {T.ago((Date.now() - x.since) / 1000)}</p>
                  </div>
                  <div className="ar-made"><span className="small faint">{C.made}</span><b className={`num ${x.pnl >= 0 ? "pos" : "neg"}`}>{usd(x.pnl, lang, true)}</b></div>
                </li>
              );
            })}
          </ul>
        </>
      );
    }
    case "stats": {
      const S = doc.strike;
      return (
        <>
          <p className="tw-hint">{C.hints.stats}</p>
          <StrikeStats T={T} lang={lang} doc={doc} />
          <figure className="cp-chart ar-chart"><Spark points={S.daily.volume} w={400} h={70} label={C.dailyVolume} />
            <figcaption className="small faint">{C.dailyVolume} · {C.history(S.daily.volume.length)}</figcaption></figure>
          <figure className="cp-chart ar-chart"><Spark points={S.daily.profits} w={400} h={70} label={C.dailyProfits} />
            <figcaption className="small faint">{C.dailyProfits} · {C.history(S.daily.profits.length)}</figcaption></figure>
          <p className="small">{C.subs30(S.subscriptions30d)} · {C.copiersLine(doc.counts.active, doc.counts.subs)}</p>
          <p className="small faint">{C.lead(doc.traders.length, doc.counts.active, doc.historyDays)}</p>
          <p className="small faint">{C.note}</p>
        </>
      );
    }
    case "door":
      return <><p className="tw-hint">{T.tower.hints.exit}</p><button type="button" className="btn btn-primary btn-block" onClick={onExit}>{C.exit}</button></>;
  }
  return null;
}

function PodiumCard({ T, lang, t, place, onProfile }: { T: CityText; lang: Lang; t: Trader; place: number; onProfile: () => void }) {
  const C = T.copy, loc = lang === "es" ? "es-ES" : "en-US";
  const won = copiersWon(t);
  return (
    <li className={`ar-place p${place}`}>
      <span className="ar-medal num" aria-label={C.rank(place)}>{place}</span>
      <div className="grow">
        <p className="ar-name"><b className="mono">{traderName(t)}</b> <span className={`cp-plat ${t.platform}`}>{t.platform === "strike" ? "Strike" : "Hyperliquid"}</span></p>
        <p className="small"><span className="faint">{C.roi30}</span> <b className={`num ${(t.roi["30d"] ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(t.roi["30d"], lang)}</b>
          <span className="faint"> · {C.dd}</span> <b className="num">{t.metrics.dd == null ? "—" : pct(-t.metrics.dd, lang)}</b>
          <span className="faint"> · {C.copiers}</span> <b className="num">{t.copiers.n ? (won == null ? t.copiers.n : pct(won, lang, false)) : "—"}</b></p>
        {t.assets.length > 0 && <p className="small faint">{t.assets.slice(0, 4).map((a) => ticker(a)).join(" · ")}</p>}
        <Spark points={curveOf(t)} w={260} h={30} label={C.curve} />
        <div className="ar-actions">
          <button type="button" className="btn btn-ghost" onClick={onProfile}>{C.open}</button>
          <a className="btn btn-primary" href={t.url} target="_blank" rel="noopener noreferrer">{C.copyOn} <Icon.external /><span className="sr-only">{C.newTab}</span></a>
        </div>
      </div>
      <div className="ar-score"><span className="small faint">{C.cityScore}</span><b className="num">{t.city?.toLocaleString(loc, { maximumFractionDigits: 0 }) ?? "—"}</b></div>
    </li>
  );
}

/** What your agent says once there. */
function say(spot: Spot, d: CopyDoc | null, T: CityText, lang: Lang): string {
  const S = T.copy.say;
  if (!d) return "";
  switch (spot) {
    case "board": return S.board(d.traders.length);
    case "podium": return d.traders[0] ? S.podium(traderName(d.traders[0])) : "";
    case "copiers": { const b = d.copiers[0]; return b ? S.copiers(usd(b.pnl, lang, true)) : ""; }
    case "stats": return S.stats(usd(d.strike.volume30d, lang));
    default: return "";
  }
}

// ------------------------------------------------------------------ the hall's screens and the podium
function screens(g: CanvasRenderingContext2D, k: number, d: CopyDoc | null, t: number, T: CityText, lang: Lang) {
  const S = ARENA.screens, C = T.copy;
  const short = (v: number | null) => plain(usd(v, lang)).replace(/\s/g, "");
  // the leaderboard: three traders at a time, a new page every 4 s (the first nine)
  const [bx, by, bw] = S.board;
  if (d?.traders.length) {
    const page = reduced ? 0 : Math.floor(t / 4) % Math.min(3, Math.ceil(d.traders.length / 3));
    // crisp type on the board's dots (the dot font makes an 8 look like a #)
    d.traders.slice(page * 3, page * 3 + 3).forEach((tr, i) => {
      const n = page * 3 + i + 1, roi = tr.roi["30d"], y = by + 7.6 + i * 8.6;
      txt(g, String(n), bx + 9, y, 6.2, AMBER, "right");
      txt(g, traderName(tr), bx + 14, y, 6.2, CREAM, "left", 600);
      txt(g, String(Math.round(tr.city ?? 0)), bx + bw * 0.62, y, 6.2, ROSE, "right");
      txt(g, plain(pct(roi, lang)).replace(/\s/g, ""), bx + bw - 4, y, 6.2, roi == null ? DIM : roi >= 0 ? UP : DOWN, "right");
    });
  } else led(g, k, [{ t: C.led.board, c: DIM }], bx + 3, by + 9, { boxW: bw - 6, align: "center" });
  // the copiers' wall: the share of copies in profit, then the best copy
  const [cx, cy, cw] = S.copiers;
  if (d) {
    const share = d.counts.subs ? d.counts.inProfit / d.counts.subs : null;
    const alt = !reduced && Math.floor(t / 5) % 2 === 1 && d.copiers[0];
    if (alt) {
      led(g, k, [{ t: C.led.best, c: DIM }], cx + 1, cy + 1.5, { boxW: cw - 2, align: "center", pitch: 0.6 });
      txt(g, plain(usd(d.copiers[0].pnl, lang, true)).replace(/\s/g, ""), cx + cw / 2, cy + 15.5, 7, UP, "center");
    } else {
      led(g, k, [{ t: C.led.inProfit, c: DIM }], cx + 1, cy + 1.5, { boxW: cw - 2, align: "center", pitch: 0.6 });
      txt(g, share == null ? "—" : plain(pct(share, lang, false)).replace(/\s/g, ""), cx + cw / 2, cy + 15.5, 8, share != null && share < 0.5 ? AMBER : UP, "center");
    }
  }
  // Strike's totals, one at a time
  const [sx, sy, sw] = S.stats;
  if (d) {
    const items: [string, string][] = [[C.led.volume, short(d.strike.volume30d)], [C.led.allocated, short(d.strike.allocated)],
      [C.led.oi, short(d.strike.openInterest)], [C.led.profits, short(d.strike.profits30d)]];
    const [label, value] = items[reduced ? 0 : Math.floor(t / 3.5) % items.length];
    led(g, k, [{ t: label, c: DIM }], sx + 1, sy + 1.5, { boxW: sw - 2, align: "center", pitch: 0.6 });
    txt(g, value, sx + sw / 2, sy + 15.5, 8, ROSE, "center");
  }
}

function podium(g: CanvasRenderingContext2D, top: Trader[], t: number) {
  const P = ARENA.podium ?? {}, S = ARENA.screens;
  // two spotlights sweeping the podium from the stage lights
  if (top.length) {
    g.save();
    g.globalCompositeOperation = "lighter";
    for (const [lx, phase] of [[8.5 * TILE, 0], [19.5 * TILE, 1.7]] as const) {
      const sway = reduced ? 0 : Math.sin(t * 0.7 + phase) * 14;
      const tx = 14 * TILE + sway, ty = 7.2 * TILE;
      const gr = g.createLinearGradient(lx, 4.5 * TILE, tx, ty);
      gr.addColorStop(0, "rgba(255,236,190,0.16)"); gr.addColorStop(1, "rgba(255,236,190,0.02)");
      g.fillStyle = gr;
      g.beginPath(); g.moveTo(lx - 2, 4.6 * TILE); g.lineTo(lx + 2, 4.6 * TILE); g.lineTo(tx + 22, ty); g.lineTo(tx - 22, ty); g.closePath(); g.fill();
    }
    g.restore();
  }
  for (let place = 1; place <= 3; place++) {
    const tr = top[place - 1], at = P[String(place)], front = S[`step${place}`];
    if (front) txt(g, String(place), front[0] + front[2] / 2, front[1] + Math.min(front[3], 9) + 0.5, place === 1 ? 9 : 7, PLACE_C[place], "center", 700);
    if (!tr || !at) continue;
    // its score over its head, its name under the step
    const sc = `${Math.round(tr.city ?? 0)}`;
    g.font = `700 6px "IBM Plex Mono", monospace`;
    const w = g.measureText(sc).width + 8, y = at[1] - 33 - (reduced ? 0 : Math.sin(t * 2 + place) * 0.8);
    g.fillStyle = "rgba(5,6,10,.85)"; g.fillRect(at[0] - w / 2, y, w, 9);
    g.strokeStyle = ROSE; g.lineWidth = 0.6; g.strokeRect(at[0] - w / 2 + 0.3, y + 0.3, w - 0.6, 8.4);
    txt(g, sc, at[0], y + 7, 6, ROSE, "center");
    txt(g, traderName(tr), at[0], 8 * TILE + 6.5, 4.2, CREAM, "center", 600);
  }
}
