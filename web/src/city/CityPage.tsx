// EdgeCraft-StrikeCity: the agents of Smart Flow users living on a map, driven by the same lifecycle as the real agent.
import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type KeyboardEvent, type ReactNode } from "react";
import { DEFAULT_STRATEGY, strategyDef } from "../strategies";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-mono/700.css";
import "./city.css";
import type { Lang } from "../i18n";
import { Icon, Mark } from "../components/ui";
import { nowDecision, stats, type AgentView, type FeedItem, type Status } from "./agents";
import { CityEngine, SCREEN_BOOK, SCREEN_CHART, STATUS_COLOR, drawIcon, type Sel } from "./engine";
import type { Look } from "./look";
import { FEET, FW, HEAD_TOP, frameAt, onSheet, sheetFor } from "./sprites";
import { BOOK_MARKET, CITY_MARKETS, CityStore, type Book } from "./store";
import { EventSoon, NewsButton, NewsView, contextLine, tapeLine } from "./NewsView";
import { useNews } from "./news";
import { cityText, describe, fmtPct, fmtPrice, fmtR, money as cents, pctSigned, ticker, type CityText } from "./text";
import { ART2, BUILDINGS, artReady } from "./world";
import { PortfolioView, livePosition } from "./portfolio";
import { TradingViewChart, warmTradingView } from "./tradingview";

type Panel = "agents" | "ranks" | "feed" | "markets" | "guide";

interface Props {
  lang: Lang; setLang: (l: Lang) => void; onConnect: () => void;
  myAgent?: ReactNode;   // the owner's dashboard (null until they sign in with their wallet)
  owner?: { id: string; token: string } | null;   // signed in: their own agent shows with its amounts
}

const SCALE = [1, 10, 50, 250, 1000, 5000];
const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const isSmall = () => window.matchMedia("(max-width: 760px)").matches;

const wantsMe = () => /[?&]me\b/.test(location.hash);
// the markets the full chart offers (the ones agents can trade)
const CHART_MARKETS = [...CITY_MARKETS, "NEAR-USD", "ZEC-USD"];
// TradingView's screen chart is laid out at this many CSS px per world px and scaled with the map: zooming only
// transforms it (no new layout inside the iframe), and its text stays readable from the default zoom
const TV_K = 2.5;
warmTradingView();   // as the city's code arrives: TradingView's connections open while the city loads

function readDeepLink(): string | null {
  const m = /[?&]agent=([\w-]+)/.exec(location.hash);
  return m ? m[1] : null;
}

