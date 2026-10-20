// A live agent's Strike account: what its owner sees in My agent (amounts) and everyone else in the city (shares of the
// account, see web/server/agents.ts publicPortfolio). P&L follows Strike's mark prices live between account reads.
import { useEffect, useState } from "react";
import type { Lang } from "../i18n";

import { accountResult, type PfPosition, type Portfolio } from "./portfolio-types";
export type { PfFill, PfOrder, PfPosition, Portfolio } from "./portfolio-types";

const TXT = {
  en: {
    equity: "Account equity", since: "since it connected", ret: "Result since it connected", upnl: "Open P&L", available: "Available",
    margin: "Margin in use", tradingFees: "Strike fees", builderFee: "Smart Flow fee (est.)", nPositions: "Open positions", nOrders: "Orders on the book",
    chart: "Account over time", chartSoon: "The chart fills in as the agent runs: one point every 5 minutes.",
    positions: "Open positions", noPositions: "No open position.", orders: "Orders on the book", noOrders: "No pending order.",
    fills: "Latest fills", noFills: "No fill yet.", entry: "Entry", mark: "Price now", stop: "Stop", noStop: "none",
    liq: "Liquidation", none: "none", lev: "Leverage", opened: "Opened", weight: "Size vs account", move: "Price move",
    funding: "Funding", onlyCloses: "only closes", buy: "BUY", sell: "SELL", pnl: "P&L", fee: "fee",
    why: "Where the result comes from", whyTrades: "The agent's trades (net of fees)", whyFees: "Strike fees", whyOpen: "Open positions",
    whyTests: "Test trades (net of fees)", whyTestsHint: "The ones you asked for with Test my agent: they never count in the agent's statistics.",
    whyOutside: "Trades outside the agent (net of fees)", test: "test",
    whyOther: "Other account movements", whyOtherHint: "Funding and rewards: what changes the balance without being a trade.",
    whyFlows: "Deposits and withdrawals", whyFlowsHint: "Money you moved in or out of the account: never part of the result.",
    whyTotal: "Result since it connected", outside: "outside the agent",
    updated: (ago: string) => `Account read ${ago} ago · P&L moves with live Strike prices`,
    publicNote: "Amounts are shown only to the owner: here, results as a share of the account.",
    types: { stop: "Stop", stop_market: "Stop", limit: "Limit", market: "Market", take_profit: "Take profit" } as Record<string, string>,
  },
  es: {
    equity: "Equity de la cuenta", since: "desde que se conectó", ret: "Resultado desde que se conectó", upnl: "Resultado abierto", available: "Disponible",
    margin: "Margen en uso", tradingFees: "Comisiones de Strike", builderFee: "Comisión Smart Flow (estim.)", nPositions: "Posiciones abiertas", nOrders: "Órdenes en el libro",
    chart: "Evolución de la cuenta", chartSoon: "La gráfica se va llenando mientras el agente funciona: un punto cada 5 minutos.",
    positions: "Posiciones abiertas", noPositions: "Ninguna posición abierta.", orders: "Órdenes en el libro", noOrders: "Ninguna orden pendiente.",
    fills: "Últimas ejecuciones", noFills: "Todavía ninguna ejecución.", entry: "Entrada", mark: "Precio ahora", stop: "Stop", noStop: "sin stop",
    liq: "Liquidación", none: "no", lev: "Apalancamiento", opened: "Abierta", weight: "Tamaño vs cuenta", move: "Movimiento",
    funding: "Financiación", onlyCloses: "solo cierra", buy: "COMPRA", sell: "VENTA", pnl: "Resultado", fee: "comisión",
    why: "De dónde sale el resultado", whyTrades: "Operaciones del agente (netas de comisiones)", whyFees: "Comisiones de Strike", whyOpen: "Posiciones abiertas",
    whyTests: "Operaciones de prueba (netas de comisiones)", whyTestsHint: "Las que pediste con Probar mi agente: nunca cuentan en las estadísticas del agente.",
    whyOutside: "Operaciones fuera del agente (netas de comisiones)", test: "prueba",
    whyOther: "Otros movimientos de la cuenta", whyOtherHint: "Financiación y recompensas: lo que cambia el saldo sin ser una operación.",
    whyFlows: "Depósitos y retiros", whyFlowsHint: "El dinero que metiste o sacaste de la cuenta: nunca cuenta como resultado.",
    whyTotal: "Resultado desde que se conectó", outside: "fuera del agente",
    updated: (ago: string) => `Cuenta leída hace ${ago} · el resultado se mueve con los precios de Strike en vivo`,
    publicNote: "Las cantidades solo las ve su dueño: aquí, los resultados en % de la cuenta.",
    types: { stop: "Stop", stop_market: "Stop", limit: "Límite", market: "Mercado", take_profit: "Take profit" } as Record<string, string>,
  },
};

