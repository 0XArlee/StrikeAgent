import { useEffect, useRef, useState } from "react";
import { ApiError, api, messageHex, type AppInfo, type Challenge, type Linked, type RiskPreset } from "../api";
import { shortAddr } from "../cardano/bech32";
import { KNOWN_WALLETS, WalletError, connect, knownIcon, signMessage, watchWallets, type Connected, type DetectedWallet } from "../cardano/wallets";
import { fmt, type Dict, type Lang } from "../i18n";
import type { Look } from "../city/look";
import type { Persona } from "../city/persona";
import { lookFor } from "../city/sprites";
import { MIN_BALANCE, strategyId, strategyName, type StrategyId } from "../strategies";
import { AvatarEditor } from "./AvatarEditor";
import { MeetCard } from "./MeetCard";
import { PersonaPicker } from "./PersonaPicker";
import { StrategyPicker, defaultPlan, type Plan } from "./StrategyPicker";
import { Alert, CardanoLogo, Icon, Mark, WalletIcon } from "./ui";

// wallet -> character and name -> personality and trade in the city -> strategy, markets and risk -> review and sign ->
// done (meet your agent); a wallet that already has an agent goes wallet -> sign in -> My agent
type Step = "wallets" | "connecting" | "signin" | "avatar" | "persona" | "plan" | "review" | "preparing" | "signing" | "verifying" | "done";

export interface LinkResult extends Linked {
  address: string; walletName: string; risk: RiskPreset; markets: string[]; name?: string; public?: boolean; look?: Look; persona?: Persona;
  strategy?: StrategyId;
}

interface Props {
  t: Dict; lang: Lang; info: AppInfo; onClose: () => void; onLinked: (r: LinkResult) => void; onOpenDashboard: () => void;
  fromCity?: boolean;                    // opened from EdgeCraft-StrikeCity: showing the agent there is the point
  onOpenCity?: (agentId: string) => void;
  strategy?: StrategyId;                 // picked in the catalog: the sign-up starts with it
}

