// Choosing whom to copy on Strike (the Copy Arena's leaderboard, also opened from its card): every trader Strike lets
// you copy, filtered by your budget, the markets you want, how deep you accept a fall, and sorted by what matters,
// with each one's profile (its history kept by Strike City, what its copiers really made, what it holds now) and the
// button that opens it on Strike, where you copy. Strike City never copies anyone.
import { useMemo, useState, type ReactNode } from "react";
import type { Lang } from "../i18n";
import { Sprite } from "../components/AvatarEditor";
import { Icon } from "../components/ui";
import { PART_WEIGHTS, copiersWon, curveOf, traderName, warnings, type CopyDoc, type CopyState, type Part, type Trader } from "./copy";
import { TRAIL_MAX } from "./engine";
import { lookFor } from "./sprites";
import { ticker, type CityText } from "./text";

type Sort = "city" | "score" | "roi" | "dd" | "copiers";
const MARKET_FILTER = ["BTC", "ETH", "SOL", "ADA", "XRP", "NEAR", "ZEC", "HYPE"];
const SHOWN = 30;

export function usd(v: number | null | undefined, lang: Lang, sign = false): string {
  if (v == null) return "—";
  const a = Math.abs(v), loc = lang === "es" ? "es-ES" : "en-US";
  const s = a >= 1e6 ? `${(a / 1e6).toLocaleString(loc, { maximumFractionDigits: 1 })} M` : a >= 1e4 ? `${(a / 1e3).toLocaleString(loc, { maximumFractionDigits: 1 })} k`
    : a.toLocaleString(loc, { maximumFractionDigits: a >= 100 ? 0 : 2 });
  return `${v < 0 ? "−" : sign && v > 0 ? "+" : ""}${s} $`;
}
export function pct(v: number | null | undefined, lang: Lang, sign = true): string {
  if (v == null) return "—";
  const loc = lang === "es" ? "es-ES" : "en-US", a = Math.abs(v * 100);
  return `${v < 0 ? "−" : sign && v > 0 ? "+" : ""}${a.toLocaleString(loc, { maximumFractionDigits: a >= 100 ? 0 : 1 })} %`;
}
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "pos" : "neg");

/** A small line of its equity (every day kept), green when it ends above where it starts. */
export function Spark({ points, w = 120, h = 34, label }: { points: [number, number][]; w?: number; h?: number; label?: string }) {
  if (points.length < 2) return <span className="cp-spark-empty" aria-hidden="true" />;
  const vs = points.map((p) => p[1]), lo = Math.min(...vs), hi = Math.max(...vs), span = hi - lo || 1;
  const d = points.map((p, i) => `${i ? "L" : "M"}${((i / (points.length - 1)) * (w - 2) + 1).toFixed(1)},${(h - 2 - ((p[1] - lo) / span) * (h - 4)).toFixed(1)}`).join(" ");
  const up = vs[vs.length - 1] >= vs[0];
  return (
    <svg className={`cp-spark ${up ? "up" : "down"}`} width={w} height={h} viewBox={`0 0 ${w} ${h}`} role={label ? "img" : undefined}
         aria-label={label} aria-hidden={label ? undefined : true}>
      <path d={`${d} L${w - 1},${h} L1,${h} Z`} className="cp-spark-fill" />
      <path d={d} className="cp-spark-line" />
    </svg>
  );
}

function Face({ id, size = 2 }: { id: string; size?: number }) {
  return <Sprite look={lookFor(`lead:${id}`)} scale={size} className="cp-face" />;
}

export function StrikeStats({ T, lang, doc }: { T: CityText; lang: Lang; doc: CopyDoc }) {
  const C = T.copy, S = doc.strike;
  const items: [string, string][] = [
    [C.strike.allocated, usd(S.allocated, lang)], [C.strike.oi, usd(S.openInterest, lang)],
    [C.strike.volume, usd(S.volume30d, lang)], [C.strike.profits, usd(S.profits30d, lang)],
  ];
  return (
    <dl className="cp-stats">
      {items.map(([k, v]) => <div key={k}><dt>{k}</dt><dd className="num">{v}</dd></div>)}
    </dl>
  );
}

