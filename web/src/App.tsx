import { Suspense, lazy, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, isMock, type AppInfo } from "./api";
import { MobileMenu } from "./components/MobileMenu";
import { useReveal } from "./components/useReveal";
import { ConnectModal, type LinkResult } from "./components/ConnectModal";
import { sessionWallet } from "./cardano/wallets";
import { Dashboard } from "./components/Dashboard";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { StrategyCatalog } from "./components/StrategyCatalog";
import { StrategyPage } from "./components/StrategyPage";
import { Icon, Mark } from "./components/ui";
import { dict, fmt, initialLang, saveLang, type Lang } from "./i18n";
import { STRATEGY_IDS, type StrategyId } from "./strategies";

const CityPage = lazy(() => import("./city/CityPage"));
const CityPreview = lazy(() => import("./city/CityPreview"));
// "city" (#/city), "strategy:<id>" (#/strategy/<id>, a strategy of the catalog) or "landing" (anything else)
const routeOf = (): string => {
  if (location.hash.startsWith("#/city")) return "city";
  const m = /^#\/strategy\/([\w-]+)/.exec(location.hash);
  return m && STRATEGY_IDS.includes(m[1]) ? `strategy:${m[1]}` : "landing";
};

const FALLBACK: AppInfo = { env: "mainnet", builderCode: "smartflow", feeBps: 20, takerFeeBps: 5, markets: ["BTC-USD", "ETH-USD", "SOL-USD"],
  riskPresets: { conservative: 0.5, standard: 1, assertive: 2 }, agentHealthy: false, engine: "1.0.0" };

// the signed-in session (7 days, see SESSION_TTL) survives closing the browser; an expired one asks to sign in again
function loadLink(): LinkResult | null {
  try { const s = localStorage.getItem("sf-link") ?? sessionStorage.getItem("sf-link"); return s ? (JSON.parse(s) as LinkResult) : null; } catch { return null; }
}

