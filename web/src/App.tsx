import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { api, isMock, type AppInfo } from "./api";
import strategy from "./data/strategy.json";   // engine version shown in the footer
import { MobileMenu } from "./components/MobileMenu";
import { ConnectModal, type LinkResult } from "./components/ConnectModal";
import { sessionWallet } from "./cardano/wallets";
import { Dashboard } from "./components/Dashboard";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { StrategyCard } from "./components/StrategyCard";
import { Icon, Mark } from "./components/ui";
import { dict, fmt, initialLang, saveLang, type Lang } from "./i18n";

const CityPage = lazy(() => import("./city/CityPage"));
const CityPreview = lazy(() => import("./city/CityPreview"));
const isCityRoute = () => location.hash.startsWith("#/city");

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
  const [city, setCity] = useState(isCityRoute);
  useEffect(() => {
    const f = () => setCity(isCityRoute());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  // the live city on the landing loads when its section comes near the viewport
  const citySection = useRef<HTMLElement>(null);
  const [showCity, setShowCity] = useState(false);
  const [cityStats, setCityStats] = useState<{ online: number; inTrade: number } | null>(null);
  const onCityStats = useCallback((s: { online: number; inTrade: number }) => setCityStats(s), []);
  useEffect(() => {
    const el = citySection.current;
    if (!el || !("IntersectionObserver" in window)) { setShowCity(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setShowCity(true); io.disconnect(); } }, { rootMargin: "300px" });
    io.observe(el);
    return () => io.disconnect();
  }, [city]);
  const heroCta = useRef<HTMLButtonElement>(null);
  const [heroCtaVisible, setHeroCtaVisible] = useState(true);
  useEffect(() => {
    const el = heroCta.current;
    if (!el || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(([e]) => setHeroCtaVisible(e.isIntersecting), { threshold: 0.1 });
    io.observe(el);
    return () => io.disconnect();
  }, [city]);

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
  const openConnect = (city: boolean) => { setFromCity(city); setOpen(true); };

  const connectLabel = link ? t.dashboard : t.connect;
  const onConnectClick = () => (link ? goDashboard() : openConnect(false));
  const modal = open && (
    <ErrorBoundary onClose={() => setOpen(false)}>
      <ConnectModal t={t} lang={lang} info={info} onClose={() => setOpen(false)} onLinked={onLinked} onOpenDashboard={goDashboard}
                    fromCity={fromCity} onOpenCity={openCity} />
    </ErrorBoundary>
  );

  if (city) {
    return (
      <>
        <Suspense fallback={<div className="city-boot" role="status"><span className="sr-only">Loading EdgeCraft-StrikeCity</span></div>}>
          <CityPage lang={lang} setLang={setLang} onConnect={() => (link ? openCity(link.cityId ?? link.accountId) : openConnect(true))}
                    myAgent={link ? <Dashboard t={t} lang={lang} info={info} link={link} onUnlinked={unlink} onSignOut={() => signOut(t.dash.signedOut)}
                                               onSignIn={() => { unlink(); openConnect(true); }} onOpenCity={openCity} /> : null}
                    owner={link?.token ? { id: link.cityId ?? link.accountId, token: link.token } : null} />
        </Suspense>
        {modal}
        {bye && <div className="toast" role="status">{bye}</div>}
      </>
    );
  }

  return (
    <>
      <a className="skip-link" href="#main">{t.skip}</a>
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
            <a href="#how">{t.nav.how}</a><a href="#strategy">{t.nav.strategy}</a>
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

      <main id="main" tabIndex={-1}>
        <section className="hero" id="top" aria-labelledby="hero-title">
          <div className="container hero-grid">
            <div>
              <h1 id="hero-title">{t.hero.title1}<em>{t.hero.title2}</em></h1>
              <p className="hero-lead">{t.hero.lead}</p>
              <div className="hero-ctas">
                <button ref={heroCta} type="button" className="btn btn-primary btn-lg" onClick={onConnectClick}>{link ? t.dashboard : t.connectCardano}</button>
                <a className="btn btn-outline btn-lg" href="#how">{t.hero.how}</a>
              </div>
              <p className="hero-balance"><Icon.alert />{t.balance.hero}</p>
              <ul className="trust">
                {t.hero.trust.map((x) => <li key={x}><Icon.shield />{x}</li>)}
              </ul>
            </div>
            <StrategyCard t={t} lang={lang} />
          </div>
        </section>

        <section className="section" id="city" aria-labelledby="city-title" ref={citySection}>
          <div className="container">
            <a className="city-show" href="#/city" aria-labelledby="city-title" aria-describedby="city-sub">
              <span className="city-show-frame">
                <img className="city-show-poster" src="/city-preview.jpg" alt="" width={1800} height={900} loading="lazy" decoding="async"
                     onError={(e) => { e.currentTarget.style.display = "none"; }} />
                {showCity && <Suspense fallback={null}><CityPreview onStats={onCityStats} /></Suspense>}
                <span className="city-show-shade" aria-hidden="true" />
              </span>
              <span className="city-show-text">
                <span className="city-show-badge"><span className="live-dot" aria-hidden="true" />{t.cityPromo.eyebrow}</span>
                <span id="city-title" className="city-show-title">{t.cityPromo.title}</span>
                <span id="city-sub" className="city-show-sub">{t.cityPromo.sub}</span>
                {cityStats && cityStats.online > 0 && (
                  <span className="city-show-stats">{fmt(t.cityPromo.stats, { n: String(cityStats.online), t: String(cityStats.inTrade) })}</span>
                )}
                <span className="btn btn-primary btn-lg">{t.cityPromo.cta}<Icon.chevron /></span>
              </span>
            </a>
          </div>
        </section>

        <section className="section" id="how" aria-labelledby="how-title">
          <div className="container">
            <div className="section-head"><span className="kicker">{t.kicker.how}</span><h2 id="how-title">{t.how.title}</h2><p>{t.how.sub}</p></div>
            <ol className="grid grid-4 steps" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {t.how.steps.map(([h, p], i) => (
                <li key={h} className="card">
                  <div className="card-head"><span className="step-num" aria-hidden="true">{i + 1}</span><h3>{h}</h3></div>
                  <p>{p}</p>
                </li>
              ))}
            </ol>
            <aside className="balance-note" aria-labelledby="balance-title">
              <span className="balance-icon" aria-hidden="true"><Icon.alert /></span>
              <div>
                <h3 id="balance-title">{t.balance.title}</h3>
                <p>{t.balance.text}</p>
              </div>
            </aside>
          </div>
        </section>

        <section className="section" id="strategy" aria-labelledby="st-title">
          <div className="container">
            <div className="section-head"><span className="kicker">{t.kicker.strategy}</span><h2 id="st-title">{t.strategy.title}</h2><p>{t.strategy.sub}</p></div>
            <div className="grid grid-2">
              {t.strategy.items.map(([h, p], i, all) => (   // an odd last card spans the row: no empty slot beside it
                <article key={h} className={`card${i === all.length - 1 && all.length % 2 ? " span-row" : ""}`}><h3>{h}</h3><p>{p}</p></article>))}
            </div>
          </div>
        </section>


        <section className="section" id="control" aria-labelledby="ctl-title">
          <div className="container">
            <div className="section-head"><span className="kicker">{t.kicker.control}</span><h2 id="ctl-title">{t.control.title}</h2></div>
            <div className="grid grid-2">
              {t.control.items.map(([h, p]) => <article key={h} className="card"><h3>{h}</h3><p>{p}</p></article>)}
            </div>
          </div>
        </section>

        <section className="section" id="faq" aria-labelledby="faq-title">
          <div className="container">
            <div className="section-head"><span className="kicker">{fmt(t.kicker.faq, { n: String(t.faq.items.length) })}</span><h2 id="faq-title">{t.faq.title}</h2></div>
            <div className="faq">
              {t.faq.items.map(([q, a]) => <details key={q}><summary>{q}</summary><div>{a}</div></details>)}
            </div>
          </div>
        </section>

        <footer className="site-footer">
          <div className="container foot">
            <div className="foot-brand"><Mark size={32} /><span className="foot-word">EdgeCraft-StrikeCity</span><span className="foot-by">{t.footBy}</span></div>
            <p>{t.footer.legal}</p><p>{t.footer.by} Engine {strategy.engine}.</p>
          </div>
        </footer>
      </main>

      <div className="mobile-cta" hidden={!!link || heroCtaVisible}>
        <button type="button" className="btn btn-primary btn-lg btn-block" onClick={onConnectClick}>{link ? t.dashboard : t.connectCardano}</button>
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
