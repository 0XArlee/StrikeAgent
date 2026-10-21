// A strategy's backtest, drawn in the city's own language: the account curve as a stepped pixel line, and the figures
// that matter to whoever picks it. Used by the catalog cards and by each strategy's page.
import type { Dict, Lang } from "../i18n";
import { STRATEGY_DATA, type StrategyId } from "../strategies";
import { Tip } from "./ui";

/** The account curve as pixel steps (one per month), crisp at any size. */
export function PixelCurve({ points, label, height = 76 }: { points: number[]; label: string; height?: number }) {
  const w = 300, h = height, pad = 3;
  const min = Math.min(...points), max = Math.max(...points);
  const step = (w - 2 * pad) / points.length;
  const y = (v: number) => Math.round(h - pad - ((v - min) / (max - min || 1)) * (h - 2 * pad));
  let d = `M${pad},${y(points[0])}`;
  points.forEach((v, i) => { d += ` V${y(v)} H${(pad + (i + 1) * step).toFixed(1)}`; });
  const area = `${d} V${h} H${pad} Z`;
  const up = points[points.length - 1] >= points[0];
  return (
    <svg className={`pixel-curve ${up ? "up" : "down"}`} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label={label} shapeRendering="crispEdges">
      <path className="pc-area" d={area} />
      <path className="pc-line" d={d} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function curveLabel(id: StrategyId, lang: Lang): string {
  const s = STRATEGY_DATA[id];
  const nf = (v: number) => v.toLocaleString(lang === "es" ? "es-ES" : "en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const first = s.equity_curve[0][0], last = s.equity_curve[s.equity_curve.length - 1][0];
  const end = s.equity_curve[s.equity_curve.length - 1][1];
  return lang === "es"
    ? `Curva de la cuenta simulada de ${first} a ${last}: de 1,00 a ${nf(end)} veces el capital inicial`
    : `Simulated account curve from ${first} to ${last}: from 1.00 to ${nf(end)} times the starting capital`;
}

/** The full figures of one strategy (its page). */
export function StrategyFigures({ id, t, lang }: { id: StrategyId; t: Dict; lang: Lang }) {
  const s = STRATEGY_DATA[id];
  const nf = (v: number, d = 2) => v.toLocaleString(lang === "es" ? "es-ES" : "en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const sign = lang === "es" ? " %" : "%";
  return (
    <article className="figures" aria-labelledby={`fig-${id}`}>
      <h2 id={`fig-${id}`} className="figures-title">{t.detail.figures}</h2>
      <div className="figures-top">
        <div><div className="figures-big num pos">+{nf(s.avg_r)}R</div><div className="kpi-label"><Tip label={t.card.avgR} text={t.card.avgRTip} /></div></div>
        <div><div className="figures-big num">{nf(s.cagr_pct, 1)}{sign}</div><div className="kpi-label"><Tip label={t.card.cagr} text={t.card.cagrTip} /></div></div>
        <div><div className="figures-big num neg">−{nf(s.equity_max_dd_pct, 1)}{sign}</div><div className="kpi-label"><Tip label={t.card.dd} text={t.card.ddTip} /></div></div>
      </div>
      <PixelCurve points={s.equity_curve.map((p) => p[1])} label={curveLabel(id, lang)} height={120} />
      <dl className="rows">
        <div className="row"><dt>{t.card.ci}</dt><dd className="num">{nf(s.ci95[0])}R … {nf(s.ci95[1])}R</dd></div>
        <div className="row"><dt>{t.card.win}</dt><dd className="num">{nf(100 * s.win_rate, 0)}{sign}</dd></div>
        <div className="row"><dt><Tip label={t.card.pf} text={t.card.pfTip} /></dt><dd className="num">{nf(s.profit_factor)}</dd></div>
        <div className="row"><dt>{t.card.trades}</dt><dd className="num">{s.trades_per_year}</dd></div>
        <div className="row"><dt>{t.detail.sample}</dt><dd className="num">{s.trades}</dd></div>
      </dl>
      <p className="disclaimer">{t.card.disclaimer}</p>
    </article>
  );
}
