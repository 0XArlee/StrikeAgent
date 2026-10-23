// EdgeCraft-StrikeCity: the agents of Smart Flow users living on a map, driven by the same lifecycle as the real agent.
import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type KeyboardEvent, type ReactNode } from "react";
import { CATALOG, DEFAULT_STRATEGY, STRATEGY_DATA, strategyDef } from "../strategies";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-mono/700.css";
import "./city.css";
import type { Lang } from "../i18n";
import { Icon, Mark } from "../components/ui";
import { atWork, keepLeadSlots, lastChecks, leadTick, leadView, mulberry, newsTrip, nowDecision, readingNews, stats, type AgentView, type FeedItem, type Prices, type Status } from "./agents";
import { CityEngine, SCREEN_BOOK, SCREEN_CHART, STATUS_COLOR, TOWER_CHARTS, drawIcon, type Sel } from "./engine";
import type { Look } from "./look";
import { FEET, FW, HEAD_TOP, frameAt, onSheet, sheetFor } from "./sprites";
import { BOOK_MARKET, CITY_MARKETS, CityStore, type Book, type Trade } from "./store";
import { EventSoon, NewsButton, NewsView, contextLine, signed, tapeLine } from "./NewsView";
import { TowerView } from "./TowerView";
import { ArenaView } from "./ArenaView";
import { StrikeView } from "./StrikeView";
import { useStrikeStats } from "./strikestats";
import { dict } from "../i18n";
import { voiceLine } from "../components/PersonaPicker";
import { TEMPER_COLOR } from "./persona";
import { useNews } from "./news";
import { positionsBySize, traderName, useCopy, type CopyState, type Trader } from "./copy";
import { MarketLogo, MarketLogos } from "./MarketLogos";
import { AlertsPanel } from "./AlertsPanel";
import { byPlace, useAlerts, type CityAlert } from "./alerts";
import { CopyChooser, Evidence, LeadCard, StrikeStats } from "./CopyView";
import { cityText, describe, fmtPct, fmtPrice, fmtR, money as cents, pctSigned, ticker, type CityText } from "./text";
import { ART2, BUILDINGS, artReady } from "./world";
import { PortfolioView, livePosition } from "./portfolio";
import { TradingViewChart, warmTradingView } from "./tradingview";
import { STRIKE_CHART_URL, StrikeChart } from "./dexscreener";

type Panel = "agents" | "ranks" | "feed" | "markets" | "guide" | "alerts";

interface Props {
  lang: Lang; setLang: (l: Lang) => void; onConnect: () => void;
  onFeedback?: () => void;   // the Feedback dialog (the site's, opened over the city)
  myAgent?: ReactNode;   // the owner's dashboard (null until they sign in with their wallet)
  owner?: { id: string; token: string } | null;   // signed in: their own agent shows with its amounts
  copyPilot?: boolean;   // copy with your agent is open: a trader's card offers it
  testSite?: boolean;    // the staging site (Strike testnet): its figures count every agent, paper and testnet
}

const SCALE = [1, 10, 50, 250, 1000, 5000];
const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const isSmall = () => window.matchMedia("(max-width: 760px)").matches;

const wantsMe = () => /[?&]me\b/.test(location.hash);
// the markets the full chart offers (the ones agents can trade)
const CHART_MARKETS = CITY_MARKETS;
// TradingView's screen chart is laid out at this many CSS px per world px and scaled with the map: zooming only
// transforms it (no new layout inside the iframe), and its text stays readable from the default zoom
const TV_K = 2.5;
warmTradingView();   // as the city's code arrives: TradingView's connections open while the city loads

// what is laid over the map's screens (world px): STRIKE on Strike Finance's, its order book beside it, each tower's market
const OVERLAYS: [string, { x: number; y: number; w: number; h: number }][] =
  [["strike", SCREEN_CHART], ["book", SCREEN_BOOK], ...TOWER_CHARTS.map((t) => [t.id, t] as [string, typeof t])];

function readDeepLink(): string | null {
  const m = /[?&]agent=([\w-]+)/.exec(location.hash);
  return m ? m[1] : null;
}
/** #/city?lead=<account>: a lead of Strike's copy trading, selected and followed once the city has it. */
const readLeadLink = () => /[?&]lead=([\w-]+)/.exec(location.hash)?.[1] ?? null;

