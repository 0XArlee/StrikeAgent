"""What one person's alerts look after: their Strike accounts and copies, and (once linked from the site) their agent.

Accounts: every position's distance to its liquidation price (a word at 15 %, a warning at 7 %, an alarm at 3 %), the
account's margin, and each copy it runs: a trade the trader made that the copy did not take, a position the copy still
holds the trader already left, the trader itself close to liquidation or out of margin (on Strike or Hyperliquid), and
the copy ending. All read from Strike's and Hyperliquid's public data, so anyone can watch any account.

Agent: what it did (an entry, an exit and its result), what went wrong (Strike not answering, a position it does not
track, a signal it had to skip and why), what its owner or the host changed, and what its copy pilot did. Read from
the agent's own journal and the pilot's state on this host.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from ..net import HttpError, request_json
from .strike import StrikePublic, label, num, pct, position_view, price, usd

HYPERLIQUID = "https://api.hyperliquid.xyz/info"
LIQ_LEVELS = ((0.03, 3), (0.07, 2), (0.15, 1))
RESET = 0.20                      # a position back this far from liquidation: the next approach is news again
CONFIRM = 2                       # checks in a row before a copy mismatch is reported (a copy takes seconds to follow)


def liq_level(d: float | None) -> int:
    if d is None:
        return 0
    return next((lvl for lim, lvl in LIQ_LEVELS if d <= lim), 0)


def msg(key: str, level: str, en: tuple[str, str], es: tuple[str, str], kind: str = "risk", url: str | None = None) -> dict:
    return {"key": key, "level": level, "kind": kind, "en": en, "es": es, **({"url": url} if url else {})}


def short(a: str) -> str:
    return a if len(a) <= 14 else f"{a[:6]}…{a[-4:]}"


# ---------------------------------------------------------------- reads
def hl_state(address: str, http=request_json) -> dict:
    _, doc, _ = http("POST", HYPERLIQUID, body=json.dumps({"type": "clearinghouseState", "user": address}).encode(),
                     headers={"Content-Type": "application/json"}, timeout=15, retries=1, retry_non_idempotent=True)
    return doc or {}


def hl_positions(st: dict) -> list[dict]:
    out = []
    for ap in st.get("assetPositions") or []:
        p = ap.get("position") or {}
        size = num(p.get("szi"))
        if not size:
            continue
        mark = (num(p.get("positionValue")) or 0) / abs(size)
        liq = num(p.get("liquidationPx"))
        out.append({"symbol": f"{p.get('coin')}-USD", "side": "long" if size > 0 else "short", "size": abs(size), "mark": mark,
                    "liq": liq, "dist": abs(mark - liq) / mark if liq and mark else None, "notional": num(p.get("positionValue")) or 0})
    return out


def copies_from_collector(db: Path, accounts: set[str]) -> list[dict]:
    """The copies Strike's leaderboard lists for these follower accounts (the collector keeps them), the latest of each."""
    if not accounts or not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    try:
        q = f"SELECT lead, follower, platform, status, created_at FROM subs WHERE follower IN ({','.join('?' * len(accounts))}) ORDER BY created_at"
        latest = {}
        for lead, fol, plat, status, created in con.execute(q, sorted(accounts)):
            latest[(lead, fol)] = {"lead": lead, "follower": fol, "platform": plat or "strike", "status": status, "since": created}
        return list(latest.values())
    finally:
        con.close()


