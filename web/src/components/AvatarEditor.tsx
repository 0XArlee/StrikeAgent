// Character creator: a live, animated preview and the pieces of the look (LimeZu's character generator: skin, eyes,
// outfit, hairstyle, accessory). Style tiles come from one pre-composed strip per part (instant); colours are the
// variants the artist drew for that style. Changing style keeps the nearest colour.
import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { NONE, PIECES, randomLook, stylesOf, type Look, type Part, type Piece } from "../city/look";
import { mulberry } from "../city/rand";
import { FEET, FH, FW, HEAD_TOP, drawFrame, onSheet, sheetOf, thumbsUrl, type Anim, type Dir } from "../city/sprites";
import type { Dict, Lang } from "../i18n";
import { Icon } from "./ui";

type Tab = "body" | "hair" | "clothes" | "extras";
const TABS: Tab[] = ["body", "hair", "clothes", "extras"];
const DIRS: Dir[] = ["down", "left", "up", "right"];
const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const VIS_H = FEET + 1 - HEAD_TOP;   // the visible character: from the top of its head to its feet (16 x 22 art px)

/** A character, drawn from its look's sheet (and redrawn once its pieces load); animated when `anim` moves. */
export function Sprite({ look, dir = "down", anim = "idle", play = false, scale, className }:
  { look: Look; dir?: Dir; anim?: Anim; play?: boolean; scale: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let raf = 0;
    const t0 = performance.now();
    const draw = () => {
      const c = ref.current, sheet = sheetOf(look);
      if (!c) return;
      const g = c.getContext("2d")!;
      g.imageSmoothingEnabled = false;
      g.clearRect(0, 0, c.width, c.height);
      if (sheet) drawFrame(g, sheet, anim, dir, play && !reduced ? (performance.now() - t0) / 1000 : 0, c.width / 2, (FEET + 1 - HEAD_TOP) * scale - scale, scale);
      if (play && !reduced) raf = requestAnimationFrame(draw);
    };
    draw();
    const off = onSheet(() => { if (!play || reduced) draw(); });
    return () => { cancelAnimationFrame(raf); off(); };
  }, [look, dir, anim, play, scale]);
  return <canvas ref={ref} width={FW * scale} height={VIS_H * scale} className={className} aria-hidden="true" />;
}

// a tile's picture: that piece on a default character, cut from its part's strip (scale k, from the head down)
function thumbStyle(part: Part, index: number, k: number, top = HEAD_TOP, h = VIS_H): CSSProperties {
  const n = PIECES[part].length;
  return {
    width: FW * k, height: h * k, backgroundImage: `url(${thumbsUrl(part)})`, backgroundRepeat: "no-repeat",
    backgroundSize: `${n * FW * k}px ${FH * k}px`, backgroundPosition: `${-index * FW * k}px ${-top * k}px`, imageRendering: "pixelated",
  };
}
const indexOf = (part: Part, id: string) => PIECES[part].findIndex((p) => p.id === id);
const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const near = (pieces: Piece[], hex: string) => pieces.reduce((a, b) => {
  const [x, y, z] = [rgb(a.rgb), rgb(b.rgb), rgb(hex)];
  return (y[0] - z[0]) ** 2 + (y[1] - z[1]) ** 2 + (y[2] - z[2]) ** 2 < (x[0] - z[0]) ** 2 + (x[1] - z[1]) ** 2 + (x[2] - z[2]) ** 2 ? b : a;
});

