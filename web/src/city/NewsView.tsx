// The news, quick view (the News Tower's content without entering it): one market's reading from the headlines, what
// pushes it up and down, what would turn it, the next scheduled US releases, the scoreboard and the headlines with the
// reaction measured on Strike. Opened from the city's dock; CityPage wraps it in its dialog.
import { useEffect, useState } from "react";
import type { Lang } from "../i18n";
import { Icon } from "../components/ui";
import { countdown, forMarket, safeUrl, type NewsDoc, type NewsItem, type Reading } from "./news";
import { fmtPct, ticker, type CityText } from "./text";

export const MARKETS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "ADA-USD", "NEAR-USD", "ZEC-USD"];
const FIRST = 20;   // headlines shown before "show more"
export const sideOf = (v: number | null | undefined) => (v == null || Math.abs(v) < 15 ? "flat" : v > 0 ? "pos" : "neg");
export const signed = (v: number, lang: Lang) => { const r = Math.round(v); return `${r > 0 ? "+" : r < 0 ? "−" : ""}${Math.abs(r).toLocaleString(lang === "es" ? "es-ES" : "en-US")}`; };
const modelName = (m: string | null) => (m && /haiku/i.test(m) ? "Claude Haiku" : m ?? "");

type Doc = NewsDoc | null | "none" | "error";

/** The top bar's way in: the word (an icon on phones) and, once scored, BTC's reading. */
export function NewsButton({ T, lang, doc, now, onOpen }: { T: CityText; lang: Lang; doc: Doc; now: number; onOpen: () => void }) {
  const N = T.news;
  const rd = doc && typeof doc === "object" && doc.classifier.on ? doc.markets["BTC-USD"] : undefined;
  const net = rd?.net ?? null;
  const ev = soonEvent(doc, now);   // phones: the top bar's warning becomes a dot here
  const said = (net != null && rd?.label ? `: BTC ${N.labels[rd.label]} ${signed(net, lang)}` : "")
    + (ev ? `. ${N.soon(N.evShort[ev.kind] ?? ev.kind, when(T, ev, now))}` : "");
  return (
    <button type="button" className="city-news-btn" aria-haspopup="dialog" aria-label={N.open + said} title={N.open} onClick={onOpen}>
      <NewsIcon />{ev && <span className="city-news-badge" aria-hidden="true" />}<span className="nb-label">{N.title}</span>
      {net != null && rd?.label && <span className={`nb-read ${sideOf(net)}`} aria-hidden="true">BTC {N.labels[rd.label].toLocaleLowerCase(lang === "es" ? "es-ES" : "en-US")}</span>}
    </button>
  );
}

/** The next scheduled release within 24 h (or one out in the last 2 h), for the top bar's warning and the tape. */
export function soonEvent(doc: Doc, now: number): { t: number; kind: string; just: boolean } | null {
  if (!doc || typeof doc !== "object") return null;
  const just = doc.events.just.find((e) => now - e.t <= 2 * 3600_000 && now >= e.t);
  if (just) return { t: just.t, kind: just.kind, just: true };
  const next = doc.events.next.find((e) => e.t > now);
  return next && next.t - now <= 24 * 3600_000 ? { t: next.t, kind: next.kind, just: false } : null;
}

const when = (T: CityText, ev: { t: number; just: boolean }, now: number) =>
  ev.just ? T.news.eventJust : T.news.inTime(countdown(ev.t - now, T.news.units));

/** The top bar's warning before a scheduled US release (24 h before, until 2 h after). */
export function EventSoon({ T, doc, now, onOpen }: { T: CityText; doc: Doc; now: number; onOpen: () => void }) {
  const ev = soonEvent(doc, now);
  if (!ev) return null;
  const text = T.news.soon(T.news.evShort[ev.kind] ?? ev.kind, when(T, ev, now));
  // where the bar is short: the release's code and the first unit of the countdown ("CPI · 3 h")
  const short = `${T.tower.codes[ev.kind] ?? ev.kind} · ${ev.just ? T.news.eventJust : countdown(ev.t - now, T.news.units).split(" ").slice(0, 2).join(" ")}`;
  return (
    <button type="button" className={`city-event${ev.just ? " just" : ""}`} title={`${text}. ${T.news.soonTip}`} onClick={onOpen} aria-haspopup="dialog">
      <span className="city-event-dot" aria-hidden="true" /><span className="ev-full" aria-hidden="true">{text}</span>
      <span className="ev-short" aria-hidden="true">{short}</span><span className="sr-only">{`${text}. ${T.news.soonTip}`}</span>
    </button>
  );
}

