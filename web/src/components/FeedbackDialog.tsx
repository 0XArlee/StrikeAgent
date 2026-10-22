// The Feedback button's dialog: a subject, a message and an optional picture (chosen, or pasted with Ctrl+V), shrunk
// in the page before it is sent. Private: only the site's admins read it (web/server/feedback.ts).
import { useEffect, useRef, useState, type ClipboardEvent } from "react";
import { ApiError, api } from "../api";
import type { Dict, Lang } from "../i18n";
import { Alert, Icon } from "./ui";

const MAX_SIDE = 1600, MAX_CHARS = 1_400_000;

/** A picture as a JPEG data URL no larger than the site accepts (null: it is not a picture). */
async function shrink(file: File): Promise<string | null> {
  if (!file.type.startsWith("image/")) return null;
  const url = URL.createObjectURL(file);
  try {
    const im = await new Promise<HTMLImageElement>((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fail; i.src = url; });
    for (const [side, q] of [[MAX_SIDE, 0.85], [1200, 0.8], [900, 0.75]] as const) {
      const k = Math.min(1, side / Math.max(im.naturalWidth, im.naturalHeight));
      const c = document.createElement("canvas");
      c.width = Math.max(1, Math.round(im.naturalWidth * k)); c.height = Math.max(1, Math.round(im.naturalHeight * k));
      const g = c.getContext("2d")!;
      g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);
      g.drawImage(im, 0, 0, c.width, c.height);
      const data = c.toDataURL("image/jpeg", q);
      if (data.length <= MAX_CHARS) return data;
    }
    return "";
  } catch { return null; } finally { URL.revokeObjectURL(url); }
}

export function FeedbackDialog({ t, lang, token, onClose }: { t: Dict; lang: Lang; token?: string; onClose: () => void }) {
  const F = t.feedback;
  const ref = useRef<HTMLDialogElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    const back = document.activeElement as HTMLElement | null;
    if (!d.open) d.showModal();
    d.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    return () => { if (d.open) d.close(); back?.focus?.(); };
  }, []);

  const take = async (f: File | null | undefined) => {
    if (!f) return;
    setError("");
    const data = await shrink(f);
    if (data === null) setError(F.errImage);
    else if (!data) setError(F.errBig);
    else setImage(data);
  };
  const onPaste = (e: ClipboardEvent) => {
    const item = [...e.clipboardData.items].find((x) => x.type.startsWith("image/"));
    if (item) { e.preventDefault(); void take(item.getAsFile()); }
  };
  const send = async () => {
    if (subject.trim().length < 2) { setError(F.errSubject); return; }
    if (message.trim().length < 2) { setError(F.errMessage); return; }
    setBusy(true); setError("");
    try {
      await api.feedback({ subject: subject.trim(), message: message.trim(), image, page: location.hash || "/", lang }, token);
      setSent(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String((e as Error).message ?? e));
    } finally { setBusy(false); }
  };

  return (
    <dialog ref={ref} className="fb" aria-labelledby="fb-title" onPaste={onPaste}
            onCancel={(e) => { e.preventDefault(); if (!busy) onClose(); }} onClick={(e) => { if (e.target === ref.current && !busy) onClose(); }}>
      <div className="fb-inner">
        <div className="fb-head">
          <h2 id="fb-title" tabIndex={-1} data-autofocus={sent || undefined}>{F.title}</h2>
          <button type="button" className="icon-btn" aria-label={F.close} onClick={onClose} disabled={busy}><Icon.close /></button>
        </div>
        {sent ? (
          <div className="fb-sent" role="status">
            <div className="success-mark" aria-hidden="true"><Icon.check size={26} /></div>
            <p>{F.sent}</p>
            <button type="button" className="btn btn-primary btn-block" onClick={onClose} data-autofocus>{F.close}</button>
          </div>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); void send(); }}>
            <p className="dialog-sub">{F.sub}</p>
            <div className="field">
              <label htmlFor="fb-subject">{F.subject}</label>
              <input id="fb-subject" type="text" value={subject} maxLength={120} placeholder={F.subjectPh} required data-autofocus
                     onChange={(e) => setSubject(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="fb-message">{F.message}</label>
              <textarea id="fb-message" value={message} maxLength={4000} rows={6} placeholder={F.messagePh} required onChange={(e) => setMessage(e.target.value)} />
            </div>
            <div className="field">
              <span className="fb-label" id="fb-image-label">{F.image}</span>
              {image ? (
                <div className="fb-preview">
                  <img src={image} alt="" />
                  <button type="button" className="btn btn-ghost" onClick={() => setImage(null)}>{F.remove}</button>
                </div>
              ) : (
                <div className="fb-drop">
                  <button type="button" className="btn btn-ghost" aria-describedby="fb-image-hint" onClick={() => file.current?.click()}>
                    <Icon.image size={16} /> {F.choose}</button>
                  <span id="fb-image-hint" className="small faint">{F.imageHint}</span>
                  <input ref={file} type="file" accept="image/*" hidden onChange={(e) => { void take(e.target.files?.[0]); e.target.value = ""; }}
                         aria-labelledby="fb-image-label" />
                </div>
              )}
            </div>
            <p className="small faint fb-private"><Icon.shield /> {F.private}</p>
            {error && <Alert kind="err">{error}</Alert>}
            <div className="fb-actions">
              <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>{F.cancel}</button>
              <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? F.sending : F.send}</button>
            </div>
          </form>
        )}
      </div>
    </dialog>
  );
}

