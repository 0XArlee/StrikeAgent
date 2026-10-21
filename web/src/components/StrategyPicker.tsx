// Strategy, markets and risk: picked when the agent is created and changed later in My agent. Picking a strategy
// resets the markets to that strategy's own (the ones with an edge after costs); the others stay opt-in.
import type { AppInfo, RiskPreset } from "../api";
import { fmt, type Dict, type Lang } from "../i18n";
import { DEFAULT_STRATEGY, MIN_BALANCE, STRATEGY_DATA, STRATEGY_IDS, STRATEGY_MARKETS, maxRisk, riskAllowed, strategyName, strategyText, type StrategyId } from "../strategies";

export interface Plan { strategy: StrategyId; markets: string[]; risk: RiskPreset }

export const defaultPlan = (info: AppInfo, strategy: StrategyId = DEFAULT_STRATEGY): Plan => ({
  strategy, markets: STRATEGY_MARKETS[strategy].filter((m) => info.markets.includes(m)),
  risk: riskAllowed(strategy, "standard") ? "standard" : maxRisk(strategy),
});

interface Props { t: Dict; lang: Lang; info: AppInfo; value: Plan; onChange: (p: Plan) => void; idPrefix: string; titled?: boolean }

export function StrategyPicker({ t, lang, info, value, onChange, idPrefix, titled = true }: Props) {
  const S = t.strategies;
  const loc = lang === "es" ? "es-ES" : "en-US";
  const nf = (v: number, d = 2) => v.toLocaleString(loc, { minimumFractionDigits: d, maximumFractionDigits: d });
  const pct = (v: number) => `${nf(v, 1)}${lang === "es" ? " %" : "%"}`;
  const core = STRATEGY_MARKETS[value.strategy].filter((m) => info.markets.includes(m));
  const more = info.markets.filter((m) => !core.includes(m));
  // a strategy may cap the risk (config/strategies.json max_risk): picking it with a higher one brings the risk down to it
  const pick = (id: StrategyId) => onChange({ ...value, strategy: id, markets: STRATEGY_MARKETS[id].filter((m) => info.markets.includes(m)),
    risk: riskAllowed(id, value.risk) ? value.risk : maxRisk(id) });
  const cap = maxRisk(value.strategy);
  const toggle = (mk: string, on: boolean) =>
    onChange({ ...value, markets: on ? info.markets.filter((m) => m === mk || value.markets.includes(m)) : value.markets.filter((m) => m !== mk) });
  const chip = (mk: string) => (
    <label key={mk}>
      <input type="checkbox" checked={value.markets.includes(mk)} onChange={(e) => toggle(mk, e.target.checked)} />
      <span>{mk.replace("-USD", "")}</span>
    </label>
  );
  return (
    <>
      <fieldset className="sp-strats">
        <legend className={titled ? undefined : "sr-only"}>{S.title}</legend>
        {titled && <p className="field-hint" style={{ marginBottom: 8 }}>{S.sub}</p>}
        {STRATEGY_IDS.map((id) => {
          const d = STRATEGY_DATA[id];
          return (
            <label key={id} className={`sp-card${value.strategy === id ? " on" : ""}`}>
              <input type="radio" name={`${idPrefix}-strategy`} value={id} checked={value.strategy === id} onChange={() => pick(id)} />
              <span className="sp-body">
                <span className="sp-name">{strategyName(id)}</span>
                <span className="sp-tagline">{strategyText(id, lang).tagline}</span>
                <span className="sp-stats">
                  <span><strong className="num">{d.trades_per_year}</strong> {S.tradesYear}</span>
                  <span><strong className="num pos">+{nf(d.avg_r)} R</strong> {S.avgR}</span>
                  <span><strong className="num">{pct(d.cagr_pct)}</strong> {S.cagr}</span>
                  <span><strong className="num neg">−{pct(d.equity_max_dd_pct)}</strong> {S.dd}</span>
                </span>
              </span>
            </label>
          );
        })}
        <p className="sp-note">{S.note}</p>
      </fieldset>
      <fieldset>
        <legend>{S.markets}</legend>
        <p className="field-hint" style={{ marginBottom: 8 }}>{S.marketsCore}</p>
        <div className="chips">{core.map(chip)}</div>
        {more.length > 0 && <>
          <p className="field-hint" style={{ margin: "12px 0 8px" }}>{S.marketsMore}</p>
          <div className="chips chips-more">{more.map(chip)}</div>
        </>}
      </fieldset>
      <fieldset>
        <legend>{S.risk}</legend>
        <p className="field-hint" style={{ marginBottom: 8 }}>{S.riskHint}</p>
        <div className="seg">
          {(Object.keys(info.riskPresets) as RiskPreset[]).map((k) => (
            <label key={k} className={riskAllowed(value.strategy, k) ? undefined : "off"}>
              <input type="radio" name={`${idPrefix}-risk`} value={k} checked={value.risk === k} disabled={!riskAllowed(value.strategy, k)}
                     onChange={() => onChange({ ...value, risk: k })} />
              <span>{t.modal.riskNames[k]}<small>{info.riskPresets[k].toLocaleString(loc)}%</small></span>
            </label>
          ))}
        </div>
        {cap !== "assertive" && <p className="field-hint">{fmt(S.riskCap, { name: strategyName(value.strategy),
          max: `${info.riskPresets[cap].toLocaleString(loc)}${lang === "es" ? " %" : "%"}`, note: strategyText(value.strategy, lang).risk_note })}</p>}
        {info.live?.enabled && <p className="field-hint balance-hint">{fmt(t.balance.pick, { min: `${MIN_BALANCE[value.risk]} $` })}</p>}
      </fieldset>
    </>
  );
}
