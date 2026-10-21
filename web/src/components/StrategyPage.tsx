// One strategy's page (#/strategy/<id>): what it does and its rules, its full backtest, the markets it trades and the
// risk it allows, and the way to use it. Everything comes from its registry entry and its figures.
import { useEffect, useRef, type Ref } from "react";
import type { AppInfo } from "../api";
import { fmt, type Dict, type Lang } from "../i18n";
import { CATALOG, RISK_ORDER, STRATEGY_DATA, riskAllowed, strategyDef, strategyText, type StrategyId } from "../strategies";
import { StrategyFigures } from "./StrategyCard";
import { Icon } from "./ui";

interface Props { id: StrategyId; t: Dict; lang: Lang; info: AppInfo; onUse: (id: StrategyId) => void; ctaRef?: Ref<HTMLButtonElement> }

export function StrategyPage({ id, t, lang, info, onUse, ctaRef }: Props) {
  const D = t.detail;
  const s = strategyDef(id);
  const tx = strategyText(id, lang);
  const f = STRATEGY_DATA[id];
  const title = useRef<HTMLHeadingElement>(null);
  const loc = lang === "es" ? "es-ES" : "en-US";
  const pct = (v: number, d = 0) => `${v.toLocaleString(loc, { minimumFractionDigits: d, maximumFractionDigits: 2 })}${lang === "es" ? " %" : "%"}`;
  // a new page: from the top, and the screen reader starts at its title
  useEffect(() => { window.scrollTo(0, 0); title.current?.focus(); }, [id]);
  const others = CATALOG.filter((x) => x.status === "live" && x.id !== id);
  return (
    <div className="spage">
      <section className="spage-hero" aria-labelledby="spage-title">
        <div className="container">
          <a className="spage-back" href="#strategies">{D.back}</a>
          <h1 id="spage-title" ref={title} tabIndex={-1}>{s.name}</h1>
          <p className="spage-lead">{tx.tagline}</p>
          <div className="spage-cta">
            <button ref={ctaRef} type="button" className="btn btn-primary btn-lg" onClick={() => onUse(id)}>{t.catalog.use}</button>
            <p className="hero-balance"><Icon.alert />{t.balance.hero}</p>
          </div>
        </div>
      </section>
      <section className="section" aria-labelledby="spage-rules">
        <div className="container spage-grid">
          <div>
            <h2 id="spage-rules" className="spage-h2">{D.rules}</h2>
            <dl className="rules">
              {tx.details.map(([h, p]) => <div key={h}><dt>{h}</dt><dd>{p}</dd></div>)}
            </dl>
            <h2 className="spage-h2">{D.setup}</h2>
            <dl className="rows">
              <div className="row"><dt>{D.markets}</dt><dd>{f.markets.map((m) => m.replace("-USD", "")).join(", ")}</dd></div>
              <div className="row"><dt>{D.candles}</dt><dd>{s.timeframe === "240" ? "4h" : s.timeframe}</dd></div>
              {s.max_stack > 1 && <div className="row"><dt>{D.stacking}</dt><dd>{fmt(t.catalog.stack, { n: String(s.max_stack) })}</dd></div>}
              <div className="row"><dt>{D.risk}</dt><dd>{RISK_ORDER.filter((r) => riskAllowed(id, r)).map((r) => `${t.modal.riskNames[r]} ${pct(info.riskPresets[r])}`).join(" · ")}</dd></div>
              <div className="row"><dt>{D.fee}</dt><dd>{pct((info.live?.feeBps ?? info.feeBps) / 100, 2)} {D.perFill}</dd></div>
            </dl>
            {tx.risk_note && <p className="field-hint" style={{ marginTop: 10 }}>{fmt(t.strategies.riskCap, { name: s.name, max: pct(info.riskPresets[s.max_risk]), note: tx.risk_note })}</p>}
          </div>
          <StrategyFigures id={id} t={t} lang={lang} />
        </div>
      </section>
      {others.length > 0 && (
        <section className="section" aria-labelledby="spage-others">
          <div className="container">
            <h2 id="spage-others" className="spage-h2">{D.others}</h2>
            <ul className="spage-others">
              {others.map((o) => (
                <li key={o.id}><a href={`#/strategy/${o.id}`}><strong>{o.name}</strong><span>{strategyText(o.id, lang).summary}</span></a></li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </div>
  );
}
