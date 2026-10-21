// TradingView's own chart (their free embed widget) for a city market, on TradingView's own price index (no exchange
// name) and 4h candles like the agents. Only for people to look and analyse: the agents never read it (they have their
// own feed, agent/runner.py). Two forms: the exchange's screen in the city (live candles, no controls, seen through the
// map) and the full chart with TradingView's drawing tools, indicators and timeframes. Its script and iframe come from
// TradingView only when one is shown.
import { useEffect, useRef } from "react";
import type { Lang } from "../i18n";

const SRC = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";

/** A city market on TradingView's own crypto index ("BTC-USD" -> "CRYPTO:BTCUSD"): no exchange's name on it. */
export const tvSymbol = (market: string) => `CRYPTO:${market.split("-")[0]}USD`;

const BASE = { autosize: true, interval: "240", timezone: "Etc/UTC", theme: "dark", style: "1", support_host: "https://www.tradingview.com" };
const SCREEN = { hide_top_toolbar: true, hide_legend: true, hide_side_toolbar: true, allow_symbol_change: false, save_image: false,
  hide_volume: true, range: "1M", backgroundColor: "#020806", gridColor: "rgba(78, 250, 176, 0.06)" };
const FULL = { hide_side_toolbar: false, allow_symbol_change: true, withdateranges: true, save_image: true, details: false, hotlist: false,
  calendar: false, backgroundColor: "#0a0a0a", gridColor: "rgba(255, 255, 255, 0.04)" };

interface Props {
  market: string; lang: Lang;
  full?: boolean;     // the whole chart with its tools; otherwise the city's screen
  title: string;      // the iframe's accessible name
}

export function TradingViewChart({ market, lang, full = false, title }: Props) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const box = document.createElement("div");
    box.className = "tradingview-widget-container__widget";
    box.style.cssText = "width:100%;height:100%";
    const s = document.createElement("script");
    s.src = SRC;
    s.async = true;
    s.textContent = JSON.stringify({ ...BASE, ...(full ? FULL : SCREEN), symbol: tvSymbol(market), locale: lang === "es" ? "es" : "en" });
    el.replaceChildren(box, s);
    // the iframe it adds gets a name; the screen's is only a picture in the map: out of the tab order
    const mo = new MutationObserver(() => {
      const f = el.querySelector("iframe");
      if (!f) return;
      f.title = title;
      if (!full) f.tabIndex = -1;
      mo.disconnect();
    });
    mo.observe(el, { childList: true, subtree: true });
    return () => { mo.disconnect(); el.replaceChildren(); };
  }, [market, lang, full, title]);
  return <div ref={host} className="tradingview-widget-container" />;
}
