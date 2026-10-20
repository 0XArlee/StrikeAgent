// The live city as a picture for the landing: same engine, data and agents as #/city, no input (the whole frame is a
// link to the city). Loaded only when the section comes into view; drawing pauses while it is off-screen.
import { useEffect, useRef, useState } from "react";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-mono/700.css";
import { CityEngine } from "./engine";
import { CityStore } from "./store";

const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
// the text covers the left of the frame: the camera puts the exchange and the plaza (where the agents gather) on the right
const VIEW = { cx: 640, cy: 490, zoom: 1.7 };
const VIEW_SMALL = { cx: 770, cy: 520, zoom: 1.25 };   // phones: the text sits below, the plaza fills the square

export default function CityPreview({ onStats }: { onStats?: (s: { online: number; inTrade: number }) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [on, setOn] = useState(false);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const store = new CityStore();
    let engine: CityEngine | null = null;
    let visible = true;
    let alive = true;
    const unsub = store.subscribe(() => { const t = store.totals(); onStats?.({ online: t.live, inTrade: t.inTrade }); });
    store.load(() => undefined).then(() => {
      if (!alive) return;
      store.start();
      engine = new CityEngine(c, {
        getAgents: () => store.agents, getPrices: () => store.prices, getHistory: (m) => store.hist[m] ?? [],
        getHeadline: () => {
          const btc = store.prices["BTC-USD"], t = store.totals();
          const px = btc ? ` · BTC ${Math.round(btc.price).toLocaleString("en-US")} ${btc.change >= 0 ? "▲" : "▼"}${Math.abs(btc.change).toFixed(2)}%` : "";
          return `EDGECRAFT-STRIKECITY · ${t.live} AGENTS ONLINE · ${t.inTrade} IN A TRADE${px}`;
        },
        getWeather: () => 0, onSelect: () => undefined,
        reducedMotion: !!reduced, interactive: false, view: VIEW, viewSmall: VIEW_SMALL,
      });
      if (visible) engine.start();
      setOn(true);
    });
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (!engine) return;
      if (visible) engine.start(); else engine.pause();
    });
    io.observe(c);
    return () => { alive = false; io.disconnect(); unsub(); engine?.stop(); store.stop(); };
  }, [onStats]);

  return <canvas ref={canvas} className={`city-show-canvas${on ? " on" : ""}`} aria-hidden="true" />;
}