// same rule as the server (web/server/util.ts cleanName), minus the reserved words it also checks
const NAME_RE = /^[\p{L}\p{N} ._·-]{2,24}$/u;

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function ConnectModal({ t, lang, info, onClose, onLinked, onOpenDashboard, fromCity, onOpenCity, strategy }: Props) {
  const m = t.modal;
  const P = t.paper;
  const A = t.avatar;
  const S = t.strategies;
  const L = t.live;
  // where builder connect is offered, creating the agent connects it to the owner's Strike account (one signature);
  // during the invite-only phase the site says per wallet, right after it connects
  const [invited, setInvited] = useState(false);
  const live = !!info.live?.enabled || invited;
  const envName = info.live?.env ?? info.env;
  const loc = lang === "es" ? "es-ES" : "en-US";
  const feePct = ((info.live?.feeBps ?? info.feeBps) / 10_000).toLocaleString(loc, { style: "percent", minimumFractionDigits: 2 });
  const [step, setStep] = useState<Step>("wallets");
  const [wallets, setWallets] = useState<DetectedWallet[]>([]);
  const [conn, setConn] = useState<Connected | null>(null);
  const [plan, setPlan] = useState<Plan>(() => defaultPlan(info, strategy));
  const [ack, setAck] = useState(false);
  const [name, setName] = useState("");
  const [pub, setPub] = useState(!!fromCity);
  const [nameErr, setNameErr] = useState("");
  const [look, setLook] = useState<Look | null>(null);
  const [persona, setPersona] = useState<Persona>({ v: 1, temper: "stoic", job: "chartist" });
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [linked, setLinked] = useState<Linked | null>(null);
  const [error, setError] = useState("");
  const [picking, setPicking] = useState("");
  const [prep, setPrep] = useState(false);   // asking the server for the sign-in message
  const [announce, setAnnounce] = useState("");
  const dialog = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<Element | null>(document.activeElement);

  useEffect(() => watchWallets(setWallets), []);

  // focus management: first focusable on open and on each step; Esc closes; Tab cycles inside
  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    const heading = el.querySelector<HTMLElement>("[data-autofocus]") ?? el.querySelector<HTMLElement>(FOCUSABLE);
    heading?.focus();
  }, [step]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !["signing", "verifying"].includes(step)) { e.preventDefault(); onClose(); }
      if (e.key !== "Tab" || !dialog.current) return;
      const f = [...dialog.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((x) => x.offsetParent !== null);
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, step]);
  // only when the dialog closes: the page stops scrolling under it while open, and focus goes back to its opener (a
  // new onClose from a re-render used to send focus back to the opener while the dialog was still open)
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
      (returnFocus.current as HTMLElement | null)?.focus?.();
    };
  }, []);

  const say = (s: string) => setAnnounce(s);
  const go = (s: Step, announce: string) => { setError(""); setStep(s); say(announce); };

  function walletErrorText(e: unknown): string {
    if (e instanceof WalletError) {
      if (e.kind === "refused") return m.errRefused;
      if (e.kind === "declined") return m.errDeclined;
      if (e.kind === "no_address") return m.errNoAddress;
      return e.message;
    }
    if (e instanceof ApiError) return fmt(m.errServer, { msg: e.message });
    return String((e as Error)?.message ?? e);
  }

  async function pickWallet(w: DetectedWallet) {
    setError("");
    setPicking(w.name);
    setStep("connecting");
    say(fmt(m.connecting, { wallet: w.name }));
    try {
      const c = await connect(w);
      const want = info.env === "mainnet" ? 1 : 0;
      if (c.networkId !== want) {
        setError(fmt(m.errNetwork, { got: c.networkId === 1 ? "Mainnet" : "Testnet", want: info.env === "mainnet" ? "Mainnet" : "Testnet (Preprod)" }));
        setStep("wallets");
        return;
      }
      setConn(c);
      say(m.signinChecking);
      const st = await api.walletStatus(c.address).catch(() => null);   // unknown: the server still routes it right
      setInvited(!!st?.live);
      if (st?.agent) { setStep("signin"); say(m.signinTitle); return; }
      setName((cur) => cur || `Agent ${c.address.slice(-4).toUpperCase()}`);
      setLook((cur) => cur ?? lookFor(c.address));   // every wallet starts from its own random look
      setStep("avatar");
      say(A.title);
    } catch (e) {
      setError(walletErrorText(e));
      setStep("wallets");
    }
  }

  const cleanName = () => name.replace(/\s+/g, " ").trim();
  const toPersona = () => {
    if (!NAME_RE.test(cleanName())) { setNameErr(P.errName); document.getElementById("cm-name")?.focus(); return; }
    setNameErr("");
    go("persona", t.persona.title);
  };
  const toReview = () => {
    if (!plan.markets.length) { setError(m.minMarkets); return; }
    go("review", P.review);
  };

  // an existing agent: open it as it is (its settings come from the server), straight into My agent
  async function finishSignIn(l: Linked, c: Connected) {
    let a = l.agent;
    if (!a) {
      const x = await api.me(l);
      a = { name: x.name ?? "", markets: x.markets, risk: x.risk, public: !!x.public, look: x.look ?? null,
        strategy: strategyId(x.strategy) };
    }
    onLinked({ ...l, address: c.address, walletName: c.wallet.name, risk: a.risk, markets: a.markets, strategy: a.strategy, name: a.name,
      public: a.public, look: a.look ?? undefined });
    onOpenDashboard();
  }

  async function signIn() {
    if (!conn) return;
    setError("");
    setPrep(true);
    say(m.preparing);
    try {
      const ch = await api.signIn(conn.address);
      setPrep(false);
      setChallenge(ch);
      setStep("signing");
      say(fmt(m.signing, { wallet: conn.wallet.name }));
      const sig = await signMessage(conn, messageHex(ch.messageToSign));
      if (Date.now() > ch.expiresAt) throw new Error(m.errExpired);
      setStep("verifying");
      say(P.verifying);
      await finishSignIn(await api.verify(ch.sessionId, sig), conn);
    } catch (e) {
      setPrep(false);
      setError(walletErrorText(e));
      setStep("signin");
    }
  }

  async function authorize() {
    if (!conn) return;
    const nm = cleanName();
    if (!NAME_RE.test(nm)) { setNameErr(P.errName); setStep("avatar"); return; }
    setNameErr("");
    setError("");
    setStep("preparing");
    say(m.preparing);
    try {
      const ch = await api.challenge(conn.address, { risk: plan.risk, markets: plan.markets, strategy: plan.strategy, name: nm, public: pub,
        look: look ?? undefined, persona });
      setChallenge(ch);
      setStep("signing");
      say(fmt(m.signing, { wallet: conn.wallet.name }));
      const sig = await signMessage(conn, messageHex(ch.messageToSign));
      if (Date.now() > ch.expiresAt) throw new Error(m.errExpired);
      setStep("verifying");
      say(ch.live ? L.verifying : P.verifying);
      const l = await api.verify(ch.sessionId, sig);
      if (l.signin) { await finishSignIn(l, conn); return; }   // it had an agent after all: nothing was changed
      setLinked(l);
      setStep("done");
      say(l.mode === "live" ? fmt(L.starting, { env: envName }) : P.done);
      onLinked({ ...l, address: conn.address, walletName: conn.wallet.name, risk: plan.risk, markets: plan.markets, strategy: plan.strategy,
        name: nm, public: pub, look: look ?? undefined, persona });
    } catch (e) {
      // a name the server refuses (reserved, invalid) is fixed on the character step, next to the field
      if (e instanceof ApiError && e.status === 400 && /name/i.test(e.message)) {
        setNameErr(e.message);
        setStep("avatar");
        return;
      }
      setError(walletErrorText(e));
      setStep("review");
    }
  }

  const missing = KNOWN_WALLETS.filter((k) => !wallets.some((w) => w.name.toLowerCase().startsWith(k.name.toLowerCase().slice(0, 4))));
  const busy = step === "connecting" || step === "preparing" || step === "signing" || step === "verifying" || prep;
  const marketList = plan.markets.map((x) => x.replace("-USD", "")).join(" · ");
  const riskText = `${m.riskNames[plan.risk]} · ${info.riskPresets[plan.risk].toLocaleString(loc)}%`;
  const nav = (back: Step) => (
    <div className="dialog-nav">
      <button type="button" className="back" onClick={() => go(back, "")} disabled={step === "preparing"}>
        <Icon.back /> {m.back}
      </button>
      <span className="chain-chip"><CardanoLogo /> Cardano</span>
    </div>
  );

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className={`dialog${step === "avatar" || step === "persona" || step === "plan" || step === "done" ? " dialog-wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby="cm-title" aria-describedby="cm-desc" ref={dialog} aria-busy={busy}>
        <button type="button" className="icon-btn dialog-close" onClick={onClose} aria-label={m.close} disabled={step === "signing" || step === "verifying"}>
          <Icon.close />
        </button>
        <div className="dialog-brand"><Mark size={48} /></div>
        <p className="sr-only" aria-live="polite">{announce}</p>

        {step === "wallets" && (
          <>
            <div className="dialog-nav">
              <h2 id="cm-title" tabIndex={-1} data-autofocus>{m.titleChain}</h2>
              <span className="chain-chip"><CardanoLogo /> Cardano</span>
            </div>
            <p id="cm-desc" className="dialog-sub">{wallets.length ? m.chooseWallet : m.noWallets}</p>
            {error && <Alert kind="err">{error}</Alert>}
            {wallets.length > 0 && (
              <ul className="list" aria-label="Cardano wallets">
                {wallets.map((w) => (
                  <li key={w.key}>
                    <button type="button" className="list-btn" onClick={() => pickWallet(w)}>
                      <WalletIcon name={w.name} icon={w.icon || knownIcon(w.name)} />
                      <span className="grow">{w.name}</span>
                      <span className="tag tag-ok">{m.detected}</span>
                      <Icon.chevron />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="divider">{wallets.length ? m.otherWallets : m.noWalletsHelp}</div>
            <ul className="list" style={{ marginTop: 10 }}>
              {missing.map((k) => (
                <li key={k.id}>
                  <a className="list-btn" href={k.url} target="_blank" rel="noopener noreferrer">
                    <WalletIcon name={k.name} icon={k.icon} />
                    <span className="grow">{k.name}</span>
                    <span className="tag tag-off">{m.install}</span>
                    <Icon.external />
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}

        {step === "connecting" && (
          <div className="center" role="status">
            <div className="spinner" aria-hidden="true" />
            <h2 id="cm-title" tabIndex={-1} data-autofocus>{fmt(m.connecting, { wallet: picking })}</h2>
            <p id="cm-desc" className="dialog-sub">{fmt(m.connectingHelp, { wallet: picking })}</p>
          </div>
        )}

        {step === "signin" && conn && (
          <>
            {nav("wallets")}
            <h2 id="cm-title" tabIndex={-1} data-autofocus>{m.signinTitle}</h2>
            <p id="cm-desc" className="dialog-sub">{m.signinSub}</p>
            <div className="box">
              <div className="kv"><span>{m.wallet}</span><span>{conn.wallet.name}</span></div>
              <div className="kv"><span>{m.address}</span><span className="mono" title={conn.address}>{shortAddr(conn.address, 12, 8)}</span></div>
              <div className="kv"><span>{m.network}</span><span>{info.env === "mainnet" ? "Mainnet" : "Testnet"}</span></div>
            </div>
            {error && <Alert kind="err">{error}</Alert>}
            <div className="actions">
              <button type="button" className="btn btn-primary btn-lg btn-block" onClick={signIn} disabled={prep}>
                {prep ? m.preparing : fmt(m.signinBtn, { wallet: conn.wallet.name })}
              </button>
            </div>
          </>
        )}

        {step === "avatar" && conn && look && (
          <>
            {nav("wallets")}
            <h2 id="cm-title" tabIndex={-1} data-autofocus>{A.title}</h2>
            <p id="cm-desc" className="dialog-sub">{A.sub}</p>
            <div className="field">
              <label htmlFor="cm-name">{P.name}</label>
              <input id="cm-name" type="text" value={name} maxLength={24} autoComplete="off" spellCheck={false}
                     aria-invalid={!!nameErr || undefined} aria-describedby="cm-name-hint"
                     onChange={(e) => { setName(e.target.value); setNameErr(""); }} />
              <p id="cm-name-hint" className={nameErr ? "field-err" : "field-hint"}>{nameErr || P.nameHint}</p>
            </div>
            <AvatarEditor t={t} lang={lang} value={look} onChange={setLook} idPrefix="cm-av" />
            <div className="actions sticky">
              <button type="button" className="btn btn-primary btn-lg btn-block" onClick={toPersona}>{A.next}</button>
            </div>
          </>
        )}

        {step === "persona" && conn && (
          <>
            {nav("avatar")}
            <h2 id="cm-title" tabIndex={-1} data-autofocus>{t.persona.title}</h2>
            <p id="cm-desc" className="dialog-sub">{t.persona.sub}</p>
            <PersonaPicker t={t} lang={lang} value={persona} onChange={setPersona} look={look} idPrefix="cm-pp" />
            <div className="actions sticky">
              <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => go("plan", S.title)}>{t.persona.next}</button>
            </div>
          </>
        )}

        {step === "plan" && conn && (
          <>
            {nav("persona")}
            <h2 id="cm-title" tabIndex={-1} data-autofocus>{S.title}</h2>
            <p id="cm-desc" className="dialog-sub">{S.sub}</p>
            <StrategyPicker t={t} lang={lang} info={info} value={plan} onChange={(p) => { setPlan(p); setError(""); }} idPrefix="cm" titled={false} />
            <label className="check check-public">
              <input type="checkbox" checked={pub} onChange={(e) => setPub(e.target.checked)} aria-describedby="cm-pub-hint" />
              <span><strong>{P.public}</strong><small id="cm-pub-hint">{P.publicHint}</small></span>
            </label>
            {error && <Alert kind="err">{error}</Alert>}
            <div className="actions sticky">
              <button type="button" className="btn btn-primary btn-lg btn-block" onClick={toReview} disabled={!plan.markets.length}>{S.next}</button>
            </div>
          </>
        )}

        {(step === "review" || step === "preparing") && conn && (
          <>
            {nav("plan")}
            <h2 id="cm-title" tabIndex={-1} data-autofocus>{P.review}</h2>
            <p id="cm-desc" className="dialog-sub">{m.reviewSub}</p>
            {live
              ? <Alert kind="info">{fmt(L.note, { env: envName })}{envName === "testnet" && <> {L.testnet}</>}</Alert>
              : <Alert kind="info">{P.note}</Alert>}
            {live && <Alert kind="warn">{fmt(t.balance.review, { risk: m.riskNames[plan.risk].toLowerCase(), min: `${MIN_BALANCE[plan.risk]} $` })}</Alert>}
            <div className="box">
              <div className="kv"><span>{m.wallet}</span><span>{conn.wallet.name}</span></div>
              <div className="kv"><span>{m.address}</span><span className="mono" title={conn.address}>{shortAddr(conn.address, 12, 8)}</span></div>
              <div className="kv"><span>{m.network}</span><span>{info.env === "mainnet" ? "Mainnet" : "Testnet"}</span></div>
              <div className="kv"><span>{P.mode}</span><span>{live ? fmt(L.mode, { env: envName }) : P.modeVal}</span></div>
              {live && <div className="kv"><span>{L.fee}</span><span className="num">{feePct}</span></div>}
              <div className="kv"><span>{S.label}</span><span>{strategyName(plan.strategy)}</span></div>
              <div className="kv"><span>{m.markets}</span><span>{marketList}</span></div>
              <div className="kv"><span>{m.risk}</span><span>{riskText}</span></div>
              <div className="kv"><span>{P.city}</span><span>{pub ? P.shown : P.privateLbl}</span></div>
              <div className="kv"><span>{t.persona.temper}</span><span>{t.persona.tempers[persona.temper].name} · {t.persona.jobs[persona.job].name}</span></div>
            </div>
            <div className="box">
              <div className="box-title">{m.canDo}</div>
              {(live ? L.canDoList : P.canDoList).map((x) => <div key={x} className="can yes"><Icon.check size={16} /><span>{fmt(x, { env: envName, fee: feePct })}</span></div>)}
              <div className="box-title" style={{ marginTop: 8 }}>{m.cannotDo}</div>
              {(live ? L.cannotDoList : P.cannotDoList).map((x) => <div key={x} className="can no"><Icon.close /><span>{x}</span></div>)}
            </div>
            <label className="check check-ack">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              <span>{live ? L.ack : P.ack}</span>
            </label>
            {error && <Alert kind="err">{error}</Alert>}
            <div className="actions sticky">
              <button type="button" className="btn btn-primary btn-lg btn-block" onClick={authorize} disabled={!ack || step === "preparing"}>
                {step === "preparing" ? m.preparing : fmt(P.sign, { wallet: conn.wallet.name })}
              </button>
            </div>
          </>
        )}

        {(step === "signing" || step === "verifying") && conn && (
          <div role="status">
            <div className="center">
              <div className="spinner" aria-hidden="true" />
              <h2 id="cm-title" tabIndex={-1} data-autofocus>{step === "signing" ? fmt(m.signing, { wallet: conn.wallet.name }) : challenge?.live ? L.verifying : P.verifying}</h2>
              <p id="cm-desc" className="dialog-sub">{step === "signing" ? (challenge?.live ? fmt(L.signingHelp, { code: info.live?.code ?? "" }) : P.signingHelp) : ""}</p>
            </div>
            {challenge && (
              <div className="box">
                <div className="box-title">{challenge.live ? L.message : P.message}</div>
                <div className="message" tabIndex={0}>{challenge.messageToSign}</div>
              </div>
            )}
          </div>
        )}

        {step === "done" && linked && conn && (
          <div>
            <div className="success-mark" aria-hidden="true"><Icon.check size={26} /></div>
            <div className="center">
              <h2 id="cm-title" tabIndex={-1} data-autofocus>{linked.mode === "live" ? fmt(L.starting, { env: envName }) : P.done}</h2>
              <p id="cm-desc" className="dialog-sub">{linked.mode === "live" ? L.startingSub : P.doneSub}</p>
            </div>
            <MeetCard t={t} lang={lang} info={{
              name: cleanName(), look, persona, citizen: linked.citizen ?? null, strategy: strategyName(plan.strategy), markets: plan.markets,
              risk: `${m.risk}: ${riskText}`,
              url: pub ? `${location.origin}/#/city?agent=${encodeURIComponent(linked.cityId ?? linked.accountId)}` : location.origin,
            }} />
            <div className="box">
              <div className="kv"><span>{P.city}</span><span>{pub ? P.shown : P.privateLbl}</span></div>
              {linked.mode === "live" && <div className="kv"><span>{L.fee}</span><span className="num">{feePct}</span></div>}
            </div>
            {!pub && <p className="note">{P.hidden}</p>}
            <div className="actions">
              {pub && onOpenCity && (
                <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => onOpenCity(linked.cityId ?? linked.accountId)}>{P.seeCity}</button>
              )}
              <button type="button" className={`btn btn-lg btn-block ${pub && onOpenCity ? "btn-ghost" : "btn-primary"}`} onClick={onOpenDashboard}>{m.openDashboard}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