class AccountWatch:
    """One Strike account (and its sub-accounts) looked after. ``mem`` is its memory between checks (kept by the bot)."""

    def __init__(self, strike: StrikePublic, listed: set[str], hl=hl_state, collector_db: Path | None = None):
        self.strike, self.listed, self.hl, self.db = strike, listed, hl, collector_db

    def accounts(self, main: str) -> dict[str, str]:
        """The account and its sub-accounts: id -> a name to show."""
        doc = self.strike.account(main)
        out = {main: "main account"}
        for s in doc.get("sub_accounts") or []:
            sid = s.get("account_id") if isinstance(s, dict) else s
            if sid:
                out[sid] = (s.get("name") if isinstance(s, dict) else None) or f"sub-account {short(sid)}"
        return out

    def check(self, main: str, mem: dict, copies_known: list[dict] | None = None, label_en: str = "", label_es: str = "") -> list[dict]:
        out: list[dict] = []
        accts = self.accounts(main)
        held: dict[str, dict[str, dict]] = {}
        for acc, name in accts.items():
            ps = [v for v in (position_view(p) for p in self.strike.positions(acc)) if v]
            held[acc] = {p["symbol"]: p for p in ps}
            out += self._liquidation(acc, name, ps, mem, label_en, label_es)
            out += self._margin(acc, name, mem)
        copies = copies_known if copies_known is not None else copies_from_collector(self.db, set(accts)) if self.db else []
        for c in copies:
            out += self._copy(c, held.get(c["follower"], {}), accts.get(c["follower"], short(c["follower"])), mem)
        return out

    def _liquidation(self, acc: str, name: str, ps: list[dict], mem: dict, who_en: str, who_es: str) -> list[dict]:
        out, seen = [], mem.setdefault("liq", {})
        for p in ps:
            k = f"{acc}:{p['symbol']}"
            lvl, was = liq_level(p["dist"]), seen.get(k, 0)
            if p["dist"] is None or p["dist"] > RESET:
                seen.pop(k, None)
                continue
            if lvl <= was:
                continue
            seen[k] = lvl
            d, side, n = p["dist"] * 100, p["side"].upper(), label(p["symbol"])
            level = {3: "alert", 2: "warn", 1: "info"}[lvl]
            where_en, where_es = (f"{who_en} · {name}" if who_en else name), (f"{who_es} · {name}" if who_es else name)
            act_en = "Add margin or reduce it now." if lvl == 3 else "Consider adding margin or reducing it."
            act_es = "Añade margen o redúcela ya." if lvl == 3 else "Valora añadir margen o reducirla."
            out.append(msg(f"liq:{k}:{lvl}", level,
                           (f"{side} {n} {d:.1f}% from liquidation", f"{where_en}: {p['size']:g} {n} at {price(p['entry'])}, mark {price(p['mark'])}, "
                            f"liquidation {price(p['liq'])} ({usd(p['notional'])}). {act_en}"),
                           (f"{side} {n} a {d:.1f}% de la liquidación", f"{where_es}: {p['size']:g} {n} a {price(p['entry'])}, mark {price(p['mark'])}, "
                            f"liquidación {price(p['liq'])} ({usd(p['notional'])}). {act_es}"),
                           url="https://app.strikefinance.org"))
        return out

    def _margin(self, acc: str, name: str, mem: dict) -> list[dict]:
        doc = self.strike.account(acc)
        mb, mm = num(doc.get("margin_balance")), num(doc.get("maintenance_margin"))
        seen = mem.setdefault("margin", {})
        if not mb or mm is None or mb <= 0:
            return []
        r = mm / mb
        lvl = 2 if r >= 0.85 else 1 if r >= 0.6 else 0
        if lvl == 0 and r < 0.4:
            seen.pop(acc, None)
        if lvl <= seen.get(acc, 0):
            return []
        seen[acc] = lvl
        return [msg(f"margin:{acc}:{lvl}", "alert" if lvl == 2 else "warn",
                    (f"{name}: margin {r * 100:.0f}% used", f"Maintenance margin {usd(mm)} of {usd(mb)}. At 100% Strike liquidates: "
                     "add funds or reduce positions."),
                    (f"{name}: {r * 100:.0f}% del margen usado", f"Margen de mantenimiento {usd(mm)} de {usd(mb)}. Al 100% Strike liquida: "
                     "añade fondos o reduce posiciones."), url="https://app.strikefinance.org")]

    def _copy(self, c: dict, mine: dict[str, dict], name: str, mem: dict) -> list[dict]:
        out = []
        key = f"{c['follower']}:{c['lead']}"
        st = mem.setdefault("copies", {})
        prev = st.get(key)
        st[key] = c.get("status") or "active"
        lead_n = short(c["lead"])
        if prev == "active" and st[key] != "active":   # it ended
            liq = st[key] == "liquidated"
            out.append(msg(f"copyend:{key}:{c.get('since')}", "alert" if liq else "info",
                           (f"Your copy of {lead_n} {'was liquidated' if liq else 'stopped'}", f"{name} no longer copies {lead_n} on Strike ({st[key]})."),
                           (f"Tu copia de {lead_n} {'fue liquidada' if liq else 'se detuvo'}", f"{name} ya no copia a {lead_n} en Strike ({st[key]})."),
                           kind="copy"))
        if st[key] != "active":
            return out
        try:
            if c.get("platform") == "hyperliquid":
                hs = self.hl(c["lead"])
                lead = {p["symbol"]: p for p in hl_positions(hs)}
                value = num((hs.get("marginSummary") or {}).get("accountValue")) or 0
                maint = num(hs.get("crossMaintenanceMarginUsed")) or 0
            else:
                lead = {p["symbol"]: p for p in (position_view(x) for x in self.strike.positions(c["lead"])) if p}
                ad = self.strike.account(c["lead"])
                value, maint = num(ad.get("margin_balance")) or 0, num(ad.get("maintenance_margin")) or 0
        except (HttpError, ValueError, KeyError):
            return out
        first = mem.setdefault("leadmk", {})
        if key not in first:   # what the trader held when the watch began: those were opened before the copy could follow
            first[key] = sorted(lead)
        base = set(first[key])
        first[key] = sorted(base & set(lead))   # a market it closed is new again if it reopens
        cnt = mem.setdefault("mismatch", {})
        # a trade the copy did not take (only markets Strike lists: the others cannot be copied)
        for m, p in lead.items():
            k = f"miss:{key}:{m}"
            if m in base or m in mine or m not in self.listed:
                cnt.pop(k, None)
                continue
            cnt[k] = cnt.get(k, 0) + 1
            if cnt[k] == CONFIRM:
                n, side = label(m), p["side"].upper()
                out.append(msg(k, "warn", (f"Your copy didn't take {side} {n}", f"{lead_n} holds {side} {n} ({usd(p['notional'])}) but {name} "
                                           "doesn't: a market the copy excludes, not enough margin, or below Strike's minimum. Check it in Strike's app."),
                               (f"Tu copia no tomó {side} {n}", f"{lead_n} tiene {side} {n} ({usd(p['notional'])}) pero {name} no: un mercado que la "
                                "copia excluye, margen insuficiente o por debajo del mínimo de Strike. Revísalo en la app de Strike."),
                               kind="copy", url="https://app.strikefinance.org"))
        # a position the copy still holds that the trader already left
        for m, p in mine.items():
            k = f"left:{key}:{m}"
            if m in lead:
                cnt.pop(k, None)
                continue
            cnt[k] = cnt.get(k, 0) + 1
            if cnt[k] == CONFIRM:
                n, side = label(m), p["side"].upper()
                out.append(msg(k, "warn", (f"{lead_n} left {n}; your copy didn't", f"{name} still holds {side} {n} ({usd(p['notional'])}, mark "
                                           f"{price(p['mark'])}) and the trader no longer does. Close it in Strike's app if you want to stay in step."),
                               (f"{lead_n} salió de {n}; tu copia no", f"{name} sigue con {side} {n} ({usd(p['notional'])}, mark {price(p['mark'])}) "
                                "y el trader ya no. Ciérrala en la app de Strike si quieres ir a la par."),
                               kind="copy", url="https://app.strikefinance.org"))
        for k in [k for k in cnt if k.startswith(("miss:" + key, "left:" + key)) and not any(k.endswith(":" + m) for m in set(lead) | set(mine))]:
            del cnt[k]
        # the trader itself in trouble
        risk = mem.setdefault("leadrisk", {})
        worst = min((p for p in lead.values() if p.get("dist") is not None), key=lambda p: p["dist"], default=None)
        ratio = maint / value if value else 0
        lvl = 2 if (worst and worst["dist"] <= 0.05) or ratio >= 0.8 else 1 if (worst and worst["dist"] <= 0.12) or ratio >= 0.55 else 0
        if lvl == 0:
            risk.pop(key, None)
        elif lvl > risk.get(key, 0):
            risk[key] = lvl
            where = "Hyperliquid" if c.get("platform") == "hyperliquid" else "Strike"
            detail_en = (f"its {worst['side'].upper()} {label(worst['symbol'])} is {worst['dist'] * 100:.1f}% from liquidation" if worst and worst["dist"] <= 0.12
                         else f"{ratio * 100:.0f}% of its margin is used")
            detail_es = (f"su {worst['side'].upper()} {label(worst['symbol'])} está a {worst['dist'] * 100:.1f}% de la liquidación"
                         if worst and worst["dist"] <= 0.12 else f"usa el {ratio * 100:.0f}% de su margen")
            out.append(msg(f"leadrisk:{key}:{lvl}", "alert" if lvl == 2 else "warn",
                           (f"The trader you copy is in trouble on {where}", f"{lead_n}: {detail_en}. Your copy follows its losses; you can stop it or "
                            "lower its stop-loss in Strike's app."),
                           (f"El trader que copias está en apuros en {where}", f"{lead_n}: {detail_es}. Tu copia sigue sus pérdidas; puedes pararla o "
                            "ajustar su stop-loss en la app de Strike."), kind="copy", url="https://app.strikefinance.org"))
        return out