export default function CityPage({ lang, setLang, onConnect, onFeedback, myAgent, owner, copyPilot, testSite }: Props) {
  const T = cityText[lang];
  const store = useMemo(() => new CityStore(), []);
  store.owner = owner?.token ? owner : null;
  useEffect(() => { if (owner?.token) void store.refreshCity(); }, [store, owner?.id, owner?.token]);
  const version = useSyncExternalStore(store.subscribe, store.getVersion);
  const [progress, setProgress] = useState(0);
  const [ready, setReady] = useState(false);
  const [sel, setSel] = useState<Sel | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [me, setMe] = useState(wantsMe);   // "My agent" open over the map
  const [details, setDetails] = useState(false);
  const [chart, setChart] = useState<string | null>(null);   // the market whose full chart is open
  const [trade, setTrade] = useState<Trade | null>(null);     // the real Strike trade a pressed car is
  const [alertToast, setAlertToast] = useState<CityAlert | null>(null);   // a new Strike alert, for a few seconds
  useEffect(() => { if (!trade) return; const id = window.setTimeout(() => setTrade(null), 9000); return () => clearTimeout(id); }, [trade]);
  const [news, setNews] = useState<string | null>(null);     // the market whose news is open
  const [tower, setTower] = useState<null | "walking" | "inside">(null);   // the News Tower: your agent on its way, or inside
  const [arena, setArena] = useState<null | "walking" | "inside">(null);   // the Copy Arena, the same way
  const [hq, setHq] = useState<null | "walking" | "inside">(null);         // Strike Finance's building, the same way
  const hqStats = useStrikeStats(hq !== null);               // Strike's numbers, read once someone heads in
  const newsDoc = useNews(ready);                             // read once the city is drawn, then every minute
  const copyDoc = useCopy(ready);                             // Strike's copy trading, the same way
  const [copy, setCopy] = useState<{ open: string | null } | null>(null);   // the chooser of whom to copy (a profile open)
  const leads = useRef<AgentView[]>([]);   // the leads walking the city with their copiers: out of the agents' totals (Agents lists them apart)
  const leadR = useMemo(() => mulberry(0x1ead), []);
  const leadLink = useRef(readLeadLink());
  // the screens' charts: shown once drawn (until then the city's own drawing shows); a tower's loads only once it has
  // been on screen, so the city never loads three charts nobody is looking at
  const [chartOn, setChartOn] = useState<Record<string, boolean>>({});
  const [towerSeen, setTowerSeen] = useState<Record<string, boolean>>({});
  const seen = useRef<Record<string, boolean>>({});
  const overlay = useRef<Record<string, HTMLDivElement | null>>({});
  const [welcome, setWelcome] = useState(() => { try { return localStorage.getItem("sf-city-welcome") !== "1"; } catch { return true; } });
  const [, force] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);
  const engine = useRef<CityEngine | null>(null);
  const headline = useRef("EDGECRAFT-STRIKECITY");
  const newsTape = useRef("");
  const newsRef = useRef<typeof newsDoc>(null);
  const langRef = useRef(lang);
  langRef.current = lang;
  const weather = useRef<0 | 1 | 2>(0);
  const deepLink = useRef(readDeepLink());   // read before the hash is rewritten below
  const towerLink = useRef(/[?&]tower\b/.test(location.hash));   // #/city?tower: straight into the News Tower
  const arenaLink = useRef(/[?&]arena\b/.test(location.hash));   // #/city?arena: straight into the Copy Arena
  const hqLink = useRef(/[?&]strike\b/.test(location.hash));     // #/city?strike: straight into Strike Finance
  const alertsLink = useRef(/[?&]alerts\b/.test(location.hash)); // #/city?alerts (the bot's "Open the city"): the Alerts tab
  // Strike's alerts (the alerts bot on the agents' host): each fresh one over the building it concerns, a new one in a toast
  const alertsDoc = useAlerts();
  const alertMap = useRef<Record<string, { level: "info" | "warn" | "alert"; text: string }>>({});
  const seenAlerts = useRef<Set<string> | null>(null);

  useEffect(() => {
    let alive = true;
    // the art (?art=old: the city drawn before) is chosen when the page loads: asked for later, it loads again
    if (/[?&]art=(new|old)\b/.test(location.hash) && ART2 !== !/[?&]art=old\b/.test(location.hash)) { location.reload(); return; }
    Promise.all([store.load((k) => alive && setProgress(k)), artReady]).then(() => { if (!alive) return; store.start(); setReady(true); });
    return () => { alive = false; store.stop(); };
  }, [store]);

  useEffect(() => {
    if (!ready || !canvas.current) return;
    const e = new CityEngine(canvas.current, {
      getAgents: () => (leads.current.length ? store.agents.concat(leads.current) : store.agents),
      getPrices: () => store.prices, getHistory: (m) => store.hist[m] ?? [],
      getHeadline: () => headline.current, getNewsTape: () => newsTape.current,
      getJobLabel: (a) => jobLabel(a, newsRef.current, store.prices, langRef.current), getWeather: () => weather.current, reducedMotion: !!reduced, getBook: () => store.book,
      getAlerts: () => alertMap.current,
      getToken: () => store.token,
      onSelect: (s) => { setSel(s); setDetails(false); if (s && isSmall()) setPanel(null); },
      onChart: (m) => setChart(m),
      takeTrades: (now) => store.dueTrades(now), onTrade: (t) => setTrade(t),   // every car is a real trade on Strike
      // TradingView's chart and Strike's book follow the screen as the map moves: one transform each, written only
      // when it changes
      onScreen: (x, y, z) => {
        const c = canvas.current;
        if (!c) return;
        for (const [id, r] of OVERLAYS) {
          const sx = x + (r.x - SCREEN_CHART.x) * z, sy = y + (r.y - SCREEN_CHART.y) * z;
          const on = sx + r.w * z > 0 && sy + r.h * z > 0 && sx < c.clientWidth && sy < c.clientHeight;
          if (on && !seen.current[id]) { seen.current[id] = true; setTowerSeen({ ...seen.current }); }
          const el = overlay.current[id];
          if (!el) continue;
          const k = `${sx.toFixed(1)},${sy.toFixed(1)},${z.toFixed(4)}`;
          if (el.dataset.k === k) continue;
          el.dataset.k = k;
          el.style.transform = `translate3d(${sx}px, ${sy}px, 0) scale(${z / TV_K})`;
          el.style.visibility = on ? "" : "hidden";
        }
      },
    });
    engine.current = e;
    e.start();
    const deep = deepLink.current;
    if (deep && store.agent(deep)) { e.select({ kind: "agent", id: deep }, false); setSel({ kind: "agent", id: deep }); }
    return () => { e.stop(); engine.current = null; };
  }, [ready, store]);

  // the leads: one walker per lead Strike City follows, kept across readings (a new move on Strike sends it to the
  // exchange); they only move when their account does something
  useEffect(() => {
    if (!copyDoc || typeof copyDoc !== "object") return;
    const prev = new Map(leads.current.map((a) => [a.id, a]));
    leads.current = copyDoc.traders.filter((t) => t.walks).map((t) => leadView(t, prev.get(`lead:${t.id}`), leadR));
    keepLeadSlots(new Set(leads.current.map((a) => a.id)));
    const id = leadLink.current;
    if (id && engine.current && leads.current.some((a) => a.id === `lead:${id}`)) {
      leadLink.current = null;
      choose({ kind: "agent", id: `lead:${id}` });
      engine.current.setFollow(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [copyDoc, leadR]);
  useEffect(() => {
    if (!ready) return;
    const id = window.setInterval(() => {
      const now = performance.now();
      for (const a of leads.current) leadTick(a, now, leadR);
      for (const a of store.agents) {   // an agent copying a trader stands where that trader is
        if (!a.copying) continue;
        const l = leads.current.find((x) => x.lead && x.lead.id.toLowerCase() === a.copying!.lead.toLowerCase());
        const place = l?.target || "arena";
        if (a.copyPlace !== place) { a.copyPlace = place; a.nextAt = 0; }
      }
    }, 400);
    return () => window.clearInterval(id);
  }, [ready, leadR, store]);
  // a market's news reading turned (neutral -> bearish...): the agents trading it go to the News Tower to read it. The
  // first reading the page gets is where things stand, not a change
  const newsLabels = useRef<Record<string, string | null> | null>(null);
  useEffect(() => {
    if (!newsDoc || typeof newsDoc !== "object") return;
    const now = Object.fromEntries(Object.entries(newsDoc.markets).map(([m, r]) => [m, r.label]));
    const prev = newsLabels.current;
    newsLabels.current = now;
    const turned = prev ? Object.keys(now).filter((m) => prev[m] && now[m] && prev[m] !== now[m]) : [];
    if (turned.length) for (const a of store.agents) newsTrip(a, turned);
  }, [newsDoc, store]);

  // keep the followed agent visible between the card (left) and the side panel (right) on desktop, above the bottom
  // card on mobile
  useEffect(() => {
    const small = isSmall();
    const card = document.querySelector<HTMLElement>(".city-card");
    engine.current?.setInsets(panel && !small ? 384 : 0, small && card ? card.offsetHeight + 8 : 0, !small && card ? card.offsetWidth + 12 : 0);
  });

  // shareable deep link to the selected agent
  useEffect(() => {
    if (!ready) return;
    const base = "#/city";
    const want = me ? `${base}?me` : arena === "inside" ? `${base}?arena` : hq === "inside" ? `${base}?strike` : sel?.kind === "agent" ? (sel.id.startsWith("lead:") ? `${base}?lead=${sel.id.slice(5)}` : `${base}?agent=${sel.id}`) : base;
    if (location.hash !== want) history.replaceState(null, "", want);
  }, [sel, ready, me, arena, hq]);

  const choose = (s: Sel | null) => {
    engine.current?.select(s, false);
    setSel(s);
    setDetails(false);
    if (s && isSmall()) setPanel(null);
  };
  const togglePanel = (p: Panel | null) => { setMe(false); setPanel((cur) => (cur === p ? null : p)); };
  useEffect(() => {
    const doc = alertsDoc;
    if (!doc) return;
    const map = () => {
      const now = Date.now();
      alertMap.current = Object.fromEntries(Object.entries(byPlace(doc.alerts, now)).map(([k, a]) => [k, { level: a.level, text: a.title[langRef.current] }]));
    };
    map();
    const id = window.setInterval(map, 60_000);
    // a new alert of the last ten minutes shows in a toast; the ones already there when the city opens do not
    const fresh = doc.alerts.filter((a) => Date.now() - a.t < 10 * 60_000 && !seenAlerts.current?.has(a.id));
    if (seenAlerts.current && fresh.length) setAlertToast(fresh[0]);
    seenAlerts.current = new Set([...(seenAlerts.current ?? []), ...doc.alerts.map((a) => a.id)]);
    return () => window.clearInterval(id);
  }, [alertsDoc, lang]);
  useEffect(() => {
    if (!alertToast) return;
    const id = window.setTimeout(() => setAlertToast(null), 9000);
    return () => window.clearTimeout(id);
  }, [alertToast]);
  useEffect(() => {
    if (!ready || !alertsLink.current) return;
    alertsLink.current = false;
    setPanel("alerts");
  }, [ready]);
  // without a session "My agent" starts the wallet sign-in; with one it opens the dashboard over the map
  const openMe = () => {
    if (!myAgent) { onConnect(); return; }
    setPanel(null);
    setMe((v) => !v);
  };
  useEffect(() => { if (me && !myAgent) setMe(false); }, [me, myAgent]);
  useEffect(() => {
    const e = engine.current;
    if (!e) return;
    // only this page stops drawing the city: the agents keep trading and everyone else sees the city as always
    if (me || tower === "inside" || arena === "inside" || hq === "inside") e.pause(); else e.start();
  }, [me, ready, tower, arena, hq]);

  // the News Tower: your agent runs to its door (the camera follows it) and you go in with it; without an agent of
  // your own you go in as a visitor
  const mine = owner?.id ? store.agent(owner.id) : undefined;
  const enterTower = () => {
    const a = mine;
    if (!a || reduced) { setTower("inside"); return; }
    a.trip = { to: "news", until: performance.now() + 10 * 60_000 };
    a.rush = true; a.nextAt = 0; a.path = [];
    choose({ kind: "agent", id: a.id });
    engine.current?.setFollow(true);
    setTower("walking");
  };
  const leaveTower = () => {
    const a = mine;
    if (a?.trip?.to === "news") { a.trip = undefined; a.rush = false; a.nextAt = 0; }
    setTower(null);
    canvas.current?.focus();
  };
  useEffect(() => {
    if (!ready || !towerLink.current) return;
    towerLink.current = false;
    enterTower();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, version]);
  useEffect(() => {
    if (tower !== "walking") return;
    const t0 = Date.now();
    const id = window.setInterval(() => {
      const a = mine;
      // there (or still far after 15 s: in it goes)
      if (!a || (a.target === "news" && !a.path.length) || Date.now() - t0 > 15_000) { window.clearInterval(id); setTower("inside"); }
    }, 200);
    return () => window.clearInterval(id);
  }, [tower, mine]);

  // the Copy Arena: the same walk to its door (the agent runs there, the camera follows), then inside
  const enterArena = () => {
    const a = mine;
    if (!a || reduced) { setArena("inside"); return; }
    a.trip = { to: "arena", until: performance.now() + 10 * 60_000 };
    a.rush = true; a.nextAt = 0; a.path = [];
    choose({ kind: "agent", id: a.id });
    engine.current?.setFollow(true);
    setArena("walking");
  };
  const leaveArena = () => {
    const a = mine;
    if (a?.trip?.to === "arena") { a.trip = undefined; a.rush = false; a.nextAt = 0; }
    setArena(null);
    canvas.current?.focus();
  };
  useEffect(() => {
    if (!ready || !arenaLink.current) return;
    arenaLink.current = false;
    enterArena();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, version]);
  useEffect(() => {
    if (arena !== "walking") return;
    const t0 = Date.now();
    const id = window.setInterval(() => {
      const a = mine;
      if (!a || (a.target === "arena" && !a.path.length) || Date.now() - t0 > 15_000) { window.clearInterval(id); setArena("inside"); }
    }, 200);
    return () => window.clearInterval(id);
  }, [arena, mine]);

  // Strike Finance: the same walk to its door, then inside its hall
  const enterHq = () => {
    const a = mine;
    if (!a || reduced) { setHq("inside"); return; }
    a.trip = { to: "exchange", until: performance.now() + 10 * 60_000 };
    a.rush = true; a.nextAt = 0; a.path = [];
    choose({ kind: "agent", id: a.id });
    engine.current?.setFollow(true);
    setHq("walking");
  };
  const leaveHq = () => {
    const a = mine;
    if (a?.trip?.to === "exchange") { a.trip = undefined; a.rush = false; a.nextAt = 0; }
    setHq(null);
    canvas.current?.focus();
  };
  useEffect(() => {
    if (!ready || !hqLink.current) return;
    hqLink.current = false;
    enterHq();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, version]);
  useEffect(() => {
    if (hq !== "walking") return;
    const t0 = Date.now();
    const id = window.setInterval(() => {
      const a = mine;
      if (!a || (a.target === "exchange" && !a.path.length) || Date.now() - t0 > 15_000) { window.clearInterval(id); setHq("inside"); }
    }, 200);
    return () => window.clearInterval(id);
  }, [hq, mine]);

  // the hash changes inside the city (e.g. right after creating your agent): select it as soon as the city has it
  const pending = useRef<string | null>(null);
  useEffect(() => {
    const f = () => {
      if (wantsMe()) { setPanel(null); setMe(true); return; }
      const id = readDeepLink();
      if (id) { setMe(false); pending.current = id; void store.refreshCity(); }
    };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, [store]);
  useEffect(() => {
    const id = pending.current;
    if (!id || !ready || !engine.current || !store.agent(id)) return;
    pending.current = null;
    choose({ kind: "agent", id });
    engine.current.setFollow(true);
  });
  const closeWelcome = () => { setWelcome(false); try { localStorage.setItem("sf-city-welcome", "1"); } catch { /* private mode */ } canvas.current?.focus(); };

  // derived (recomputed at most once per second, when the store emits)
  const totals = store.totals(testSite);
  const btc = store.prices["BTC-USD"];
  weather.current = !btc ? 0 : Math.abs(btc.change) >= 4 ? 2 : Math.abs(btc.change) >= 1.5 ? 1 : 0;
  // the screen's tape: the latest decision an agent made (its warnings, like Strike not answering, stay in Feed)
  const latest = store.feed.find((x) => x.d.kind !== "analysis" && x.d.kind !== "alert") ?? store.feed.find((x) => x.d.kind !== "alert");
  const tape = tapeLine(newsDoc, T, lang, Date.now());   // the news reading and the next US release, after the agents' line
  newsRef.current = newsDoc;
  newsTape.current = newsDoc && typeof newsDoc === "object"
    ? newsDoc.headlines.filter((h) => h.catalyst).slice(0, 6).map((h) => (lang === "es" && h.es ? h.es : h.title).toUpperCase()).join("   ◆   ")
    : "";
  headline.current = (latest ? `${latest.agent.toUpperCase()} · ${describe(latest.d, T, lang).text}`
    : btc ? `EDGECRAFT-STRIKECITY · BTC ${fmtPrice(btc.price, lang)} ${fmtPct(btc.change, lang)}` : "EDGECRAFT-STRIKECITY")
    + (tape ? `      ${tape}` : "");
  const agent = sel?.kind === "agent" ? store.agent(sel.id) : undefined;
  const lead = sel?.kind === "agent" && sel.id.startsWith("lead:") ? leads.current.find((a) => a.id === sel.id) : undefined;
  const bld = sel?.kind === "building" ? BUILDINGS.find((b) => b.id === sel.id) : undefined;
  // copy with your agent: My agent opens with the plan for this trader (signing in first without a session)
  const copyWithAgent = (t: { id: string; platform: string }) => {
    if (!myAgent) { onConnect(); return; }
    setCopy(null);
    location.hash = `#/city?me&copy=${t.id}&pf=${t.platform}`;
  };
  // a trader from a list: followed in the city when it walks it, else its profile
  const openTrader = (id: string) => (leads.current.some((a) => a.id === `lead:${id}`) ? followLead(id) : setCopy({ open: id }));
  // from the chooser: the lead walking the city, selected and followed
  const followLead = (id: string) => {
    setCopy(null);
    if (!leads.current.some((a) => a.id === `lead:${id}`)) return;
    choose({ kind: "agent", id: `lead:${id}` });
    engine.current?.setFollow(true);
  };
  void version;

  return (
    <div className="city" data-ready={ready || undefined}>
      <header className="city-top">
        <a className="city-brand" href="#top" aria-label={`${T.back}: ${T.title}`}>
          <Mark size={32} /><span className="city-word"><span className="cw-pre">EdgeCraft<span className="cw-dash">-</span></span>StrikeCity</span>
        </a>
        {/* the city's figures (online, in a trade, the last 24 hours) live in Results, the map keeps the room */}
        <ul className="city-tickers" aria-label={T.markets.title}>
          {["BTC-USD", "ETH-USD", "SOL-USD"].map((m) => {
            const p = store.prices[m];
            return p ? (
              <li key={m}><button type="button" className="city-tk-btn" title={T.chart.open} onClick={() => setChart(m)}>
                <span className="sr-only">{T.chart.open}: </span><span className="tk">{ticker(m)}</span><span className="num">{fmtPrice(p.price, lang)}</span>
                <span className={`num ${p.change >= 0 ? "pos" : "neg"}`}>{fmtPct(p.change, lang)}</span></button></li>
            ) : null;
          })}
        </ul>
        <div className="city-top-actions">
          <EventSoon T={T} doc={newsDoc} now={Date.now()} onOpen={() => setNews("BTC-USD")} />
          <NewsButton T={T} lang={lang} doc={newsDoc} now={Date.now()} onOpen={() => setNews("BTC-USD")} />
          <span className={`city-weather w${weather.current}`} title={T.weather.tip}>
            <WeatherIcon w={weather.current} /><span className="hide-sm">{[T.weather.calm, T.weather.breezy, T.weather.storm][weather.current]}</span>
            <span className="sr-only">. {T.weather.tip}</span>
          </span>
          <div className="lang" role="group" aria-label="Language">
            <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>EN</button>
            <button type="button" aria-pressed={lang === "es"} onClick={() => setLang("es")}>ES</button>
          </div>
        </div>
      </header>

      <div className="city-stage">
        <canvas ref={canvas} className="city-canvas" tabIndex={0} role="application" aria-roledescription="map"
                aria-label={T.canvas(totals.live, totals.inTrade, leads.current.length)} />
        {/* it loads as soon as the city is drawn (loading it during the city's own load delayed the city ~0.35 s, measured);
            until its candles are drawn the screen shows the city's own chart (Strike's prices), then it fades in */}
        {ready && (
          <div ref={(el) => { overlay.current.strike = el; }} className={`city-tv${chartOn.strike ? " on" : ""}`} aria-hidden="true"
               style={{ width: SCREEN_CHART.w * TV_K, height: SCREEN_CHART.h * TV_K, visibility: "hidden" }}>
            <StrikeChart title={T.chart.screen} onReady={() => setChartOn((v) => ({ ...v, strike: true }))} />
          </div>
        )}
        {ready && TOWER_CHARTS.filter((t) => towerSeen[t.id]).map((t) => (
          <div key={t.id} ref={(el) => { overlay.current[t.id] = el; }} className={`city-tv${chartOn[t.id] ? " on" : ""}`} aria-hidden="true"
               style={{ width: t.w * TV_K, height: t.h * TV_K, visibility: "hidden" }}>
            <TradingViewChart market={t.market} lang={lang} title={T.chart.tower.replace("{m}", ticker(t.market))}
                              onReady={() => setChartOn((v) => ({ ...v, [t.id]: true }))} />
          </div>
        ))}
        {ready && store.book && (
          <div ref={(el) => { overlay.current.book = el; }} className="city-book" aria-hidden="true"
               style={{ width: SCREEN_BOOK.w * TV_K, height: SCREEN_BOOK.h * TV_K, visibility: "hidden" }}>
            <BookRows book={store.book} lang={lang} />
          </div>
        )}

        {!me && <SwarmScale T={T} n={totals.total} />}

        <div className="city-zoom" role="group" aria-label="Zoom" hidden={me}>
          <button type="button" className="city-fab" aria-label={T.zoomIn} title={T.zoomIn} onClick={() => engine.current?.zoomBy(1.25)}>+</button>
          <button type="button" className="city-fab" aria-label={T.zoomOut} title={T.zoomOut} onClick={() => engine.current?.zoomBy(0.8)}>−</button>
          <button type="button" className="city-fab" aria-label={T.recenter} title={T.recenter} onClick={() => { engine.current?.recenter(); choose(null); }}><Ico.target /></button>
        </div>

        {panel && (
          <section id="city-panel" className="city-panel" aria-labelledby="city-panel-title">
            <div className="city-panel-head">
              <h2 id="city-panel-title">{panelTitle(panel, T)}</h2>
              <button type="button" className="icon-btn" aria-label={T.card.close} onClick={() => setPanel(null)}><Icon.close /></button>
            </div>
            <div className="city-panel-body">
              {panel === "agents" && <AgentsPanel T={T} lang={lang} store={store} leads={leads.current} selected={agent?.id ?? lead?.id}
                                                  traders={copyDoc && typeof copyDoc === "object" ? copyDoc.traders : []}
                                                  onPick={(id) => choose({ kind: "agent", id })} onTrader={openTrader} />}
              {panel === "ranks" && <ResultsPanel T={T} lang={lang} store={store} testSite={testSite} totals={totals} onPick={(id) => choose({ kind: "agent", id })} onConnect={onConnect}
                                               leads={leads.current.length}
                                                copy={copyDoc} onArena={enterArena} onTrader={openTrader} />}
              {panel === "feed" && <FeedPanel T={T} lang={lang} store={store} onPick={(id) => choose({ kind: "agent", id })} />}
              {panel === "markets" && <MarketsPanel T={T} lang={lang} store={store} onPick={(id) => choose({ kind: "building", id })} />}
              {panel === "guide" && <GuidePanel T={T} n={totals.total} copyPilot={copyPilot} />}
              {panel === "alerts" && <AlertsPanel T={T} lang={lang} doc={alertsDoc} owner={owner?.token ? { token: owner.token } : null}
                                                  onConnect={onConnect} onPlace={(place) => choose({ kind: "building", id: place })} />}
            </div>
          </section>
        )}

        {me && myAgent && (
          <div className="city-me" role="region" aria-label={T.nav.me}>
            <div className="city-me-bar">
              <button type="button" className="btn btn-ghost" onClick={() => setMe(false)}><Icon.back /> {T.me.back}</button>
            </div>
            {myAgent}
          </div>
        )}

        {agent && !me && !(panel && isSmall()) && (
          <AgentCard T={T} lang={lang} a={agent} following={engine.current?.following === agent.id}
                     onFollow={() => { engine.current?.setFollow(engine.current.following !== agent.id); force((x) => x + 1); }}
                     onDetails={() => setDetails(true)} onClose={() => choose(null)} marks={marksOf(store.prices)}
                     context={agent.position ? contextLine(newsDoc, agent.position.market, T, lang, Date.now()) : null}
                     job={jobLabel(agent, newsDoc, store.prices, lang)} />
        )}
        {lead?.lead && !me && !(panel && isSmall()) && (
          <LeadCard T={T} lang={lang} t={lead.lead} following={engine.current?.following === lead.id} followIcon={<Ico.target />}
                    onFollow={() => { engine.current?.setFollow(engine.current.following !== lead.id); force((x) => x + 1); }}
                    onProfile={() => setCopy({ open: lead.lead!.id })} onClose={() => choose(null)}
                    onCopy={copyPilot ? () => copyWithAgent(lead.lead!) : undefined} />
        )}
        {bld && !me && !(panel && isSmall()) && (
          <aside className="city-card" aria-labelledby="bld-title">
            <div className="city-card-head">
              <span className="bld-swatch" style={{ background: bld.neon }} aria-hidden="true" />
              <div className="grow"><h2 id="bld-title" className="city-card-name">{bld.label}</h2>{bld.sub && <p className="faint small">{bld.sub}</p>}</div>
              <button type="button" className="icon-btn" aria-label={T.building.close} onClick={() => choose(null)}><Icon.close /></button>
            </div>
            <p className="muted city-card-text">{T.buildings[bld.id]}</p>
            <p className="small faint">{T.building.agentsHere(store.agents.filter((a) => a.target === bld.id && !a.path.length).length)}</p>
            {bld.id === "arena" && leads.current.length > 0 && <p className="small faint">{T.copy.inCity(leads.current.length)}</p>}
            {(bld.market || bld.id === "exchange") && (
              <button type="button" className="btn btn-ghost btn-block city-card-chart" onClick={() => setChart(bld.market ?? "STRIKE")}>{T.chart.open}</button>
            )}
            {bld.id === "exchange" && (
              <div className="city-card-actions">
                <button type="button" className="btn btn-primary btn-block" onClick={enterHq}>{T.hq.enter}</button>
              </div>
            )}
            {bld.id === "arena" && (
              <div className="city-card-actions">
                <button type="button" className="btn btn-primary btn-block" onClick={enterArena}>{T.copy.enter}</button>
                <button type="button" className="btn btn-ghost btn-block" onClick={() => setCopy({ open: null })}>{T.copy.quick}</button>
              </div>
            )}
            {bld.id === "news" && (
              <div className="city-card-actions">
                <button type="button" className="btn btn-primary btn-block" onClick={enterTower}>{mine ? T.tower.enter : T.tower.visitorEnter}</button>
                <button type="button" className="btn btn-ghost btn-block" onClick={() => setNews("BTC-USD")}>{T.tower.quick}</button>
              </div>
            )}
          </aside>
        )}

        {tower === "walking" && mine && (
          <div className="city-toast" role="status">
            <p>{T.tower.entering(mine.name)}</p>
            <button type="button" className="btn btn-primary" onClick={() => setTower("inside")}>{T.tower.enterNow}</button>
            <button type="button" className="icon-btn" aria-label={T.card.close} onClick={leaveTower}><Icon.close /></button>
          </div>
        )}

        {trade && (   // a pressed car: the real Strike trade it is
          <div className="city-toast city-trade" role="status">
            <p><strong>{T.trade.title}</strong><br />
              <span className={trade.side === "buy" ? "pos" : "neg"}>{ticker(trade.market)} · {trade.side === "buy" ? T.trade.bought : T.trade.sold}</span>{" "}
              {trade.qty.toLocaleString(lang === "es" ? "es-ES" : "en-US", { maximumSignificantDigits: 6 })} @ {fmtPrice(trade.price, lang)} ·{" "}
              {trade.usd.toLocaleString(lang === "es" ? "es-ES" : "en-US", { maximumFractionDigits: 2 })} $ · {ago(T, trade.time)}<br />
              <span className="faint small">{T.trade.note}</span></p>
            <button type="button" className="icon-btn" aria-label={T.card.close} onClick={() => setTrade(null)}><Icon.close /></button>
          </div>
        )}

        {alertToast && !trade && (   // a new Strike alert: a press shows it among the others
          <div className={`city-toast city-alert-toast ${alertToast.level}`} role="status">
            <p><strong>{T.alerts.toast} · {T.alerts.kinds[alertToast.kind] ?? alertToast.kind}</strong><br />{alertToast.title[lang]}</p>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setAlertToast(null); setMe(false); setPanel("alerts"); }}>{T.alerts.see}</button>
            <button type="button" className="icon-btn" aria-label={T.card.close} onClick={() => setAlertToast(null)}><Icon.close /></button>
          </div>
        )}

        {hq === "walking" && mine && (
          <div className="city-toast" role="status">
            <p>{T.hq.entering(mine.name)}</p>
            <button type="button" className="btn btn-primary" onClick={() => setHq("inside")}>{T.tower.enterNow}</button>
            <button type="button" className="icon-btn" aria-label={T.card.close} onClick={leaveHq}><Icon.close /></button>
          </div>
        )}

        {arena === "walking" && mine && (
          <div className="city-toast" role="status">
            <p>{T.copy.entering(mine.name)}</p>
            <button type="button" className="btn btn-primary" onClick={() => setArena("inside")}>{T.tower.enterNow}</button>
            <button type="button" className="icon-btn" aria-label={T.card.close} onClick={leaveArena}><Icon.close /></button>
          </div>
        )}

        {!ready && (
          <div className="city-loading" role="status" aria-live="polite">
            <div className="city-loading-inner">
              <Mark size={48} />
              <p className="city-loading-title">{T.loading.toUpperCase()}</p>
              <p className="muted">{T.loadingSteps[Math.min(T.loadingSteps.length - 1, Math.floor(progress * T.loadingSteps.length))]}</p>
              <div className="city-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} aria-label={T.loading}>
                <span style={{ width: `${Math.round(progress * 100)}%` }} />
              </div>
            </div>
          </div>
        )}
        {ready && store.source !== "strike" && <p className="city-source-warn" role="status">{T.source[store.source]}</p>}
        {ready && !store.agents.length && (
          <div className="city-empty" role="status">
            <p className="city-empty-title">{T.empty.title}</p>
            <p className="muted">{store.apiOk ? T.empty.body : T.empty.offline}</p>
            {store.apiOk && <button type="button" className="btn btn-primary" onClick={onConnect}>{T.ranks.cta}</button>}
          </div>
        )}
      </div>

      <nav className="city-dock" aria-label={T.title}>
        <DockBtn label={T.nav.map} active={!panel && !me} onClick={() => { setPanel(null); setMe(false); }} icon={<Ico.map />} className="city-dock-map" />
        <DockBtn label={T.nav.agents} active={panel === "agents"} onClick={() => togglePanel("agents")} icon={<Ico.users />} controls />
        <DockBtn label={T.nav.ranks} active={panel === "ranks"} onClick={() => togglePanel("ranks")} icon={<Ico.trophy />} controls />
        <DockBtn label={T.nav.feed} active={panel === "feed"} onClick={() => togglePanel("feed")} icon={<Ico.pulse />} controls />
        <DockBtn label={T.nav.markets} active={panel === "markets"} onClick={() => togglePanel("markets")} icon={<Ico.bars />} controls />
        <DockBtn label={T.nav.alerts} active={panel === "alerts"} onClick={() => togglePanel("alerts")} icon={<Ico.bell />} controls />
        <DockBtn label={T.nav.guide} active={panel === "guide"} onClick={() => togglePanel("guide")} icon={<Ico.help />} controls />
        {myAgent ? <DockBtn label={T.nav.me} active={me} onClick={openMe} icon={<Ico.user />} /> : (
          // no wallet yet: this place is where you connect one (My agent comes back once you have)
          <button type="button" className="city-dock-btn city-dock-connect" onClick={onConnect} aria-haspopup="dialog" aria-label={T.nav.connect}>
            <Ico.wallet /><span className="lg" aria-hidden="true">{T.nav.connect}</span><span className="sm" aria-hidden="true">{T.nav.connectShort}</span>
          </button>
        )}
        {onFeedback && (   // suggestions, where everyone sees them: it opens a dialog (no pressed state)
          <button type="button" className="city-dock-btn city-dock-fb" onClick={onFeedback} aria-haspopup="dialog" title={dict[lang].feedback.title}>
            <FeedbackIcon size={20} /><span>{T.nav.feedback}</span>
          </button>
        )}
      </nav>

      {ready && welcome && (
        <Modal onClose={closeWelcome} labelledBy="welcome-title" className="city-welcome">
          <div className="dialog-brand"><Mark size={48} /></div>
          <h2 id="welcome-title" className="center">{T.welcome.title}</h2>
          <p className="dialog-sub center">{T.welcome.lead}</p>
          <ul className="city-points">{T.welcome.points.map((p) => <li key={p}><Icon.check size={16} />{p}</li>)}</ul>
          <div className="alert alert-live" role="note"><span className="city-live-dot" aria-hidden="true" /><div>{T.welcome.liveNote}</div></div>
          <div className="actions"><button type="button" className="btn btn-primary btn-lg btn-block" data-autofocus onClick={closeWelcome}>{T.welcome.enter}</button></div>
        </Modal>
      )}
      {chart && <ChartModal T={T} lang={lang} market={chart} onMarket={setChart} onClose={() => setChart(null)} />}
      {news && (
        <Modal onClose={() => setNews(null)} labelledBy="news-title" className="city-chart city-news">
          <NewsView T={T} lang={lang} doc={newsDoc} market={news} onMarket={setNews} onClose={() => setNews(null)} live={totals.live} inTrade={totals.inTrade} />
        </Modal>
      )}
      {tower === "inside" && (
        <TowerView T={T} lang={lang} doc={newsDoc} agent={mine ?? null} market0={mine?.position?.market ?? mine?.markets[0] ?? "BTC-USD"} onExit={leaveTower} />
      )}
      {copy && (
        <Modal onClose={() => setCopy(null)} labelledBy="copy-title" className="city-chart city-copy">
          <div className="chart-head">
            <h2 id="copy-title" className="grow">{T.copy.choose}</h2>
            <button type="button" className="icon-btn" aria-label={T.card.close} data-autofocus onClick={() => setCopy(null)}><Icon.close /></button>
          </div>
          <div className="cp-body"><CopyChooser T={T} lang={lang} doc={copyDoc} initial={copy.open} onFollow={followLead}
                                                 onCopy={copyPilot ? copyWithAgent : undefined} /></div>
        </Modal>
      )}
      {hq === "inside" && (
        <StrikeView T={T} lang={lang} stats={hqStats} agent={mine ?? null} onExit={leaveHq}
                    vol24={Object.values(store.prices).reduce((a, p) => a + (p.volume ?? 0), 0) || null} />
      )}
      {arena === "inside" && (
        <ArenaView T={T} lang={lang} doc={copyDoc} agent={mine ?? null} onExit={leaveArena}
                   onFollow={(id) => { leaveArena(); followLead(id); }}
                   onCopy={copyPilot ? (t) => { leaveArena(); copyWithAgent(t); } : undefined} />
      )}
      {details && agent && <DetailsModal T={T} lang={lang} a={agent} marks={marksOf(store.prices)} onClose={() => setDetails(false)} />}
    </div>
  );
}

function panelTitle(p: Panel, T: CityText) {
  return { agents: T.agents.title, ranks: T.results.title, feed: T.feed.title, markets: T.markets.title, guide: T.guide.title, alerts: T.alerts.title }[p];
}

// ---------------------------------------------------------------- pieces
function DockBtn({ label, active, onClick, icon, controls, className }: { label: string; active: boolean; onClick: () => void; icon: ReactNode;
  controls?: boolean; className?: string }) {
  return (
    <button type="button" className={`city-dock-btn${className ? ` ${className}` : ""}`} aria-pressed={active} aria-controls={controls && active ? "city-panel" : undefined} onClick={onClick}>
      {icon}<span>{label}</span>
    </button>
  );
}

function SwarmScale({ T, n, inline }: { T: CityText; n: number; inline?: boolean }) {
  const level = SCALE.filter((s) => n >= s).length;
  const next = SCALE[level];
  const prev = SCALE[level - 1] ?? 0;
  const k = next ? Math.min(1, (n - prev) / (next - prev)) : 1;
  return (
    <div className={inline ? "city-scale city-scale-inline" : "city-scale city-scale-float"}>
      <p className="city-scale-title">{T.scale.title}</p>
      <p className="city-scale-level"><strong>{T.scale.names[Math.max(0, level - 1)]}</strong> <span className="faint">· {T.scale.level(level, SCALE.length)}</span></p>
      <div className="city-scale-steps" aria-hidden="true">
        {SCALE.map((s, i) => <span key={s} className={i < level ? "on" : i === level ? "part" : ""} style={i === level ? { ["--k" as string]: k } : undefined} />)}
      </div>
      {next && <p className="faint small">{T.scale.next(next)}</p>}
    </div>
  );
}

// the character facing you, from the top of its head to its feet (16 x 22 art px); drawn again once its pieces load
const AV_H = FEET + 1 - HEAD_TOP;
function Avatar({ id, look, size = 24 }: { id: string; look?: Look; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const draw = () => {
      const c = ref.current, sheet = sheetFor(id, look);
      if (!c || !sheet) return false;
      const g = c.getContext("2d")!;
      g.imageSmoothingEnabled = false;
      g.clearRect(0, 0, c.width, c.height);
      const [sx, sy] = frameAt("idle", "down", 0);
      g.drawImage(sheet, sx, sy + HEAD_TOP, FW, AV_H, 0, 0, c.width, c.height);
      return true;
    };
    if (draw()) return;
    return onSheet(() => { draw(); });
  }, [id, look]);
  return <canvas ref={ref} className="city-avatar" width={FW * 2} height={AV_H * 2} style={{ width: size, height: (size * AV_H) / FW }} aria-hidden="true" />;
}

