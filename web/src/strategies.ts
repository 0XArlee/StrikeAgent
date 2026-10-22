// The strategies users can pick: the registry the agents' host also reads (config/strategies.json) and each one's
// backtest figures (config/figures/<id>.json, `smartflow figures`). Adding a strategy there adds it to the catalog,
// its page, the sign-up and My agent; web/server/util.ts checks the same file.
import registry from "../../config/strategies.json";
import type { Lang } from "./i18n";

export type StrategyId = string;
export type RiskPreset = "conservative" | "standard" | "assertive";
export const RISK_ORDER: RiskPreset[] = ["conservative", "standard", "assertive"];

export interface StrategyText { tagline: string; summary: string; details: [string, string][]; risk_note: string }
export interface StrategyDef {
  id: StrategyId; name: string; tag: string; status: "live" | "soon"; listed: boolean; engine: string; timeframe: string;
  policy: string; max_stack: number; max_risk: RiskPreset; markets: { core: string[]; allowed: string[] };
  texts: Record<Lang, StrategyText>;
}
export interface Figures {
  strategy: string; timeframe: string; markets: string[]; period: string[]; risk_per_trade_pct: number; clean_stop_pct: number;
  trades: number; trades_per_year: number; avg_r: number; ci95: number[]; win_rate: number; avg_win_r: number; profit_factor: number;
  max_dd_r: number; cagr_pct: number; equity_max_dd_pct: number; sharpe: number; equity_curve: [string, number][];
}

const ALL = registry.strategies as unknown as StrategyDef[];
const FIGS: Record<string, Figures> = Object.fromEntries(
  Object.entries(import.meta.glob("../../config/figures/*.json", { eager: true, import: "default" }))
    .map(([path, f]) => [path.split("/").pop()!.replace(/\.json$/, ""), f as Figures]));

/** In the catalog: the live strategies with their figures, then the ones shown as coming. */
export const CATALOG: StrategyDef[] = ALL.filter((s) => s.listed && (s.status === "soon" || !!FIGS[s.id]));
export const STRATEGY_IDS: StrategyId[] = CATALOG.filter((s) => s.status === "live").map((s) => s.id);
export const DEFAULT_STRATEGY: StrategyId = registry.default;
export const STRATEGY_DATA: Record<StrategyId, Figures> = FIGS;
export const STRATEGY_MARKETS: Record<StrategyId, string[]> = Object.fromEntries(ALL.map((s) => [s.id, s.markets.core]));
export const strategyId = (v: unknown): StrategyId => (typeof v === "string" && STRATEGY_IDS.includes(v) ? v : DEFAULT_STRATEGY);
export const strategyDef = (id: StrategyId): StrategyDef => ALL.find((s) => s.id === id) ?? ALL.find((s) => s.id === DEFAULT_STRATEGY)!;
export const strategyName = (id: unknown): string => strategyDef(typeof id === "string" ? id : DEFAULT_STRATEGY).name;
export const strategyText = (id: StrategyId, lang: Lang): StrategyText => strategyDef(id).texts[lang];
/** Whether a risk preset is allowed with a strategy (its max_risk; web/server/util.ts checks the same). */
export const riskAllowed = (strategy: StrategyId, risk: RiskPreset) =>
  RISK_ORDER.indexOf(risk) <= RISK_ORDER.indexOf(strategyDef(strategy).max_risk);
/** The highest preset a strategy allows: picking it with a higher one brings the risk down to this. */
export const maxRisk = (strategy: StrategyId): RiskPreset => strategyDef(strategy).max_risk;
/** The recommended balance in the Strike account, the same at every preset (Edgar 2026-10-21: 250 $). With it the
 *  agent takes ~99 % of the signals above Strike's ~10 $ minimum order even at 0.5 % (backtest 2022-2026; docs/OPERATIONS.md). */
export const MIN_BALANCE: Record<RiskPreset, number> = { conservative: 250, standard: 250, assertive: 250 };
/** "Test my agent" needs about this much available: Strike's smallest order (~11 $) + 5 % (web/server/handlers.ts). */
export const TEST_MIN_AVAILABLE = 12;
