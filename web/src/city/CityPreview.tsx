// The live city as a picture for the landing's hero: same engine, data and agents as #/city, no input (the whole frame
// is a link to the city). Built while the browser is idle (App.tsx); it draws only while it is on screen and the page
// is not scrolling, so it never stalls a scroll. Until its first frame the poster under it shows.
import { useEffect, useRef, useState } from "react";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-mono/700.css";
import { CityEngine, idleMoment, prepareLayers } from "./engine";
import { artReady } from "./world";
import { CityStore } from "./store";

const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
// a wide frame (700 px and more) has room for the exchange and the plaza (where the agents gather) side by side; the
// hero's square frame takes the small view: the exchange's board on top, the plaza filling the rest
const VIEW = { cx: 640, cy: 490, zoom: 1.7 };
const VIEW_SMALL = { cx: 760, cy: 470, zoom: 1.15 };   // the exchange's big screen whole at the top (its label too in the wider frame), the plaza below

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
    let lastScroll = performance.now();   // a scroll already going on when it mounts is not missed: it waits for quiet
    let timer = 0;
    let check = 0;
    // it draws only while the page is still: a scroll pauses it and it carries on 180 ms after (in the hero it is on
    // screen as the scroll starts; its frames there were the only hitches left, on a throttled phone)
    const run = () => {
      clearTimeout(timer);
      cancelAnimationFrame(check);
      if (!engine || !visible || !alive) return;
      const quiet = performance.now() - lastScroll;
      if (quiet < 180) { timer = window.setTimeout(run, 180 - quiet); return; }
      // a slow task can outlast the 180 ms while the scroll goes on; its scroll event only comes with the next frame,
      // so the last check is made in that frame (after its scroll events)
      check = requestAnimationFrame(() => {
        if (!engine || !visible || !alive) return;
        if (performance.now() - lastScroll < 180) { timer = window.setTimeout(run, 180); return; }
        engine.start();
        setOn(true);
      });
    };
    const onScroll = () => {
      lastScroll = performance.now();
      if (!engine || !visible) return;
      engine.pause();
      clearTimeout(timer);
      cancelAnimationFrame(check);
      timer = window.setTimeout(run, 180);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    const unsub = store.subscribe(() => { const t = store.totals(); onStats?.({ online: t.live, inTrade: t.inTrade }); });
    // each heavy step waits for a pause in the scrolling and an idle moment: none of them lands in the middle of a scroll
    const whenQuiet = async () => {
      for (let q = performance.now() - lastScroll; q < 300; q = performance.now() - lastScroll) await new Promise((r) => setTimeout(r, 300 - q));
      await idleMoment();
    };
    store.load(() => undefined).then(() => artReady).then(() => prepareLayers(whenQuiet)).then(() => {
      if (!alive) return;
      store.start();
      engine = new CityEngine(c, {
        getAgents: () => store.agents, getPrices: () => store.prices, getHistory: (m) => store.hist[m] ?? [],
        takeTrades: (now) => store.dueTrades(now),   // the cars are Strike's real trades here too
        getHeadline: () => {
          const btc = store.prices["BTC-USD"], t = store.totals();
          const px = btc ? ` · BTC ${Math.round(btc.price).toLocaleString("en-US")} ${btc.change >= 0 ? "▲" : "▼"}${Math.abs(btc.change).toFixed(2)}%` : "";
          return `EDGECRAFT-STRIKECITY · ${t.live} AGENTS ONLINE · ${t.inTrade} IN A TRADE${px}`;
        },
        getWeather: () => 0, onSelect: () => undefined, getBook: () => store.book,
        reducedMotion: !!reduced, interactive: false, view: VIEW, viewSmall: VIEW_SMALL,
      });
      run();
    });
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (!engine) return;
      if (visible) run(); else { clearTimeout(timer); cancelAnimationFrame(check); engine.pause(); }
    });
    io.observe(c);
    return () => { alive = false; clearTimeout(timer); cancelAnimationFrame(check); window.removeEventListener("scroll", onScroll); io.disconnect(); unsub(); engine?.stop(); store.stop(); };
  }, [onStats]);

  return <canvas ref={canvas} className={`city-show-canvas${on ? " on" : ""}`} aria-hidden="true" />;
}