function Glyph({ status, side }: { status: Status; side?: "long" | "short" }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const g = c.getContext("2d")!;
    g.setTransform(2, 0, 0, 2, 0, 0);
    g.clearRect(0, 0, 18, 18);
    const color = status === "in_trade" ? (side === "short" ? "#f43f5e" : "#4efab0") : STATUS_COLOR[status];
    drawIcon(g, { status, position: side ? { market: "", side, entry: 0, stop: 0, trail: 0, size: 0, rOpen: 0, stopKnown: true, upnl: null } : null }, 0, 0, 18, 18, color);
  }, [status, side]);
  return <canvas ref={ref} width={36} height={36} className="city-glyph" aria-hidden="true" />;
}

function StatusPill({ T, a }: { T: CityText; a: AgentView }) {
  const color = a.status === "in_trade" && a.position ? (a.position.side === "long" ? "#4efab0" : "#f43f5e") : STATUS_COLOR[a.status];
  return <span className="city-pill" style={{ color, borderColor: `${color}55`, background: `${color}14` }}>{T.status[a.status]}</span>;
}

function ago(T: CityText, time: number) { return T.ago((Date.now() - time) / 1000); }

const tfLabel = (tf: string) => ({ "60": "1h", "120": "2h", "240": "4h", D: "1D", W: "1W" } as Record<string, string>)[tf] ?? tf;

