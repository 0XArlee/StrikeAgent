"""Audit report of one user's agent: everything it and its owner did, in order, with where each action came from,
and whether the records are intact. For claims: what the owner signed, what the agent decided and why, what was sent
to Strike and what Strike answered, what was executed on the account and what moved its balance.

    smartflow audit verify [--runs runs]                       every chain under runs/
    smartflow audit report <user> [--env mainnet] [--since 2026-10-01] [--until ...] [--site]
        <user>: u-xxxxxxxxxxxx, the agent's name or the wallet address
        writes reports/audit/<user>-<time>.md (to read) and .json (every record, as kept)

Sources (all append-only, hash-chained, smartflow.audit):
  runs/web-audit-<env>.jsonl         the site's record of every owner action, with the exact message and signature
  runs/live-<uid>/journal.jsonl      the agent: checks, signals, risk decisions, orders, Strike calls, exits, alerts,
                                     starts and stops, and what the fleet did with it ("host")
  runs/live-<uid>/fills.jsonl        every fill of the Strike account (the agent's and anyone else's)
  runs/live-<uid>/account.jsonl      every change of the account's balance, positions and orders
The report is in Spanish: it is read by the operator (docs/08).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from .. import audit

WINDOW_MS = 60_000   # an account fill within a minute of the agent's own order or exit is the agent's


def _ms(ts) -> int:
    if isinstance(ts, (int, float)):
        return int(ts)
    return int(dt.datetime.fromisoformat(str(ts)).timestamp() * 1000)


def _iso(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _n(v, d: int = 2) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{x:,.{d}f}".replace(",", " ")


def uid_for(who: str, runs: Path, env: str) -> str:
    """u-… from a user id, a wallet address (the site's id is u- + 12 hex of SHA-256 of the address) or a name."""
    who = who.strip()
    if who.startswith("u-"):
        return who
    if who.startswith("addr"):
        return "u-" + hashlib.sha256(who.encode()).hexdigest()[:12]
    try:
        reg = json.loads((runs / f"fleet-{env}.json").read_text(encoding="utf-8"))
        for uid, v in reg.items():
            if str(v.get("name", "")).lower() == who.lower():
                return uid
    except (OSError, json.JSONDecodeError):
        pass
    for r in audit.read(runs / f"web-audit-{env}.jsonl"):
        if str((r.get("detail") or {}).get("name", "")).lower() == who.lower() and r.get("user_id"):
            return r["user_id"]
    raise SystemExit(f"no agent found for {who!r} on {env}")


# ---------------------------------------------------------------------------------------------- what each record says
def _web(r: dict) -> str:
    d = r.get("detail") or {}
    a, ok = r.get("action", ""), bool(r.get("ok"))
    if not ok:
        return f"Intento de «{a}» rechazado: {d.get('error', '—')}"
    if a == "create":
        return (f"Creó el agente «{d.get('name')}» firmando con su wallet: {d.get('strategy')}, mercados "
                f"{', '.join(d.get('markets') or [])}, riesgo {d.get('risk')}"
                + (" — con la misma firma conectó su cuenta de Strike (línea siguiente)" if d.get("live") else ""))
    texts = {"signin": "Inició sesión en su agente (firma que prueba la propiedad de la wallet; no cambia nada)",
             "pause": "Pausó el agente", "resume": "Reanudó el agente", "show": "Mostró el agente en la ciudad",
             "hide": "Ocultó el agente de la ciudad", "look": "Cambió el personaje", "revoke": "Borró el agente",
             "live_off": "Detuvo la operativa real (solo con su sesión: parar siempre está permitido)",
             "test": "Pidió una operación de prueba (la mínima de Strike, unos 2 minutos)"}
    if a == "settings":
        return (f"Cambió la configuración: {d.get('strategy')}, mercados {', '.join(d.get('markets') or [])}, riesgo "
                f"{d.get('risk')} (antes: {d.get('before')})")
    if a == "live_connect":
        return (f"Conectó su cuenta de Strike {d.get('env')} ({d.get('accountId')}) y aprobó la comisión de builder "
                f"{d.get('builderCode')} de {d.get('feeBps')} bps; Strike lo confirmó para la API wallet {d.get('pub')}")
    return texts.get(a, a) + ("" if d.get("changed", True) else " (ya estaba así: nada cambió)")


def _order_body(b) -> str:
    if not isinstance(b, dict):
        return ""
    keys = ("symbol", "side", "type", "size", "quantity", "price", "stop_price", "trigger_price", "reduce_only",
            "time_in_force", "client_order_id")
    parts = [f"{k}={b[k]}" for k in keys if b.get(k) not in (None, "")]
    for leg in ("primary", "tp_order", "sl_order", "orders"):
        if leg in b:
            parts.append(f"{leg}={json.dumps(b[leg], ensure_ascii=False)[:300]}")
    return ", ".join(parts)


def _journal(r: dict) -> tuple[str, str] | None:
    """(source, text) for one journal record; None for what says nothing new."""
    k, m = r.get("kind"), r.get("market", "")
    if k == "analysis":
        why = "; ".join(r.get("why") or []) or ("señal" if r.get("sig_dir") else "sin setup")
        return "agente", f"Revisó {m} al cierre de la vela {_iso(int(r.get('bar') or 0))}: cierre {_n(r.get('close'))} — {why}"
    if k == "signal":
        if not r.get("trade_id"):
            return "agente", f"Señal en {m} no operada: {r.get('reason', '—')}"
        side = "LARGO" if r.get("dir") == 1 else "CORTO"
        src = "prueba pedida por el dueño" if r.get("test") else "señal de la estrategia"
        return "agente", (f"{src.capitalize()} {side} en {m} ({r['trade_id']}): cierre {_n(r.get('close'))}, ATR "
                          f"{_n(r.get('atr'))}, stop {_n(r.get('stop'))}"
                          + (f", volumen {_n(r.get('rel_vol'))}× su media" if r.get("rel_vol") is not None else ""))
    if k == "decision":
        if r.get("action"):
            return "agente", f"{r['action']} ({r.get('trade_id')})"
        if r.get("accepted"):
            return "agente", f"Motor de riesgo: aprobada ({r.get('trade_id')}) — {r.get('summary', '')}"
        return "agente", f"Motor de riesgo: descartada ({r.get('trade_id')}) — {'; '.join(r.get('reasons') or [])}"
    if k in ("live_order", "paper_order"):
        what = {"entry": "entrada", "stop": "stop de protección", "exit": "cierre", "stop moved": "stop subido"}.get(
            r.get("action", ""), r.get("action", ""))
        extra = f" de {_n(r.get('old'))} a {_n(r.get('new'))}" if r.get("action") == "stop moved" else ""
        res = "aceptada" if r.get("ok") else f"FALLÓ: {r.get('error', '')[:300]}"
        why = f" — motivo: {r['reason']}" if r.get("reason") else ""
        return "agente", f"Orden de {what}{extra} ({r.get('trade_id')}, {r.get('client_order_id', '')}): {res}{why}"
    if k == "strike_call":
        st = r.get("status")
        out = (f"respondió {st}" if st else "sin respuesta (puede o no haber llegado)") + f" en {r.get('ms')} ms"
        if r.get("error"):
            out += f": {str(r['error'])[:300]}"
        fee = f", cabecera de builder {r['builder_fee_bps']} bps" if r.get("builder_fee_bps") is not None else ""
        return "strike", f"{r.get('method')} {str(r.get('url', '')).split('.org', 1)[-1]} ({_order_body(r.get('body'))}{fee}) → {out}"
    if k == "fill":
        return "agente", f"Entrada ejecutada ({r.get('trade_id')}): {r.get('qty')} {m} a {_n(r.get('entry'))}"
    if k == "exit":
        res = f", resultado {_n(r.get('r'))} R" if r.get("r") is not None else ""
        return "agente", f"Salida de {r.get('trade_id', m)}: {r.get('reason', '—')}{res}"
    if k == "alert":
        return "agente", f"Aviso {r.get('level')}: {r.get('message')}"
    if k == "test":
        return "agente", f"Recibió la petición de prueba del dueño (pedida a las {_iso(int(r.get('at') or 0))})"
    if k == "agent_start":
        rk = r.get("risk") or {}
        return "agente", (f"Arrancó en {r.get('env')} ({r.get('mode')}): {r.get('policy')}, mercados "
                          f"{', '.join(r.get('markets') or [])}, riesgo {_n(100 * float(rk.get('risk_per_trade') or 0))} % "
                          f"por operación, parámetros {r.get('params')}, builder {r.get('builder_code')} "
                          f"{r.get('builder_fee_bps')} bps, API wallet {r.get('api_wallet')}")
    if k == "agent_stop":
        return "agente", f"Se detuvo: {r.get('reason')}" + (f" ({r['error']})" if r.get("error") else "")
    if k == "host":
        a = r.get("action")
        if a == "start":
            l = r.get("link") or {}
            return "flota", (f"Arrancó el agente con lo que el dueño eligió en la web: {l.get('strategy')}, "
                             f"{', '.join(l.get('markets') or [])}, riesgo {l.get('risk')}, cuenta {l.get('accountId')}")
        if a == "stop":
            return "flota", f"Detuvo el agente: {r.get('reason')}"
        if a == "test_handed":
            return "flota", (f"Pasó al agente la petición de prueba firmada por el dueño (pedida a las "
                             f"{_iso(int(r.get('at') or 0))}; tras un reinicio se vuelve a pasar y el agente no repite "
                             "una prueba ya hecha)")
        return "flota", f"{a}: {r.get('reason') or r.get('error') or ''}"
    return None


def _fill(f: dict, agent_times: dict[str, list[int]]) -> str:
    ours = any(abs(int(f.get("time") or 0) - t) <= WINDOW_MS for t in agent_times.get(f.get("market", ""), []))
    auto = f" — cierre forzoso de Strike ({f['auto']})" if f.get("auto") else ""
    return (f"Ejecución en la cuenta: {str(f.get('side', '')).upper()} {f.get('size')} {f.get('market')} a {_n(f.get('price'))}, "
            f"comisión {_n(f.get('fee'), 4)} $, resultado {_n(f.get('pnl'), 4)} $ — "
            + ("del agente" if ours else "FUERA del agente (no la pidió el agente)") + auto)


def _account(r: dict) -> str:
    ch, net = r.get("balance_change"), r.get("new_fills_net") or 0
    pos = ", ".join(f"{p.get('side')} {p.get('size')} {p.get('market')}" for p in r.get("positions") or []) or "ninguna"
    txt = f"Cuenta: saldo {_n(r.get('balance'))} $"
    if ch is not None:
        txt += f" ({'+' if ch >= 0 else ''}{_n(ch, 4)} $; ejecuciones nuevas {r.get('new_fills', 0)}, neto {_n(net, 4)} $)"
        rest = ch - net
        if abs(rest) >= 0.5:
            txt += f" — {'+' if rest >= 0 else ''}{_n(rest, 2)} $ que no vienen de ejecuciones: depósito, retirada o funding"
    return txt + f"; posiciones: {pos}; órdenes en el libro: {len(r.get('orders') or [])}"


# ---------------------------------------------------------------------------------------------- the report
def build(runs: Path, uid: str, env: str, since: int | None = None, until: int | None = None, checks: bool = True,
          anchors: dict | None = None) -> dict:
    run = runs / f"live-{uid}"
    paths = {"web": runs / f"web-audit-{env}.jsonl", "journal": run / "journal.jsonl", "fills": run / "fills.jsonl",
             "account": run / "account.jsonl"}
    web = [r for r in audit.read(paths["web"]) if r.get("user_id") == uid]
    journal, fills, account = (audit.read(paths[k]) for k in ("journal", "fills", "account"))
    inside = lambda t: (since is None or t >= since) and (until is None or t <= until)
    agent_times: dict[str, list[int]] = {}
    for r in journal:   # when the agent itself traded: its fills, exits and the order calls it sent
        if r.get("kind") in ("fill", "exit") or (r.get("kind") == "strike_call" and r.get("method") == "POST"):
            mk = r.get("market") or ((r.get("body") or {}).get("symbol") if isinstance(r.get("body"), dict) else "")
            if mk:
                agent_times.setdefault(mk, []).append(_ms(r["ts"]))
    rows = []
    for r in web:
        rows.append({"t": int(r.get("time") or _ms(r["ts"])), "src": "web", "text": _web(r), "file": "web", "seq": r.get("seq")})
    for r in journal:
        if r.get("kind") == "analysis" and not checks:
            continue
        said = _journal(r)
        if said:
            rows.append({"t": _ms(r["ts"]), "src": said[0], "text": said[1], "file": "journal", "seq": r.get("seq")})
    for f in fills:
        rows.append({"t": int(f.get("time") or _ms(f["ts"])), "src": "cuenta", "text": _fill(f, agent_times), "file": "fills",
                     "seq": f.get("seq")})
    for r in account:
        rows.append({"t": _ms(r["ts"]), "src": "cuenta", "text": _account(r), "file": "account", "seq": r.get("seq")})
    rows = sorted((x for x in rows if inside(x["t"])), key=lambda x: (x["t"], x["file"], x["seq"] or 0))
    integrity = {k: audit.verify(p) for k, p in paths.items() if p.exists()}
    anchored = {}
    for k, p in paths.items():   # what the site saw must still be in the file, line for line
        rel = p.relative_to(runs).as_posix()
        for seq, h in (anchors or {}).get(rel, []):
            got = next((r.get("hash") for r in audit.read(p) if r.get("seq") == seq), None)
            anchored.setdefault(k, []).append({"seq": seq, "ok": got == h})
    return {"user": uid, "env": env, "generated": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000),
            "since": since, "until": until, "timeline": rows, "trades": _trades(journal, fills, agent_times, inside),
            "consents": _consents(web), "integrity": integrity, "anchors": anchored,
            "records": {"web": web, "journal": journal, "fills": fills, "account": account}}


