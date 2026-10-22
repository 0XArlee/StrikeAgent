// The end of creating an agent: "Meet <name>", a card drawn on a canvas so it can be saved and shared as a picture.
// Its workplace in EdgeCraft-StrikeCity at night (the city's own picture and its lit windows), the character standing
// in front, its citizen number, personality, trade, strategy, markets and risk, and a line in its own voice.
import { useEffect, useRef, useState } from "react";
import type { Look } from "../city/look";
import { TEMPER_COLOR, type Persona } from "../city/persona";
import { drawFrame, onSheet, sheetOf } from "../city/sprites";
import type { Dict, Lang } from "../i18n";
import { voiceLine } from "./PersonaPicker";
import { Icon } from "./ui";

const ART = `${import.meta.env.BASE_URL ?? "/"}art/city/`;
const W = 1200, H = 630;
// its workplace: the building's middle (art px of the city's picture), placed behind the character
const FOCUS: Record<string, [number, number]> = { chartist: [176, 112], reporter: [192, 470], tape: [768, 440], guardian: [1312, 800] };
const ZOOM = 2.6;
const backdrops = new WeakMap<HTMLImageElement, Map<string, HTMLCanvasElement>>();

/** Its workplace at night, drawn once per trade: the city's picture, darkened, with its windows lit. */
function backdrop(art: { base: HTMLImageElement; glow: HTMLImageElement }, job: string): HTMLCanvasElement {
  let m = backdrops.get(art.base);
  if (!m) { m = new Map(); backdrops.set(art.base, m); }
  const hit = m.get(job);
  if (hit) return hit;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d")!;
  g.imageSmoothingEnabled = false;
  g.fillStyle = "#070a14"; g.fillRect(0, 0, W, H);
  const [fx, fy] = FOCUS[job] ?? FOCUS.chartist;
  const dx = 820 - fx * ZOOM, dy = 300 - fy * ZOOM;
  g.drawImage(art.base, dx, dy, art.base.width * ZOOM, art.base.height * ZOOM);
  g.fillStyle = "rgba(8,12,34,0.6)"; g.fillRect(0, 0, W, H);
  g.globalCompositeOperation = "lighter"; g.globalAlpha = 0.85;
  g.drawImage(art.glow, dx, dy, art.glow.width * ZOOM, art.glow.height * ZOOM);
  m.set(job, c);
  return c;
}
const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function load(src: string): Promise<HTMLImageElement> {
  return new Promise((ok, fail) => { const im = new Image(); im.onload = () => ok(im); im.onerror = fail; im.src = src; });
}

export interface MeetInfo {
  name: string; look: Look | null; persona: Persona; citizen: number | null; strategy: string; markets: string[]; risk: string;
  url: string;   // where the agent can be seen (the city, or the site)
}

export function MeetCard({ t, lang, info }: { t: Dict; lang: Lang; info: MeetInfo }) {
  const P = t.persona, M = t.meet;
  const ref = useRef<HTMLCanvasElement>(null);
  const [art, setArt] = useState<{ base: HTMLImageElement; glow: HTMLImageElement } | null>(null);
  const [shared, setShared] = useState("");
  useEffect(() => { Promise.all([load(`${ART}base.webp`), load(`${ART}glow.webp`)]).then(([base, glow]) => setArt({ base, glow })).catch(() => undefined); }, []);

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    let raf = 0;
    const t0 = performance.now();
    const draw = () => {
      const g = c.getContext("2d")!;
      paint(g, info, art, t, lang, reduced ? 0 : (performance.now() - t0) / 1000);
      if (!reduced) raf = requestAnimationFrame(draw);
    };
    void document.fonts?.ready.then(draw);
    draw();
    const off = onSheet(draw);
    return () => { cancelAnimationFrame(raf); off(); };
  }, [info, art, t, lang]);

  const file = async (): Promise<File | null> => {
    const blob = await new Promise<Blob | null>((ok) => ref.current?.toBlob(ok, "image/png"));
    return blob ? new File([blob], `edgecraft-${info.name.replace(/[^\p{L}\p{N}]+/gu, "-").toLowerCase()}.png`, { type: "image/png" }) : null;
  };
  const save = async () => {
    const f = await file();
    if (!f) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(f); a.download = f.name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    setShared(M.saved);
  };
  const text = M.shareText(info.name, P.tempers[info.persona.temper].name, P.jobs[info.persona.job].name);
  const share = async () => {
    const f = await file();
    const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
    try {
      if (f && nav.share && nav.canShare?.({ files: [f] })) { await nav.share({ files: [f], title: M.title(info.name), text, url: info.url }); setShared(M.sharedOk); return; }
      if (nav.share) { await nav.share({ title: M.title(info.name), text, url: info.url }); setShared(M.sharedOk); return; }
    } catch (e) { if ((e as Error).name === "AbortError") return; }
    window.open(`https://x.com/intent/post?text=${encodeURIComponent(text)}&url=${encodeURIComponent(info.url)}`, "_blank", "noopener,noreferrer");
  };

  return (
    <figure className="meet">
      <canvas ref={ref} width={W} height={H} className="meet-canvas" role="img"
              aria-label={`${M.title(info.name)}. ${P.tempers[info.persona.temper].name}, ${P.jobs[info.persona.job].name}.`} />
      <figcaption className="meet-actions">
        <button type="button" className="btn btn-ghost" onClick={save}><Icon.download size={16} /> {M.save}</button>
        <button type="button" className="btn btn-ghost" onClick={share}><Icon.share size={16} /> {M.share}</button>
        <span className="small faint" role="status">{shared}</span>
      </figcaption>
    </figure>
  );
}