/** "BTC · ETH · SOL +5": long market lists stay on one line. */
const marketList = (ms: string[]) => ms.slice(0, 3).map(ticker).join(" · ") + (ms.length > 3 ? ` +${ms.length - 3}` : "");

const owner = (T: CityText, a: AgentView) => (a.owner === "Strike user" ? T.ownerUser : a.owner);

function KindTag({ T, a, short }: { T: CityText; a: AgentView; short?: boolean }) {
  // a user's agent on Strike testnet trades test money: never labelled as real (a list row says "Testnet", the rest
  // stays in its tooltip and for screen readers)
  if (a.kind === "live" && a.real?.env === "testnet") {
    return short ? <span className="city-tag testnet" title={T.kindTestnet}><span aria-hidden="true">{T.kindTestnetShort}</span><span className="sr-only">{T.kindTestnet}</span></span>
      : <span className="city-tag testnet">{T.kindTestnet}</span>;
  }
  return <span className={`city-tag ${a.kind === "live" ? "real" : "live"}`}>{a.kind === "live" ? T.kindLive : T.realTag}</span>;
}

const money = (v: number, lang: Lang) => v.toLocaleString(lang === "es" ? "es-ES" : "en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function AgentCard({ T, lang, a, following, onFollow, onDetails, onClose, marks, context, job }: { T: CityText; lang: Lang; a: AgentView; following: boolean;
  onFollow: () => void; onDetails: () => void; onClose: () => void; marks: Record<string, number>; context?: string | null; job?: string | null }) {
  const PT = dict[lang].persona;
  const last = nowDecision(a);
  const p = a.position;
  const today = a.trades.filter((x) => x.time >= Date.now() - 86400_000).reduce((s, x) => s + x.r, 0);
  const real = a.real;
  const nOpen = real?.positions.length ?? 0;
  // a live agent: its Strike account, as a share of it (the amounts are its owner's), moving with live prices
  const pf = a.portfolio;
  const pfPos = pf && p ? pf.positions.find((x) => x.market === p.market) : undefined;
  const share = pfPos ? livePosition(pfPos, marks).pct : null;
  const pct = (v: number) => v.toLocaleString(lang === "es" ? "es-ES" : "en-US", { style: "percent", minimumFractionDigits: 2, signDisplay: "exceptZero" });
  const accountRows = pf && (
    <>
      {pf.ret != null && <div><dt>{T.card.ret}</dt><dd className={`num ${pf.ret >= 0 ? "pos" : "neg"}`}>{pct(pf.ret)}</dd></div>}
      <div><dt>{T.card.positions}</dt><dd className="num">{pf.positions.length}</dd></div>
    </>
  );
  return (
    <aside className="city-card" aria-labelledby="agent-card-title">
      <div className="city-card-head">
        <Avatar id={a.id} look={a.look} size={30} />
        <div className="grow">
          <h2 id="agent-card-title" className="city-card-name">{a.name}</h2>
          <p className="faint small mono">{owner(T, a)}</p>
        </div>
        <button type="button" className="icon-btn" aria-label={T.card.close} onClick={onClose}><Icon.close /></button>
      </div>
      <div className="city-card-status"><KindTag T={T} a={a} />{strategyDef(a.strategy ?? "").tag && a.strategy !== DEFAULT_STRATEGY && <span className="city-tag strat">{strategyDef(a.strategy!).tag}</span>}<StatusPill T={T} a={a} /><span className="faint small">{a.real ? `${tfLabel(a.real.tf)} · ` : ""}{marketList(a.markets)}</span></div>
      {a.copying && (
        <p className="city-card-copying small"><span className="city-tag lead">{T.copy.leadTag}</span>{" "}
          {T.copy.agentCopies(traderName({ id: a.copying.lead, platform: a.copying.platform === "hyperliquid" ? "hyperliquid" : "strike" }))}</p>
      )}
      <p className="city-card-label">{T.card.now}</p>
      <p className="city-card-text">{a.status === "unfunded" ? T.unfundedNow : last ? describe(last, T, lang).text : T.status[a.status]}</p>
      {last?.code === "checks" && a.status !== "unfunded" && (   // each market it checked, and why it did not trade it
        <ul className="city-checks">{lastChecks(a).map((c) => (
          <li key={c.market}><b>{ticker(c.market)}</b> {describe(c, T, lang).text.replace(/^[^:]+:\s*/, "")}</li>
        ))}</ul>
      )}
      {p ? (
        <dl className="city-kv">
          <div><dt>{T.card.position}</dt><dd className={p.side === "long" ? "pos" : "neg"}>{p.side === "long" ? "LONG" : "SHORT"} {ticker(p.market)}</dd></div>
          <div><dt>{T.card.entry}</dt><dd className="num">{fmtPrice(p.entry, lang)}</dd></div>
          <div><dt>{T.card.stop}</dt><dd className="num">{p.stopKnown ? fmtPrice(p.stop, lang) : "—"}</dd></div>
          {p.stopKnown && p.trail !== p.stop && <div><dt>{T.card.exit}</dt><dd className="num">{fmtPrice(p.trail, lang)}</dd></div>}
          {p.stopKnown
            ? <div><dt>{T.card.rOpen}</dt><dd className={`num ${p.rOpen >= 0 ? "pos" : "neg"}`}>{fmtR(p.rOpen, lang)}</dd></div>
            : share != null ? <div><dt>{T.card.pnl}</dt><dd className={`num ${share >= 0 ? "pos" : "neg"}`}>{pct(share)}</dd></div>
            : p.upnl != null && <div><dt>{T.card.pnl}</dt><dd className={`num ${p.upnl >= 0 ? "pos" : "neg"}`}>{money(p.upnl, lang)}</dd></div>}
          {pf ? accountRows : nOpen > 1 && <div><dt /><dd className="faint">{T.card.more(nOpen - 1)}</dd></div>}
        </dl>
      ) : real ? (
        <dl className="city-kv">
          {a.status !== "offline" && <div><dt>{T.card.nextCheck}</dt><dd>{T.inTime((real.nextCheck - Date.now()) / 1000)}</dd></div>}
          {real.lastCheck && <div><dt>{T.card.lastCheck}</dt><dd>{ago(T, real.lastCheck)}</dd></div>}
          {real.cash != null && real.equity0 != null && (
            // a live account: its result leaves deposits out (equity0 = start + money deposited since)
            (() => { const ret = real.result != null ? real.result / real.equity0 : real.cash / real.equity0 - 1;
              return <div><dt>{a.kind === "live" ? T.card.accountLive : T.card.account}</dt><dd className="num">{money(real.cash, lang)} <span className={ret >= 0 ? "pos" : "neg"}>{fmtPct(ret * 100, lang)}</span></dd></div>; })()
          )}
          {accountRows}
          <div><dt>{T.card.trades}</dt><dd className="num">{a.trades.length}</dd></div>
        </dl>
      ) : (
        <dl className="city-kv">
          <div><dt>{T.card.risk}</dt><dd className="num">{a.risk.toLocaleString(lang === "es" ? "es-ES" : "en-US")}%</dd></div>
          <div><dt>{T.card.today}</dt><dd className={`num ${today >= 0 ? "pos" : "neg"}`}>{fmtR(today, lang)}</dd></div>
        </dl>
      )}
      {a.persona && (   // its personality and trade (never how it trades): what it says, what it reads at work
        <div className="city-persona" style={{ ["--tc" as string]: TEMPER_COLOR[a.persona.temper] }}>
          <p className="city-say">“{sayLine(a, lang)}”</p>
          <p className="small"><span className="city-persona-t">{PT.tempers[a.persona.temper].name}</span>
            <span className="faint"> · {PT.jobs[a.persona.job].name}{job ? ` · ${atWork(a) ? PT.atWork(PT.jobs[a.persona.job].place) : PT.worksAt(PT.jobs[a.persona.job].place)}` : ""}</span></p>
          {job && <p className="small mono city-persona-job">{job}</p>}
          {a.trip?.to === "news" && a.trip.market && <p className="small faint">{PT.newsTurned(ticker(a.trip.market))}</p>}
        </div>
      )}
      {p && context && <p className="city-card-context small"><span className="muted">{T.news.context}:</span> {context} <span className="faint">({T.news.contextNote})</span></p>}
      <div className="city-card-actions">
        <button type="button" className="btn btn-ghost" aria-pressed={following} onClick={onFollow}><Ico.target />{following ? T.card.following : T.card.follow}</button>
        <button type="button" className="btn btn-primary" onClick={onDetails}>{T.card.details}</button>
      </div>
    </aside>
  );
}

