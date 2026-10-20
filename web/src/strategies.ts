// The strategies a user can pick (web/server/util.ts STRATEGIES on the site; smartflow.agent.config policy on the host).
import pyramid from "./data/strategy-pyramid.json";
import smartflow from "./data/strategy.json";

export type StrategyId = "smartflow" | "pyramid";
export const STRATEGY_IDS: StrategyId[] = ["smartflow", "pyramid"];
/** Where both strategies have shown an edge after costs (2022-2026); the other markets are opt-in. */
export const CORE_MARKETS = ["BTC-USD", "ETH-USD", "SOL-USD"];
export const STRATEGY_MARKETS: Record<StrategyId, string[]> = { smartflow: CORE_MARKETS, pyramid: CORE_MARKETS };
export const STRATEGY_DATA = { smartflow, pyramid };
export const strategyId = (v: unknown): StrategyId => (v === "pyramid" ? "pyramid" : "smartflow");
/** The balance below which many signals come out under Strike's ~10 $ minimum order (docs/08, the FAQ). */
export const MIN_BALANCE: Record<"conservative" | "standard" | "assertive", number> = { conservative: 300, standard: 150, assertive: 150 };
/** "Test my agent" needs about this much available: Strike's smallest order (~11 $) + 5 % (web/server/handlers.ts). */
export const TEST_MIN_AVAILABLE = 12;