function paint(g: CanvasRenderingContext2D, info: MeetInfo, art: { base: HTMLImageElement; glow: HTMLImageElement } | null, t: Dict, lang: Lang, time: number) {
  const P = t.persona, M = t.meet, tc = TEMPER_COLOR[info.persona.temper];
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.imageSmoothingEnabled = false;
  g.fillStyle = "#070a14"; g.fillRect(0, 0, W, H);
  // its workplace, at night
  if (art) g.drawImage(backdrop(art, info.persona.job), 0, 0);
  // the text side, darker
  const grad = g.createLinearGradient(0, 0, W * 0.75, 0);
  grad.addColorStop(0, "rgba(5,7,14,0.96)"); grad.addColorStop(0.55, "rgba(5,7,14,0.82)"); grad.addColorStop(1, "rgba(5,7,14,0)");
  g.fillStyle = grad; g.fillRect(0, 0, W, H);
  // the character, big, with its shadow and a ring of its temper's colour
  const sheet = info.look ? sheetOf(info.look) : null;
  const cx = 930, feet = 560, s = 12;
  g.fillStyle = "rgba(0,0,0,0.45)"; g.beginPath(); g.ellipse(cx, feet + 4, 70, 16, 0, 0, Math.PI * 2); g.fill();
  g.strokeStyle = tc; g.globalAlpha = 0.7; g.lineWidth = 4; g.beginPath(); g.ellipse(cx, feet + 4, 92, 22, 0, 0, Math.PI * 2); g.stroke(); g.globalAlpha = 1;
  if (sheet) drawFrame(g, sheet, "idle", "down", time, cx, feet, s);
  // what it says (one or two lines)
  g.font = `600 26px "IBM Plex Sans", sans-serif`;
  const lines = wrap(g, `“${voiceLine(t, info.persona.temper, "wait", 0)}”`, 360);
  const qw = Math.max(...lines.map((l) => g.measureText(l).width)) + 36, qh = 18 + lines.length * 32;
  const qx = Math.min(W - qw - 24, cx - qw / 2), qy = 150 - qh;
  g.fillStyle = "rgba(255,255,255,0.96)"; roundRect(g, qx, qy, qw, qh, 14); g.fill();
  g.beginPath(); g.moveTo(cx - 12, qy + qh); g.lineTo(cx + 12, qy + qh); g.lineTo(cx, qy + qh + 18); g.fill();
  g.fillStyle = "#0b0d12"; g.textBaseline = "middle"; g.textAlign = "left";
  lines.forEach((l, i) => g.fillText(l, qx + 18, qy + 25 + i * 32));
  // the words
  g.textAlign = "left"; g.textBaseline = "alphabetic";
  g.fillStyle = "#4efab0"; g.font = `700 22px "IBM Plex Mono", monospace`;
  g.fillText("EDGECRAFT-STRIKECITY", 64, 84);
  g.fillStyle = "#a3a3a3"; g.font = `500 28px "IBM Plex Sans", sans-serif`;
  g.fillText(M.kicker, 64, 150);
  let size = 84;
  g.font = `700 ${size}px "IBM Plex Sans", sans-serif`;
  while (g.measureText(info.name).width > 640 && size > 40) { size -= 4; g.font = `700 ${size}px "IBM Plex Sans", sans-serif`; }
  g.fillStyle = "#fff"; g.fillText(info.name, 64, 150 + size + 6);
  let y = 150 + size + 60;
  if (info.citizen != null) {
    g.fillStyle = tc; g.font = `700 26px "IBM Plex Mono", monospace`;
    g.fillText(M.citizen(info.citizen), 64, y); y += 54;
  }
  // chips: personality, trade
  let x = 64;
  for (const [label, color] of [[P.tempers[info.persona.temper].name, tc], [P.jobs[info.persona.job].name, "#e5e7eb"]] as const) {
    g.font = `600 24px "IBM Plex Sans", sans-serif`;
    const w = g.measureText(label).width + 32;
    g.strokeStyle = color; g.lineWidth = 2; roundRect(g, x, y - 32, w, 46, 23); g.stroke();
    g.fillStyle = color; g.fillText(label, x + 16, y);
    x += w + 12;
  }
  y += 62;
  g.fillStyle = "#d4d4d4"; g.font = `500 24px "IBM Plex Sans", sans-serif`;
  g.fillText(`${info.strategy} · ${info.markets.map((m) => m.replace("-USD", "")).join(" · ")}`, 64, y);
  g.fillStyle = "#8a8a8a"; g.font = `500 22px "IBM Plex Sans", sans-serif`;
  g.fillText(info.risk, 64, y + 36);
  g.fillStyle = "#6b7280"; g.font = `500 18px "IBM Plex Sans", sans-serif`;
  g.fillText(M.footer(new Date().toLocaleDateString(lang === "es" ? "es-ES" : "en-US", { day: "numeric", month: "long", year: "numeric" })), 64, H - 40);
}

/** Words into lines no wider than `max` (two at most; the second ends in "…" if it must). */
function wrap(g: CanvasRenderingContext2D, text: string, max: number): string[] {
  const out: string[] = [];
  let cur = "";
  for (const w of text.split(" ")) {
    const next = cur ? `${cur} ${w}` : w;
    if (g.measureText(next).width <= max || !cur) cur = next;
    else { out.push(cur); cur = w; }
  }
  if (cur) out.push(cur);
  if (out.length > 2) out.splice(1, out.length - 1, `${out.slice(1).join(" ").slice(0, 28)}…`);
  return out;
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath();
  g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}