export function App() {
  const [lang, setLang] = useState<Lang>(initialLang);
  const [info, setInfo] = useState<AppInfo>(FALLBACK);
  const [open, setOpen] = useState(false);
  const [fromCity, setFromCity] = useState(false);
  const [link, setLink] = useState<LinkResult | null>(loadLink);
  const t = dict[lang];
  const [route, setRoute] = useState(routeOf);
  const city = route === "city";
  const landing = route === "landing";
  const strategyPage: StrategyId | null = route.startsWith("strategy:") ? route.slice(9) : null;
  useEffect(() => {
    const f = () => setRoute(routeOf());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  // back on the landing from a strategy's page through one of its anchors (#strategies, #faq...): the browser looked for
  // it before the landing was there, so it is scrolled to once it is
  useLayoutEffect(() => {
    if (!landing || !/^#[\w-]+$/.test(location.hash)) return;
    document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: "instant" as ScrollBehavior });
  }, [landing]);
  // the live city in the hero: its engine is built while the browser is idle soon after the page loads (it takes a
  // ~100 ms block on a phone; mid-scroll that was a visible hitch), never in the middle of a scroll
  const citySection = useRef<HTMLAnchorElement>(null);
  const [showCity, setShowCity] = useState(false);
  const [cityStats, setCityStats] = useState<{ online: number; inTrade: number } | null>(null);
  useReveal(!city, route);   // the landing's entrances (components/useReveal.ts)
  const onCityStats = useCallback((s: { online: number; inTrade: number }) => setCityStats(s), []);
  useEffect(() => {
    if (!landing) return;
    const el = citySection.current;
    if (!el || !("IntersectionObserver" in window)) { setShowCity(true); return; }
    // never in the middle of a scroll: its code loads at the first pause (the page waits 400 ms without scrolling)
    let lastScroll = 0, t = 0;
    const onScroll = () => { lastScroll = performance.now(); };
    window.addEventListener("scroll", onScroll, { passive: true });
    const idle = (window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback;
    const go = () => {
      clearTimeout(t);
      const q = performance.now() - lastScroll;
      if (q < 400) { t = window.setTimeout(go, 400 - q); return; }
      if (idle) idle(() => setShowCity(true), { timeout: 2500 }); else setShowCity(true);
    };
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { go(); io.disconnect(); } }, { rootMargin: "300px" });
    io.observe(el);
    t = window.setTimeout(go, 1200);
    return () => { io.disconnect(); clearTimeout(t); window.removeEventListener("scroll", onScroll); };
  }, [landing]);
  const heroCta = useRef<HTMLButtonElement>(null);
  const [heroCtaVisible, setHeroCtaVisible] = useState(true);
  useEffect(() => {
    const el = heroCta.current;
    if (!el || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(([e]) => setHeroCtaVisible(e.isIntersecting), { threshold: 0.1 });
    io.observe(el);
    return () => io.disconnect();
  }, [route]);

  useEffect(() => { document.documentElement.lang = lang; saveLang(lang); }, [lang]);
  useEffect(() => { api.info().then(setInfo).catch(() => undefined); }, []);

  const onLinked = useCallback((r: LinkResult) => {
    setLink(r);
    try { localStorage.setItem("sf-link", JSON.stringify(r)); } catch { /* ignore */ }
  }, []);
  // "My agent" is part of EdgeCraft-StrikeCity: the dashboard opens over the map
  const goDashboard = () => { setOpen(false); location.hash = "#/city?me"; };
  const openCity = (id: string) => { setOpen(false); location.hash = `#/city?agent=${id}`; };
  const unlink = useCallback(() => {
    setLink(null);
    try { localStorage.removeItem("sf-link"); sessionStorage.removeItem("sf-link"); } catch { /* ignore */ }
  }, []);
  // why the session just ended (shown for a few seconds)
  const [bye, setBye] = useState("");
  useEffect(() => { if (!bye) return; const id = window.setTimeout(() => setBye(""), 9000); return () => clearTimeout(id); }, [bye]);
  const signOut = useCallback((why: string) => { unlink(); setBye(why); }, [unlink]);
  // the session belongs to one wallet account: if the extension now has another one selected (or no longer allows the
  // site), it ends. Checked when the page opens (wallets inject late), when the tab comes back, and every 20 s
  useEffect(() => {
    if (!link) return;
    let alive = true;
    const check = () => sessionWallet(link.walletName, link.address).then((r) => {
      if (!alive) return;
      if (r === "other") signOut(t.dash.walletChanged);
      else if (r === "off") signOut(t.dash.walletOff);
    });
    const timers = [1500, 4500].map((ms) => window.setTimeout(check, ms));
    const every = window.setInterval(check, 20_000);
    const onFocus = () => { void check(); };
    window.addEventListener("focus", onFocus);
    return () => { alive = false; timers.forEach(clearTimeout); clearInterval(every); window.removeEventListener("focus", onFocus); };
  }, [link, signOut, t]);
  const [picked, setPicked] = useState<StrategyId | undefined>(undefined);   // the strategy the sign-up starts with
  const openConnect = (city: boolean, strategy?: StrategyId) => { setFromCity(city); setPicked(strategy); setOpen(true); };

  const connectLabel = link ? t.dashboard : t.connect;
  const onConnectClick = () => (link ? goDashboard() : openConnect(false));
  // "Use this strategy": the sign-up with it already picked, or My agent (where the strategy is changed) for an agent
  const onUse = (id: StrategyId) => (link ? goDashboard() : openConnect(false, id));
  const modal = open && (
    <ErrorBoundary onClose={() => setOpen(false)}>
      <ConnectModal t={t} lang={lang} info={info} onClose={() => setOpen(false)} onLinked={onLinked} onOpenDashboard={goDashboard}
                    fromCity={fromCity} onOpenCity={openCity} strategy={picked} />
    </ErrorBoundary>
  );

  if (city) {
    return (
      <>
        {/* its code failing to load (a lost connection, a page left open across a deploy) explains itself and goes back */}
        <ErrorBoundary onClose={() => { location.hash = ""; }}>
        <Suspense fallback={<div className="city-boot" role="status"><span className="sr-only">Loading EdgeCraft-StrikeCity</span></div>}>
          <CityPage lang={lang} setLang={setLang} onConnect={() => (link ? openCity(link.cityId ?? link.accountId) : openConnect(true))}
                    myAgent={link ? <Dashboard t={t} lang={lang} info={info} link={link} onUnlinked={unlink} onSignOut={() => signOut(t.dash.signedOut)}
                                               onSignIn={() => { unlink(); openConnect(true); }} onOpenCity={openCity} /> : null}
                    owner={link?.token ? { id: link.cityId ?? link.accountId, token: link.token } : null} />
        </Suspense>
        </ErrorBoundary>
        {modal}
        {bye && <div className="toast" role="status">{bye}</div>}
      </>
    );
  }

  return (
    <>
      <a className="skip-link" href="#main">{t.skip}</a>
      {/* the city's pixel grid under the whole landing, with its mint glow (as the mobile menu) */}
      <div className="landing-bg" aria-hidden="true" />
      <header className="header">
        <div className="container header-inner">
          <div className="brand-wrap">
            <a className="brand" href="#top" aria-label="EdgeCraft-StrikeCity">
              <Mark /><span className="brand-word"><span className="bw-pre">EdgeCraft<span className="bw-dash">-</span></span>StrikeCity</span>
            </a>
            <a className="brand-on" href="https://www.strikefinance.org" target="_blank" rel="noopener noreferrer">
              {t.on}<span className="sr-only"> (opens in a new tab)</span>
            </a>
          </div>
          <nav className="nav" aria-label="Main">
            <a href="#strategies">{t.nav.strategy}</a><a href="#how">{t.nav.how}</a>
            <a href="#faq">{t.nav.faq}</a>
            <a href="#/city" className="nav-city">{t.nav.city}</a>
          </nav>
          <div className="header-actions">
            <div className="lang" role="group" aria-label="Language">
              <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>EN</button>
              <button type="button" aria-pressed={lang === "es"} onClick={() => setLang("es")}>ES</button>
            </div>
            <button type="button" className="btn btn-primary connect-desktop" onClick={onConnectClick}>
              {link ? <Icon.wallet /> : null}{connectLabel}
            </button>
            <MobileMenu t={t} lang={lang} setLang={setLang} connectLabel={link ? t.dashboard : t.connectCardano} onConnect={onConnectClick} />
          </div>
        </div>
      </header>

      <main id="main" className="landing" tabIndex={-1}>
        {strategyPage ? <StrategyPage id={strategyPage} t={t} lang={lang} info={info} onUse={onUse} ctaRef={heroCta} /> : <>
        <section className="hero" id="top" aria-labelledby="hero-title">
          <div className="container hero-grid">
            <div className="hero-text" data-reveal-group>
              <h1 id="hero-title">{t.hero.title}</h1>
              <p className="hero-lead">{t.hero.lead}</p>
              <div className="hero-ctas">
                <button ref={heroCta} type="button" className="btn btn-primary btn-lg" onClick={onConnectClick}>{link ? t.dashboard : t.connectCardano}</button>
                <a className="btn btn-outline btn-lg" href="#strategies">{t.hero.browse}</a>
              </div>
              <p className="hero-balance"><Icon.alert />{t.balance.hero}</p>
            </div>
            {/* the live city: every agent of every strategy, on Strike's prices; the whole frame opens it. On a phone it
                comes right after the buttons, before the guarantees */}
            <a className="hero-city" href="#/city" ref={citySection} aria-label={t.cityPromo.label}>
              <span className="hero-city-frame">
                <img className="city-show-poster" src="/city-preview.webp" alt="" width={1800} height={900} decoding="async"
                     onError={(e) => { e.currentTarget.style.display = "none"; }} />
                {showCity && <ErrorBoundary silent><Suspense fallback={null}><CityPreview onStats={onCityStats} /></Suspense></ErrorBoundary>}
                <span className="hero-city-scan" aria-hidden="true" />
              </span>
              <span className="hero-city-bar">
                <span className="hero-city-badge"><span className="live-dot" aria-hidden="true" />{t.cityPromo.eyebrow}</span>
                <span className="hero-city-title">{t.cityPromo.title}</span>
                {cityStats && cityStats.online > 0 && (
                  <span className="hero-city-stats">{fmt(t.cityPromo.stats, { n: String(cityStats.online), t: String(cityStats.inTrade) })}</span>
                )}
                <span className="hero-city-go">{t.cityPromo.cta}<Icon.chevron /></span>
              </span>
            </a>
            <ul className="trust" data-reveal-group>
              {t.hero.trust.map((x) => <li key={x}><Icon.shield />{x}</li>)}
            </ul>
          </div>
        </section>

        <section className="section" id="strategies" aria-labelledby="strategies-title">
          <div className="container">
            <div className="section-head" data-reveal><h2 id="strategies-title">{t.catalog.title}</h2><p>{t.catalog.sub}</p></div>
            <StrategyCatalog t={t} lang={lang} info={info} onUse={onUse} headingId="cat" />
            <p className="catalog-note">{t.catalog.note}</p>
          </div>
        </section>

        <section className="section" id="how" aria-labelledby="how-title">
          <div className="container">
            <div className="section-head" data-reveal><span className="kicker">{t.kicker.how}</span><h2 id="how-title">{t.how.title}</h2><p>{t.how.sub}</p></div>
            <ol className="grid grid-4 steps" data-reveal-group style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {t.how.steps.map(([h, p], i) => (
                <li key={h} className="card">
                  <div className="card-head"><span className="step-num" aria-hidden="true">{i + 1}</span><h3>{h}</h3></div>
                  <p>{p}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="section" id="control" aria-labelledby="ctl-title">
          <div className="container">
            <div className="section-head" data-reveal><span className="kicker">{t.kicker.control}</span><h2 id="ctl-title">{t.control.title}</h2></div>
            <div className="grid grid-2" data-reveal-group>
              {t.control.items.map(([h, p]) => <article key={h} className="card"><h3>{h}</h3><p>{p}</p></article>)}
            </div>
          </div>
        </section>

        <section className="section" id="faq" aria-labelledby="faq-title">
          <div className="container">
            <div className="section-head" data-reveal><span className="kicker">{fmt(t.kicker.faq, { n: String(t.faq.items.length) })}</span><h2 id="faq-title">{t.faq.title}</h2></div>
            <div className="faq" data-reveal-group>
              {t.faq.items.map(([q, a]) => <details key={q}><summary>{q}</summary><div>{a}</div></details>)}
            </div>
          </div>
        </section>
        </>}

        <footer className="site-footer">
          <div className="container foot" data-reveal>
            <div className="foot-brand"><Mark size={32} /><span className="foot-word">EdgeCraft-StrikeCity</span><span className="foot-by">{t.footBy}</span></div>
            <p>{t.footer.legal}</p><p>{t.footer.by} Engine {info.engine}. <a href="https://limezu.itch.io/" target="_blank" rel="noopener noreferrer">{t.footer.art}<span className="sr-only"> (opens in a new tab)</span></a></p>
          </div>
        </footer>
      </main>

      <div className="mobile-cta" hidden={!!link || heroCtaVisible}>
        {strategyPage
          ? <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => onUse(strategyPage)}>{t.catalog.use}</button>
          : <button type="button" className="btn btn-primary btn-lg btn-block" onClick={onConnectClick}>{link ? t.dashboard : t.connectCardano}</button>}
      </div>

      <div className="statusbar" role="contentinfo">
        <div className="container statusbar-inner">
          {isMock && <span className="hide-sm" style={{ color: "var(--golden)" }}>{t.status.demo}</span>}
          <span className="push">
            <a href="https://app.strikefinance.org" target="_blank" rel="noopener noreferrer">Strike app <span className="sr-only">(opens in a new tab)</span></a>
            <a className="hide-sm" href="https://docs.strikefinance.org/api/builder-codes" target="_blank" rel="noopener noreferrer">Builder codes</a>
          </span>
        </div>
      </div>

      {modal}
      {bye && <div className="toast" role="status">{bye}</div>}
    </>
  );
}
