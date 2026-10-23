import { useEffect, useState } from "react";
import { ApiError, api, messageHex, type AgentAction, type AppInfo, type CopyPlan, type JournalEntry, type Me } from "../api";
import { shortAddr } from "../cardano/bech32";
import { connect, scanWallets, signMessage } from "../cardano/wallets";
import type { Decision } from "../city/agents";
import { normalizeLook, type Look } from "../city/look";
import { lookFor } from "../city/sprites";
import { cityText, describe } from "../city/text";
import { fmt, type Dict, type Lang } from "../i18n";
import type { LinkResult } from "./ConnectModal";
import { AvatarEditor, Sprite } from "./AvatarEditor";
import { PersonaPicker } from "./PersonaPicker";
import { FeedbackInbox } from "./FeedbackDialog";
import { personaFor, type Persona } from "../city/persona";
import { PortfolioView, useMarks } from "../city/portfolio";
import { MIN_BALANCE, TEST_MIN_AVAILABLE, strategyId, strategyName } from "../strategies";
import { StrategyPicker, type Plan } from "./StrategyPicker";
import { Alert, Icon } from "./ui";
import { CopyPlanDialog, CopySection, defaultPlan } from "./CopyPanel";
import { traderName } from "../city/copy";

/** #/city?me&copy=<trader>&pf=<platform>: "Copy with my agent" on a trader's card opens the plan with that trader. */
const copyLink = () => {
  const m = /[?&]copy=([\w-]+)(?:&pf=(strike|hyperliquid))?/.exec(location.hash);
  return m ? { id: m[1], platform: (m[2] ?? (m[1].startsWith("0x") ? "hyperliquid" : "strike")) as "strike" | "hyperliquid" } : null;
};

interface Props {
  t: Dict; lang: Lang; info: AppInfo; link: LinkResult;
  onUnlinked: () => void;                 // the agent was deleted or the session is gone
  onSignOut: () => void;                  // "Disconnect wallet": the session ends here, the agent keeps running
  onSignIn: () => void;                   // open the wallet dialog again
  onOpenCity: (agentId: string) => void;
}