/** My agent, for the site's admins: the suggestions people sent, newest first (read every minute). */
export function FeedbackInbox({ t, lang, token }: { t: Dict; lang: Lang; token: string }) {
  const F = t.feedback;
  const [box, setBox] = useState<FeedbackInboxDoc | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const load = () => api.feedbackInbox(token).then((b) => { if (alive) { setBox(b); setError(""); } })
      .catch((e) => { if (alive) setError(e instanceof ApiError ? e.message : String(e)); });
    void load();
    const id = window.setInterval(load, 60_000);
    return () => { alive = false; window.clearInterval(id); };
  }, [token]);
  const readAll = async () => {
    if (!box) return;
    const ids = box.items.filter((x) => !x.read).map((x) => x.id);
    if (!ids.length) return;
    await api.feedbackRead(token, ids).catch(() => undefined);
    setBox({ unread: 0, items: box.items.map((x) => ({ ...x, read: true })) });
  };
  const loc = lang === "es" ? "es-ES" : "en-US";
  return (
    <section className="fb-inbox" aria-labelledby="fb-inbox-title">
      <div className="fb-inbox-head">
        <h3 id="fb-inbox-title">{F.inbox}{box && box.unread > 0 && <span className="fb-badge">{F.unread(box.unread)}</span>}</h3>
        {box && box.unread > 0 && <button type="button" className="btn btn-ghost" onClick={readAll}>{F.markRead}</button>}
      </div>
      {error && <Alert kind="err">{error}</Alert>}
      {box && !box.items.length && <p className="small muted">{F.none}</p>}
      <ul className="fb-list">
        {box?.items.map((x) => (
          <li key={x.id} className={x.read ? "" : "unread"}>
            <div className="fb-meta small faint">
              <time dateTime={new Date(x.t).toISOString()}>{new Date(x.t).toLocaleString(loc, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</time>
              <span>{x.user ? F.from(x.user.name ?? x.user.id) : F.anon}</span>
              {x.page && <span>{F.page}: <span className="mono">{x.page}</span></span>}
              {x.lang && <span className="mono">{x.lang}</span>}
            </div>
            <p className="fb-subject">{x.subject}</p>
            <p className="fb-message">{x.message}</p>
            {x.image && <details className="fb-image"><summary>{F.openImage}</summary><img src={x.image} alt="" /></details>}
          </li>
        ))}
      </ul>
    </section>
  );
}
type FeedbackInboxDoc = { unread: number; items: { id: string; t: number; subject: string; message: string; image: string | null; page: string | null;
  lang: string | null; user: { id: string; name: string | null } | null; read: boolean }[] };
