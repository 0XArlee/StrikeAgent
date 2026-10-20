// Character creator: a live, walking preview and the options of the look (body, hair, clothes, accessories). Every
// style tile shows the character wearing that option; every colour has a palette plus a free colour picker.
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  BACK_STYLES, BOTTOM_STYLES, CLOTHES, EYES, FACE_STYLES, HAIRS, HAIR_STYLES, HEAD_STYLES, SKINS, TOP_STYLES,
  randomLook, type Look, type Swatch,
} from "../city/look";
import { mulberry } from "../city/rand";
import { buildSprites, type Dir } from "../city/sprites";
import type { Dict, Lang } from "../i18n";
import { Icon } from "./ui";

type Tab = "body" | "hair" | "clothes" | "extras";
const TABS: Tab[] = ["body", "hair", "clothes", "extras"];
const DIRS: Dir[] = ["down", "left", "up", "right"];
const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function Sprite({ look, dir = "down", frame = 0, scale, className }: { look: Look; dir?: Dir; frame?: number; scale: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const g = c.getContext("2d")!;
    g.imageSmoothingEnabled = false;
    g.clearRect(0, 0, c.width, c.height);
    g.drawImage(buildSprites(look)[dir][frame], 0, 0, 12 * scale, 16 * scale);
  }, [look, dir, frame, scale]);
  return <canvas ref={ref} width={12 * scale} height={16 * scale} className={className} aria-hidden="true" />;
}

export function AvatarEditor({ t, lang, value, onChange, idPrefix = "av" }: { t: Dict; lang: Lang; value: Look; onChange: (l: Look) => void; idPrefix?: string }) {
  const A = t.avatar;
  const [tab, setTab] = useState<Tab>("body");
  const [dir, setDir] = useState(0);
  const [walk, setWalk] = useState(!reduced);
  const [frame, setFrame] = useState(0);
  const rolls = useRef(1);
  useEffect(() => {
    if (!walk) { setFrame(0); return; }
    const id = window.setInterval(() => setFrame((f) => 1 - f), 260);
    return () => clearInterval(id);
  }, [walk]);
  const set = (patch: Partial<Look>) => onChange({ ...value, ...patch });
  const name = (s: Swatch) => (lang === "es" ? s.es : s.en);

  const onTabKey = (e: KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = TABS.indexOf(tab), n = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    setTab(n);
    document.getElementById(`${idPrefix}-tab-${n}`)?.focus();
    e.preventDefault();
  };

  // plain render helpers, not components: a component defined here would remount on every change and drop focus
  function styles<K extends keyof Look>(field: K, options: readonly string[], legend: string) {
    return (
      <fieldset className="av-group" key={String(field)}>
        <legend>{legend}</legend>
        <div className="av-tiles">
          {options.map((o) => (
            <label key={o} className="av-tile">
              <input type="radio" name={`${idPrefix}-${String(field)}`} value={o} checked={value[field] === o} onChange={() => set({ [field]: o } as Partial<Look>)} />
              <span><Sprite look={{ ...value, [field]: o } as Look} scale={3} /><small>{A.styles[o] ?? o}</small></span>
            </label>
          ))}
        </div>
      </fieldset>
    );
  }

  function colors<K extends keyof Look>(field: K, swatches: Swatch[], legend: string) {
    const cur = String(value[field]).toLowerCase();
    const custom = !swatches.some((s) => s.hex === cur);
    return (
      <fieldset className="av-group" key={String(field)}>
        <legend>{legend}</legend>
        <div className="av-swatches">
          {swatches.map((s) => (
            <label key={s.hex} className="av-swatch" title={name(s)}>
              <input type="radio" name={`${idPrefix}-${String(field)}`} value={s.hex} checked={cur === s.hex} onChange={() => set({ [field]: s.hex } as Partial<Look>)} />
              <span style={{ background: s.hex }}><span className="sr-only">{name(s)}</span></span>
            </label>
          ))}
          <label className={`av-swatch av-custom${custom ? " on" : ""}`} title={A.custom}>
            <input type="color" value={cur} onChange={(e) => set({ [field]: e.target.value.toLowerCase() } as Partial<Look>)} />
            <span style={custom ? { background: cur } : undefined}><span className="sr-only">{`${A.custom}: ${legend}`}</span></span>
          </label>
        </div>
      </fieldset>
    );
  }

  return (
    <div className="av">
      <div className="av-stage">
        <p className="av-stage-title">{A.preview}</p>
        <div className="av-stage-art">
          <Sprite look={value} dir={DIRS[dir]} frame={frame} scale={12} className="av-big" />
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
            {colors("skin", SKINS, A.skin)}
            {colors("eyes", EYES, A.eyes)}
          </>}
          {tab === "hair" && <>
            {styles("hair", HAIR_STYLES, A.hairStyle)}
            {colors("hairColor", HAIRS, A.hairColor)}
          </>}
          {tab === "clothes" && <>
            {styles("top", TOP_STYLES, A.top)}
            {colors("topColor", CLOTHES, A.topColor)}
            {colors("top2", CLOTHES, A.top2)}
            {colors("accent", CLOTHES, A.accent)}
            {styles("bottom", BOTTOM_STYLES, A.bottom)}
            {colors("pants", CLOTHES, A.pants)}
            {colors("shoes", CLOTHES, A.shoes)}
          </>}
          {tab === "extras" && <>
            {styles("face", FACE_STYLES, A.face)}
            {value.face !== "none" && colors("faceColor", CLOTHES, A.faceColor)}
            {styles("head", HEAD_STYLES, A.head)}
            {value.head !== "none" && colors("headColor", CLOTHES, A.headColor)}
            {styles("back", BACK_STYLES, A.back)}
            {value.back !== "none" && colors("backColor", CLOTHES, A.backColor)}
          </>}
        </div>
      </div>
    </div>
  );
}