/** The exchange screen's tape: the news reading of BTC, the theme it follows and the next release. */
export function tapeLine(doc: Doc, T: CityText, lang: Lang, now: number): string {
  if (!doc || typeof doc !== "object") return "";
  const N = T.news, parts: string[] = [N.tape];
  const rd = doc.classifier.on ? doc.markets["BTC-USD"] : undefined;
  if (rd?.net != null && rd.label) {
    parts.push(`BTC ${N.labels[rd.label].toUpperCase()} ${signed(rd.net, lang)}`);
    const top = rd.drivers[rd.net >= 0 ? "up" : "down"][0]?.top;
    const h = top ? doc.headlines.find((x) => x.id === top) : undefined;
    if (h) parts.push(lang === "es" && h.es ? h.es : h.title);
  } else if (lang === "en" && doc.headlines[0]) {
    parts.push(doc.headlines[0].title);   // not scored yet: the newest headline (they are in English)
  }
  const next = doc.events.next.find((e) => e.t > now);
  if (next) parts.push(`${(N.evShort[next.kind] ?? next.name).toUpperCase()} ${N.inTime(countdown(next.t - now, N.units))}`);
  return parts.length > 1 ? parts.join(" · ") : "";
}

/** For an agent in a trade: what the news say about its market, as context for whoever looks (never as its reason). */
export function contextLine(doc: Doc, market: string, T: CityText, lang: Lang, now: number): string | null {
  if (!doc || typeof doc !== "object") return null;
  const N = T.news, parts: string[] = [];
  const rd = doc.classifier.on ? doc.markets[market] : undefined;
  if (rd?.net != null && rd.label) parts.push(`${N.labels[rd.label]} ${signed(rd.net, lang)}`);
  const ev = soonEvent(doc, now);
  if (ev) parts.push(N.soon(N.evShort[ev.kind] ?? ev.kind, when(T, ev, now)));
  return parts.length ? parts.join(" · ") : null;
}

export const NewsIcon = () => (
  <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 5h13v14H6a2 2 0 0 1-2-2z" /><path d="M17 9h3v8a2 2 0 0 1-2 2M7.5 9h6M7.5 12.5h6M7.5 16h4" />
  </svg>
);

export function NewsView({ T, lang, doc, market, onMarket, onClose, live, inTrade }:
  { T: CityText; lang: Lang; doc: Doc; market: string; onMarket: (m: string) => void; onClose: () => void; live: number; inTrade: number }) {
  const N = T.news;
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 30_000); return () => window.clearInterval(id); }, []);

  return (
    <>
      <div className="chart-head">
        <h2 id="news-title">{N.title} · {ticker(market)}</h2>
        <div className="chart-tabs" role="group" aria-label={N.markets}>
          {MARKETS.map((m) => <button key={m} type="button" aria-pressed={m === market} onClick={() => onMarket(m)}>{ticker(m)}</button>)}
        </div>
        <button type="button" className="icon-btn" aria-label={T.card.close} data-autofocus onClick={onClose}><Icon.close /></button>
      </div>
      {doc === null ? <p className="news-state" role="status">{N.loading}</p>
        : doc === "none" ? <p className="news-state" role="status">{N.empty}</p>
        : doc === "error" ? <p className="news-state" role="status">{N.error}</p>
        : <Body T={T} lang={lang} doc={doc} market={market} now={now} live={live} inTrade={inTrade} />}
    </>
  );
}