export default function CityPage({ lang, setLang, onConnect, myAgent, owner }: Props) {
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
  const [news, setNews] = useState<string | null>(null);     // the market whose news is open
  const newsDoc = useNews(ready);                             // read once the city is drawn, then every minute
  const [tvOn, setTvOn] = useState(false);                   // TradingView's candles are drawn: show them
  const tvScreen = useRef<HTMLDivElement>(null);
  const bookScreen = useRef<HTMLDivElement>(null);
  const [welcome, setWelcome] = useState(() => { try { return localStorage.getItem("sf-city-welcome") !== "1"; } catch { return true; } });
  const [, force] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);
  const engine = useRef<CityEngine | null>(null);
  const headline = useRef("EDGECRAFT-STRIKECITY");
  const weather = useRef<0 | 1 | 2>(0);
  const deepLink = useRef(readDeepLink());   // read before the hash is rewritten below

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
      getAgents: () => store.agents, getPrices: () => store.prices, getHistory: (m) => store.hist[m] ?? [],
      getHeadline: () => headline.current, getWeather: () => weather.current, reducedMotion: !!reduced, getBook: () => store.book,
      onSelect: (s) => { setSel(s); setDetails(false); if (s && isSmall()) setPanel(null); },
      onChart: (m) => setChart(m),
      // TradingView's chart and Strike's book follow the screen as the map moves: one transform each, written only
      // when it changes
      onScreen: (x, y, z) => {
        const c = canvas.current;
        if (!c) return;
        for (const [el, r] of [[tvScreen.current, SCREEN_CHART], [bookScreen.current, SCREEN_BOOK]] as const) {
          if (!el) continue;
          const sx = x + (r.x - SCREEN_CHART.x) * z, sy = y + (r.y - SCREEN_CHART.y) * z;
          const k = `${sx.toFixed(1)},${sy.toFixed(1)},${z.toFixed(4)}`;
          if (el.dataset.k === k) continue;
          el.dataset.k = k;
          const on = sx + r.w * z > 0 && sy + r.h * z > 0 && sx < c.clientWidth && sy < c.clientHeight;
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

  // keep the followed agent visible beside the side panel (desktop) or above the bottom card (mobile)
  useEffect(() => {
    const small = isSmall();
    const card = document.querySelector<HTMLElement>(".city-card");
    engine.current?.setInsets(panel && !small ? 384 : 0, small && card ? card.offsetHeight + 8 : 0);
  });

  // shareable deep link to the selected agent
  useEffect(() => {
    if (!ready) return;
    const base = "#/city";
    const want = me ? `${base}?me` : sel?.kind === "agent" ? `${base}?agent=${sel.id}` : base;
    if (location.hash !== want) history.replaceState(null, "", want);
  }, [sel, ready, me]);

  const choose = (s: Sel | null) => {
    engine.current?.select(s, false);
    setSel(s);
    setDetails(false);
    if (s && isSmall()) setPanel(null);
  };
  const togglePanel = (p: Panel | null) => { setMe(false); setPanel((cur) => (cur === p ? null : p)); };
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
    if (me) e.pause(); else e.start();
  }, [me, ready]);

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
  const totals = store.totals();
  const btc = store.prices["BTC-USD"];
  weather.current = !btc ? 0 : Math.abs(btc.change) >= 4 ? 2 : Math.abs(btc.change) >= 1.5 ? 1 : 0;
  const latest = store.feed.find((x) => x.d.kind !== "analysis") ?? store.feed[0];
  const SL = T.stats;
  const tape = tapeLine(newsDoc, T, lang, Date.now());   // the news reading and the next US release, after the agents' line
  headline.current = (latest ? `${latest.agent.toUpperCase()} · ${describe(latest.d, T, lang).text}`
    : btc ? `EDGECRAFT-STRIKECITY · BTC ${fmtPrice(btc.price, lang)} ${fmtPct(btc.change, lang)}` : "EDGECRAFT-STRIKECITY")
    + (tape ? `      ${tape}` : "");
  const agent = sel?.kind === "agent" ? store.agent(sel.id) : undefined;
  const bld = sel?.kind === "building" ? BUILDINGS.find((b) => b.id === sel.id) : undefined;
  void version;

  return (
    <div className="city" data-ready={ready || undefined}>
      <header className="city-top">
        <a className="city-brand" href="#top" aria-label={`${T.back}: ${T.title}`}>
          <Mark size={32} /><span className="city-word"><span className="cw-pre">EdgeCraft<span className="cw-dash">-</span></span>StrikeCity</span>
        </a>
        {store.live && <span className="city-live" title={T.liveLong}><span className="city-live-dot" aria-hidden="true" /><span className="city-live-txt">{T.live}</span><span className="sr-only">: {T.liveLong}</span></span>}
        <dl className="city-stats" aria-label={T.title}>
          <div><dt>{SL.live}</dt><dd className="num">{totals.live}</dd></div>
          <div><dt>{SL.inTrade}</dt><dd className="num">{totals.inTrade}</dd></div>
          <div className="hide-xs"><dt>{SL.trades}</dt><dd className="num">{totals.trades}</dd></div>
          <div><dt>{SL.r}</dt><dd className={`num ${totals.rToday >= 0 ? "pos" : "neg"}`}>{fmtR(totals.rToday, lang)}</dd></div>
        </dl>
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
                aria-label={T.canvas(totals.live, totals.inTrade)} />
        {/* it loads as soon as the city is drawn (loading it during the city's own load delayed the city ~0.35 s, measured);
            until its candles are drawn the screen shows the city's own chart (Strike's prices), then it fades in */}
        {ready && (
          <div ref={tvScreen} className={`city-tv${tvOn ? " on" : ""}`} aria-hidden="true"
               style={{ width: SCREEN_CHART.w * TV_K, height: SCREEN_CHART.h * TV_K, visibility: "hidden" }}>
            <TradingViewChart market="BTC-USD" lang={lang} title={T.chart.screen} onReady={() => setTvOn(true)} />
          </div>
        )}
        {ready && store.book && (
          <div ref={bookScreen} className="city-book" aria-hidden="true"
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
              {panel === "agents" && <AgentsPanel T={T} lang={lang} store={store} selected={agent?.id} onPick={(id) => choose({ kind: "agent", id })} />}
              {panel === "ranks" && <RanksPanel T={T} lang={lang} store={store} onPick={(id) => choose({ kind: "agent", id })} onConnect={onConnect} />}
              {panel === "feed" && <FeedPanel T={T} lang={lang} store={store} onPick={(id) => choose({ kind: "agent", id })} />}
              {panel === "markets" && <MarketsPanel T={T} lang={lang} store={store} onPick={(id) => choose({ kind: "building", id })} />}
              {panel === "guide" && <GuidePanel T={T} n={totals.total} />}
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
                     context={agent.position ? contextLine(newsDoc, agent.position.market, T, lang, Date.now()) : null} />
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
            {(bld.market || bld.id === "exchange") && (
              <button type="button" className="btn btn-ghost btn-block city-card-chart" onClick={() => setChart(bld.market ?? "BTC-USD")}>{T.chart.open}</button>
            )}
          </aside>
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
        <DockBtn label={T.nav.map} active={!panel && !me} onClick={() => { setPanel(null); setMe(false); }} icon={<Ico.map />} />
        <DockBtn label={T.nav.agents} active={panel === "agents"} onClick={() => togglePanel("agents")} icon={<Ico.users />} controls />
        <DockBtn label={T.nav.ranks} active={panel === "ranks"} onClick={() => togglePanel("ranks")} icon={<Ico.trophy />} controls />
        <DockBtn label={T.nav.feed} active={panel === "feed"} onClick={() => togglePanel("feed")} icon={<Ico.pulse />} controls />
        <DockBtn label={T.nav.markets} active={panel === "markets"} onClick={() => togglePanel("markets")} icon={<Ico.bars />} controls />
        <DockBtn label={T.nav.guide} active={panel === "guide"} onClick={() => togglePanel("guide")} icon={<Ico.help />} controls />
        <DockBtn label={T.nav.me} active={me} onClick={openMe} icon={<Ico.user />} />
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
      {details && agent && <DetailsModal T={T} lang={lang} a={agent} marks={marksOf(store.prices)} onClose={() => setDetails(false)} />}
    </div>
  );
}

function panelTitle(p: Panel, T: CityText) {
  return { agents: T.agents.title, ranks: T.ranks.title, feed: T.feed.title, markets: T.markets.title, guide: T.guide.title }[p];
}

// ---------------------------------------------------------------- pieces
function DockBtn({ label, active, onClick, icon, controls }: { label: string; active: boolean; onClick: () => void; icon: ReactNode; controls?: boolean }) {
  return (
    <button type="button" className="city-dock-btn" aria-pressed={active} aria-controls={controls && active ? "city-panel" : undefined} onClick={onClick}>
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

function KindTag({ T, a }: { T: CityText; a: AgentView }) {
  // a user's agent on Strike testnet trades test money: never labelled as real
  if (a.kind === "live" && a.real?.env === "testnet") return <span className="city-tag testnet">{T.kindTestnet}</span>;
  return <span className={`city-tag ${a.kind === "live" ? "real" : "live"}`}>{a.kind === "live" ? T.kindLive : T.realTag}</span>;
}

const money = (v: number, lang: Lang) => v.toLocaleString(lang === "es" ? "es-ES" : "en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function AgentCard({ T, lang, a, following, onFollow, onDetails, onClose, marks, context }: { T: CityText; lang: Lang; a: AgentView; following: boolean;
  onFollow: () => void; onDetails: () => void; onClose: () => void; marks: Record<string, number>; context?: string | null }) {
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
      <p className="city-card-label">{T.card.now}</p>
      <p className="city-card-text">{a.status === "unfunded" ? T.unfundedNow : last ? describe(last, T, lang).text : T.status[a.status]}</p>
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
      {p && context && <p className="city-card-context small"><span className="muted">{T.news.context}:</span> {context} <span className="faint">({T.news.contextNote})</span></p>}
      <div className="city-card-actions">
        <button type="button" className="btn btn-ghost" aria-pressed={following} onClick={onFollow}><Ico.target />{following ? T.card.following : T.card.follow}</button>
        <button type="button" className="btn btn-primary" onClick={onDetails}>{T.card.details}</button>
      </div>
    </aside>
  );
}

function AgentsPanel({ T, lang, store, selected, onPick }: { T: CityText; lang: Lang; store: CityStore; selected?: string; onPick: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [f, setF] = useState<"all" | "in_trade" | "analyzing" | "waiting" | "paused">("all");
  const groups: Record<typeof f, Status[]> = { all: [], in_trade: ["in_trade", "entering"], analyzing: ["analyzing", "signal", "risk", "exiting"], waiting: ["waiting", "unfunded"], paused: ["paused", "offline"] };
  const list = store.agents.filter((a) => (f === "all" || groups[f].includes(a.status)) && a.name.toLowerCase().includes(q.trim().toLowerCase()));
  const rows = (xs: AgentView[]) => (
    <ul className="city-list">
      {xs.map((a) => (
        <li key={a.id}>
          <button type="button" className="city-row real" aria-current={selected === a.id || undefined} onClick={() => onPick(a.id)}>
            <Avatar id={a.id} look={a.look} />
            <span className="grow"><span className="city-row-name">{a.name}</span>
              <span className="city-row-tags"><KindTag T={T} a={a} /><StatusPill T={T} a={a} /></span></span>
            {a.position ? <span className={`num ${a.position.rOpen >= 0 ? "pos" : "neg"}`}>{fmtR(a.position.rOpen, lang)}</span>
              : <span className="faint small">{ticker(a.focus)}</span>}
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
      </div>
      <p className="faint small" aria-live="polite">{T.agents.count(list.length)}</p>
      {!list.length && <p className="muted">{T.agents.none}</p>}
      {list.length > 0 && rows(list)}
    </>
  );
}

function RanksPanel({ T, lang, store, onPick, onConnect }: { T: CityText; lang: Lang; store: CityStore; onPick: (id: string) => void; onConnect: () => void }) {
  return (
    <>
      <p className="muted small">{T.ranks.by}</p>
      {store.agents.length > 0 && <RankTable T={T} lang={lang} agents={store.agents} onPick={onPick} />}
      <button type="button" className="btn btn-outline btn-block city-cta" onClick={onConnect}>{T.ranks.cta}</button>
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
  return items.length ? (
    <ol className="city-feed" role="log" aria-live="polite" aria-relevant="additions">
      {items.slice(0, 40).map((it) => (
        <li key={it.id} className={`tone-${it.tone}`}>
          <div className="city-feed-meta"><button type="button" className="city-link" onClick={() => onPick(it.agentId)}>{it.agent}</button>
            <time className="faint small" dateTime={new Date(it.time).toISOString()}>{ago(T, it.time)}</time></div>
          <p>{describe(it.d, T, lang).text}</p>
        </li>
      ))}
    </ol>
  ) : <p className="muted">{T.feed.empty}</p>;
}

function MarketsPanel({ T, lang, store, onPick }: { T: CityText; lang: Lang; store: CityStore; onPick: (building: string) => void }) {
  const tower: Record<string, string> = { "BTC-USD": "btc", "ETH-USD": "eth", "SOL-USD": "sol" };
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
      <p className="note">{T.markets.fundingTip}</p>
    </>
  );
}

function GuidePanel({ T, n }: { T: CityText; n: number }) {
  const legend: Status[] = ["analyzing", "waiting", "signal", "risk", "in_trade", "exiting", "paused", "unfunded"];
  return (
    <>
      <SwarmScale T={T} n={n} inline />
      <p className="muted small">{T.guide.sub}</p>
      <div className="faq city-faq">
        {T.guide.qa.map(([q, a]) => <details key={q}><summary>{q}</summary><div>{a}</div></details>)}
      </div>
      <h3 className="city-h3">{T.legend.title}</h3>
      <ul className="city-legend">
        {legend.map((s) => <li key={s}><Glyph status={s} />{T.status[s]}</li>)}
        <li><Glyph status="in_trade" side="short" />{T.status.in_trade} · SHORT</li>
      </ul>
      <h3 className="city-h3">{T.roadmap.title}</h3>
      <div className="city-roadmap">
        {(["live", "next", "later"] as const).map((k) => (
          <div key={k} className={`rm rm-${k}`}><p className="rm-title">{T.roadmap[k]}</p>
            <ul>{T.roadmap.items[k].map((x) => <li key={x}>{x}</li>)}</ul></div>
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
          {CHART_MARKETS.map((m) => (
            <button key={m} type="button" aria-pressed={m === market} onClick={() => onMarket(m)}>{ticker(m)}</button>
          ))}
        </div>
        <button type="button" className="icon-btn" aria-label={T.card.close} data-autofocus onClick={onClose}><Icon.close /></button>
      </div>
      <div className="chart-body">
        <TradingViewChart market={market} lang={lang} full title={T.chart.frame.replace("{m}", ticker(market))} />
      </div>
      <p className="chart-note">{T.chart.note} <a href="https://www.tradingview.com/" target="_blank" rel="noopener nofollow">TradingView<span className="sr-only"> (opens in a new tab)</span></a></p>
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
  help: () => <svg {...SI}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.6 2.6 0 1 1 3.6 2.4c-.7.3-1.1.9-1.1 1.6v.5M12 17h.01" /></svg>,
  target: () => <svg {...SI} width={16} height={16}><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2.5" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>,
};