/** The chooser: filters, the ranked list, and a trader's profile when one is open. */
export function CopyChooser({ T, lang, doc, onFollow, initial, compact, onCopy }:
  { T: CityText; lang: Lang; doc: CopyState; onFollow?: (id: string) => void; initial?: string | null; compact?: boolean; onCopy?: (t: Trader) => void }) {
  const C = T.copy;
  const [platform, setPlatform] = useState<"all" | "strike" | "hyperliquid">("all");
  const [budget, setBudget] = useState("");
  const [market, setMarket] = useState("");
  const [risk, setRisk] = useState<number>(0);
  const [sort, setSort] = useState<Sort>("city");
  const [open, setOpen] = useState<string | null>(initial ?? null);
  const d = doc && typeof doc === "object" ? doc : null;

  const list = useMemo(() => {
    if (!d) return [];
    const b = Number(budget.replace(",", "."));
    const xs = d.traders.filter((t) => (platform === "all" || t.platform === platform)
      && (!b || t.recommended == null || t.recommended <= b)
      && (!market || t.assets.includes(market))
      && (!risk || (t.metrics.dd ?? 0) <= risk / 100));
    const key: Record<Sort, (t: Trader) => number> = {
      city: (t) => -(t.city ?? 0), score: (t) => -(t.score ?? 0), roi: (t) => -(t.roi["30d"] ?? -9),
      dd: (t) => (t.metrics.dd ?? 1), copiers: (t) => -(t.copiers.n ? t.copiers.pnl : -1e12),
    };
    return [...xs].sort((a, b2) => key[sort](a) - key[sort](b2));
  }, [d, platform, budget, market, risk, sort]);

  if (!d) return <p className="news-state" role="status">{doc === null ? C.loading : doc === "none" ? C.none : C.error}</p>;
  const t = open ? d.traders.find((x) => x.id === open) : null;
  if (t) return <Profile T={T} lang={lang} t={t} onBack={() => setOpen(null)} onFollow={onFollow} onCopy={onCopy} />;

  return (
    <div className={`cp${compact ? " compact" : ""}`}>
      <p className="cp-lead small muted">{C.lead(d.traders.length, d.counts.active, d.historyDays)}</p>
      {!compact && <StrikeStats T={T} lang={lang} doc={d} />}
      {d.evidence && <Evidence T={T} lang={lang} ev={d.evidence} />}
      {!!d.copyingOthers?.length && <p className="small faint cp-note">{C.leftOut(d.copyingOthers.length)}</p>}
      <div className="cp-filters">
        <div className="cp-seg" role="group" aria-label={C.platform}>
          {(["all", "strike", "hyperliquid"] as const).map((p) => (
            <button key={p} type="button" aria-pressed={platform === p} onClick={() => setPlatform(p)}>{p === "all" ? C.all : p === "strike" ? C.strikeP : C.hl}</button>
          ))}
        </div>
        <label className="cp-field"><span>{C.budget}</span>
          <input type="number" inputMode="decimal" min={0} step={50} value={budget} placeholder="500" onChange={(e) => setBudget(e.target.value)}
                 title={C.budgetHint} aria-describedby="cp-budget-hint" />
        </label>
        <span id="cp-budget-hint" className="sr-only">{C.budgetHint}</span>
        <label className="cp-field"><span>{C.market}</span>
          <select value={market} onChange={(e) => setMarket(e.target.value)}>
            <option value="">{C.anyMarket}</option>
            {MARKET_FILTER.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <label className="cp-field"><span>{C.risk}</span>
          <select value={risk} onChange={(e) => setRisk(Number(e.target.value))}>
            <option value={0}>{C.any}</option>
            {[5, 10, 25].map((p) => <option key={p} value={p}>{C.upTo(p)}</option>)}
          </select>
        </label>
        <label className="cp-field"><span>{C.sort}</span>
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            {(Object.keys(C.sorts) as Sort[]).map((k) => <option key={k} value={k}>{C.sorts[k]}</option>)}
          </select>
        </label>
      </div>
      {!list.length ? <p className="small muted">{C.empty}</p> : (
        <ol className="cp-list">
          {list.slice(0, SHOWN).map((x, i) => {
            const won = copiersWon(x);
            const w = warnings(x).filter((k) => k === "copiersLost" || k === "deep" || k === "fresh");
            return (
              <li key={x.id}>
                <button type="button" className="cp-row" onClick={() => setOpen(x.id)} aria-label={`${C.open}: ${traderName(x)}`}>
                  <span className="cp-rank num">{i + 1}</span>
                  <Face id={x.id} />
                  <span className="cp-who">
                    <b>{traderName(x)}</b>
                    <span className={`cp-plat ${x.platform}`}>{x.platform === "strike" ? "Strike" : "Hyperliquid"}</span>
                    <span className="small faint">{x.assets.slice(0, 3).join(" · ")}</span>
                  </span>
                  <span className="cp-num"><span className="faint small">{C.cityScore}</span><b className="num cp-big">{x.city?.toLocaleString(lang === "es" ? "es-ES" : "en-US", { maximumFractionDigits: 0 }) ?? "—"}</b></span>
                  <span className="cp-num"><span className="faint small">{C.roi30}</span><b className={`num ${tone(x.roi["30d"])}`}>{pct(x.roi["30d"], lang)}</b></span>
                  <span className="cp-num hide-sm"><span className="faint small">{C.dd}</span><b className="num">{x.metrics.dd == null ? "—" : pct(-x.metrics.dd, lang)}</b></span>
                  <span className="cp-num hide-sm"><span className="faint small">{C.parts.copiers}</span>
                    <b className={`num ${won == null ? "" : won >= 0.5 ? "pos" : "neg"}`}>{x.copiers.n ? C.inProfit(x.copiers.won, x.copiers.n) : "—"}</b></span>
                  <span className="hide-sm"><Spark points={curveOf(x)} /></span>
                  {w.length > 0 && <span className="cp-warn" title={w.map((k) => C.warn[k]).join(" · ")} aria-label={w.map((k) => C.warn[k]).join(". ")}>!</span>}
                </button>
              </li>
            );
          })}
        </ol>
      )}
      <p className="small faint cp-note">{onCopy ? C.notePilot : C.note}</p>
    </div>
  );
}

/** A lead selected on the map: what it holds now, what choosing it would mean (its score, its fall, what its copiers
 *  made), and the way to copy it on Strike. */
export function LeadCard({ T, lang, t, following, followIcon, onFollow, onProfile, onClose, onCopy }: { T: CityText; lang: Lang; t: Trader; following: boolean;
  followIcon?: ReactNode; onFollow: () => void; onProfile: () => void; onClose: () => void; onCopy?: () => void }) {
  const C = T.copy, loc = lang === "es" ? "es-ES" : "en-US";
  const won = copiersWon(t);
  const w = warnings(t).filter((k) => k !== "noCopiers");
  const pos = [...(t.positions ?? [])].sort((a, b) => Math.abs(b.size * (b.entry ?? 1)) - Math.abs(a.size * (a.entry ?? 1)));
  const shown = Math.min(TRAIL_MAX, t.copiers.active);
  return (
    <aside className="city-card cp-card" aria-labelledby="lead-card-title">
      <div className="city-card-head">
        <Face id={t.id} size={2} />
        <div className="grow">
          <h2 id="lead-card-title" className="city-card-name mono">{traderName(t)}</h2>
          <p className="faint small">{t.subOf ? C.subOf(t.subOf === "?" ? null : t.subOf) : C.leadWho}</p>
        </div>
        <button type="button" className="icon-btn" aria-label={T.card.close} onClick={onClose}><Icon.close /></button>
      </div>
      <div className="city-card-status">
        <span className="city-tag lead">{C.leadTag}</span>
        <span className={`cp-plat ${t.platform}`}>{t.platform === "strike" ? "Strike" : "Hyperliquid"}</span>
        {t.style && <span className="faint small">{C.styles[t.style]}</span>}
      </div>
      <p className="city-card-label">{C.positions}</p>
      {pos.length ? (
        <ul className="cp-pos">{pos.slice(0, 3).map((p) => (
          <li key={p.market}><b className={p.side === "long" ? "pos" : "neg"}>{p.side === "long" ? "LONG" : "SHORT"}</b> {ticker(p.market)}
            {p.leverage ? <span className="faint"> ×{p.leverage}</span> : null}<span className={`num ${tone(p.upnl)}`}> {usd(p.upnl, lang, true)}</span></li>
        ))}{pos.length > 3 && <li className="faint">{T.card.more(pos.length - 3)}</li>}</ul>
      ) : <p className="city-card-text small muted">{C.noPositions}</p>}
      <dl className="city-kv">
        <div><dt>{C.cityScore}</dt><dd className="num cp-score">{t.city?.toLocaleString(loc, { maximumFractionDigits: 0 }) ?? "—"}</dd></div>
        <div><dt>{C.roi30}</dt><dd className={`num ${tone(t.roi["30d"])}`}>{pct(t.roi["30d"], lang)}</dd></div>
        <div><dt>{C.dd}</dt><dd className="num">{t.metrics.dd == null ? "—" : pct(-t.metrics.dd, lang)}</dd></div>
        {/* who copies it now, apart from every copy it ever had: "3 copiers" read as three people copying it today */}
        <div><dt>{C.copyingNow}</dt><dd className="num">{t.copiers.active}</dd></div>
        <div><dt>{C.copiesAll}</dt><dd className="num">{t.copiers.n || "—"}</dd></div>
      </dl>
      <Spark points={curveOf(t)} w={300} h={40} label={`${C.curve} · ${C.history(Math.max(t.metrics.days, curveOf(t).length))}`} />
      <p className="small cp-card-copiers">
        {t.copiers.n ? <><span className={won == null ? undefined : won >= 0.5 ? "pos" : "neg"}>{C.inProfit(t.copiers.won, t.copiers.n)}</span>
          {" · "}<span className={tone(t.copiers.pnl)}>{C.copiersPnl(usd(t.copiers.pnl, lang, true))}</span></>
          : <span className="muted">{C.noCopiersYet}</span>}
        {shown > 0 && <span className="faint"> · {C.trail(shown, t.copiers.active)}</span>}
      </p>
      {w.length > 0 && <ul className="cp-warns small">{w.slice(0, 2).map((k) => <li key={k}><Icon.alert /> {C.warn[k]}</li>)}</ul>}
      <div className="city-card-actions">
        <button type="button" className="btn btn-ghost" aria-pressed={following} onClick={onFollow}>{followIcon}{following ? T.card.following : T.card.follow}</button>
        <button type="button" className="btn btn-ghost" onClick={onProfile}>{C.open}</button>
        {onCopy && <button type="button" className="btn btn-primary cp-card-copy" onClick={onCopy}>{C.withAgent}</button>}
        <a className={`btn ${onCopy ? "btn-ghost" : "btn-primary"} cp-card-copy`} href={t.url} target="_blank" rel="noopener noreferrer">{C.copyOn} <Icon.external /><span className="sr-only">{C.newTab}</span></a>
      </div>
    </aside>
  );
}

/** Does the score work? The live test on every copy Strike City has seen: the share in profit of the third each score
 *  puts on top, against the average copy. */
export function Evidence({ T, lang, ev }: { T: CityText; lang: Lang; ev: NonNullable<CopyDoc["evidence"]> }) {
  const C = T.copy, E = C.evidence;
  const max = Math.max(ev.top.city, ev.top.strike, ev.base, 0.01);
  const bar = (label: string, v: number, cls: string) => (
    <li className={cls}><span className="cp-ev-name">{label}</span>
      <span className="cp-ev-bar" aria-hidden="true"><span style={{ width: `${(v / max) * 100}%` }} /></span>
      <b className="num">{pct(v, lang, false)}</b></li>
  );
  return (
    <section className="cp-ev" aria-labelledby="cp-ev-title">
      <h4 id="cp-ev-title">{E.title}</h4>
      <p className="small muted">{E.body(ev.copies, ev.leads)}</p>
      <ul>
        {bar(E.city, ev.top.city, "ev-city")}
        {bar(E.strike, ev.top.strike, "ev-strike")}
        {bar(E.base, ev.base, "ev-base")}
      </ul>
      <p className="small faint">{E.auc(ev.auc.city.toLocaleString(lang === "es" ? "es-ES" : "en-US"), ev.auc.strike.toLocaleString(lang === "es" ? "es-ES" : "en-US"))} {E.caveat}</p>
    </section>
  );
}

/** How its Strike City score is made: each part, its weight, and what is not known yet. */
function ScoreParts({ T, lang, parts }: { T: CityText; lang: Lang; parts: Record<Part, number | null> }) {
  const C = T.copy, loc = lang === "es" ? "es-ES" : "en-US";
  return (
    <section className="cp-parts" aria-labelledby="cp-parts-title">
      <h4 id="cp-parts-title">{C.partsTitle}</h4>
      <ul>
        {(Object.keys(PART_WEIGHTS) as Part[]).map((k) => {
          const v = parts[k];
          return (
            <li key={k} className={v == null ? "unknown" : undefined}>
              <span className="cp-part-name">{C.parts[k]} <span className="faint">· {PART_WEIGHTS[k] ? `${PART_WEIGHTS[k]} %` : C.partInfo}</span></span>
              <span className="cp-part-bar" aria-hidden="true"><span style={{ width: `${v ?? 0}%` }} /></span>
              <span className="num cp-part-v">{v == null ? C.partUnknown : v.toLocaleString(loc, { maximumFractionDigits: 0 })}</span>
            </li>
          );
        })}
      </ul>
      <p className="small faint">{C.cityHow}</p>
    </section>
  );
}

function Profile({ T, lang, t, onBack, onFollow, onCopy }: { T: CityText; lang: Lang; t: Trader; onBack: () => void; onFollow?: (id: string) => void;
  onCopy?: (t: Trader) => void }) {
  const C = T.copy, loc = lang === "es" ? "es-ES" : "en-US";
  const won = copiersWon(t);
  const w = warnings(t);
  const ago = (ms: number) => T.ago((Date.now() - ms) / 1000);
  return (
    <div className="cp-profile">
      <button type="button" className="btn btn-ghost cp-back" onClick={onBack}><Icon.back /> {C.back}</button>
      <div className="cp-p-head">
        <Face id={t.id} size={4} />
        <div className="grow">
          <h3>{traderName(t)} <span className={`cp-plat ${t.platform}`}>{t.platform === "strike" ? "Strike" : "Hyperliquid"}</span></h3>
          <p className="small muted">{[t.subOf ? C.subOf(t.subOf === "?" ? null : t.subOf) : null, t.style ? C.styles[t.style] : null,
            t.bias ? C.biases[t.bias] : null].filter(Boolean).join(" · ")}
            {t.lastTrade ? ` · ${ago(t.lastTrade)}` : ""}</p>
        </div>
        <div className="cp-p-score">
          <span className="faint small">{C.cityScore}</span>
          <b className="num">{t.city?.toLocaleString(loc, { maximumFractionDigits: 0 }) ?? "—"}</b>
          <span className="small faint">{C.copyScore}: <span className="num">{t.score ?? "—"}</span></span>
        </div>
      </div>
      <figure className="cp-chart">
        <Spark points={curveOf(t)} w={560} h={120} label={`${C.curve} · ${C.history(Math.max(t.metrics.days, curveOf(t).length))}`} />
        <figcaption className="small faint">{C.curve} · {C.history(Math.max(t.metrics.days, curveOf(t).length))} · {C.historyNote}</figcaption>
      </figure>
      {t.parts && <ScoreParts T={T} lang={lang} parts={t.parts} />}
      {w.length > 0 && <ul className="cp-warns">{w.map((k) => <li key={k}><Icon.alert /> {C.warn[k]}</li>)}</ul>}
      <dl className="cp-grid">
        {(["1d", "7d", "30d", "all"] as const).map((k) => (
          <div key={k}><dt>{C.windows[k]}</dt><dd className={`num ${tone(t.roi[k])}`}>{pct(t.roi[k], lang)}<span className="faint"> · {usd(t.pnl[k], lang, true)}</span></dd></div>
        ))}
        <div><dt>{C.value}</dt><dd className="num">{usd(t.value, lang)}</dd></div>
        <div><dt>{C.volume30}</dt><dd className="num">{usd(t.volume["30d"], lang)}</dd></div>
        <div><dt>{C.dd}</dt><dd className="num">{t.metrics.dd == null ? "—" : pct(-t.metrics.dd, lang)}</dd></div>
        <div><dt>{C.upDays}</dt><dd className="num">{t.metrics.upDays == null ? "—" : pct(t.metrics.upDays, lang, false)}</dd></div>
        <div><dt>{C.assets}</dt><dd>{t.assets.join(" · ") || "—"}</dd></div>
        <div><dt>{C.from}</dt><dd className="num" title={C.recHint}>{usd(t.recommended, lang)}</dd></div>
      </dl>
      <section className="cp-copiers" aria-label={C.copiesAll}>
        <h4>{C.copiesAll}</h4>
        {t.copiers.n ? (
          <p>{C.copiersLine(t.copiers.active, t.copiers.n)} · <span className={won == null ? undefined : won >= 0.5 ? "pos" : "neg"}>{C.inProfit(t.copiers.won, t.copiers.n)}</span>
            {" · "}<span className={tone(t.copiers.pnl)}>{C.copiersPnl(usd(t.copiers.pnl, lang, true))}</span></p>
        ) : <p className="muted">{C.noCopiersYet}</p>}
      </section>
      {t.walks && (
        <section aria-label={C.positions}>
          <h4>{C.positions}</h4>
          {t.positions?.length ? (
            <ul className="cp-pos">{t.positions.slice(0, 8).map((p) => (
              <li key={p.market}><b className={p.side === "long" ? "pos" : "neg"}>{p.side === "long" ? "LONG" : "SHORT"}</b> {ticker(p.market)}
                {p.leverage ? <span className="faint"> ×{p.leverage}</span> : null}
                <span className={`num ${tone(p.upnl)}`}> {usd(p.upnl, lang, true)}</span></li>
            ))}</ul>
          ) : <p className="small muted">{C.noPositions}</p>}
          {!!t.events?.length && (
            <>
              <h4>{C.moves}</h4>
              <ul className="cp-pos">{t.events.slice(0, 6).map((e, i) => (
                <li key={i}><span className="faint">{ago(e.t)}</span> {C.kinds[e.kind]} {e.side === "long" ? "LONG" : "SHORT"} {ticker(e.market)}</li>
              ))}</ul>
            </>
          )}
        </section>
      )}
      <div className="cp-actions">
        {onCopy && <button type="button" className="btn btn-primary" onClick={() => onCopy(t)}>{C.withAgent}</button>}
        <a className={`btn ${onCopy ? "btn-ghost" : "btn-primary"}`} href={t.url} target="_blank" rel="noopener noreferrer">{C.copyOn} <Icon.external /><span className="sr-only">{C.newTab}</span></a>
        {t.walks && onFollow && <button type="button" className="btn btn-ghost" onClick={() => onFollow(t.id)}>{C.follow}</button>}
      </div>
      <p className="small faint cp-note">{onCopy ? C.notePilot : C.note}</p>
    </div>
  );
}
