// STRIKE, Strike Finance's own token (Cardano), on DEX Screener's embedded chart: TradingView's charting library over
// the STRIKE/ADA pool on SundaeSwap, in USD and 4h candles. TradingView has no chart of it (its "STRIKE" and "STRK" are
// other projects), DEX Screener does. Two forms, like tradingview.tsx: Strike Finance's screen in the city (its toolbar
// cropped off, scaled down, seen through the map) and the full chart. Its iframe comes from DEX Screener only when shown.
import { useEffect, useRef } from "react";
import { STRIKE_PAIR } from "./store";

export const STRIKE_CHART_URL = `https://dexscreener.com/cardano/${STRIKE_PAIR}`;
const Q = "embed=1&loadChartSettings=0&trades=0&tabs=0&info=0&chartTheme=dark&theme=dark&chartStyle=1&chartType=usd&interval=240";

interface Props {
  full?: boolean;          // the whole chart with its tools; otherwise the city's screen
  title: string;           // the iframe's accessible name
  onReady?: () => void;    // its candles are drawn (a moment after the page loads)
}

export function StrikeChart({ full = false, title, onReady }: Props) {
  const ready = useRef(onReady);
  ready.current = onReady;
  const timer = useRef(0);
  useEffect(() => () => clearTimeout(timer.current), []);
  const loaded = () => { clearTimeout(timer.current); timer.current = window.setTimeout(() => ready.current?.(), 1500); };
  if (full) return <iframe className="dex-full" src={`${STRIKE_CHART_URL}?${Q}`} title={title} referrerPolicy="strict-origin-when-cross-origin" />;
  // the screen: no left toolbar, and the top one cropped off (the legend with STRIKE/ADA stays), drawn at 1.5x and scaled
  return (
    <div className="dex-crop">
      <iframe src={`${STRIKE_CHART_URL}?${Q}&chartLeftToolbar=0`} title={title} tabIndex={-1} onLoad={loaded}
              referrerPolicy="strict-origin-when-cross-origin" />
    </div>
  );
}