def _consents(web: list[dict]) -> list[dict]:
    """Each signed message once (creating an agent and connecting Strike is one signature, kept in two rows)."""
    seen, out = set(), []
    for r in web:
        k = (r.get("message"), r.get("signature"))
        if r.get("message") and k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _trades(journal: list[dict], fills: list[dict], agent_times, inside) -> list[dict]:
    out: dict[str, dict] = {}
    for r in journal:
        tid = r.get("trade_id")
        if not tid:
            continue
        t = out.setdefault(tid, {"trade": tid, "market": r.get("market", ""), "test": False, "steps": []})
        if r.get("kind") == "signal":
            t.update(market=r.get("market", ""), side="largo" if r.get("dir") == 1 else "corto", test=bool(r.get("test")),
                     signal=_ms(r["ts"]), stop=r.get("stop"))
        elif r.get("kind") == "decision":
            t["decision"] = "aprobada" if r.get("accepted") else "descartada: " + "; ".join(r.get("reasons") or [])
        elif r.get("kind") == "fill":
            t.update(entry=r.get("entry"), qty=r.get("qty"), opened=_ms(r["ts"]))
        elif r.get("kind") == "exit":
            t.update(exit=r.get("reason"), closed=_ms(r["ts"]))
        elif r.get("kind") in ("live_order", "paper_order"):
            t["steps"].append(f"{r.get('action')}: {'ok' if r.get('ok') else 'falló'}")
    res = []
    for t in out.values():
        if not inside(t.get("signal") or t.get("opened") or 0):
            continue
        lo, hi = (t.get("opened") or t.get("signal") or 0) - WINDOW_MS, (t.get("closed") or 0) + WINDOW_MS
        mine = [f for f in fills if f.get("market") == t["market"] and lo <= int(f.get("time") or 0) <= hi]
        t["net"] = round(sum(float(f.get("pnl") or 0) - float(f.get("fee") or 0) for f in mine), 6) if t.get("closed") else None
        res.append(t)
    return res


