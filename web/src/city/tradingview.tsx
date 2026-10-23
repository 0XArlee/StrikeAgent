// TradingView's own chart (their free embed widgets) for a city market, on TradingView's own price index (no exchange
// name) and 4h candles like the agents. Only for people to look and analyse: the agents never read it (they have their
// own feed, agent/runner.py). Two forms: a tower's screen in the city (a month of live candles, no controls, seen
// through the map) and the full chart with TradingView's drawing tools, indicators and timeframes. The screen is
// TradingView's light widget (Symbol Overview, ~0.5 MB): the full chart's (Advanced Chart) is ~3.7 MB of script per
// screen, and three at once kept the towers empty for seconds (measured). Their script and iframe come from TradingView
// only when one is shown.
import { useEffect, useRef } from "react";
import type { Lang } from "../i18n";

const FULL_SRC = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
const SCREEN_SRC = "https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js";
const FRAME_ORIGIN = "https://www.tradingview-widget.com";

/** Opens the connections to TradingView ahead (DNS, TLS): its chart then starts loading at once. */
export function warmTradingView(): void {
  if (typeof document === "undefined" || document.querySelector('link[data-tv-warm]')) return;
  for (const href of ["https://s3.tradingview.com", FRAME_ORIGIN]) {
    const l = document.createElement("link");
    l.rel = "preconnect"; l.href = href; l.crossOrigin = "anonymous"; l.dataset.tvWarm = "1";
    document.head.appendChild(l);
  }
}

/** A city market on TradingView's own crypto index ("BTC-USD" -> "CRYPTO:BTCUSD"): no exchange's name on it. */
export const tvSymbol = (market: string) => `CRYPTO:${market.split("-")[0]}USD`;

const FULL = { autosize: true, interval: "240", timezone: "Etc/UTC", theme: "dark", style: "1", support_host: "https://www.tradingview.com",
  hide_side_toolbar: false, allow_symbol_change: true, withdateranges: true, save_image: true, details: false, hotlist: false,
  calendar: false, backgroundColor: "#0a0a0a", gridColor: "rgba(255, 255, 255, 0.04)" };
// the screen: only the chart (no header, ranges, logo or volume), a month of 4h candles ("1m|240")
const SCREEN = { autosize: true, width: "100%", height: "100%", chartOnly: true, chartType: "candlesticks", dateRanges: ["1m|240"],
  colorTheme: "dark", isTransparent: false, backgroundColor: "#020806", gridLineColor: "rgba(78, 250, 176, 0.06)", fontSize: "12",
  showVolume: false, showMA: false, hideDateRanges: true, hideMarketStatus: true, hideSymbolLogo: true, scalePosition: "right",
  scaleMode: "Normal", noTimeScale: false };
const config = (market: string, lang: Lang, full: boolean) => {
  const locale = lang === "es" ? "es" : "en";
  return full ? { ...FULL, symbol: tvSymbol(market), locale } : { ...SCREEN, symbols: [[`${tvSymbol(market)}|1M`]], locale };
};

interface Props {
  market: string; lang: Lang;
  full?: boolean;     // the whole chart with its tools; otherwise the city's screen
  title: string;      // the iframe's accessible name
  onReady?: () => void;   // its candles are drawn (a moment after its page has loaded)
}

export function TradingViewChart({ market, lang, full = false, title, onReady }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const ready = useRef(onReady);
  ready.current = onReady;
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const box = document.createElement("div");
    box.className = "tradingview-widget-container__widget";
    box.style.cssText = "width:100%;height:100%";
    const s = document.createElement("script");
    s.src = full ? FULL_SRC : SCREEN_SRC;
    s.async = true;
    s.textContent = JSON.stringify(config(market, lang, full));
    el.replaceChildren(box, s);
    // the iframe it adds gets a name; the screen's is only a picture in the map: out of the tab order. Its candles are
    // drawn 0.2-0.45 s after its page has loaded (measured; the light widget sends no message of its own), so the chart is
    // shown a little after that and never as an empty box
    let timer = 0;
    const mo = new MutationObserver(() => {
      const f = el.querySelector("iframe");
      if (!f) return;
      f.title = title;
      if (!full) f.tabIndex = -1;
      f.addEventListener("load", () => { clearTimeout(timer); timer = window.setTimeout(() => ready.current?.(), 500); });
      mo.disconnect();
    });
    mo.observe(el, { childList: true, subtree: true });
    return () => { mo.disconnect(); clearTimeout(timer); el.replaceChildren(); };
  }, [market, lang, full, title]);
  return <div ref={host} className="tradingview-widget-container" />;
}
