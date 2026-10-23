// The landing's questions, by topic: one topic shown at a time (WAI-ARIA tabs, arrows move between them), each question a
// disclosure that opens in place, and a button that opens or closes every answer of the topic. Short however many
// questions there are.
import { useRef, useState, type KeyboardEvent } from "react";
import type { Dict } from "../i18n";

export function Faq({ t }: { t: Dict }) {
  const F = t.faq;
  const groups = Object.keys(F.groups).filter((g) => F.items.some(([c]) => c === g));
  const [cur, setCur] = useState(groups[0]);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const items = F.items.filter(([c]) => c === cur);
  const allOpen = items.every(([, q]) => open[q]);
  const key = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = groups.indexOf(cur), n = groups.length;
    const j = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i - 1 + n) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (j < 0) return;
    e.preventDefault();
    setCur(groups[j]);
    tabs.current[j]?.focus();
  };
  return (
    <div className="faq2">
      <div className="faq2-tabs" role="tablist" aria-label={F.cats} onKeyDown={key}>
        {groups.map((g, i) => {
          const n = F.items.filter(([c]) => c === g).length;
          return (
            <button key={g} ref={(el) => { tabs.current[i] = el; }} type="button" role="tab" id={`faq-tab-${g}`} aria-selected={g === cur}
                    aria-controls="faq-panel" tabIndex={g === cur ? 0 : -1} onClick={() => setCur(g)}>
              {F.groups[g]} <span className="faq2-n" aria-hidden="true">{n}</span>
            </button>
          );
        })}
      </div>
      <div id="faq-panel" role="tabpanel" aria-labelledby={`faq-tab-${cur}`} className="faq2-panel">
        <div className="faq2-tools">
          <button type="button" className="link-btn" onClick={() => setOpen((o) => ({ ...o, ...Object.fromEntries(items.map(([, q]) => [q, !allOpen])) }))}>
            {allOpen ? F.close : F.open}
          </button>
        </div>
        <div className="faq">
          {items.map(([, q, a]) => (
            <details key={q} open={!!open[q]} onToggle={(e) => { const v = (e.currentTarget as HTMLDetailsElement).open; setOpen((o) => (o[q] === v ? o : { ...o, [q]: v })); }}>
              <summary>{q}</summary><div>{a}</div>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
}