export function AvatarEditor({ t, lang, value, onChange, idPrefix = "av" }: { t: Dict; lang: Lang; value: Look; onChange: (l: Look) => void; idPrefix?: string }) {
  const A = t.avatar;
  const [tab, setTab] = useState<Tab>("body");
  const [dir, setDir] = useState(0);
  const [walk, setWalk] = useState(!reduced);
  const rolls = useRef(1);
  const set = (patch: Partial<Look>) => onChange({ ...value, ...patch });
  const groups = useMemo(() => ({ hair: stylesOf("hair"), outfit: stylesOf("outfit"), acc: stylesOf("acc") }), []);
  const accName = (name?: string) => (name ? (A.accNames as Record<string, string>)[name] ?? name : "");
  void lang;

  const onTabKey = (e: KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = TABS.indexOf(tab), n = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    setTab(n);
    document.getElementById(`${idPrefix}-tab-${n}`)?.focus();
    e.preventDefault();
  };

  // plain render helpers, not components: a component defined here would remount on every change and drop focus
  /** Pieces shown one per tile (skin tones, eyes). */
  function pieceTiles(part: "body" | "eyes", legend: string, label: (i: number) => string) {
    const eyes = part === "eyes";
    return (
      <fieldset className="av-group" key={part}>
        <legend>{legend}</legend>
        <div className={`av-tiles${eyes ? " av-tiles-face" : ""}`}>
          {PIECES[part].map((p, i) => (
            <label key={p.id} className="av-tile">
              <input type="radio" name={`${idPrefix}-${part}`} value={p.id} checked={value[part] === p.id} onChange={() => set({ [part]: p.id } as Partial<Look>)} />
              <span><i style={eyes ? thumbStyle(part, i, 5, 15, 7) : thumbStyle(part, i, 2)} aria-hidden="true" /><small>{label(i)}</small></span>
            </label>
          ))}
        </div>
      </fieldset>
    );
  }

  /** A part with styles and their colour variants (hairstyles, outfits, accessories); hair and acc can be none. */
  function styleTiles(part: "hair" | "outfit" | "acc", legend: string, colourLegend: string, noneLabel?: string) {
    const list = groups[part];
    const cur = value[part];
    const curPiece = PIECES[part].find((p) => p.id === cur);
    const curStyle = curPiece?.style ?? NONE;
    const pickStyle = (style: string) => {
      if (style === NONE) { set({ [part]: NONE } as Partial<Look>); return; }
      const g = list.find((x) => x.style === style)!;
      set({ [part]: (curPiece ? near(g.pieces, curPiece.rgb) : g.pieces[0]).id } as Partial<Look>);
    };
    const group = list.find((x) => x.style === curStyle);
    return (
      <div key={part} style={{ display: "grid", gap: 16 }}>
        <fieldset className="av-group">
          <legend>{legend}</legend>
          <div className="av-tiles">
            {noneLabel && (
              <label className="av-tile">
                <input type="radio" name={`${idPrefix}-${part}`} value={NONE} checked={curStyle === NONE} onChange={() => pickStyle(NONE)} />
                <span><i className="av-none" aria-hidden="true" /><small>{noneLabel}</small></span>
              </label>
            )}
            {list.map((g, n) => (
              <label key={g.style} className="av-tile">
                <input type="radio" name={`${idPrefix}-${part}`} value={g.style} checked={curStyle === g.style} onChange={() => pickStyle(g.style)} />
                <span><i style={thumbStyle(part, indexOf(part, g.pieces[0].id), 2)} aria-hidden="true" />
                  <small>{part === "acc" ? accName(g.name) : `${A.style} ${n + 1}`}</small></span>
              </label>
            ))}
          </div>
        </fieldset>
        {group && group.pieces.length > 1 && (
          <fieldset className="av-group">
            <legend>{colourLegend}</legend>
            <div className="av-swatches">
              {group.pieces.map((p, n) => (
                <label key={p.id} className="av-swatch" title={`${A.colour} ${n + 1}`}>
                  <input type="radio" name={`${idPrefix}-${part}-colour`} value={p.id} checked={cur === p.id} onChange={() => set({ [part]: p.id } as Partial<Look>)} />
                  <span style={{ background: p.rgb }}><span className="sr-only">{`${colourLegend}: ${A.colour} ${n + 1}`}</span></span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
      </div>
    );
  }

  return (
    <div className="av">
      <div className="av-stage">
        <p className="av-stage-title">{A.preview}</p>
        <div className="av-stage-art">
          <Sprite look={value} dir={DIRS[dir]} anim={walk ? "walk" : "idle"} play scale={8} className="av-big" />
          <span className="av-shadow" aria-hidden="true" />
        </div>
        <div className="av-stage-actions">
          <button type="button" className="btn btn-ghost" onClick={() => setDir((d) => (d + 1) % 4)}><Icon.back />{A.turn}</button>
          <button type="button" className="btn btn-ghost" aria-pressed={walk} onClick={() => setWalk((w) => !w)}>{walk ? <Icon.pause /> : <Icon.play />}{A.walk}</button>
          <button type="button" className="btn btn-ghost" onClick={() => onChange(randomLook(mulberry(Date.now() + rolls.current++ * 7919)))}>{A.random}</button>
        </div>
      </div>
      <div className="av-controls">
        <div className="av-tabs" role="tablist" aria-label={A.title} onKeyDown={onTabKey}>
          {TABS.map((k) => (
            <button key={k} id={`${idPrefix}-tab-${k}`} type="button" role="tab" aria-selected={tab === k} aria-controls={`${idPrefix}-panel`}
                    tabIndex={tab === k ? 0 : -1} onClick={() => setTab(k)}>{A.tabs[k]}</button>
          ))}
        </div>
        <div id={`${idPrefix}-panel`} role="tabpanel" aria-labelledby={`${idPrefix}-tab-${tab}`} className="av-panel" tabIndex={0}>
          {tab === "body" && <>
            {pieceTiles("body", A.skin, (i) => `${A.tone} ${i + 1}`)}
            {pieceTiles("eyes", A.eyes, (i) => `${A.eyesN} ${i + 1}`)}
          </>}
          {tab === "hair" && styleTiles("hair", A.hairStyle, A.hairColor, A.noHair)}
          {tab === "clothes" && styleTiles("outfit", A.outfit, A.outfitColor)}
          {tab === "extras" && styleTiles("acc", A.acc, A.accColor, A.none)}
          <p className="av-credit">{A.credit}</p>
        </div>
      </div>
    </div>
  );
}
