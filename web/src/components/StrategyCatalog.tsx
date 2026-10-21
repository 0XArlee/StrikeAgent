// The catalog: one card per strategy of the registry (config/strategies.json), with what someone needs to choose:
// what it does, its account curve and figures at the default risk, its markets and its risk cap. A new strategy in the
// registry shows up here with no other change.
import type { AppInfo } from "../api";
import { fmt, type Dict, type Lang } from "../i18n";
import { CATALOG, STRATEGY_DATA, strategyText, type StrategyDef, type StrategyId } from "../strategies";
import { PixelCurve, curveLabel } from "./StrategyCard";

interface Props { t: Dict; lang: Lang; info: AppInfo; onUse: (id: StrategyId) => void; headingId: string }

export function StrategyCatalog({ t, lang, info, onUse, headingId }: Props) {
  const C = t.catalog;
  const loc = lang === "es" ? "es-ES" : "en-US";
  const nf = (v: number, d = 1) => v.toLocaleString(loc, { minimumFractionDigits: d, maximumFractionDigits: d });
  const sign = lang === "es" ? " %" : "%";
  const pct = (v: number) => `${nf(v, v % 1 ? 1 : 0)}${sign}`;
  const tf = (s: StrategyDef) => (s.timeframe === "240" ? "4h" : s.timeframe === "60" ? "1h" : s.timeframe === "1D" ? "1D" : s.timeframe);
  const live = CATALOG.filter((s) => s.status === "live");
  const soon = CATALOG.filter((s) => s.status === "soon");
  return (
    <div className="catalog" data-reveal-group>
      {live.map((s) => {
        const f = STRATEGY_DATA[s.id];
        const tx = strategyText(s.id, lang);
        return (
          <article key={s.id} className="strat" aria-labelledby={`${headingId}-${s.id}`}>
            <header className="strat-head">
              <h3 id={`${headingId}-${s.id}`} className="strat-name"><a href={`#/strategy/${s.id}`}>{s.name}</a></h3>
              <span className="strat-chips">
                <span className="chip">{tf(s)}</span>
                {s.max_stack > 1 && <span className="chip chip-stack">{fmt(C.stack, { n: String(s.max_stack) })}</span>}
              </span>
            </header>
            <p className="strat-summary">{tx.summary}</p>
            <PixelCurve points={f.equity_curve.map((p) => p[1])} label={curveLabel(s.id, lang)} />
            <dl className="strat-figs">
              <div><dt>{C.year}</dt><dd className="num pos">{nf(f.cagr_pct)}{sign}</dd></div>
              <div><dt>{C.dd}</dt><dd className="num neg">−{nf(f.equity_max_dd_pct)}{sign}</dd></div>
              <div><dt>{C.trades}</dt><dd className="num">{f.trades_per_year}</dd></div>
              <div><dt>{C.avgR}</dt><dd className="num">+{nf(f.avg_r, 2)}R</dd></div>
            </dl>
            <p className="strat-meta">
              <span>{s.markets.core.map((m) => m.replace("-USD", "")).join(", ")}</span>
              <span>{fmt(C.maxRisk, { max: pct(info.riskPresets[s.max_risk]) })}</span>
            </p>
            <div className="strat-actions">
              <button type="button" className="btn btn-primary" onClick={() => onUse(s.id)}>{C.use}</button>
              <a className="btn btn-ghost" href={`#/strategy/${s.id}`}>{C.view}</a>
            </div>
          </article>
        );
      })}
      {soon.map((s) => (
        <article key={s.id} className="strat strat-soon" aria-labelledby={`${headingId}-${s.id}`}>
          <h3 id={`${headingId}-${s.id}`} className="strat-name">{s.name}</h3>
          <p className="strat-summary">{strategyText(s.id, lang).summary}</p>
          <p className="strat-meta"><span>{C.soonBadge}</span></p>
        </article>
      ))}
      <aside className="strat strat-more" aria-label={C.moreTitle}>
        <span className="strat-more-mark" aria-hidden="true">+</span>
        <div><h3 className="strat-name">{C.moreTitle}</h3><p className="strat-summary">{C.moreText}</p></div>
      </aside>
    </div>
  );
}