/** Everyone walking the city: the agents (Smart Flow's and its users'), then the traders people copy on Strike. */
function AgentsPanel({ T, lang, store, leads, traders, selected, onPick, onTrader }: { T: CityText; lang: Lang; store: CityStore; leads: AgentView[];
  traders: Trader[]; selected?: string; onPick: (id: string) => void; onTrader: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [f, setF] = useState<"all" | "in_trade" | "analyzing" | "waiting" | "paused" | "leads">("all");
  const groups: Record<Exclude<typeof f, "leads">, Status[]> = { all: [], in_trade: ["in_trade", "entering"], analyzing: ["analyzing", "signal", "risk", "exiting"], waiting: ["waiting", "unfunded"], paused: ["paused", "offline"] };
  const match = (a: AgentView) => a.name.toLowerCase().includes(q.trim().toLowerCase());
  const list = f === "leads" ? [] : store.agents.filter((a) => (f === "all" || groups[f].includes(a.status)) && match(a));
  const leadList = f === "all" || f === "leads" ? leads.filter(match).sort((x, y) => (y.lead?.city ?? 0) - (x.lead?.city ?? 0)) : [];
  // every other trader people can copy on Strike (only some walk the city at a time): its profile opens on a press
  const walking = new Set(leads.map((a) => a.lead?.id.toLowerCase()));
  const others = f === "all" || f === "leads"
    ? traders.filter((t) => !walking.has(t.id.toLowerCase()) && traderName(t).toLowerCase().includes(q.trim().toLowerCase()))
      .sort((x, y) => (y.city ?? 0) - (x.city ?? 0))
    : [];
  const traderCount = leadList.length + others.length;
  // what a trader holds: its side and market for one position, the logos of the largest two and "+n" for more
  const holding = (t: Trader | undefined, score: number | null) => {
    const ps = t ? positionsBySize(t) : [];
    const side = (p: (typeof ps)[number]) => `${p.side === "long" ? "LONG" : "SHORT"} ${ticker(p.market)}`;
    if (ps.length > 1) return <MarketLogos markets={ps.map((p) => p.market)} names={ps.map(side).join(", ")} label={T.agents.holds} />;
    if (ps.length === 1) return <span className={`small strong city-hold ${ps[0].side === "long" ? "pos" : "neg"}`}><MarketLogo m={ps[0].market} />{side(ps[0])}</span>;
    return <span className="num city-copy-score" title={T.copy.cityScore}><span className="sr-only">{T.copy.cityScore}: </span>{score == null ? "—" : Math.round(score)}</span>;
  };
  const otherRows = (
    <ul className="city-list">
      {others.map((t) => {
        return (
          <li key={t.id}>
            <button type="button" className="city-row real" onClick={() => onTrader(t.id)}>
              <Avatar id={`lead:${t.id}`} />
              <span className="grow"><span className="city-row-name">{traderName(t)}</span>
                <span className="city-row-tags"><span className="city-tag lead">{T.copy.leadTag}</span>
                  <span className={`cp-plat ${t.platform}`}>{t.platform === "hyperliquid" ? "Hyperliquid" : "Strike"}</span></span></span>
              {holding(t, t.city ?? null)}
            </button>
          </li>
        );
      })}
    </ul>
  );
  const leadRows = (
    <ul className="city-list">
      {leadList.map((a) => {
        return (
          <li key={a.id}>
            <button type="button" className="city-row real" aria-current={selected === a.id || undefined} onClick={() => onPick(a.id)}>
              <Avatar id={a.id} />
              <span className="grow"><span className="city-row-name">{a.name}</span>
                <span className="city-row-tags"><span className="city-tag lead">{T.copy.leadTag}</span>
                  <span className={`cp-plat ${a.lead?.platform}`}>{a.lead?.platform === "hyperliquid" ? "Hyperliquid" : "Strike"}</span></span></span>
              {holding(a.lead, a.lead?.city ?? 0)}
            </button>
          </li>
        );
      })}
    </ul>
  );
  const rows = (xs: AgentView[]) => (
    <ul className="city-list">
      {xs.map((a) => (
        <li key={a.id}>
          <button type="button" className="city-row real" aria-current={selected === a.id || undefined} onClick={() => onPick(a.id)}>
            <Avatar id={a.id} look={a.look} />
            <span className="grow"><span className="city-row-name">{a.name}</span>
              <span className="city-row-tags"><KindTag T={T} a={a} short /><StatusPill T={T} a={a} /></span></span>
            <span className="city-row-end">
              {a.position && <span className={`num ${a.position.rOpen >= 0 ? "pos" : "neg"}`}>{fmtR(a.position.rOpen, lang)}</span>}
              <MarketLogos markets={a.markets.length ? a.markets : [a.focus]} label={T.agents.analyses} />
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
  return (
    <>
      <label className="city-search"><span className="sr-only">{T.agents.search}</span>
        <input type="search" placeholder={T.agents.search} value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      <div className="city-filters" role="group" aria-label={T.agents.title}>
        {(Object.keys(groups) as (typeof f)[]).map((k) => (
          <button key={k} type="button" aria-pressed={f === k} onClick={() => setF(k)}>{k === "all" ? T.agents.all : T.status[k as Status]}</button>
        ))}
        {(leads.length > 0 || traders.length > 0) && <button type="button" aria-pressed={f === "leads"} onClick={() => setF("leads")}>{T.agents.leads}</button>}
      </div>
      <p className="faint small" aria-live="polite">{f === "leads" ? T.agents.leadCount(traderCount) : f === "all" && traderCount
        ? `${T.agents.count(list.length)} · ${T.agents.leadCount(traderCount)}` : T.agents.count(list.length)}</p>
      {!list.length && !traderCount && <p className="muted">{T.agents.none}</p>}
      {list.length > 0 && rows(list)}
      {traderCount > 0 && (
        <section className="city-leads" aria-labelledby="city-leads-title">
          <h3 id="city-leads-title" className="city-leads-title">{T.agents.leads}</h3>
          {leadList.length > 0 && <>
            <h4 className="city-leads-sub">{T.agents.inCity} · {leadList.length}</h4>
            <p className="small faint">{T.agents.leadsAbout}</p>
            {leadRows}
          </>}
          {others.length > 0 && <>
            <h4 className="city-leads-sub">{T.agents.moreTraders} · {others.length}</h4>
            <p className="small faint">{T.agents.moreAbout}</p>
            {otherRows}
          </>}
        </section>
      )}
    </>
  );
}

type RTab = "overview" | "strategies" | "copilot" | "strike" | "ranking";
const RTABS: RTab[] = ["overview", "strategies", "copilot", "strike", "ranking"];

/** Results: the agents on the marketplace's strategies, the copies agents run, Strike's copy trading and the ranking,
 *  each in a tab (WAI-ARIA tabs: arrows move between them). Production counts real accounts only; staging all. */
function ResultsPanel({ T, lang, store, testSite, totals, onPick, onConnect, copy, onArena, onTrader, leads }: { T: CityText; lang: Lang; store: CityStore;
  testSite?: boolean; totals: ReturnType<CityStore["totals"]>; onPick: (id: string) => void; onConnect: () => void; copy: CopyState; onArena: () => void; onTrader: (id: string) => void; leads: number }) {
  const R = T.results, loc = lang === "es" ? "es-ES" : "en-US";
  const [tab, setTab] = useState<RTab>("overview");
  const btns = useRef<(HTMLButtonElement | null)[]>([]);
  const doc = copy && typeof copy === "object" ? copy : null;
  const agents = store.agents;
  const all = agents.map((a) => stats(a));
  const n = all.reduce((s, x) => s + x.n, 0);
  const wins = all.reduce((s, x) => s + x.winRate * x.n, 0);
  const totalR = all.reduce((s, x) => s + x.totalR, 0);
  const copying = agents.filter((a) => a.copying);
  const pct = (v: number) => `${(v * 100).toLocaleString(loc, { maximumFractionDigits: 0 })} %`;
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = RTABS.indexOf(tab), j = e.key === "ArrowRight" ? (i + 1) % RTABS.length : e.key === "ArrowLeft" ? (i - 1 + RTABS.length) % RTABS.length
      : e.key === "Home" ? 0 : e.key === "End" ? RTABS.length - 1 : -1;
    if (j < 0) return;
    e.preventDefault(); setTab(RTABS[j]); btns.current[j]?.focus();
  };
  const tile = (label: string, value: string, tone = "", k?: string) => <div className="rs-tile" data-k={k}><span>{label}</span><b className={`num ${tone}`}>{value}</b></div>;
  return (
    <div className="rs">
      <div className="rs-tabs" role="tablist" aria-label={R.tabs} onKeyDown={onKey}>
        {RTABS.map((x, i) => (
          <button key={x} ref={(el) => { btns.current[i] = el; }} type="button" role="tab" id={`rs-tab-${x}`} aria-selected={tab === x}
                  aria-controls="rs-panel" tabIndex={tab === x ? 0 : -1} onClick={() => setTab(x)}>{R.t[x]}</button>
        ))}
      </div>
      <div id="rs-panel" role="tabpanel" aria-labelledby={`rs-tab-${tab}`} className="rs-panel">
        {tab === "overview" && (
          <>
            <p className="small faint">{testSite ? R.allHere : R.realOnly}</p>
            <div className="rs-tiles">
              {tile(R.k.online, String(totals.live), "", "online")}
              {tile(R.k.inTrade, String(totals.inTrade), "", "inTrade")}
              {tile(R.k.trades24, totals.trades.toLocaleString(loc), "", "trades24")}
              {tile(R.k.r24, fmtR(totals.rToday, lang), totals.trades ? (totals.rToday >= 0 ? "pos" : "neg") : "", "r24")}
              {tile(R.k.agents, String(agents.length))}
              {tile(R.k.trades, n.toLocaleString(loc))}
              {tile(R.k.win, n ? pct(wins / n) : "—")}
              {tile(R.k.total, n ? fmtR(totalR, lang) : "—", n ? (totalR >= 0 ? "pos" : "neg") : "")}
              {tile(R.k.copying, String(copying.length))}
              {tile(R.k.leads, String(leads))}
              {tile(R.k.copiesWon, doc && doc.counts.subs ? pct(doc.counts.inProfit / doc.counts.subs) : "—")}
            </div>
          </>
        )}
        {tab === "strategies" && (
          <>
            <p className="small faint">{R.strategiesNote} {testSite ? R.allHere : R.realOnly}</p>
            <ul className="rs-cards">
              {CATALOG.filter((s) => s.status === "live").map((s) => {
                const mine = agents.filter((a) => (a.strategy ?? DEFAULT_STRATEGY) === s.id), st = mine.map((a) => stats(a));
                const sn = st.reduce((q, x) => q + x.n, 0), sr = st.reduce((q, x) => q + x.totalR, 0), sw = st.reduce((q, x) => q + x.winRate * x.n, 0);
                const f = STRATEGY_DATA[s.id];
                return (
                  <li key={s.id} className="rs-card">
                    <div className="rs-card-head"><h4>{s.name}</h4><span className="faint small">{R.agents(mine.length)}</span></div>
                    <p className="rs-sub">{R.live}</p>
                    {mine.length ? (
                      <dl className="rs-kv">
                        <div><dt>{R.k.inTrade}</dt><dd className="num">{mine.filter((a) => a.position).length}</dd></div>
                        <div><dt>{R.k.trades}</dt><dd className="num">{sn}</dd></div>
                        <div><dt>{R.k.win}</dt><dd className="num">{sn ? pct(sw / sn) : "—"}</dd></div>
                        <div><dt>{R.k.total}</dt><dd className={`num ${sn ? (sr >= 0 ? "pos" : "neg") : ""}`}>{sn ? fmtR(sr, lang) : "—"}</dd></div>
                      </dl>
                    ) : <p className="small muted">{R.noAgents}</p>}
                    {f && <>
                      <p className="rs-sub">{R.backtest}</p>
                      <dl className="rs-kv">
                        <div><dt>{R.annual}</dt><dd className="num pos">+{f.cagr_pct.toLocaleString(loc, { maximumFractionDigits: 1 })} %</dd></div>
                        <div><dt>{R.pf}</dt><dd className="num">{f.profit_factor.toLocaleString(loc, { maximumFractionDigits: 2 })}</dd></div>
                        <div><dt>{R.avgR}</dt><dd className="num">+{f.avg_r.toLocaleString(loc, { maximumFractionDigits: 2 })} R</dd></div>
                        <div><dt>{R.k.win}</dt><dd className="num">{pct(f.win_rate > 1 ? f.win_rate / 100 : f.win_rate)}</dd></div>
                      </dl>
                    </>}
                    <a className="btn btn-ghost btn-block" href={`#/strategy/${s.id}`}>{R.open}</a>
                  </li>
                );
              })}
            </ul>
          </>
        )}
        {tab === "copilot" && (
          <>
            <p className="small faint">{R.copilotNote}</p>
            <div className="rs-tiles two">{tile(R.k.copying, String(copying.length))}{tile(R.k.agents, String(agents.length))}</div>
            {!copying.length ? <p className="small muted">{R.copilotNone}</p> : (
              <ul className="rs-list">
                {copying.map((a) => {
                  const t = doc?.traders.find((x) => x.id.toLowerCase() === a.copying!.lead.toLowerCase());
                  return (
                    <li key={a.id}>
                      <button type="button" className="city-link" onClick={() => onPick(a.id)}>{a.name}</button>
                      <span className="faint"> {R.copies} </span>
                      <button type="button" className="city-link mono" onClick={() => onTrader(a.copying!.lead)}>
                        {traderName({ id: a.copying!.lead, platform: a.copying!.platform === "hyperliquid" ? "hyperliquid" : "strike" })}</button>
                      {t?.city != null && <span className="faint small"> · {R.score} {Math.round(t.city)}</span>}
                    </li>
                  );
                })}
              </ul>
            )}
            <button type="button" className="btn btn-primary btn-block" onClick={onArena}>{R.copyCta}</button>
          </>
        )}
        {tab === "strike" && (
          <>
            <p className="small faint">{R.strikeNote}</p>
            {doc ? <>
              <StrikeStats T={T} lang={lang} doc={doc} />
              {doc.evidence && <Evidence T={T} lang={lang} ev={doc.evidence} />}
              <h4 className="rs-h">{R.top}</h4>
              <ol className="rs-list">
                {doc.traders.slice(0, 3).map((t) => (
                  <li key={t.id}><button type="button" className="city-link mono" onClick={() => onTrader(t.id)}>{traderName(t)}</button>
                    <span className="faint small"> · {t.platform === "strike" ? "Strike" : "Hyperliquid"} · {R.score} {Math.round(t.city ?? 0)}</span></li>
                ))}
              </ol>
            </> : <p className="small muted">{T.copy.loading}</p>}
            <button type="button" className="btn btn-primary btn-block" onClick={onArena}>{R.enter}</button>
          </>
        )}
        {tab === "ranking" && <RanksPanel T={T} lang={lang} store={store} testSite={testSite} onPick={onPick} onConnect={onConnect} copy={copy}
                                          onArena={onArena} onTrader={onTrader} />}
      </div>
    </div>
  );
}

function RanksPanel({ T, lang, store, testSite, onPick, onConnect, copy, onArena, onTrader }: { T: CityText; lang: Lang; store: CityStore; testSite?: boolean;
  onPick: (id: string) => void; onConnect: () => void; copy: CopyState; onArena: () => void; onTrader: (id: string) => void }) {
  const top = copy && typeof copy === "object" ? copy.traders.slice(0, 3) : [];
  // real accounts and paper agents are ranked apart: paper results never mix with real money
  const real = store.agents.filter((a) => a.kind === "live");
  const paper = store.agents.filter((a) => a.kind !== "live");
  return (
    <>
      <p className="muted small">{T.ranks.by}</p>
      <section className="city-ranks-group" aria-labelledby="ranks-real-title">
        <h3 id="ranks-real-title" className="city-leads-title">{testSite ? T.ranks.testTitle : T.ranks.realTitle}</h3>
        <p className="small faint">{testSite ? T.ranks.testNote : T.ranks.realNote}</p>
        {real.some((a) => stats(a).n > 0) ? <RankTable T={T} lang={lang} agents={real} onPick={onPick} />
          : <p className="small muted">{T.ranks.realNone}</p>}
      </section>
      {paper.length > 0 && (
        <section className="city-ranks-group" aria-labelledby="ranks-paper-title">
          <h3 id="ranks-paper-title" className="city-leads-title">{T.ranks.paperTitle}</h3>
          <p className="small faint">{T.ranks.paperNote}</p>
          <RankTable T={T} lang={lang} agents={paper} onPick={onPick} />
        </section>
      )}
      <button type="button" className="btn btn-outline btn-block city-cta" onClick={onConnect}>{T.ranks.cta}</button>
      {top.length > 0 && (   // and the traders people copy on Strike: the Copy Arena's three best
        <section className="city-copy-top" aria-labelledby="ranks-copy-title">
          <h3 id="ranks-copy-title">{T.copy.ranksTitle}</h3>
          <p className="small muted">{T.copy.top3}</p>
          <ol>
            {top.map((t, i) => (
              <li key={t.id}>
                <button type="button" className="city-row" onClick={() => onTrader(t.id)}>
                  <span className="num faint">{i + 1}</span>
                  <span className="grow"><span className="city-row-name mono">{traderName(t)}</span>
                    <span className="small faint">{t.platform === "strike" ? "Strike" : "Hyperliquid"} · {t.assets.slice(0, 3).join(" · ")}</span></span>
                  <span className="num city-copy-score">{t.city?.toLocaleString(lang === "es" ? "es-ES" : "en-US", { maximumFractionDigits: 0 }) ?? "—"}</span>
                </button>
              </li>
            ))}
          </ol>
          <button type="button" className="btn btn-primary btn-block" onClick={onArena}>{T.copy.enter}</button>
        </section>
      )}
    </>
  );
}

function RankTable({ T, lang, agents, onPick }: { T: CityText; lang: Lang; agents: AgentView[]; onPick: (id: string) => void }) {
  const rows = agents.map((a) => ({ a, s: stats(a) })).sort((x, y) => y.s.totalR - x.s.totalR).slice(0, 25);
  const loc = lang === "es" ? "es-ES" : "en-US";
  return (
      <table className="city-table">
        <thead><tr><th scope="col">#</th><th scope="col">{T.ranks.agent}</th><th scope="col" className="right">{T.ranks.total}</th>
          <th scope="col" className="right">{T.ranks.win}</th><th scope="col" className="right">{T.ranks.trades}</th></tr></thead>
        <tbody>
          {rows.map(({ a, s }, i) => (
            <tr key={a.id}>
              <td className="num faint">{i + 1}</td>
              <td><button type="button" className="city-link" onClick={() => onPick(a.id)}>{a.name}</button></td>
              <td className={`right num ${s.totalR >= 0 ? "pos" : "neg"}`}>{fmtR(s.totalR, lang)}</td>
              <td className="right num">{(s.winRate * 100).toLocaleString(loc, { maximumFractionDigits: 0 })}%</td>
              <td className="right num">{s.n}</td>
            </tr>
          ))}
        </tbody>
      </table>
  );
}

function FeedPanel({ T, lang, store, onPick }: { T: CityText; lang: Lang; store: CityStore; onPick: (id: string) => void }) {
  const items: FeedItem[] = store.feed;
  // the live region wraps the list (a role on the list itself would hide that it is a list)
  return items.length ? (
    <div role="log" aria-live="polite" aria-relevant="additions"><ol className="city-feed">
      {items.slice(0, 40).map((it) => (
        <li key={it.id} className={`tone-${it.tone}`}>
          <div className="city-feed-meta"><button type="button" className="city-link" onClick={() => onPick(it.agentId)}>{it.agent}</button>
            <time className="faint small" dateTime={new Date(it.time).toISOString()}>{ago(T, it.time)}</time></div>
          <p>{describe(it.d, T, lang).text}</p>
        </li>
      ))}
    </ol></div>
  ) : <p className="muted">{T.feed.empty}</p>;
}

function MarketsPanel({ T, lang, store, onPick }: { T: CityText; lang: Lang; store: CityStore; onPick: (building: string) => void }) {
  const tower: Record<string, string> = { "BTC-USD": "btc", "ETH-USD": "eth", "SOL-USD": "sol" };
  const loc = lang === "es" ? "es-ES" : "en-US";
  // the rest of Strike's markets, busiest first (their prices come in the same reading as the agents' markets)
  const more = Object.keys(store.prices).filter((m) => !CITY_MARKETS.includes(m))
    .sort((x, y) => (store.prices[y].volume ?? 0) - (store.prices[x].volume ?? 0));
  return (
    <>
      <p className="small faint"><span className={`dot ${store.source === "strike" ? "" : store.source === "binance" ? "warn" : "err"}`} aria-hidden="true" />
        {T.source[store.source]}{store.updatedAt ? ` · ${ago(T, store.updatedAt)}` : ""}</p>
      <ul className="city-markets">
        {CITY_MARKETS.filter((m) => store.prices[m]).map((m) => {
          const p = store.prices[m];
          const pos = store.positioning(m);
          const tot = pos.long + pos.short;
          return (
            <li key={m}>
              <div className="city-market-top">
                {tower[m] ? <button type="button" className="city-link strong" onClick={() => onPick(tower[m])}>{m}</button> : <strong>{m}</strong>}
                <span className="num">{fmtPrice(p.price, lang)}</span>
                <span className={`num ${p.change >= 0 ? "pos" : "neg"}`}>{fmtPct(p.change, lang)}</span>
              </div>
              <div className="city-market-sub small">
                <span className="faint" title={T.markets.fundingTip}>{T.markets.funding}</span>
                <span className={`num ${p.funding >= 0 ? "pos" : "neg"}`}>{fmtPct(p.funding * 100, lang, 4)}</span>
                <span className="faint">{T.markets.agents}</span>
                <span className="num">{pos.long} {T.markets.long} · {pos.short} {T.markets.short}</span>
              </div>
              <div className="city-ls" aria-hidden="true"><span style={{ width: tot ? `${(pos.long / tot) * 100}%` : "50%" }} /></div>
            </li>
          );
        })}
      </ul>
      {more.length > 0 && (   // and every other market Strike lists: stocks, indices, commodities, more crypto
        <section className="city-leads" aria-labelledby="markets-more-title">
          <h3 id="markets-more-title" className="city-leads-title">{T.markets.more} · {more.length}</h3>
          <p className="small faint">{T.markets.moreAbout(CITY_MARKETS.filter((m) => store.prices[m]).length + more.length)}</p>
          <ul className="city-markets">
            {more.map((m) => {
              const p = store.prices[m], info = store.markets[m];
              return (
                <li key={m}>
                  <div className="city-market-top">
                    <span className="city-market-name"><strong>{ticker(m)}</strong>{info && info.name.toUpperCase() !== ticker(m) && <span className="faint small"> {info.name}</span>}</span>
                    <span className="num">{fmtPrice(p.price, lang)}</span>
                    <span className={`num ${p.change >= 0 ? "pos" : "neg"}`}>{fmtPct(p.change, lang)}</span>
                  </div>
                  <div className="city-market-sub small">
                    <span className="faint" title={T.markets.fundingTip}>{T.markets.funding}</span>
                    <span className={`num ${p.funding >= 0 ? "pos" : "neg"}`}>{fmtPct(p.funding * 100, lang, 4)}</span>
                    {p.volume != null && <><span className="faint">{T.markets.volume}</span>
                      <span className="num">{p.volume.toLocaleString(loc, { notation: "compact", maximumFractionDigits: 1 })} $</span></>}
                    {info?.maxLev ? <><span className="faint">{T.markets.leverage}</span><span className="num">{T.markets.upTo(info.maxLev)}</span></> : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
      <p className="note">{T.markets.fundingTip}</p>
    </>
  );
}

function GuidePanel({ T, n, copyPilot }: { T: CityText; n: number; copyPilot?: boolean }) {
  const legend: Status[] = ["analyzing", "waiting", "signal", "risk", "in_trade", "exiting", "paused", "unfunded"];
  // copying with your agent: live where it is open, on the way where it is not
  const qa: [string, string][] = [...T.guide.qa, [T.copyQa.q, copyPilot ? T.copyQa.on : T.copyQa.off]];
  const road = { ...T.roadmap.items, live: copyPilot ? [...T.roadmap.items.live, T.roadmap.copyAgent] : T.roadmap.items.live,
    next: copyPilot ? T.roadmap.items.next : [T.roadmap.copyAgent, ...T.roadmap.items.next] };
  return (
    <>
      <SwarmScale T={T} n={n} inline />
      <p className="muted small">{T.guide.sub}</p>
      <div className="faq city-faq">
        {qa.map(([q, a]) => <details key={q}><summary>{q}</summary><div>{a}</div></details>)}
      </div>
      <h3 className="city-h3">{T.legend.title}</h3>
      <ul className="city-legend">
        {legend.map((s) => <li key={s}><Glyph status={s} />{T.status[s]}</li>)}
        <li><Glyph status="in_trade" side="short" />{T.status.in_trade} · SHORT</li>
        <li><span className="city-legend-lead" aria-hidden="true">★ 62</span>{T.legend.leadIdle}</li>
        <li><span className="city-legend-lead pos" aria-hidden="true">LONG BTC</span>{T.legend.leadPos}</li>
        <li><span className="city-legend-trail" aria-hidden="true" />{T.legend.copiers}</li>
        <li><span className="city-legend-car buy" aria-hidden="true" />{T.legend.carBuy}</li>
        <li><span className="city-legend-car sell" aria-hidden="true" />{T.legend.carSell}</li>
      </ul>
      <h3 className="city-h3">{T.roadmap.title}</h3>
      <div className="city-roadmap">
        {(["live", "next", "later"] as const).map((k) => (
          <div key={k} className={`rm rm-${k}`}><p className="rm-title">{T.roadmap[k]}</p>
            <ul>{road[k].map((x) => <li key={x}>{x}</li>)}</ul></div>
        ))}
      </div>
      <p className="note">{T.liveLong}</p>
      <p className="note"><a href="https://limezu.itch.io/" target="_blank" rel="noopener noreferrer">{T.artCredit}<span className="sr-only"> (opens in a new tab)</span></a></p>
    </>
  );
}

const marksOf = (prices: Record<string, { price: number }>) => Object.fromEntries(Object.entries(prices).map(([m, p]) => [m, p.price]));

type Tab = "portfolio" | "activity" | "trades" | "stats";

function DetailsModal({ T, lang, a, marks, onClose }: { T: CityText; lang: Lang; a: AgentView; marks: Record<string, number>; onClose: () => void }) {
  // a live agent opens on its Strike account; the others on their activity
  const tabs: Tab[] = a.portfolio ? ["portfolio", "activity", "trades", "stats"] : ["activity", "trades", "stats"];
  const [tab, setTab] = useState<Tab>(tabs[0]);
  const s = stats(a);
  const loc = lang === "es" ? "es-ES" : "en-US";
  const onKey = (e: KeyboardEvent) => {
    const i = tabs.indexOf(tab);
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      setTab(n);
      document.getElementById(`tab-${n}`)?.focus();
      e.preventDefault();
    }
  };
  return (
    <Modal onClose={onClose} labelledBy="details-title" className="city-details">
      <div className="city-card-head">
        <Avatar id={a.id} look={a.look} size={34} />
        <div className="grow"><h2 id="details-title">{a.name}</h2><p className="faint small mono">{owner(T, a)} · <KindTag T={T} a={a} /></p></div>
        <button type="button" className="icon-btn" aria-label={T.card.close} onClick={onClose}><Icon.close /></button>
      </div>
      <div className="city-tabs" role="tablist" aria-label={a.name} onKeyDown={onKey}>
        {tabs.map((k) => (
          <button key={k} id={`tab-${k}`} type="button" role="tab" aria-selected={tab === k} aria-controls={`tp-${k}`} tabIndex={tab === k ? 0 : -1}
                  onClick={() => setTab(k)} data-autofocus={k === tabs[0] || undefined}>{T.details[k]}</button>
        ))}
      </div>
      <div id={`tp-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className="city-tabpanel" tabIndex={0}>
        {tab === "portfolio" && a.portfolio && <PortfolioView p={a.portfolio} lang={lang} marks={marks} idPrefix="city-pf" />}
        {tab === "activity" && (a.decisions.length ? (
          <ol className="timeline">
            {a.decisions.map((d, i) => {
              const x = describe(d, T, lang);
              return (
                <li key={`${d.time}-${i}`}>
                  <time dateTime={new Date(d.time).toISOString()}>{ago(T, d.time)} · {ticker(d.market)}</time>
                  <p>{x.text}</p>
                  {(x.why || x.invalidates || x.next) && (
                    <dl className="city-why">
                      {x.why && <div><dt>{T.details.why}</dt><dd>{x.why}</dd></div>}
                      {x.invalidates && <div><dt>{T.details.invalidates}</dt><dd>{x.invalidates}</dd></div>}
                      {x.next && <div><dt>{T.details.next}</dt><dd>{x.next}</dd></div>}
                    </dl>
                  )}
                </li>
              );
            })}
          </ol>
        ) : <p className="muted">{T.details.empty}</p>)}
        {tab === "trades" && (a.trades.length || a.testTrades?.length ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th scope="col">{T.details.market}</th><th scope="col">{T.details.side}</th><th scope="col" className="right">{T.details.result}</th>
                <th scope="col" className="hide-sm">{T.details.reason}</th><th scope="col" className="right">{T.details.when}</th></tr></thead>
              <tbody>
                {[...a.trades, ...(a.testTrades ?? [])].sort((p, q) => q.time - p.time).slice(0, 30).map((x, i) => (
                  <tr key={`${x.time}-${i}`}>
                    <td>{ticker(x.market)}{x.test && <span className="city-tag test">{T.testTag}</span>}</td>
                    <td className={x.side === "long" ? "pos" : "neg"}>{x.side === "long" ? "LONG" : "SHORT"}</td>
                    <td className={`right num ${x.r > 0 ? "pos" : "neg"}`}>{fmtR(x.r, lang)}
                      {(x.pnl != null || x.pnlPct != null) && (
                        <small className="trade-money">{x.pnl != null ? cents(x.pnl, loc) : ""}{x.pnl != null && x.pnlPct != null ? " · " : ""}
                          {x.pnlPct != null ? pctSigned(x.pnlPct, loc) : ""}</small>)}</td>
                    <td className="hide-sm muted">{x.reason === "stop" ? T.card.stop : x.reason === "trail" ? T.card.exit : T.ev.exitReason[x.reason]}</td>
                    <td className="right faint">{ago(T, x.time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">{T.details.empty}</p>)}
        {tab === "trades" && [...a.trades, ...(a.testTrades ?? [])].some((x) => x.pnlPct != null) && <p className="faint small" style={{ marginTop: 10 }}>{T.details.netNote}</p>}
        {tab === "trades" && !!a.testTrades?.length && <p className="faint small" style={{ marginTop: 6 }}>{T.st.testsApart}</p>}
        {tab === "stats" && (
          <dl className="city-statgrid">
            <div><dt>{T.st.trades}</dt><dd className="num">{s.n}</dd></div>
            {a.trades.some((x) => x.pnl != null) && (() => {
              const net = a.trades.reduce((m, x) => m + (x.pnl ?? 0), 0);
              return <div><dt>{T.st.money}</dt><dd className={`num ${net >= 0 ? "pos" : "neg"}`}>{cents(net, loc)}</dd></div>;
            })()}
            <div><dt>{T.st.win}</dt><dd className="num">{(s.winRate * 100).toLocaleString(loc, { maximumFractionDigits: 1 })}%</dd></div>
            <div><dt>{T.st.total}</dt><dd className={`num ${s.totalR >= 0 ? "pos" : "neg"}`}>{fmtR(s.totalR, lang)}</dd></div>
            <div><dt>{T.st.pf}</dt><dd className="num">{Number.isFinite(s.pf) ? s.pf.toLocaleString(loc, { maximumFractionDigits: 2 }) : "∞"}</dd></div>
            <div><dt>{T.st.best}</dt><dd className={`num ${s.best > 0 ? "pos" : s.best < 0 ? "neg" : ""}`}>{fmtR(s.best, lang)}</dd></div>
            <div><dt>{T.card.risk}</dt><dd className="num">{a.risk.toLocaleString(loc)}%</dd></div>
            {a.real && <div><dt>{T.card.params}</dt><dd>{a.real.variant === "reference" ? T.card.reference : a.real.variant === "official" ? T.card.official : T.card.experimental(a.real.changes.join(", "))}</dd></div>}
            {a.real && <div><dt>{T.card.fee}</dt><dd>{T.card.feeVal(a.real.feeBps)}</dd></div>}
          </dl>
        )}
        {tab === "stats" && a.kind === "live" && <p className="faint" style={{ marginTop: 12 }}>{T.st.onlyAgent}</p>}
      </div>
      <p className="note">{a.kind === "live" ? T.realNoteLive : T.realNote}</p>
    </Modal>
  );
}

/** Native modal dialog: the browser traps focus and makes the page behind inert; Esc and a backdrop click close it. */
/** Strike's real order book on the exchange's screen: the 4 best asks over the 4 best bids, the spread between them;
 *  each bar is a level's size against the biggest shown, and slides to every new reading. */
function BookRows({ book, lang }: { book: Book; lang: Lang }) {
  const asks = book.asks.slice(0, 4), bids = book.bids.slice(0, 4);
  if (!asks.length || !bids.length) return null;
  const top = Math.max(...asks.map((l) => l[1]), ...bids.map((l) => l[1]));
  const loc = lang === "es" ? "es-ES" : "en-US";
  const size = (q: number) => q.toLocaleString(loc, { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  // rows keyed by their place (not their price): the same row takes each new reading, so its bar slides
  const row = ([p, q]: [number, number], side: "ask" | "bid", i: number) => (
    <div key={`${side}${i}`} className={`bk-row ${side}`}>
      <span className="bk-bar" style={{ transform: `scaleX(${q / top})` }} />
      <span className="bk-px">{fmtPrice(p, lang)}</span><span className="bk-q">{size(q)}</span>
    </div>
  );
  const spread = asks[0][0] - bids[0][0];
  return (
    <div className="bk">
      <div className="bk-head"><span>Strike</span><span>{BOOK_MARKET}</span></div>
      {[...asks].reverse().map((l, i) => row(l, "ask", i))}
      <div className="bk-mid"><span>{fmtPrice((asks[0][0] + bids[0][0]) / 2, lang)}</span><span>spread {spread.toLocaleString(loc, { maximumFractionDigits: 2 })}</span></div>
      {bids.map((l, i) => row(l, "bid", i))}
    </div>
  );
}

/** TradingView's full chart of a market, over the city: drawing tools, indicators, timeframes; tabs for the markets. */
function ChartModal({ T, lang, market, onMarket, onClose }: { T: CityText; lang: Lang; market: string; onMarket: (m: string) => void; onClose: () => void }) {
  return (
    <Modal onClose={onClose} labelledBy="chart-title" className="city-chart">
      <div className="chart-head">
        <h2 id="chart-title">{ticker(market)} · {T.chart.title}</h2>
        <div className="chart-tabs" role="group" aria-label={T.chart.markets}>
          {["STRIKE", ...CHART_MARKETS].map((m) => (
            <button key={m} type="button" aria-pressed={m === market} onClick={() => onMarket(m)}>{ticker(m)}</button>
          ))}
        </div>
        <button type="button" className="icon-btn" aria-label={T.card.close} data-autofocus onClick={onClose}><Icon.close /></button>
      </div>
      <div className="chart-body">
        {market === "STRIKE" ? <StrikeChart full title={T.chart.frame.replace("{m}", "STRIKE")} />
          : <TradingViewChart market={market} lang={lang} full title={T.chart.frame.replace("{m}", ticker(market))} />}
      </div>
      {market === "STRIKE"
        ? <p className="chart-note">{T.chart.noteStrike} <a href={STRIKE_CHART_URL} target="_blank" rel="noopener nofollow">DEX Screener<span className="sr-only"> (opens in a new tab)</span></a></p>
        : <p className="chart-note">{T.chart.note} <a href="https://www.tradingview.com/" target="_blank" rel="noopener nofollow">TradingView<span className="sr-only"> (opens in a new tab)</span></a></p>}
    </Modal>
  );
}

function Modal({ onClose, labelledBy, className, children }: { onClose: () => void; labelledBy: string; className?: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const back = document.activeElement as HTMLElement | null;
    if (!d.open) d.showModal();
    d.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    return () => { if (d.open) d.close(); back?.focus?.(); };
  }, []);
  return (
    <dialog ref={ref} className={`city-dialog ${className ?? ""}`} aria-labelledby={labelledBy}
            onCancel={(e) => { e.preventDefault(); onClose(); }} onClick={(e) => { if (e.target === ref.current) onClose(); }}>
      <div className="city-dialog-inner">{children}</div>
    </dialog>
  );
}

const FeedbackIcon = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 5h16v11H9l-5 4z" /><path d="M8 9.5h8M8 12.5h5" /></svg>
);

function WeatherIcon({ w }: { w: 0 | 1 | 2 }) {
  const S = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, "aria-hidden": true };
  if (w === 0) return <svg {...S}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>;
  if (w === 1) return <svg {...S}><path d="M3 8h11a3 3 0 1 0-3-3M3 12h15a3 3 0 1 1-3 3M3 16h7" /></svg>;
  return <svg {...S}><path d="M7 16a5 5 0 1 1 1-9.9A6 6 0 0 1 19 9a4 4 0 0 1-1 7.9" /><path d="M8 19l-1 2M12 19l-1 2M16 19l-1 2" /></svg>;
}

const SI = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
const Ico = {
  map: () => <svg {...SI}><path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z" /><path d="M9 4v14M15 6v14" /></svg>,
  users: () => <svg {...SI}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" /><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.8c1.9.7 3 2.4 3.5 5.2" /></svg>,
  trophy: () => <svg {...SI}><path d="M8 4h8v5a4 4 0 0 1-8 0z" /><path d="M8 6H4.5a3 3 0 0 0 3.6 4M16 6h3.5a3 3 0 0 1-3.6 4M12 13v4M8.5 20h7M10 17h4v3h-4z" /></svg>,
  pulse: () => <svg {...SI}><path d="M3 12h4l2.5-6 4 12 2.5-6H21" /></svg>,
  bars: () => <svg {...SI}><path d="M6 4v16M6 8h-2v7h2M12 3v18M12 6h-2v9h2M18 6v14M18 10h-2v6h2" /></svg>,
  user: () => <svg {...SI}><circle cx="12" cy="8" r="4" /><path d="M4 20.5c1-4 4-6.2 8-6.2s7 2.2 8 6.2" /></svg>,
  wallet: () => <svg {...SI}><path d="M4 7h15a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a1 1 0 0 1-1-1z" /><path d="M4 7l12-3.5V7M16.5 13.5h.01" /></svg>,
  bell: () => <svg {...SI}><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" /><path d="M10 20.5a2 2 0 0 0 4 0" /></svg>,
  help: () => <svg {...SI}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.6 2.6 0 1 1 3.6 2.4c-.7.3-1.1.9-1.1 1.6v.5M12 17h.01" /></svg>,
  target: () => <svg {...SI} width={16} height={16}><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2.5" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>,
};

/** What an agent's trade reads where it works, from real data: the chartist its last candle's range and volume, the
 *  reporter the news reading, the tape reader the price change, the risk keeper its day. One market at a time. At the
 *  News Tower because a market's reading just turned (newsTrip): that market's reading. */
function jobLabel(a: AgentView, doc: ReturnType<typeof useNews>, prices: Prices, lang: Lang): string | null {
  const PT = dict[lang].persona, loc = lang === "es" ? "es-ES" : "en-US";
  const reading = (m: string) => {
    const rd = doc && typeof doc === "object" ? doc.markets[m] : undefined;
    return rd?.net != null ? `${ticker(m)} ${signed(rd.net, lang)} ${rd.label ? cityText[lang].news.labels[rd.label].toLocaleLowerCase(loc) : ""}`.trim()
      : `${ticker(m)} ${PT.noReading}`;
  };
  if (readingNews(a)) return reading(a.trip!.market!);
  const job = a.persona?.job;
  if (!job) return null;
  const ms = a.markets.length ? a.markets : ["BTC-USD"];
  const m = ms[Math.floor(performance.now() / 3000) % ms.length], tk = ticker(m);
  const f = (v: unknown, d: number) => Number(v).toLocaleString(loc, { minimumFractionDigits: d, maximumFractionDigits: d });
  switch (job) {
    case "chartist": {
      const c = a.real?.checks?.[m]?.args as Record<string, unknown> | undefined;
      const parts = c ? [c.range != null ? `${f(c.range, 2)} ATR` : "", c.vol != null ? `vol ×${f(c.vol, 2)}` : ""].filter(Boolean) : [];
      return parts.length ? `${tk} ${parts.join(" · ")}` : null;
    }
    case "reporter": return reading(m);
    case "tape": { const px = prices[m]; return px ? `${tk} ${fmtPrice(px.price, lang)} · ${fmtPct(px.change, lang)} 24h` : null; }
    case "guardian": return `${PT.today} ${fmtR(a.rToday, lang)} · ${a.risk.toLocaleString(loc)} %`;
  }
}

/** Its line, in its own voice, for what it is doing now (an exit says how it went). */
function sayLine(a: AgentView, lang: Lang): string {
  const t = dict[lang], temper = a.persona?.temper ?? "stoic", tk = ticker(a.position?.market ?? a.focus ?? a.markets[0] ?? "BTC-USD");
  const last = a.trades[0];
  const fresh = last && Date.now() - last.time < 6 * 3600_000;
  const moment = a.status === "in_trade" || a.status === "entering" ? "enter" : a.status === "signal" ? "signal" : a.status === "risk" ? "risk"
    : a.status === "analyzing" ? "analyze" : fresh ? (last.r > 0 ? "win" : "loss") : "wait";
  const r = fresh ? Math.abs(last.r).toLocaleString(lang === "es" ? "es-ES" : "en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : "";
  return voiceLine(t, temper, moment, Math.floor((last?.time ?? 0) / 1000), tk, r);
}
