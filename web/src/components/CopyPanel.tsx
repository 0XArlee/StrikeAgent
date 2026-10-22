// Copy with your agent, in My agent: how the copy goes (whom it copies, since when, its result, why, what the agent did)
// and the plan its owner signs with their wallet: one trader or the agent's choice by the owner's rules (pilot), how
// much, the stop-loss, the leverage, markets never opened, until when, and the pause on the News Tower's security alarm.
// The agents' host carries it out on Strike's copy trading (smartflow/copytrade/pilot.py); Strike City never holds money.
import { useMemo, useState } from "react";
import type { CopyPlan, CopyStatus, CopyView } from "../api";
import { traderName, useCopy, type CopyDoc, type Trader } from "../city/copy";
import { fmt, type Dict, type Lang } from "../i18n";
import { Alert } from "./ui";

const EXCLUDABLE = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "HYPE", "SP500"];
const REVIEWS = [6, 12, 24, 72, 168];
const MIN_COPY = 20;   // Strike's minimum copy amount and margin per entry

export const defaultPlan = (mode: "manual" | "pilot", lead?: Trader | null): CopyPlan => {
  const amount = Math.max(50, Math.ceil((lead?.recommended ?? 0) / 10) * 10);
  return {
    mode, lead: lead?.id ?? null, platform: lead?.platform ?? null, sizing: { kind: "ratio", amount },
    stopLoss: Math.round(amount * 0.2), leverage: 3, excluded: [], until: null, alarmPause: true,
    pilot: mode === "pilot" ? { minScore: 70, platforms: ["strike", "hyperliquid"], review: 24, maxSwitches: 2 } : null,
  };
};

/** The traders the pilot may choose now (the host's rule, smartflow/copytrade/pilot.py candidates). */
export function pilotChoice(doc: CopyDoc | null, plan: CopyPlan): Trader | null {
  if (!doc || !plan.pilot) return null;
  const budget = plan.sizing.kind === "ratio" ? plan.sizing.amount : plan.sizing.funding;
  return doc.traders.filter((t) => plan.pilot!.platforms.includes(t.platform) && (t.city ?? 0) >= plan.pilot!.minScore
    && (t.direction == null || t.direction === "copy") && !(t.recommended && t.recommended > budget)
    && !(t.copiers.n >= 3 && t.copiers.pnl < 0)).sort((a, b) => (b.city ?? 0) - (a.city ?? 0))[0] ?? null;
}

function invalid(p: CopyPlan): string | null {
  const budget = p.sizing.kind === "ratio" ? p.sizing.amount : p.sizing.funding;
  if (p.sizing.kind === "ratio" && !(p.sizing.amount >= MIN_COPY)) return "amount";
  if (p.sizing.kind === "fixed" && !(p.sizing.margin >= MIN_COPY && p.sizing.funding >= p.sizing.margin)) return "margin";
  if (!(p.stopLoss >= 1 && p.stopLoss <= budget)) return "stop";
  if (p.mode === "manual" && !p.lead) return "lead";
  if (p.mode === "pilot" && !p.pilot?.platforms.length) return "platforms";
  return null;
}