function Body({ T, lang, doc, market, now, live, inTrade }: { T: CityText; lang: Lang; doc: NewsDoc; market: string; now: number; live: number; inTrade: number }) {
  const N = T.news;
  const [all, setAll] = useState(false);
  useEffect(() => setAll(false), [market]);
  const items = forMarket(doc.headlines, market);
  const shown = all ? items : items.slice(0, FIRST);
  const okFeeds = doc.feeds.filter((f) => f.ok).length;
  return (
    <div className="news-body">
      <div className="news-side">
        <section className="news-read" aria-labelledby="news-read-title">
          <h3 id="news-read-title" className="sr-only">{N.reading}</h3>
          <ReadingBlock T={T} lang={lang} doc={doc} market={market} />
        </section>

        <section className="news-box" aria-labelledby="news-cal-title">
          <h3 id="news-cal-title">{N.events}</h3>
          <EventsList T={T} lang={lang} doc={doc} now={now} />
        </section>

        <section className="news-box" aria-labelledby="news-board-title">
          <h3 id="news-board-title">{N.board}</h3>
          <ScoreBox T={T} doc={doc} market={market} />
        </section>

        <p className="news-agents"><span className="city-live-dot" aria-hidden="true" />{N.agents(live, inTrade)}</p>
      </div>

      <section className="news-list" aria-labelledby="news-list-title">
        <h3 id="news-list-title">{N.headlines} <span className="faint num">{items.length}</span></h3>
        <ul>
          {shown.map((h) => <Headline key={h.id} T={T} lang={lang} h={h} now={now} />)}
        </ul>
        {!all && items.length > FIRST && (
          <button type="button" className="btn btn-ghost btn-block" onClick={() => setAll(true)}>{N.more(items.length - FIRST)}</button>
        )}
      </section>

      <p className="news-note">
        {N.note}{" "}
        <span className="faint">{N.updated(T.ago((now - doc.generated) / 1000))} · {N.sources(okFeeds, doc.feeds.length)}
          {doc.classifier.on && doc.classifier.model ? ` · ${N.scoredBy(modelName(doc.classifier.model))}` : ""}</span>
        {doc.stale && <span className="news-stale"> {N.stale}</span>}
      </p>
    </div>
  );
}

/** A market's reading (or why there is none), with the theme the price is following. */
export function ReadingBlock({ T, lang, doc, market }: { T: CityText; lang: Lang; doc: NewsDoc; market: string }) {
  const N = T.news;
  const rd = doc.markets[market];
  const byId = new Map(doc.headlines.map((h) => [h.id, h]));
  const follow = doc.following.find((f) => f.follow > 0);
  return (
    <>
      {!doc.classifier.on ? <p className="news-pending">{N.pending}</p>
        : rd?.net == null ? <p className="news-pending">{market !== "BTC-USD" && rd && rd.n ? N.fewOwn(ticker(market)) : N.noReading}</p>
        : <Reading T={T} lang={lang} rd={rd} byId={byId} />}
      {doc.classifier.on && rd?.net != null && follow && (
        <p className="news-follow">{N.follows(N.cats[follow.cat] ?? follow.cat, follow.follow.toLocaleString(lang === "es" ? "es-ES" : "en-US", { maximumFractionDigits: 1 }))}</p>
      )}
    </>
  );
}