const MARKS = "https://api.strikefinance.org/price/v2/premiumIndex";

/** Strike mark prices every 15 s (the testnet marks follow the same index). */
export function useMarks(on: boolean): Record<string, number> {
  const [marks, setMarks] = useState<Record<string, number>>({});
  useEffect(() => {
    if (!on) return;
    let alive = true;
    const load = () => fetch(MARKS).then((r) => (r.ok ? r.json() : [])).then((rows: { symbol: string; markPrice: string }[]) => {
      if (alive) setMarks(Object.fromEntries(rows.map((x) => [x.symbol, +x.markPrice]).filter(([, v]) => Number.isFinite(v as number) && (v as number) > 0)));
    }).catch(() => undefined);
    load();
    const id = window.setInterval(load, 15_000);
    return () => { alive = false; clearInterval(id); };
  }, [on]);
  return marks;
}

/** The position at the current price: mark, price move (fraction), P&L in money (owner) and as a share of the account. */
export function livePosition(p: PfPosition, marks: Record<string, number>) {
  const dir = p.side === "long" ? 1 : -1;
  const mark = marks[p.market] ?? p.mark ?? p.entry;
  const move = p.entry ? ((mark - p.entry) / p.entry) * dir : 0;
  const upnl = p.size != null ? (mark - p.entry) * p.size * dir : null;
  const pct = p.weight != null ? p.weight * move : p.pnlPct ?? null;
  return { mark, move, upnl, pct };
}

const tick = (m: string) => m.replace("-USD", "");