export function Dashboard({ t, lang, info, link, onUnlinked, onSignOut, onSignIn, onOpenCity }: Props) {
  const d = t.dash, P = t.paper;
  const [me, setMe] = useState<Me | null>(null);
  const [busy, setBusy] = useState<AgentAction | "live" | "liveOff" | "">("");
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const [editing, setEditing] = useState<Look | null>(null);
  const [persona, setPersona] = useState<Persona | null>(null);   // the personality dialog
  const [plan, setPlan] = useState<Plan | null>(null);   // the strategy/markets/risk dialog
  const [copyEdit, setCopyEdit] = useState<CopyPlan | null>(() => {   // the copy plan dialog
    const l = copyLink();
    return l ? defaultPlan("manual", { id: l.id, platform: l.platform } as Parameters<typeof defaultPlan>[1]) : null;
  });
  useEffect(() => { if (copyLink()) history.replaceState(null, "", location.hash.replace(/&copy=[\w-]+(&pf=\w+)?/, "")); }, []);
  const [notice, setNotice] = useState("");
  const loc = lang === "es" ? "es-ES" : "en-US";
  const usd = (v: number | null | undefined) => v == null ? "—" : v.toLocaleString(loc, { style: "currency", currency: "USD" });
  const paper = me?.mode === "paper" || !!info.paper;   // the site's own features (city, character) exist in both modes
  const real = me?.mode === "live";                     // numbers from the owner's Strike account, not a simulation
  const marks = useMarks(!!me?.portfolio);

  useEffect(() => {
    let alive = true;
    const load = () => api.me(link).then((x) => { if (alive) { setMe(x); setExpired(false); } }).catch((e) => {
      if (!alive) return;
      if (e instanceof ApiError && e.status === 401) setExpired(true);
      else if (e instanceof ApiError && e.status === 404) onUnlinked();
      else setError(String(e.message ?? e));
    });
    load();
    const id = window.setInterval(load, 10_000);   // the host pushes within ~10 s of what the agent does
    return () => { alive = false; clearInterval(id); };
  }, [link, onUnlinked]);

  async function act(action: AgentAction, look?: Look, settings?: Plan, nextPersona?: Persona, copy?: CopyPlan) {
    setError("");
    setNotice("");
    setBusy(action);
    try {
      const w = scanWallets().find((x) => x.name === link.walletName) ?? scanWallets()[0];
      if (!w) throw new Error(t.modal.noWallets);
      const conn = await connect(w);
      const ch = await api.actionChallenge(link.accountId, action, look, settings, nextPersona, copy);
      const sig = await signMessage(conn, messageHex(ch.messageToSign));
      const r = await api.action(ch.sessionId, sig);
      if ("deleted" in r) { onUnlinked(); return; }
      setMe(r);
      if (action === "look") { setEditing(null); setPersona(null); }
      if (action === "settings") { setPlan(null); if (r.live?.status === "active") setNotice(t.strategies.restart); }
      if (action === "test") setNotice(t.live.testAsked);
      if (action === "copy") { setCopyEdit(null); setNotice(t.copyPlan.signed); }
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy("");
    }
  }

  /** Builder connect: Strike's own message, signed by this agent's wallet; Strike then authorises our API wallet. */
  async function goLive() {
    setError("");
    setBusy("live");
    try {
      if (!link.token) throw new Error(P.signIn);
      const w = scanWallets().find((x) => x.name === link.walletName) ?? scanWallets()[0];
      if (!w) throw new Error(t.modal.noWallets);
      const conn = await connect(w);
      if (conn.address !== link.address) throw new Error(fmt(L.wrongWallet, { addr: shortAddr(link.address, 10, 6) }));
      const ch = await api.liveChallenge(link.token);
      const sig = await signMessage(conn, messageHex(ch.messageToSign));
      const v = await api.liveVerify(link.token, ch.sessionId, sig);
      setMe((m) => (m ? { ...m, live: v } : m));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setExpired(true);
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy("");
    }
  }

  async function stopLive() {
    setError("");
    setBusy("liveOff");
    try {
      const v = await api.liveOff(link.token ?? "");
      setMe((m) => (m ? { ...m, live: v } : m));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setExpired(true);
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy("");
    }
  }

  const L = t.live;
  const live = me?.live;
  const liveOn = live?.status === "active";
  const envName = (live?.env ?? info.live?.env) === "testnet" ? "testnet" : "mainnet";
  const feePct = ((live?.feeBps ?? info.live?.feeBps ?? 20) / 10_000).toLocaleString(loc, { style: "percent", minimumFractionDigits: 2 });
  const active = me?.status !== "paused";
  const look = normalizeLook(me?.look ?? link.look) ?? lookFor(link.accountId);
  const shown = me?.public ?? link.public ?? false;
  const T = cityText[lang];
  const text = (x: JournalEntry) => x.code ? describe(x as unknown as Decision, T, lang).text : x.text ?? "";
  const when = (ms: number) => new Date(ms).toLocaleString(loc, { dateStyle: "medium", timeStyle: "short" });
  const label = (a: AgentAction, txt: string) => (busy === a ? d.signToConfirm : txt);
  const S = t.strategies;
  const strat = strategyId(me?.strategy ?? link.strategy);
  const running = liveOn && !!me?.portfolio;   // connected and the host already runs it (else: starting)
  // testnet's book rejects closing orders (2026-10-20): a test trade there could not be closed
  const canTest = running && envName === "mainnet";
  // the smallest test needs about this much available (the agent and the site refuse it below)
  const available = me?.portfolio?.available ?? null;
  const testShort = canTest && available != null && available < TEST_MIN_AVAILABLE;

  const liveCard = me?.live?.enabled ? (
    <div className={`card live-card${liveOn ? " live-on" : ""}`}>
      <h3>{liveOn ? fmt(L.on, { env: envName }) : L.title}</h3>
      {liveOn ? (
        <>
          <dl className="rows">
            <div className="row"><dt>{L.account}</dt><dd className="mono">{live?.accountId ?? "—"}</dd></div>
            {live?.since && <div className="row"><dt>{L.since}</dt><dd>{when(live.since)}</dd></div>}
            <div className="row"><dt>{L.fee}</dt><dd>{feePct}</dd></div>
          </dl>
          {running
            ? <p className="faint" style={{ marginTop: 10 }}>{fmt(L.seeStrike, { env: envName })}</p>
            : <p className="live-starting" role="status"><span className="spinner spinner-sm" aria-hidden="true" /> {fmt(L.startingCard, { env: envName })}</p>}
          {canTest && <p className="faint" style={{ marginTop: 10 }}>{L.testHint}</p>}
          {testShort && <p className="field-hint" id="test-needs" style={{ marginTop: 6 }}>{fmt(L.testNeeds, { min: `${TEST_MIN_AVAILABLE} $`, avail: usd(available) })}</p>}
          <div className="actions-row">
            {canTest && (
              <button type="button" className="btn btn-outline" onClick={() => act("test")} disabled={!!busy || expired || testShort}
                      aria-describedby={testShort ? "test-needs" : undefined}>
                {label("test", L.test)}
              </button>
            )}
            <button type="button" className="btn btn-danger" onClick={stopLive} disabled={!!busy || expired}>
              {busy === "liveOff" ? "…" : L.stop}
            </button>
          </div>
        </>
      ) : (
        <>
          <p style={{ marginTop: 8 }}>{fmt(L.intro, { env: envName })}</p>
          {envName === "testnet" && <p className="faint" style={{ marginTop: 6 }}>{L.testnet}</p>}
          <ul className="live-points">
            {L.points.map((x) => <li key={x}>{fmt(x, { fee: feePct })}</li>)}
          </ul>
          {live?.status === "off" && <p className="faint">{L.off}</p>}
          <div className="actions-row">
            <button type="button" className="btn btn-primary" onClick={goLive} disabled={!!busy || expired}>
              {busy === "live" ? d.signToConfirm : fmt(L.connect, { env: envName })}
            </button>
          </div>
        </>
      )}
    </div>
  ) : null;
  const statusCard = (
    <div className="card">
      <h3>{d.status}</h3>
      <p style={{ marginTop: 10 }}>
        <span className={`status-pill ${active ? "status-on" : "status-off"}`}>
          <span className={`dot ${active ? "" : "warn"}`} aria-hidden="true" />{active ? d.active : d.paused}
        </span>
      </p>
      <dl className="rows">
        <div className="row"><dt>{S.label}</dt><dd>{strategyName(strat)}</dd></div>
        <div className="row"><dt>{t.modal.risk}</dt><dd>{t.modal.riskNames[me?.risk ?? link.risk]} · {info.riskPresets[me?.risk ?? link.risk]}%</dd></div>
        <div className="row"><dt>{t.modal.markets}</dt><dd>{(me?.markets ?? link.markets).map((x) => x.replace("-USD", "")).join(" · ")}</dd></div>
        {paper && <div className="row"><dt>{P.city}</dt><dd>{shown
          ? <button type="button" className="link-btn" onClick={() => onOpenCity(link.cityId ?? link.accountId)}>{P.shown} · {P.seeCity}</button>
          : P.privateLbl}</dd></div>}
        {me?.createdAt && <div className="row"><dt>{P.since}</dt><dd>{when(me.createdAt)}</dd></div>}
        {me?.copy && <div className="row"><dt>{d.copyRow}</dt><dd>{me.copy.status?.state === "copying" && me.copy.status.lead
          ? <a href="#copy-with-agent">{d.copyOn(traderName({ id: me.copy.status.lead, platform: me.copy.status.platform === "hyperliquid" ? "hyperliquid" : "strike" }))}</a>
          : d.copyOff}</dd></div>}
      </dl>
      {me?.copy && <p className="field-hint">{d.independent}</p>}
    </div>
  );
  // a live agent with its account: Strike connection and status side by side, the portfolio full width below;
  // otherwise the connection on top and status, equity and positions in three columns
  const wide = !!me?.portfolio && !!liveCard;
  // below the recommended balance many signals come out under Strike's minimum order: say so while it lasts
  const riskNow = me?.risk ?? link.risk;
  const equityNow = me?.portfolio?.equity ?? null;
  // connected but nothing deposited yet: say exactly that (the agent waits and takes the next signals once it arrives)
  const emptyAccount = running && equityNow != null && equityNow < 1 && !me?.portfolio?.positions.length;
  const lowBalance = running && !emptyAccount && equityNow != null && equityNow < MIN_BALANCE[riskNow];

  return (
    <section className="section" id="agent" aria-labelledby="agent-title">
      <div className="container">
        <div className="section-head dash-head">
          <div className="dash-who">
            <span className="dash-avatar"><Sprite look={look} scale={4} /></span>
            <div>
            <h2 id="agent-title">{d.title}{me?.name ? ` · ${me.name}` : link.name ? ` · ${link.name}` : ""}</h2>
            <p className="mono faint" style={{ marginTop: 4 }}>
              {shortAddr(link.address, 14, 8)} · {link.walletName}{liveOn ? <> · <span className="tag tag-live">{envName === "testnet" ? T.kindTestnet : fmt(L.tag, { env: envName })}</span></> : paper && <> · <span className="tag tag-paper">{P.badge}</span></>}
            </p>
            </div>
          </div>
          <div className="dash-actions">
            {active ? (
              <button type="button" className="btn btn-ghost" onClick={() => act("pause")} disabled={!!busy || expired}><Icon.pause /> {label("pause", d.pause)}</button>
            ) : (
              <button type="button" className="btn btn-primary" onClick={() => act("resume")} disabled={!!busy || expired}><Icon.play /> {label("resume", d.resume)}</button>
            )}
            {paper && (shown
              ? <button type="button" className="btn btn-ghost" onClick={() => act("hide")} disabled={!!busy || expired}>{label("hide", P.hide)}</button>
              : <button type="button" className="btn btn-ghost" onClick={() => act("show")} disabled={!!busy || expired}>{label("show", P.show)}</button>)}
            <button type="button" className="btn btn-ghost" onClick={() => setPlan({ strategy: strat, markets: me?.markets ?? link.markets, risk: me?.risk ?? link.risk })}
                    disabled={!!busy || expired}>{S.edit}</button>
            {paper && <button type="button" className="btn btn-ghost" onClick={() => setEditing(look)} disabled={!!busy || expired}>{t.avatar.edit}</button>}
            {paper && <button type="button" className="btn btn-ghost" onClick={() => setPersona(me?.persona ?? personaFor(link.cityId ?? link.accountId))}
                              disabled={!!busy || expired}>{t.persona.edit}</button>}
            <button type="button" className="btn btn-danger" onClick={() => act("revoke")} disabled={!!busy || expired}>{label("revoke", paper ? P.remove : d.revoke)}</button>
            <button type="button" className="btn btn-ghost" onClick={onSignOut} disabled={!!busy}><Icon.logout /> {d.signOut}</button>
          </div>
        </div>
        {expired && (
          <div className="alert alert-warn" role="status"><Icon.alert /><div>{P.signIn}{" "}
            <button type="button" className="btn btn-outline" style={{ marginLeft: 8 }} onClick={onSignIn}>{P.signInBtn}</button></div></div>
        )}
        {error && <Alert kind="err">{error}</Alert>}
        {notice && <Alert kind="info">{notice}</Alert>}
        {me?.hold && liveOn && <Alert kind="warn">{fmt(t.hold, { strategy: strategyName(strat) })}</Alert>}
        {emptyAccount && (me?.copy?.status?.state === "copying"   // the copy has its own money: only the strategy waits
          ? <Alert kind="info">{fmt(t.balance.emptyCopy, { min: `${MIN_BALANCE[riskNow]} $` })}</Alert>
          : <Alert kind="warn">{fmt(t.balance.empty, { min: `${MIN_BALANCE[riskNow]} $` })}</Alert>)}
        {lowBalance && <Alert kind="warn">{fmt(t.balance.low, { eq: usd(equityNow), min: `${MIN_BALANCE[riskNow]} $`, risk: t.modal.riskNames[riskNow].toLowerCase() })}</Alert>}
        {paper && !me?.live?.enabled && <Alert kind="info">{P.note}</Alert>}
        {liveCard && !wide && <div style={{ marginTop: 16 }}>{liveCard}</div>}
        <div className={`dash-grid${wide ? " dash-grid-2" : ""}`} style={{ marginTop: 16 }}>
          {wide && liveCard}
          {statusCard}
          {!me?.portfolio && <>
          <div className="card">
            <h3>{real ? d.equity : paper ? P.equity : d.equity}</h3>
            <div className="kpi-big num" style={{ marginTop: 10 }}>{usd(me?.equity)}</div>
            <dl className="rows">
              {paper
                ? <div className="row"><dt>{P.trades}</dt><dd className="num">{me?.trades ?? 0}</dd></div>
                : <div className="row"><dt>{d.fees}</dt><dd className="num">{usd(me?.feesPaid)}</dd></div>}
            </dl>
          </div>
          <div className="card">
            <h3>{d.positions}</h3>
            {!me?.openPositions.length ? <p>{d.noPositions}</p> : (
              <dl className="rows">
                {me.openPositions.map((p) => (
                  <div key={p.market} className="row">
                    <dt>{p.market} <span className={p.side === "long" ? "pos" : "neg"}>{p.side === "long" ? "Long" : "Short"}</span><br />
                      <span className="faint num">{p.size.toLocaleString(loc, { maximumSignificantDigits: 4 })} @ {p.entry.toLocaleString(loc)} · {d.stop} {p.stop != null ? p.stop.toLocaleString(loc) : "—"}</span></dt>
                    <dd className={`num ${(p.upnl ?? 0) >= 0 ? "pos" : "neg"}`}>{usd(p.upnl)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
          </>}
        </div>
        {me?.portfolio && (
          <div className="card" style={{ marginTop: 16 }}>
            <h3>{fmt(L.portfolio, { env: envName })}</h3>
            <PortfolioView p={me.portfolio} lang={lang} marks={marks} idPrefix="dash-pf" subAccounts={me.copy?.status?.accounts} />
          </div>
        )}
        {me?.copy && <CopySection t={t} lang={lang} view={me.copy} liveOn={liveOn} busy={!!busy} onEdit={(x) => { setError(""); setCopyEdit(x); }}
                     onStop={() => me?.copy?.plan && act("copy", undefined, undefined, undefined, { ...me.copy.plan, mode: "off" })} />}
        <div className="card" style={{ marginTop: 16 }}>
          <h3>{d.decisions}</h3>
          {me && !me.decisions.length ? <p>{P.noDecisions}</p> : (
            <ol className="timeline">
              {(me?.decisions ?? []).map((x, i) => (
                <li key={i}><time dateTime={new Date(x.time).toISOString()}>{when(x.time)} · {x.market.replace("-USD", "")}</time><div>{text(x)}</div></li>
              ))}
            </ol>
          )}
        </div>
        {me?.admin && link.token && <div className="card" style={{ marginTop: 16 }}><FeedbackInbox t={t} lang={lang} token={link.token} /></div>}
      </div>
      {editing && (
        <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) setEditing(null); }}>
          <div className="dialog dialog-wide" role="dialog" aria-modal="true" aria-labelledby="av-edit-title">
            <h2 id="av-edit-title">{t.avatar.edit}</h2>
            <AvatarEditor t={t} lang={lang} value={editing} onChange={setEditing} idPrefix="dash-av" />
            {error && <Alert kind="err">{error}</Alert>}
            <div className="actions">
              <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => act("look", editing)} disabled={!!busy}>
                {busy === "look" ? d.signToConfirm : t.avatar.save}
              </button>
              <button type="button" className="btn btn-ghost btn-lg btn-block" onClick={() => setEditing(null)} disabled={!!busy}>{t.avatar.cancel}</button>
            </div>
          </div>
        </div>
      )}
      {persona && (
        <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) setPersona(null); }}>
          <div className="dialog dialog-wide" role="dialog" aria-modal="true" aria-labelledby="pp-edit-title">
            <h2 id="pp-edit-title">{t.persona.edit}</h2>
            <p className="dialog-sub">{t.persona.sub}</p>
            <PersonaPicker t={t} lang={lang} value={persona} onChange={setPersona} look={look} idPrefix="dash-pp" />
            {error && <Alert kind="err">{error}</Alert>}
            <div className="actions">
              <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => act("look", undefined, undefined, persona)} disabled={!!busy}>
                {busy === "look" ? d.signToConfirm : t.avatar.save}
              </button>
              <button type="button" className="btn btn-ghost btn-lg btn-block" onClick={() => setPersona(null)} disabled={!!busy}>{t.avatar.cancel}</button>
            </div>
          </div>
        </div>
      )}
      {copyEdit && me?.copy && (
        <CopyPlanDialog t={t} lang={lang} initial={copyEdit} accounts={me.copy.status?.accounts} busy={busy === "copy"} error={error}
                        onSign={(x) => act("copy", undefined, undefined, undefined, x)} onCancel={() => setCopyEdit(null)} />
      )}
      {plan && (
        <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) setPlan(null); }}>
          <div className="dialog dialog-wide" role="dialog" aria-modal="true" aria-labelledby="plan-edit-title">
            <h2 id="plan-edit-title">{S.editTitle}</h2>
            <StrategyPicker t={t} lang={lang} info={info} value={plan} onChange={setPlan} idPrefix="dash-plan" />
            {liveOn && <p className="field-hint">{S.restart}</p>}
            {error && <Alert kind="err">{error}</Alert>}
            <div className="actions sticky">
              <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => act("settings", undefined, plan)}
                      disabled={!!busy || !plan.markets.length}>
                {busy === "settings" ? d.signToConfirm : S.save}
              </button>
              <button type="button" className="btn btn-ghost btn-lg btn-block" onClick={() => setPlan(null)} disabled={!!busy}>{t.avatar.cancel}</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