/** The scheduled US releases with their countdown (one just out stays for 2 h). */
export function EventsList({ T, lang, doc, now, max = 4 }: { T: CityText; lang: Lang; doc: NewsDoc; now: number; max?: number }) {
  const N = T.news;
  return (
    <ul className="news-cal">
      {doc.events.just.map((e) => (
        <li key={`j${e.t}`} className="just"><span>{N.evNames[e.kind] ?? e.name}</span><span className="num">{N.eventJust}</span></li>
      ))}
      {doc.events.next.filter((e) => e.t > now).slice(0, max).map((e) => (
        <li key={e.t}>
          <span>{N.evNames[e.kind] ?? e.name}<time className="faint" dateTime={new Date(e.t).toISOString()}>
            {new Date(e.t).toLocaleString(lang === "es" ? "es-ES" : "en-US", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</time></span>
          <span className="num">{N.inTime(countdown(e.t - now, N.units))}</span>
        </li>
      ))}
    </ul>
  );
}

/** Did the readings predict the next 4 h on Strike? (empty until it has some) */
export function ScoreBox({ T, doc, market }: { T: CityText; doc: NewsDoc; market: string }) {
  const N = T.news;
  const board = doc.scoreboard[market];
  return board && board.called ? (
    <>
      <p className="news-board-num"><span className="num">{Math.round((board.hits / board.called) * 100)} %</span></p>
      <p className="small muted">{N.boardLine(board.hits, board.called)} {N.boardBase(board.up, board.readings)}</p>
    </>
  ) : <p className="small muted">{N.boardEmpty}</p>;
}

function Reading({ T, lang, rd, byId }: { T: CityText; lang: Lang; rd: Reading; byId: Map<string, NewsItem> }) {
  const N = T.news;
  const net = rd.net ?? 0;
  const side = sideOf(net);
  const pct = Math.max(-100, Math.min(100, net)) / 2;   // half the track each way
  const title = (id: string | null) => {
    const h = id ? byId.get(id) : undefined;
    return h ? (lang === "es" && h.es ? h.es : h.title) : "";
  };
  return (
    <>
      <div className="nr-top">
        <span className={`nr-num num ${side}`}>{signed(net, lang)}</span>
        <div className="nr-what">
          <span className={`nr-label ${side}`}>{rd.label ? N.labels[rd.label] : ""}</span>
          <span className="faint small">{N.netOf(rd.n)}</span>
        </div>
        {rd.whipsaw && <span className="nr-whip" title={N.whipsawTip}><Icon.alert />{N.whipsaw}<span className="sr-only">: {N.whipsawTip}</span></span>}
      </div>
      <div className="nr-gauge" aria-hidden="true">
        <span className={`nr-fill ${side}`} style={net >= 0 ? { left: "50%", width: `${pct}%` } : { right: "50%", width: `${-pct}%` }} />
        <span className="nr-mark" style={{ left: `${50 + pct}%` }} />
      </div>
      <details className="nr-how"><summary>{N.how}</summary><p>{N.netHow}</p></details>
      <div className="nr-drivers">
        {([["up", N.up, rd.drivers.up], ["down", N.down, rd.drivers.down]] as const).map(([k, label, list]) => (
          <div key={k} className={`nr-drv ${k}`}>
            <h4>{label}</h4>
            {list.length ? (
              <ul>{list.map((d) => (
                <li key={d.cat}><span className="nr-cat">{N.cats[d.cat] ?? d.cat}</span><span className={`num ${k === "up" ? "pos" : "neg"}`}>{signed(d.push, lang)}</span>
                  {d.top && <p>{title(d.top)}</p>}</li>
              ))}</ul>
            ) : <p className="faint small">{N.none}</p>}
          </div>
        ))}
      </div>
      {rd.flip && (rd.flip[lang] ?? rd.flip.en).length > 0 && (
        <div className="nr-flip"><h4>{N.flip}</h4><ul>{(rd.flip[lang] ?? rd.flip.en).map((x) => <li key={x}>{x}</li>)}</ul></div>
      )}
    </>
  );
}

export function Headline({ T, lang, h, now }: { T: CityText; lang: Lang; h: NewsItem; now: number }) {
  const N = T.news;
  const text = lang === "es" && h.es ? h.es : h.title;
  const url = safeUrl(h.url);
  // the move, and how it compares with the market's normal move over that time (|z| under 1: nothing unusual)
  const react = (v: number | null, z: number | null | undefined, label: string, due: number) => (
    <span>{label} {v != null ? <><b className={`num ${v > 0 ? "pos" : v < 0 ? "neg" : ""}`}>{fmtPct(v, lang)}</b>
      {z != null && <span className={`nl-z${Math.abs(z) >= 1 ? " big" : ""}`}>{Math.abs(z) < 1 ? N.normal : N.timesNormal(Math.abs(z).toLocaleString(lang === "es" ? "es-ES" : "en-US", { maximumFractionDigits: 1 }))}</span>}</>
      : <span className="faint">{now < h.t + due + 10 * 60_000 ? N.measuring : "—"}</span>}</span>
  );
  const quiet = h.catalyst === false;   // a price recap, a prediction or unclear: listed, never in the reading
  return (
    <li className={`nl${quiet ? " quiet" : ""}`}>
      <div className="nl-meta">
        <time dateTime={new Date(h.t).toISOString()}>{T.ago((now - h.t) / 1000)}</time>
        <span>{h.source}</span>
        {h.sources != null && h.sources > 1 && <span className="nl-more" title={(h.also ?? []).join(", ")}>{N.moreSources(h.sources - 1)}</span>}
        {h.cat && <span className="nl-cat">{N.cats[h.cat] ?? h.cat}</span>}
        {h.impact === "high" && <span className="nl-hi">{N.impact.high}</span>}
        {quiet && <span className="nl-quiet" title={N.notCountedTip}>{N.notCounted}</span>}
      </div>
      <p className="nl-title">
        {url ? <a href={url} target="_blank" rel="noopener nofollow noreferrer">{text}<span className="sr-only">{N.newTab}</span></a> : text}
      </p>
      <div className="nl-nums">
        {h.score != null && !quiet && <span className={`nl-score num ${sideOf(h.score) === "flat" ? "" : sideOf(h.score)}`} title={N.score}>
          <span className="sr-only">{N.score}: </span>{signed(h.score, lang)}</span>}
        {h.rm && <span className="nl-react"><span className="faint">{N.reaction} ({ticker(h.rm)}):</span>
          {react(h.r15, h.z15, "15 min", 15 * 60_000)}{react(h.r60, h.z60, "1 h", 60 * 60_000)}</span>}
        {h.against && <span className="nl-rej">{N.rejected}</span>}
      </div>
    </li>
  );
}
