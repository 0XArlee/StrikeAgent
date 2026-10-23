// The Alerts tab: the bot on Telegram (Strike Finance for everyone; the owner's agent, accounts and copies once linked)
// and Strike's latest alerts, each one a press away from the building it concerns.
import { useEffect, useState } from "react";
import type { Lang } from "../i18n";
import type { CityText } from "./text";
import { botUrl, tgLink, tgStatus, tgUnlink, type AlertsDoc } from "./alerts";

const ago = (t: number, now: number) => {
  const m = Math.max(1, Math.round((now - t) / 60_000));
  return m < 60 ? `${m} min` : m < 48 * 60 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`;
};

export function AlertsPanel({ T, lang, doc, owner, onConnect, onPlace }: { T: CityText; lang: Lang; doc: AlertsDoc | null;
  owner: { token: string } | null; onConnect: () => void; onPlace: (place: string) => void }) {
  const A = T.alerts;
  const [chats, setChats] = useState<{ label: string; since: number }[] | null>(null);
  const [state, setState] = useState<"" | "linking" | "open">("");
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const token = owner?.token;
  // the linked chats: now, and every few seconds while a link waits for Start in Telegram
  useEffect(() => {
    if (!token) return;
    let live = true;
    const load = () => tgStatus(token).then((d) => {
      if (!live) return;
      setChats(d.chats);
      if (d.chats.length && url) { setUrl(null); setState(""); }
    }).catch(() => undefined);
    void load();
    const id = url ? window.setInterval(load, 4000) : 0;
    return () => { live = false; if (id) window.clearInterval(id); };
  }, [token, url]);

  const link = async () => {
    if (!token) return;
    setError("");
    setState("linking");
    const w = window.open("about:blank", "_blank");   // opened inside the press: one opened after waiting is blocked
    if (w) w.opener = null;
    try {
      const d = await tgLink(token, lang);
      setUrl(d.url);
      if (w) w.location.href = d.url;
      setState("open");
    } catch (e) {
      w?.close();
      setError((e as Error).message);
      setState("");
    }
  };
  const unlink = async () => {
    if (!token) return;
    try { await tgUnlink(token); setChats([]); } catch (e) { setError((e as Error).message); }
  };
  const now = Date.now();
  const list = (doc?.alerts ?? []).slice(0, 15);
  return (
    <div className="al">
      <p className="al-lead">{A.lead}</p>
      <section className="al-card al-strike" aria-labelledby="al-strike">
        <h3 id="al-strike">{A.strikeTitle}</h3>
        <p className="small">{A.strikeBody}</p>
        <a className="btn btn-primary btn-block" href={botUrl("strike")} target="_blank" rel="noopener noreferrer"><TgIcon />{A.strikeCta}</a>
      </section>
      <section className="al-card al-mine" aria-labelledby="al-mine">
        <h3 id="al-mine">{A.mineTitle}</h3>
        <p className="small">{A.mineBody}</p>
        {!token ? (
          <button type="button" className="btn btn-ghost btn-block" onClick={onConnect}>{A.signIn}</button>
        ) : chats && chats.length ? (
          <div className="al-linked" role="status">
            <span className="al-ok" aria-hidden="true">✓</span>
            <span className="grow">{A.linked(chats.map((c) => c.label).join(", "))}</span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={unlink}>{A.unlink}</button>
          </div>
        ) : (
          <>
            <button type="button" className="btn btn-primary btn-block" onClick={link} disabled={state === "linking"}><TgIcon />{state === "linking" ? A.linking : A.link}</button>
            {url && <p className="small al-hint"><a href={url} target="_blank" rel="noopener noreferrer">{A.open}</a> · {A.linkHint}</p>}
          </>
        )}
        {error && <p className="small neg" role="alert">{error}</p>}
        <p className="small faint">{A.watchHint}</p>
      </section>
      <section aria-labelledby="al-feed">
        <h3 id="al-feed" className="al-feed-title">{A.feed}</h3>
        {doc?.stale && <p className="small faint">{A.stale}</p>}
        {!list.length ? <p className="small faint">{A.none}</p> : (
          <ul className="al-list">
            {list.map((a) => (
              <li key={a.id} className={`al-item ${a.level}`}>
                <div className="al-item-head">
                  <span className="al-kind">{A.kinds[a.kind] ?? a.kind}</span>
                  <time dateTime={new Date(a.t).toISOString()} className="faint small">{A.ago(ago(a.t, now))}</time>
                </div>
                <p className="al-title">{a.title[lang]}</p>
                <p className="small muted">{a.body[lang]}</p>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => onPlace(a.place)}>{A.see}</button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function TgIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" style={{ marginRight: 8, flex: "none" }}>
      <path fill="currentColor" d="M21.9 4.6 18.8 19c-.2 1-.9 1.3-1.8.8l-4.8-3.6-2.3 2.2c-.3.3-.5.5-1 .5l.3-4.9 8.9-8c.4-.4-.1-.6-.6-.2L6.6 12.7 1.9 11.2c-1-.3-1-1 .2-1.5L20.6 2.6c.9-.3 1.6.2 1.3 2z" />
    </svg>
  );
}