def markdown(doc: dict) -> str:
    L = [f"# Informe de auditoría · {doc['user']} · {doc['env']}", "",
         f"Generado {_iso(doc['generated'])}"
         + (f" · desde {_iso(doc['since'])}" if doc["since"] else "") + (f" · hasta {_iso(doc['until'])}" if doc["until"] else ""), ""]
    bad = [k for k, v in doc["integrity"].items() if not v["ok"]] + [k for k, v in doc["anchors"].items() if not all(a["ok"] for a in v)]
    L += ["## Integridad", "",
          "**Todo intacto**: ninguna línea se cambió, borró ni movió desde que se escribió." if not bad
          else f"**ATENCIÓN**: fallos de integridad en {', '.join(bad)} (detalle abajo).", ""]
    for k, v in doc["integrity"].items():
        L.append(f"- {k}: {v['lines']} líneas, {v['chained']} encadenadas"
                 + (f", {v['legacy']} anteriores al registro (selladas)" if v["legacy"] else "")
                 + (f" — {'; '.join(v['problems'])}" if v["problems"] else " — correcto"))
    for k, v in doc["anchors"].items():
        L.append(f"- {k}: {sum(a['ok'] for a in v)} de {len(v)} huellas guardadas en la web coinciden")
    L += ["", "## Firmas del dueño (consentimientos)", ""]
    for r in doc["consents"]:
        L += [f"### {_iso(int(r['time']))} · {r.get('action')} · {'aceptada' if r.get('ok') else 'rechazada'}", "",
              _web(r), "", f"Wallet `{r.get('address')}` · IP {r.get('ip') or '—'} ({r.get('country') or '—'})", "",
              "Mensaje firmado:", "", "```", str(r.get("message")), "```", "",
              f"Firma (CIP-30): `{str(r.get('signature'))[:120]}…` (completa en el .json)", ""]
    if not doc["consents"]:
        L += ["(ninguna en este periodo)", ""]
    L += ["## Operaciones", "", "| Operación | Mercado | Tipo | Señal | Riesgo | Entrada | Salida | Neto $ |", "|---|---|---|---|---|---|---|---|"]
    for t in doc["trades"]:
        L.append(f"| {t['trade']} | {t['market']} {t.get('side', '')} | {'prueba' if t['test'] else 'estrategia'} | "
                 f"{_iso(t['signal']) if t.get('signal') else '—'} | {t.get('decision', '—')} | "
                 f"{_n(t.get('entry')) if t.get('entry') else '—'} × {t.get('qty', '—')} | {t.get('exit', 'abierta')} | "
                 f"{_n(t['net'], 4) if t.get('net') is not None else '—'} |")
    L += ["", "## Cronología completa", "", "Origen: **web** = lo firmó el dueño · **flota** = el servidor de agentes · "
          "**agente** = su decisión · **strike** = lo que se envió a Strike y lo que respondió · **cuenta** = lo que pasó "
          "en la cuenta de Strike (ejecuciones y saldo).", ""]
    for x in doc["timeline"]:
        L.append(f"- `{_iso(x['t'])}` **{x['src']}** — {x['text']}  <sub>{x['file']}#{x['seq']}</sub>")
    return "\n".join(L) + "\n"
