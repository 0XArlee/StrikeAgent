// The landing's navigation on phones and narrow tablets (the bar's links do not fit under 860 px): a menu button that
// turns into an X and a panel that unrolls under the header, over the city's pixel grid. Closes on a link, Esc, a tap
// outside or growing back to the desktop layout; focus goes in when it opens and back to the button when it closes.
// The panel lives in <body> (a portal): the header's backdrop-filter would make it fixed to the header, not the screen.
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import type { Dict, Lang } from "../i18n";
import { Mark } from "./ui";

interface Props {
  t: Dict; lang: Lang; setLang: (l: Lang) => void;
  connectLabel: string; onConnect: () => void;
}

const WIDE = "(min-width: 861px)";   // .nav shows from here (styles.css)

export function MobileMenu({ t, lang, setLang, connectLabel, onConnect }: Props) {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const M = t.menu;
  const close = useCallback((focusButton = true) => {
    setOpen(false);
    if (focusButton) btn.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    const wide = window.matchMedia(WIDE);
    const onWide = () => { if (wide.matches) close(false); };
    document.addEventListener("keydown", onKey);
    wide.addEventListener("change", onWide);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";   // the page behind does not scroll under the panel
    panel.current?.querySelector<HTMLElement>("a, button")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      wide.removeEventListener("change", onWide);
      document.body.style.overflow = prev;
    };
  }, [open, close]);

  const items: { href: string; label: string; sub: string }[] = [
    { href: "#how", label: t.nav.how, sub: M.how },
    { href: "#strategy", label: t.nav.strategy, sub: M.strategy },
    { href: "#faq", label: t.nav.faq, sub: M.faq },
  ];

  return (
    <>
      <button ref={btn} type="button" className={`menu-btn${open ? " is-open" : ""}`} aria-expanded={open} aria-controls="mobile-menu"
              aria-label={open ? M.close : M.open} onClick={() => (open ? close() : setOpen(true))}>
        <span className="menu-bars" aria-hidden="true"><i /><i /><i /></span>
      </button>
      {createPortal(<>
      <div className="mm-backdrop" data-open={open} aria-hidden="true" onClick={() => close()} />
      <div ref={panel} id="mobile-menu" className="mm" data-open={open} role="dialog" aria-modal="true" aria-label={M.title}>
        <div className="mm-inner">
          <p className="mm-eyebrow mono">{M.title}</p>
          <nav aria-label="Main">
            <ol className="mm-list">
              {items.map((x, i) => (
                <li key={x.href} style={{ "--i": i } as CSSProperties}>
                  <a href={x.href} onClick={() => close(false)}>
                    <span className="mm-num mono" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
                    <span className="mm-text"><span className="mm-label">{x.label}</span><span className="mm-sub">{x.sub}</span></span>
                    <span className="mm-arrow" aria-hidden="true">→</span>
                  </a>
                </li>
              ))}
            </ol>
          </nav>
          <a className="mm-city" href="#/city" onClick={() => close(false)} style={{ "--i": items.length } as CSSProperties}>
            <span className="mm-city-mark" aria-hidden="true"><Mark size={44} /></span>
            <span className="mm-text">
              <span className="mm-live mono"><span className="mm-live-dot" aria-hidden="true" />{M.live}</span>
              <span className="mm-label">{t.nav.city}</span>
              <span className="mm-sub">{M.city}</span>
            </span>
            <span className="mm-arrow" aria-hidden="true">→</span>
          </a>
          <div className="mm-foot" style={{ "--i": items.length + 1 } as CSSProperties}>
            <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => { close(false); onConnect(); }}>{connectLabel}</button>
            <div className="mm-row">
              <div className="lang" role="group" aria-label="Language">
                <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>EN</button>
                <button type="button" aria-pressed={lang === "es"} onClick={() => setLang("es")}>ES</button>
              </div>
              <a className="mm-strike" href="https://www.strikefinance.org" target="_blank" rel="noopener noreferrer">
                {t.on} ↗<span className="sr-only"> (opens in a new tab)</span>
              </a>
            </div>
          </div>
        </div>
      </div>
      </>, document.body)}
    </>
  );
}
