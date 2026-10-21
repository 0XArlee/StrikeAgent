// A crash inside a part of the page (a wallet extension misbehaving, a bug) shows a message there instead of
// unmounting the whole app and leaving a black screen.
import { Component, type ReactNode } from "react";

// silent: nothing is shown instead (an ornament, like the landing's live city: the poster under it stays)
interface Props { children: ReactNode; onClose?: () => void; inline?: boolean; silent?: boolean }

export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) { return { error }; }

  componentDidCatch(error: Error) { console.error("ui error", error); }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.silent) return null;
    const es = document.documentElement.lang === "es";
    const body = (
      <div className="dialog" role="alertdialog" aria-modal="true" aria-labelledby="eb-title" aria-describedby="eb-desc">
        <h2 id="eb-title">{es ? "Algo ha fallado" : "Something went wrong"}</h2>
        <p id="eb-desc" className="dialog-sub">
          {es ? "No se ha podido abrir esta parte. Recarga la página; si vuelve a pasar, prueba con otra wallet o avísanos."
            : "This part could not open. Reload the page; if it happens again, try another wallet or let us know."}
        </p>
        <p className="mono faint small" style={{ wordBreak: "break-word" }}>{String(error.message).slice(0, 200)}</p>
        <div className="actions">
          <button type="button" className="btn btn-primary btn-lg btn-block" autoFocus
                  onClick={() => { this.setState({ error: null }); this.props.onClose?.(); }}>{es ? "Cerrar" : "Close"}</button>
        </div>
      </div>
    );
    return this.props.inline ? body : <div className="overlay">{body}</div>;
  }
}