function agoText(lang: Lang, ms: number): string {
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 90) return lang === "es" ? `${s} s` : `${s}s`;
  const m = Math.round(s / 60);
  if (m < 90) return `${m} min`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h} h` : lang === "es" ? `${Math.round(h / 24)} d` : `${Math.round(h / 24)}d`;
}

export function PortfolioView({ p, lang, marks, idPrefix = "pf" }: { p: Portfolio; lang: Lang; marks: Record<string, number>; idPrefix?: string }) {
  const L = TXT[lang];
  const loc = lang === "es" ? "es-ES" : "en-US";
  const owner = !p.public;
  const usd = (v: number | null | undefined, signed = false) => v == null ? "—"
    : v.toLocaleString(loc, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: Math.abs(v) < 1 ? 4 : 2,
      ...(signed ? { signDisplay: "exceptZero" } : {}) });
  const pct = (v: number | null | undefined, signed = true) => v == null ? "—"
    : (v).toLocaleString(loc, { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2, ...(signed ? { signDisplay: "exceptZero" } : {}) });
  const px = (v: number | null | undefined) => v == null ? "—" : v.toLocaleString(loc, { maximumSignificantDigits: 6 });
  const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "pos" : "neg");

  const live = p.positions.map((x) => ({ x, ...livePosition(x, marks) }));
  const sizes = live.every((l) => l.upnl != null);
  const upnl = owner ? (sizes ? live.reduce((s, l) => s + (l.upnl ?? 0), 0) : p.upnl) : null;
  const equity = owner ? (p.balance != null && sizes ? p.balance + (upnl ?? 0) : p.equity) : null;
  const upnlPct = owner ? null : live.length ? live.reduce((s, l) => s + (l.pct ?? 0), 0) : p.upnlPct ?? 0;
  // the result since it started leaves deposits and withdrawals out (portfolio-types accountResult)
  const mine = owner ? accountResult(p, equity) : null;
  const ret = owner ? mine!.ret
    : p.ret != null ? (1 + p.ret) * (1 + (upnlPct ?? 0) - (p.upnlPct ?? 0)) - 1 : null;
  const flows = owner ? p.flows ?? 0 : 0;

  // the owner's result since connecting, split: the strategy's trades, test trades and trades outside the agent (each
  // net of fees), open P&L, and the rest of the balance's movements (deposits apart: they are not a result)
  const total = owner ? mine!.total : null;
  const sp = p.split ?? { strategy: (p.realized ?? 0) - (p.fees.trading ?? 0), test: 0, outside: 0 };
  const otherRaw = total != null ? total - sp.strategy - sp.test - sp.outside - (upnl ?? 0) : 0;
  const other = Math.abs(otherRaw) < 5e-5 ? 0 : otherRaw;
  const hasTests = p.fills.some((f) => f.test) || sp.test !== 0;

  const hist: [number, number][] = p.history.map((pt) => [pt[0], pt[1]]);   // the owner: equity; the public: growth
  if (owner && equity != null) hist.push([Date.now(), equity]);
  if (!owner && ret != null) hist.push([Date.now(), 1 + ret]);

  return (
    <div className="pf">
      <dl className="pf-kpis">
        {owner ? (
          <>
            <div className="pf-kpi pf-main"><dt>{L.equity}</dt><dd className="num">{usd(equity)}</dd>
              <dd className={`num small ${tone(total)}`}>{total != null ? `${usd(total, true)} · ${pct(ret)}` : "—"} <span className="faint">{L.since}</span></dd></div>
            <div className="pf-kpi"><dt>{L.upnl}</dt><dd className={`num ${tone(upnl)}`}>{usd(upnl, true)}</dd></div>
            <div className="pf-kpi"><dt>{L.available}</dt><dd className="num">{usd(p.available)}</dd></div>
            <div className="pf-kpi"><dt>{L.margin}</dt><dd className="num">{usd(p.margin)}</dd></div>
            <div className="pf-kpi"><dt>{L.tradingFees}</dt><dd className="num">{usd(p.fees.trading)}</dd></div>
            <div className="pf-kpi"><dt>{L.builderFee}</dt><dd className="num">{usd(p.fees.builder)}</dd></div>
          </>
        ) : (
          <>
            <div className="pf-kpi pf-main"><dt>{L.ret}</dt><dd className={`num ${tone(ret)}`}>{pct(ret)}</dd></div>
            <div className="pf-kpi"><dt>{L.upnl}</dt><dd className={`num ${tone(upnlPct)}`}>{pct(upnlPct)}</dd></div>
            <div className="pf-kpi"><dt>{L.nPositions}</dt><dd className="num">{p.positions.length}</dd></div>
            <div className="pf-kpi"><dt>{L.nOrders}</dt><dd className="num">{p.orders.length}</dd></div>
          </>
        )}
      </dl>

      {total != null && (
        <section className="pf-block" aria-labelledby={`${idPrefix}-why`}>
          <h4 id={`${idPrefix}-why`}>{L.why}</h4>
          <ul className="pf-rows pf-why">
            <li><span>{L.whyTrades}</span><span className={`num ${tone(sp.strategy)}`}>{usd(sp.strategy, true)}</span></li>
            {hasTests && <li><span>{L.whyTests}<small className="faint">{L.whyTestsHint}</small></span><span className={`num ${tone(sp.test)}`}>{usd(sp.test, true)}</span></li>}
            {sp.outside !== 0 && <li><span>{L.whyOutside}</span><span className={`num ${tone(sp.outside)}`}>{usd(sp.outside, true)}</span></li>}
            <li><span>{L.whyOpen}</span><span className={`num ${tone(upnl)}`}>{usd(upnl ?? 0, true)}</span></li>
            <li><span>{L.whyOther}<small className="faint">{L.whyOtherHint}</small></span><span className={`num ${tone(other)}`}>{usd(other, true)}</span></li>
            <li className="pf-why-total"><span>{L.whyTotal}</span><span className={`num ${tone(total)}`}>{usd(total, true)}</span></li>
            {flows !== 0 && <li className="pf-why-flows"><span>{L.whyFlows}<small className="faint">{L.whyFlowsHint}</small></span><span className="num">{usd(flows, true)}</span></li>}
          </ul>
        </section>
      )}

      <section className="pf-block" aria-labelledby={`${idPrefix}-chart`}>
        <h4 id={`${idPrefix}-chart`}>{L.chart}</h4>
        <Chart pts={hist} label={(v) => (owner ? usd(v) : pct(v - 1))} lang={lang} />
      </section>

      <section className="pf-block" aria-labelledby={`${idPrefix}-pos`}>
        <h4 id={`${idPrefix}-pos`}>{L.positions} · {p.positions.length}</h4>
        {!live.length ? <p className="faint">{L.noPositions}</p> : (
          <ul className="pf-list">
            {live.map(({ x, mark, move, upnl: u, pct: share }) => (
              <li key={x.market} className="pf-pos">
                <div className="pf-pos-head">
                  <span className={`pf-side ${x.side === "long" ? "pos" : "neg"}`}>{x.side === "long" ? "LONG" : "SHORT"}</span>
                  <strong>{tick(x.market)}</strong>
                  {owner && x.size != null && <span className="faint num">{px(x.size)}</span>}
                  <span className={`pf-pnl num ${tone(owner ? u : share)}`}>{owner ? usd(u, true) : pct(share)}</span>
                </div>
                <dl className="pf-kv">
                  <div><dt>{L.entry}</dt><dd className="num">{px(x.entry)}</dd></div>
                  <div><dt>{L.mark}</dt><dd className="num">{px(mark)}</dd></div>
                  <div><dt>{L.move}</dt><dd className={`num ${tone(move)}`}>{pct(move)}</dd></div>
                  <div><dt>{L.stop}</dt><dd className="num">{x.stop != null ? px(x.stop) : L.noStop}</dd></div>
                  {!owner && <div><dt>{L.weight}</dt><dd className="num">{pct(x.weight, false)}</dd></div>}
                  <div><dt>{L.lev}</dt><dd className="num">{x.lev != null ? `${x.lev}×` : "—"}</dd></div>
                  <div><dt>{L.liq}</dt><dd className="num">{x.liq ? px(x.liq) : L.none}</dd></div>
                  {x.openedAt != null && <div><dt>{L.opened}</dt><dd>{agoText(lang, x.openedAt)}</dd></div>}
                  {owner && x.funding != null && x.funding !== 0 && <div><dt>{L.funding}</dt><dd className="num">{usd(-x.funding, true)}</dd></div>}
                </dl>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="pf-block" aria-labelledby={`${idPrefix}-ord`}>
        <h4 id={`${idPrefix}-ord`}>{L.orders} · {p.orders.length}</h4>
        {!p.orders.length ? <p className="faint">{L.noOrders}</p> : (
          <ul className="pf-rows">
            {p.orders.map((o, i) => (
              <li key={`${o.market}-${i}`}>
                <span>{L.types[o.type] ?? o.type} · <span className={o.side === "buy" ? "pos" : "neg"}>{o.side === "buy" ? L.buy : L.sell}</span> {tick(o.market)}
                  {owner && o.size != null ? ` ${px(o.size)}` : ""}</span>
                <span className="num">{o.stop != null ? `@ ${px(o.stop)}` : o.price != null ? `@ ${px(o.price)}` : ""}{o.reduceOnly ? <span className="faint"> · {L.onlyCloses}</span> : null}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="pf-block" aria-labelledby={`${idPrefix}-fills`}>
        <h4 id={`${idPrefix}-fills`}>{L.fills}</h4>
        {!p.fills.length ? <p className="faint">{L.noFills}</p> : (
          <ul className="pf-rows">
            {p.fills.slice(0, 12).map((f, i) => (
              <li key={`${f.time}-${i}`}>
                <span><span className="faint">{agoText(lang, f.time)}</span> · <span className={f.side === "buy" ? "pos" : "neg"}>{f.side === "buy" ? L.buy : L.sell}</span> {tick(f.market)}
                  {owner && f.size != null ? ` ${px(f.size)}` : ""} @ {px(f.price)}
                  {f.agent === false && <span className="faint"> · {L.outside}</span>}
                  {f.test && <span className="faint"> · {L.test}</span>}</span>
                <span className="num">
                  {(() => {   // a close as Strike shows it: P&L net of this fill's fee, and that over the size closed
                    const net = owner && f.pnl ? f.pnl - (f.fee ?? 0) : null;
                    const cp = owner ? (net != null && f.size ? net / (f.price * Math.abs(f.size)) : null) : f.pnlPct ?? null;
                    return <>
                      {net != null && <span className={tone(net)}>{usd(net, true)} </span>}
                      {cp != null && <span className={tone(cp)}>({pct(cp)})</span>}
                      {owner && <span className="faint">{net != null || cp != null ? " · " : ""}{L.fee} {usd(f.fee)}</span>}
                    </>;
                  })()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="pf-note faint">{p.time ? L.updated(agoText(lang, p.time)) : ""}{!owner && <> {L.publicNote}</>}</p>
    </div>
  );
}

/** Equity line: SVG, no library. */
function Chart({ pts, label, lang }: { pts: [number, number][]; label: (v: number) => string; lang: Lang }) {
  const L = TXT[lang];
  if (pts.length < 2) return <p className="faint">{L.chartSoon}</p>;
  const W = 600, H = 120, pad = 6;
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0] || t0 + 1;
  const vs = pts.map((p) => p[1]);
  let lo = Math.min(...vs), hi = Math.max(...vs);
  if (hi - lo < Math.abs(hi) * 1e-4 || hi === lo) { const m = Math.abs(hi) * 5e-4 || 1; lo -= m; hi += m; }
  const x = (t: number) => pad + ((t - t0) / Math.max(1, t1 - t0)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((v - lo) / (hi - lo)) * (H - 2 * pad);
  const line = pts.map(([t, v], i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const up = vs[vs.length - 1] >= vs[0];
  return (
    <figure className="pf-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
           aria-label={`${L.chart}: ${label(vs[0])} → ${label(vs[vs.length - 1])}`}>
        <path d={`${line} L${x(t1).toFixed(1)},${H - pad} L${x(t0).toFixed(1)},${H - pad} Z`} className={`pf-area ${up ? "up" : "down"}`} />
        <path d={line} className={`pf-line ${up ? "up" : "down"}`} vectorEffect="non-scaling-stroke" />
      </svg>
      <figcaption className="pf-axis num"><span>{label(hi)}</span><span>{label(lo)}</span></figcaption>
    </figure>
  );
}