// ------------------------------------------------------------------ My agent's section
export function CopySection({ t, lang, view, liveOn, busy, onEdit, onStop }: { t: Dict; lang: Lang; view: CopyView | undefined; liveOn: boolean;
  busy: boolean; onEdit: (p: CopyPlan) => void; onStop: () => void }) {
  const C = t.copyPlan, loc = lang === "es" ? "es-ES" : "en-US";
  const doc = useCopy(true);
  const d = doc && typeof doc === "object" ? doc : null;
  const plan = view?.plan ?? null, st: CopyStatus | null = view?.status ?? null;
  const on = !!plan && plan.mode !== "off";
  const usd = (v: number | null | undefined, sign = false) => v == null ? "—"
    : `${sign && v > 0 ? "+" : ""}${v.toLocaleString(loc, { style: "currency", currency: "USD" })}`;
  const when = (ms: number) => new Date(ms).toLocaleString(loc, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const name = (id?: string | null, platform?: string | null) => id ? traderName({ id, platform: platform === "hyperliquid" ? "hyperliquid" : "strike" }) : "—";
  const applying = !!plan && (st?.version ?? 0) < (view?.version ?? 0);
  const state = applying ? "starting" : st?.state ?? (on ? "waiting" : "off");
  const lead = st?.lead && d ? d.traders.find((x) => x.id.toLowerCase() === st.lead!.toLowerCase()) : undefined;
  return (
    <div className="card copy-card" style={{ marginTop: 16 }}>
      <div className="copy-head">
        <h3>{C.title}</h3>
        {on && <span className={`copy-state ${state}`}>{C.states[state]}</span>}
      </div>
      <p className="field-hint">{C.lead}</p>
      {!liveOn ? <Alert kind="info">{C.notLive}</Alert> : !on ? (
        <div className="actions-row copy-actions">
          <button type="button" className="btn btn-primary" onClick={() => onEdit(defaultPlan("pilot"))} disabled={busy}>{C.choosePilot}</button>
          <a className="btn btn-ghost" href="#/city?arena">{C.chooseArena}</a>
        </div>
      ) : (
        <>
          {applying && <p className="copy-why" role="status">{C.applying}</p>}
          {!applying && st?.why && C.why[st.why] && <p className="copy-why">{C.why[st.why]}</p>}
          <dl className="rows">
            <div className="row"><dt>{C.who}</dt><dd>{st?.lead ? <a href={`#/city?lead=${st.lead}`}>{name(st.lead, st.platform)}</a> : "—"}
              <span className="faint"> · {C.modes[plan!.mode]}</span>{lead?.city != null && <span className="faint"> · {Math.round(lead.city)}</span>}</dd></div>
            {st?.since && <div className="row"><dt>{C.since}</dt><dd>{when(st.since)}</dd></div>}
            {st?.copy && <div className="row"><dt>{C.pnl}</dt><dd className={(st.copy.pnl ?? 0) >= 0 ? "pos" : "neg"}>{usd(st.copy.pnl, true)}</dd></div>}
            {st?.copy && <div className="row"><dt>{C.margin}</dt><dd>{usd(st.copy.total_margin)}</dd></div>}
            <div className="row"><dt>{C.stopLoss}</dt><dd>{usd(plan!.stopLoss)}</dd></div>
            {st?.subAccount && <div className="row"><dt>{C.subAccount}</dt><dd className="mono">{st.subAccount.slice(0, 8)}…</dd></div>}
            {plan!.mode === "pilot" && st?.reviewAt && <div className="row"><dt>{C.nextReview}</dt><dd>{when(st.reviewAt)}</dd></div>}
          </dl>
          {st?.error && <Alert kind="warn">{st.error}</Alert>}
          {!!st?.log?.length && (
            <>
              <h4 className="copy-log-title">{C.log}</h4>
              <ol className="timeline copy-log">
                {[...st.log].reverse().slice(0, 6).map((x, i) => (
                  <li key={i}><time dateTime={new Date(x.t).toISOString()}>{when(x.t)}</time>
                    <div>{fmt(C.logKinds[x.kind] ?? x.kind, { lead: name(x.lead, x.lead?.startsWith("0x") ? "hyperliquid" : "strike"),
                      available: usd(x.available ?? null) })}
                      {x.reason && C.why[x.reason] ? <span className="faint"> · {C.why[x.reason]}</span> : null}
                      {x.text ? <span className="faint"> · {x.text}</span> : null}</div></li>
                ))}
              </ol>
            </>
          )}
          <div className="actions-row copy-actions">
            <button type="button" className="btn btn-primary" onClick={() => onEdit(plan!)} disabled={busy}>{C.edit}</button>
            <button type="button" className="btn btn-ghost" onClick={onStop} disabled={busy}>{C.stop}</button>
          </div>
          <p className="field-hint">{C.moneyNote}</p>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ the plan
export function CopyPlanDialog({ t, lang, initial, busy, error, onSign, onCancel }: { t: Dict; lang: Lang; initial: CopyPlan; busy: boolean;
  error: string; onSign: (p: CopyPlan) => void; onCancel: () => void }) {
  const C = t.copyPlan, D = C.dialog, loc = lang === "es" ? "es-ES" : "en-US";
  const doc = useCopy(true);
  const d = doc && typeof doc === "object" ? doc : null;
  const [p, setP] = useState<CopyPlan>(initial);
  const [ack, setAck] = useState(false);
  const set = (x: Partial<CopyPlan>) => setP((v) => ({ ...v, ...x }));
  const lead = d && p.lead ? d.traders.find((x) => x.id.toLowerCase() === p.lead!.toLowerCase()) : undefined;
  const pick = useMemo(() => (p.mode === "pilot" ? pilotChoice(d, p) : null), [d, p]);
  const bad = invalid(p);
  const money = (v: number) => `${v.toLocaleString(loc, { maximumFractionDigits: 0 })} $`;
  const numIn = (id: string, label: string, value: number, onChange: (v: number) => void, hint?: string) => (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} type="number" inputMode="decimal" min={0} step={1} value={Number.isFinite(value) ? value : ""}
             onChange={(e) => onChange(Number(e.target.value))} aria-describedby={hint ? `${id}-hint` : undefined} />
      {hint && <p id={`${id}-hint`} className="field-hint">{hint}</p>}
    </div>
  );
  const traders = d ? d.traders.slice(0, 30) : [];
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onCancel(); }}>
      <div className="dialog dialog-wide copy-dialog" role="dialog" aria-modal="true" aria-labelledby="cp-plan-title">
        <h2 id="cp-plan-title">{D.title}</h2>
        <p className="dialog-sub">{D.sub}</p>
        <fieldset>
          <legend>{D.mode}</legend>
          <div className="seg seg-2">
            {(["manual", "pilot"] as const).map((m) => (
              <label key={m}>
                <input type="radio" name="cp-mode" checked={p.mode === m} onChange={() => set({ mode: m, pilot: m === "pilot" ? p.pilot ?? defaultPlan("pilot").pilot : null })} />
                <span>{C.modes[m]}</span>
              </label>
            ))}
          </div>
          {p.mode === "manual" ? (
            <div className="field">
              <label htmlFor="cp-lead">{D.pickTrader}</label>
              <select id="cp-lead" value={p.lead ?? ""} onChange={(e) => {
                const x = traders.find((y) => y.id === e.target.value);
                set({ lead: x?.id ?? null, platform: x?.platform ?? null });
              }}>
                {!p.lead && <option value="">—</option>}
                {p.lead && !traders.some((x) => x.id === p.lead) && <option value={p.lead}>{traderName({ id: p.lead, platform: p.platform ?? "strike" })}</option>}
                {traders.map((x) => <option key={x.id} value={x.id}>{traderName(x)} · {x.platform === "strike" ? "Strike" : "Hyperliquid"} · {Math.round(x.city ?? 0)}</option>)}
              </select>
              {lead?.recommended && <p className="field-hint">{D.rec(money(lead.recommended))}</p>}
            </div>
          ) : p.pilot && (
            <>
              <div className="copy-grid">
                <div className="field">
                  <label htmlFor="cp-min">{D.minScore}</label>
                  <select id="cp-min" value={p.pilot.minScore} onChange={(e) => set({ pilot: { ...p.pilot!, minScore: Number(e.target.value) } })}>
                    {[50, 60, 70, 75, 80].map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="cp-review">{D.review}</label>
                  <select id="cp-review" value={p.pilot.review} onChange={(e) => set({ pilot: { ...p.pilot!, review: Number(e.target.value) } })}>
                    {REVIEWS.map((v) => <option key={v} value={v}>{D.hours(v)}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="cp-sw">{D.maxSwitches}</label>
                  <select id="cp-sw" value={p.pilot.maxSwitches} onChange={(e) => set({ pilot: { ...p.pilot!, maxSwitches: Number(e.target.value) } })}>
                    {[0, 1, 2, 3, 5].map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                </div>
              </div>
              <p className="field-hint copy-sub">{D.platforms}</p>
              <div className="chips">
                {(["strike", "hyperliquid"] as const).map((x) => (
                  <label key={x}><input type="checkbox" checked={p.pilot!.platforms.includes(x)}
                    onChange={(e) => set({ pilot: { ...p.pilot!, platforms: e.target.checked ? [...p.pilot!.platforms, x] : p.pilot!.platforms.filter((y) => y !== x) } })} />
                    <span>{x === "strike" ? "Strike" : "Hyperliquid"}</span></label>
                ))}
              </div>
              <p className="copy-pick" role="status">{pick ? D.wouldPick(traderName(pick), String(Math.round(pick.city ?? 0))) : d ? D.wouldNone : ""}</p>
            </>
          )}
        </fieldset>
        <fieldset>
          <legend>{D.sizing}</legend>
          <div className="seg seg-2">
            {(["ratio", "fixed"] as const).map((k) => (
              <label key={k}>
                <input type="radio" name="cp-kind" checked={p.sizing.kind === k} onChange={() => set({ sizing: k === "ratio" ? { kind: "ratio", amount: 50 } : { kind: "fixed", margin: 20, funding: 100 } })} />
                <span>{k === "ratio" ? D.ratio : D.fixed}</span>
              </label>
            ))}
          </div>
          {p.sizing.kind === "ratio"
            ? numIn("cp-amount", D.amount, p.sizing.amount, (v) => set({ sizing: { kind: "ratio", amount: v } }), D.ratioHint)
            : <div className="copy-grid">
                {numIn("cp-margin", D.margin, p.sizing.margin, (v) => set({ sizing: { ...(p.sizing as { kind: "fixed"; margin: number; funding: number }), margin: v } }))}
                {numIn("cp-funding", D.funding, p.sizing.funding, (v) => set({ sizing: { ...(p.sizing as { kind: "fixed"; margin: number; funding: number }), funding: v } }), D.fixedHint)}
              </div>}
          <div className="copy-grid">
            {numIn("cp-stop", D.stopLoss, p.stopLoss, (v) => set({ stopLoss: v }), D.stopHint)}
            <div className="field">
              <label htmlFor="cp-lev">{D.leverage}</label>
              <select id="cp-lev" value={p.leverage} onChange={(e) => set({ leverage: Number(e.target.value) })} aria-describedby="cp-lev-hint">
                {[1, 2, 3, 5, 10, 20].map((v) => <option key={v} value={v}>{v}x</option>)}
              </select>
              <p id="cp-lev-hint" className="field-hint">{D.leverageHint}</p>
            </div>
          </div>
          <p className="field-hint copy-sub">{D.excluded}</p>
          <div className="chips">
            {EXCLUDABLE.map((m) => {
              const sym = `${m}-USD`;
              return <label key={m}><input type="checkbox" checked={p.excluded.includes(sym)}
                onChange={(e) => set({ excluded: e.target.checked ? [...p.excluded, sym] : p.excluded.filter((y) => y !== sym) })} /><span>{m}</span></label>;
            })}
          </div>
        </fieldset>
        <fieldset>
          <legend>{D.when}</legend>
          <div className="field">
            <label htmlFor="cp-until">{D.until}</label>
            <select id="cp-until" value={p.until ? "keep" : "none"} onChange={(e) => {
              const v = e.target.value;
              set({ until: v === "none" ? null : v === "keep" ? p.until : Date.now() + Number(v) * 86_400_000 });
            }}>
              <option value="none">{D.untilNone}</option>
              {p.until && <option value="keep">{new Date(p.until).toLocaleDateString(loc)}</option>}
              {[7, 30, 90].map((n) => <option key={n} value={n}>{D.untilDays(n)}</option>)}
            </select>
          </div>
          <label className="check">
            <input type="checkbox" checked={p.alarmPause} onChange={(e) => set({ alarmPause: e.target.checked })} />
            <span>{D.alarm}</span>
          </label>
        </fieldset>
        <label className="check check-ack">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          <span>{D.ack}</span>
        </label>
        {bad && <p className="field-err" role="alert">{D.invalid[bad]}</p>}
        {error && <Alert kind="err">{error}</Alert>}
        <div className="actions sticky">
          <button type="button" className="btn btn-primary btn-lg btn-block" onClick={() => onSign(p)} disabled={busy || !!bad || !ack}>
            {busy ? t.dash.signToConfirm : D.sign}
          </button>
          <button type="button" className="btn btn-ghost btn-lg btn-block" onClick={onCancel} disabled={busy}>{D.cancel}</button>
        </div>
      </div>
    </div>
  );
}
