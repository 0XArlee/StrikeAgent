import { useState } from "react";
import type { Dict, Lang } from "../i18n";
import { STRATEGY_DATA, STRATEGY_IDS, type StrategyId } from "../strategies";
import { Mark, Tip } from "./ui";

function Sparkline({ points, label }: { points: number[]; label: string }) {
  const w = 300, h = 76, pad = 4;
  const min = Math.min(...points), max = Math.max(...points);
  const x = (i: number) => pad + (i / (points.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - min) / (max - min || 1)) * (h - 2 * pad);
  const d = points.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${d} L${x(points.length - 1).toFixed(1)},${h} L${x(0).toFixed(1)},${h} Z`;
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <defs>
        <linearGradient id="sf-area" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#4efab0" stopOpacity=".22" />
          <stop offset="1" stopColor="#4efab0" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#sf-area)" />
      <path d={d} fill="none" stroke="#4efab0" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function StrategyCard({ t, lang }: { t: Dict; lang: Lang }) {
  const [id, setId] = useState<StrategyId>("smartflow");   // the two strategies a user can pick, same method
  const s = STRATEGY_DATA[id];
  const nf = (v: number, d = 2) => v.toLocaleString(lang === "es" ? "es-ES" : "en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const curve = s.equity_curve.map((p) => p[1] as number);
  const first = s.equity_curve[0][0] as string, last = s.equity_curve[s.equity_curve.length - 1][0] as string;
  const spark = lang === "es"
    ? `Curva de la cuenta simulada de ${first} a ${last}: de 1,00 a ${nf(curve[curve.length - 1])} veces el capital inicial`
    : `Simulated account curve from ${first} to ${last}: from 1.00 to ${nf(curve[curve.length - 1])} times the starting capital`;
  return (
    <article className="card card-raised" aria-labelledby="sc-title">
      <div className="card-head">
        <span className="avatar"><Mark size={32} /></span>
        <div>
          <h2 id="sc-title" className="card-title">{t.strategies.names[id]} · 4h</h2>
          <p className="card-sub" style={{ marginTop: 0 }}>{t.card.sub}</p>
        </div>
      </div>
      <div className="seg seg-sm" role="radiogroup" aria-label={t.strategies.label}>
        {STRATEGY_IDS.map((k) => (
          <label key={k}>
            <input type="radio" name="sc-strategy" value={k} checked={id === k} onChange={() => setId(k)} />
            <span>{t.strategies.names[k]}</span>
          </label>
        ))}
      </div>
      <p className="card-sub sc-tagline">{t.strategies.taglines[id]}</p>
      <div className="kpi-top">
        <div>
          <div className="kpi-big num pos">+{nf(s.avg_r)}R</div>
          <div className="kpi-label"><Tip label={t.card.avgR} text={t.card.avgRTip} /></div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="kpi-big num">{nf(s.cagr_pct, 1)}%</div>
          <div className="kpi-label"><Tip label={t.card.cagr} text={t.card.cagrTip} /></div>
        </div>
      </div>
      <Sparkline points={curve} label={spark} />
      <dl className="rows">
        <div className="row"><dt>{t.card.ci}</dt><dd className="num">{nf(s.ci95[0])}R … {nf(s.ci95[1])}R</dd></div>
        <div className="row"><dt>{t.card.win}</dt><dd className="num">{nf(100 * s.win_rate, 0)}%</dd></div>
        <div className="row"><dt><Tip label={t.card.pf} text={t.card.pfTip} /></dt><dd className="num">{nf(s.profit_factor)}</dd></div>
        <div className="row"><dt><Tip label={t.card.dd} text={t.card.ddTip} /></dt><dd className="num neg">−{nf(s.equity_max_dd_pct, 1)}%</dd></div>
        <div className="row"><dt>{t.card.trades}</dt><dd className="num">{s.trades_per_year}</dd></div>
      </dl>
      <p className="disclaimer">{t.card.disclaimer}</p>
    </article>
  );
}