# ---------------------------------------------------------------- the agent's journal and its copy pilot
DIGITS = re.compile(r"[\d.,]+")
QUIET_REASONS = ("an opposite position is open", "stack full", "a previous entry is not settled yet", "analysis mode")


class AgentWatch:
    """A user's agent on this host: its journal (runs/live-<user>/journal.jsonl) and its copy pilot's state."""

    def __init__(self, runs: Path, copy_dir: Path):
        self.runs, self.copy_dir = runs, copy_dir

    def check(self, user: str, env: str, name: str, mem: dict) -> list[dict]:
        return self._journal(user, name, mem) + self._pilot(user, env, mem)

    def _journal(self, user: str, name: str, mem: dict) -> list[dict]:
        path = self.runs / f"live-{user}" / "journal.jsonl"
        try:
            size = path.stat().st_size
        except OSError:
            return []
        pos = mem.get("pos")
        if pos is None or pos > size:   # first look (or a new journal): from now on, never the backlog
            mem["pos"] = size
            return []
        out, trades = [], mem.setdefault("trades", {})
        with path.open("rb") as f:
            f.seek(pos)
            raw = f.read(2_000_000)
        mem["pos"] = pos + raw.rfind(b"\n") + 1 if b"\n" in raw else pos
        for line in raw[: raw.rfind(b"\n") + 1].decode("utf-8", "replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            out += self._event(r, name, trades, mem)
        if len(trades) > 50:
            for k in list(trades)[:-50]:
                del trades[k]
        return out

    def _event(self, r: dict, name: str, trades: dict, mem: dict) -> list[dict]:
        k, tid = r.get("kind"), str(r.get("trade_id") or "")
        if r.get("test") or "-test-" in tid:
            return []
        if k == "signal":
            trades[tid] = {"dir": r.get("dir"), "stop": r.get("stop"), "market": r.get("market")}
        elif k == "fill" and tid in trades and "entry" not in trades[tid]:
            t = trades[tid]
            t.update(entry=num(r.get("entry")), qty=num(r.get("qty")))
            side, n = ("LONG" if t["dir"] == 1 else "SHORT"), label(t["market"] or r.get("market") or "")
            stop = num(t.get("stop"))
            risk = f" · stop {price(stop)} ({pct((stop / t['entry'] - 1) * 100)})" if stop and t["entry"] else ""
            return [msg(f"open:{tid}", "info", (f"{name} opened {side} {n}", f"{t['qty']:g} {n} at {price(t['entry'])}{risk}. Its stop rests on Strike."),
                        (f"{name} abrió {side} {n}", f"{t['qty']:g} {n} a {price(t['entry'])}{risk}. Su stop queda en Strike."),
                        kind="trades")]
        elif k == "exit":
            t = trades.get(tid) or {"market": r.get("market")}
            n = label(t.get("market") or r.get("market") or "")
            px, entry, stop, d = num(r.get("price")), t.get("entry"), num(t.get("stop")), t.get("dir")
            res_en = res_es = ""
            if px and entry and stop and d and entry != stop:
                rr = (px - entry) / abs(entry - stop) * (1 if d == 1 else -1)
                pnl = (px - entry) * (t.get("qty") or 0) * (1 if d == 1 else -1)
                res_en = f" {rr:+.2f}R ({'+' if pnl >= 0 else '−'}{abs(pnl):,.2f} $)."
                res_es = res_en
            why = str(r.get("reason") or "")
            why_es = {"stop": "en su stop", "exit": "por su regla de salida", "trail": "en su stop móvil"}.get(why, why)
            good = res_en.startswith(" +")
            return [msg(f"close:{tid}", "info", (f"{name} closed {n}", f"At {price(px) if px else 'market'} ({why}).{res_en}"),
                        (f"{name} cerró {n}", f"A {price(px) if px else 'mercado'} ({why_es}).{res_es}"),
                        kind="trades")] if good or res_en or why else []
        elif k == "alert" and r.get("level") in ("warning", "error", "critical"):
            text = str(r.get("message") or "")[:300]
            key = "problem:" + DIGITS.sub("#", text)[:120]
            last = mem.setdefault("problems", {})
            ts = r.get("ts") or ""
            if key in last and last[key][:13] == ts[:13]:   # once an hour for the same problem
                return []
            last[key] = ts
            if len(last) > 40:
                for x in list(last)[:-40]:
                    del last[x]
            return [msg(key, "alert" if r.get("level") != "warning" else "warn", (f"{name} needs a look", text),
                        (f"{name} necesita que lo mires", text), kind="problems")]
        elif k == "decision" and r.get("accepted") is False:
            reasons = [x for x in (r.get("reasons") or []) if not str(x).startswith(QUIET_REASONS)]
            if reasons and "market blocked" not in reasons[0]:
                t = trades.get(tid) or {}
                n = label(t.get("market") or tid.split("-USD")[0] + "-USD")
                text = "; ".join(map(str, reasons))[:240]
                return [msg(f"skip:{tid}", "warn", (f"{name} skipped a {n} signal", text), (f"{name} descartó una señal de {n}", text), kind="problems")]
        elif k == "host":
            a = str(r.get("action") or "")
            words = {"pause": ("paused", "pausado"), "resume": ("resumed", "reanudado"), "stop": ("stopped", "detenido"),
                     "start": ("started on Strike", "arrancado en Strike"), "delete": ("deleted", "borrado"), "revoked": ("disconnected from Strike", "desconectado de Strike")}
            if a in words:
                en, es = words[a]
                return [msg(f"host:{a}:{r.get('ts')}", "info", (f"{name} {en}", "As shown in My agent on the site."),
                            (f"{name} {es}", "Como se ve en Mi agente en la web."), kind="status")]
        return []

    def _pilot(self, user: str, env: str, mem: dict) -> list[dict]:
        try:
            st = (json.loads((self.copy_dir / f"pilot-{env}.json").read_text(encoding="utf-8")) or {}).get(user) or {}
        except (OSError, ValueError):
            return []
        out, since = [], mem.get("pilot_t")
        log = st.get("log") or []
        if since is None:
            mem["pilot_t"] = max((x.get("t") or 0 for x in log), default=0)
            mem["pilot_why"] = st.get("why")
            return []
        for x in log:
            t = x.get("t") or 0
            if t <= since:
                continue
            mem["pilot_t"] = max(mem["pilot_t"], t)
            lead = short(str(x.get("lead") or ""))
            avail = x.get("available")
            texts = {
                "start": ((f"Copying {lead}", "Your agent started the copy on Strike's copy trading."), (f"Copiando a {lead}", "Tu agente empezó la copia en el copy trading de Strike.")),
                "stop": ((f"Stopped copying {lead}", "Your agent stopped the copy."), (f"Dejó de copiar a {lead}", "Tu agente paró la copia.")),
                "ended": ((f"The copy of {lead} ended", "Strike ended it (its stop-loss, or the trader stopped)."), (f"Terminó la copia de {lead}", "Strike la terminó (su stop-loss, o el trader paró).")),
                "refused": (("Strike refused the copy", str(x.get("text") or "")[:200]), ("Strike rechazó la copia", str(x.get("text") or "")[:200])),
                "no_funds": (("The copy is waiting for money", f"{avail} $ available in your account: deposit in Strike, or sign a smaller amount."),
                             ("La copia espera dinero", f"{avail} $ disponibles en tu cuenta: deposita en Strike o firma un importe menor.")),
                "no_funds_sub": (("The sub-account needs money", f"{avail} $ in it: top it up in Strike's app."), ("La subcuenta necesita dinero", f"{avail} $ en ella: recárgala en la app de Strike.")),
                "short": (("Copying with less than planned", f"{avail} $ in a free sub-account rather than open another: top it up in Strike's app."),
                          ("Copia con menos de lo previsto", f"{avail} $ en una subcuenta libre en vez de abrir otra: recárgala en la app de Strike.")),
                "account_busy": (("Waiting for your sub-account", "It still runs another copy."), ("Esperando a tu subcuenta", "Aún lleva otra copia.")),
                "error": (("Strike did not answer the copy pilot", "It tries again every minute."), ("Strike no respondió al copiloto", "Lo vuelve a intentar cada minuto.")),
            }.get(x.get("kind"))
            if texts:
                lvl = "alert" if x.get("kind") in ("refused", "ended") else "warn" if x.get("kind") in ("no_funds", "no_funds_sub", "error") else "info"
                out.append(msg(f"pilot:{x.get('kind')}:{t}", lvl, texts[0], texts[1], kind="copy"))
        why = st.get("why")
        if why != mem.get("pilot_why"):
            mem["pilot_why"] = why
            pause = {"alarm": (("Copy paused: security alarm", "A major hack or an exchange going down: it resumes when the alarm ends."),
                               ("Copia en pausa: alarma de seguridad", "Un hackeo grave o un exchange caído: sigue cuando acabe la alarma.")),
                     "macro": (("Copy paused for a US release", "From 30 minutes before to an hour after, as you chose."),
                               ("Copia en pausa por un dato de EE. UU.", "De 30 minutos antes a una hora después, como elegiste."))}.get(why or "")
            if pause:
                out.append(msg(f"pilot:why:{why}", "info", pause[0], pause[1], kind="copy"))
        return out
