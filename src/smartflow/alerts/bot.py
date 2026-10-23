"""The alerts bot on Telegram: Strike Finance for everyone, and each person's own agent, accounts and copies.

Anyone can open the bot and get Strike's moments (``strike.py``). An agent's owner links it from the site's Alerts tab
(a one-time code made with their session: ``/start <code>``), and the bot then looks after their agent, their Strike
account, its sub-accounts and every copy they run (``watch.py``). Anyone can also ask it to watch any Strike account
(``/watch <address or account>``): the copy checks only need public data.

One process for both networks: the testnet site (staging) and the mainnet site (production) each answer for their own
link codes (``q…`` and ``m…``). Outbound only: long polling to Telegram, signed requests to the sites, public reads of
Strike and Hyperliquid. State in ``/var/lib/smartflow/alerts`` (chats, settings, what was already said).
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import re
import threading
import time
from pathlib import Path

from ..net import HttpError, request_json
from .strike import MAINNET, TESTNET, StrikePublic, StrikeWatch, label, pct, position_view, price, usd
from .telegram import Telegram, TelegramError
from .watch import AccountWatch, AgentWatch, copies_from_collector, es_name, hl_state, short

STRIKE_KINDS = ("move", "funding", "liquidation", "whale", "crowd", "listing", "security", "macro", "reading", "arena")
MINE_KINDS = ("risk", "copy", "trades", "problems", "status")
DEFAULT_OFF = {"crowd", "reading"}
MAJORS = {"BTC-USD", "ETH-USD", "SOL-USD"}
ICON = {"alert": "🚨", "warn": "⚠️", "info": "🔔"}
KIND_ICON = {"move": "📈", "funding": "💸", "liquidation": "🧨", "whale": "🐋", "crowd": "⚖️", "listing": "🆕", "status": "⏸️",
             "security": "🛡️", "macro": "🗓️", "reading": "📰", "arena": "🏟️"}
CODE = re.compile(r"^[qm][A-Za-z0-9_-]{16,40}$")
ACCOUNT = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
ADDRESS = re.compile(r"^(addr1[0-9a-z]{50,120}|addr_test1[0-9a-z]{50,120}|0x[0-9a-fA-F]{40})$")
MAX_WATCH = 5
SITES = {"testnet": "https://qa.edgecraft-strikecity.pages.dev", "mainnet": "https://edgecraft-strikecity.pages.dev"}

T = {
    "en": {
        "hello": "⚡ <b>EdgeCraft-StrikeCity alerts</b>\nStrike Finance's moments worth a look, and everything about your own agent, account and copies.",
        "menu_strike": "Strike Finance alerts: <b>{state}</b>", "on": "on", "off": "off",
        "menu_agent": "Your agent: <b>{name}</b>", "menu_noagent": "Your agent: not linked. Link it from the site's <b>Alerts</b> tab.",
        "menu_watch": "Watching: {n}", "menu_muted": "🔕 Muted until {t} UTC",
        "b_strike": "🔔 Strike alerts", "b_agent": "🤖 My agent", "b_watch": "👀 Watch an account", "b_now": "📊 Strike now",
        "b_settings": "⚙️ Settings", "b_help": "❓ Help", "b_city": "🏙️ Open the city", "b_back": "← Back", "b_app": "Open Strike",
        "b_mute1": "🔕 1 h", "b_mute8": "🔕 8 h", "b_unmute": "🔔 Unmute", "b_scope_all": "Markets: all", "b_scope_majors": "Markets: BTC, ETH, SOL",
        "settings": "⚙️ <b>Settings</b>\nTap to turn an alert on or off. Urgent liquidation warnings always arrive, even muted.",
        "k_move": "Big moves", "k_funding": "Extreme funding", "k_liquidation": "Liquidation radar", "k_whale": "Whales", "k_crowd": "Crowded markets",
        "k_listing": "New and halted markets", "k_security": "Security alarm", "k_macro": "US macro calendar", "k_reading": "News readings", "k_arena": "Copy Arena",
        "k_risk": "My liquidation risk", "k_copy": "My copies", "k_trades": "My agent's trades", "k_problems": "My agent's problems", "k_status": "My agent's status",
        "linked": "✅ <b>Linked to {name}</b> ({env}).\nFrom now on: its trades and results, anything that goes wrong, its copy pilot, and your Strike "
                  "account, sub-accounts and copies: liquidation risk, trades a copy didn't take, positions the trader already left, the trader in trouble.",
        "link_bad": "That link has expired or was already used. Make a new one in the site's Alerts tab.",
        "unlinked": "Your agent is no longer linked to this chat.", "noagent": "No agent linked. Open the site, sign in, and press <b>Connect Telegram</b> in Alerts.",
        "watch_ask": "Send <code>/watch</code> and a Strike account: its id, or the wallet address that owns it (addr1… or 0x…). I'll check its positions and "
                     "every copy it runs every 2 minutes.",
        "watch_ok": "👀 Watching <b>{name}</b>{subs}. I'll write when something needs a look.", "watch_subs": " and its {n} sub-accounts",
        "watch_bad": "I couldn't find that account on Strike.", "watch_max": "You already watch {n} accounts: remove one with /unwatch first.",
        "watch_list": "👀 <b>Watching</b>\n{items}", "watch_none": "Not watching any account yet. /watch &lt;account&gt;",
        "unwatch_ok": "Stopped watching {name}.", "muted": "🔕 Muted for {h} h. Urgent liquidation warnings still arrive.", "unmuted": "🔔 Alerts are back on.",
        "stopped": "All alerts are off and this chat is forgotten. /start brings them back.",
        "help": "<b>What I do</b>\n• <b>Strike Finance</b>: big moves, extreme funding, large positions close to liquidation, whales, new or halted markets, "
                "the security alarm, the big US releases, the Copy Arena's top traders.\n• <b>Your agent</b> (link it from the site's Alerts tab): "
                "its trades and results, problems, its copy pilot.\n• <b>Your accounts and copies</b>: liquidation distance of every position, margin, "
                "trades a copy didn't take, positions the trader already left, the trader in trouble on Strike or Hyperliquid.\n\n"
                "/menu · /strike · /status · /watch &lt;account&gt; · /unwatch · /settings · /mute 8 · /unmute · /lang es · /stop",
        "now": "📊 <b>Strike now</b>", "now_movers": "Biggest 24 h moves", "now_funding": "Most extreme funding", "now_near": "Closest large position to liquidation",
        "now_oi": "Open interest on Strike: {oi} · {share} of positions long", "now_vol": "24 h volume: {v}", "now_news": "News Tower on BTC: {r}", "now_next": "Next US release: {e}",
        "status_title": "🤖 <b>{name}</b>", "status_pos": "Open positions", "status_none": "No open position.", "status_copy": "Copy: {s}",
        "status_margin": "Margin used: {r}", "status_watch": "👀 <b>{name}</b>", "per_hour": "an hour", "to_liq": "to liquidation", "copy_none": "no copy",
        "unknown": "I didn't get that. /help lists what I can do.",
    },
    "es": {
        "hello": "⚡ <b>Alertas de EdgeCraft-StrikeCity</b>\nLos momentos de Strike Finance que merecen un vistazo, y todo sobre tu agente, tu cuenta y tus copias.",
        "menu_strike": "Alertas de Strike Finance: <b>{state}</b>", "on": "activadas", "off": "desactivadas",
        "menu_agent": "Tu agente: <b>{name}</b>", "menu_noagent": "Tu agente: sin vincular. Vincúlalo desde la pestaña <b>Alertas</b> de la web.",
        "menu_watch": "Vigilando: {n}", "menu_muted": "🔕 En silencio hasta las {t} UTC",
        "b_strike": "🔔 Alertas de Strike", "b_agent": "🤖 Mi agente", "b_watch": "👀 Vigilar una cuenta", "b_now": "📊 Strike ahora",
        "b_settings": "⚙️ Ajustes", "b_help": "❓ Ayuda", "b_city": "🏙️ Abrir la ciudad", "b_back": "← Volver", "b_app": "Abrir Strike",
        "b_mute1": "🔕 1 h", "b_mute8": "🔕 8 h", "b_unmute": "🔔 Quitar silencio", "b_scope_all": "Mercados: todos", "b_scope_majors": "Mercados: BTC, ETH, SOL",
        "settings": "⚙️ <b>Ajustes</b>\nToca para activar o desactivar cada alerta. Los avisos urgentes de liquidación llegan siempre, incluso en silencio.",
        "k_move": "Grandes movimientos", "k_funding": "Funding extremo", "k_liquidation": "Radar de liquidaciones", "k_whale": "Ballenas", "k_crowd": "Mercados abarrotados",
        "k_listing": "Mercados nuevos y pausados", "k_security": "Alarma de seguridad", "k_macro": "Calendario macro de EE. UU.", "k_reading": "Lecturas de noticias",
        "k_arena": "Copy Arena", "k_risk": "Mi riesgo de liquidación", "k_copy": "Mis copias", "k_trades": "Operaciones de mi agente",
        "k_problems": "Problemas de mi agente", "k_status": "Estado de mi agente",
        "linked": "✅ <b>Vinculado a {name}</b> ({env}).\nDesde ahora: sus operaciones y resultados, cualquier problema, su copiloto, y tu cuenta de Strike, "
                  "subcuentas y copias: riesgo de liquidación, operaciones que una copia no tomó, posiciones que el trader ya cerró, el trader en apuros.",
        "link_bad": "Ese enlace ha caducado o ya se usó. Crea otro en la pestaña Alertas de la web.",
        "unlinked": "Tu agente ya no está vinculado a este chat.", "noagent": "Ningún agente vinculado. Abre la web, conéctate y pulsa <b>Conectar Telegram</b> en Alertas.",
        "watch_ask": "Envía <code>/watch</code> y una cuenta de Strike: su id, o la dirección de la wallet que la tiene (addr1… o 0x…). Revisaré sus posiciones y "
                     "cada copia que lleve cada 2 minutos.",
        "watch_ok": "👀 Vigilando <b>{name}</b>{subs}. Te escribiré cuando algo merezca un vistazo.", "watch_subs": " y sus {n} subcuentas",
        "watch_bad": "No encuentro esa cuenta en Strike.", "watch_max": "Ya vigilas {n} cuentas: quita una con /unwatch primero.",
        "watch_list": "👀 <b>Vigilando</b>\n{items}", "watch_none": "Aún no vigilas ninguna cuenta. /watch &lt;cuenta&gt;",
        "unwatch_ok": "Dejé de vigilar {name}.", "muted": "🔕 En silencio {h} h. Los avisos urgentes de liquidación llegan igualmente.", "unmuted": "🔔 Alertas activadas de nuevo.",
        "stopped": "Todas las alertas están desactivadas y este chat olvidado. /start las vuelve a traer.",
        "help": "<b>Qué hago</b>\n• <b>Strike Finance</b>: grandes movimientos, funding extremo, posiciones grandes cerca de la liquidación, ballenas, mercados "
                "nuevos o pausados, la alarma de seguridad, los grandes datos de EE. UU., los mejores traders de la Copy Arena.\n• <b>Tu agente</b> (vincúlalo "
                "desde la pestaña Alertas de la web): sus operaciones y resultados, problemas, su copiloto.\n• <b>Tus cuentas y copias</b>: distancia a la "
                "liquidación de cada posición, margen, operaciones que una copia no tomó, posiciones que el trader ya cerró, el trader en apuros en Strike o "
                "Hyperliquid.\n\n/menu · /strike · /status · /watch &lt;cuenta&gt; · /unwatch · /settings · /mute 8 · /unmute · /lang en · /stop",
        "now": "📊 <b>Strike ahora</b>", "now_movers": "Mayores movimientos en 24 h", "now_funding": "Funding más extremo",
        "now_near": "Posición grande más cerca de la liquidación", "now_oi": "Interés abierto en Strike: {oi} · {share} de las posiciones en largo", "now_vol": "Volumen 24 h: {v}",
        "now_news": "News Tower sobre BTC: {r}", "now_next": "Próximo dato de EE. UU.: {e}",
        "status_title": "🤖 <b>{name}</b>", "status_pos": "Posiciones abiertas", "status_none": "Ninguna posición abierta.", "status_copy": "Copia: {s}",
        "status_margin": "Margen usado: {r}", "status_watch": "👀 <b>{name}</b>", "per_hour": "por hora", "to_liq": "a la liquidación", "copy_none": "sin copia",
        "unknown": "No te he entendido. /help muestra lo que puedo hacer.",
    },
}


def esc(s) -> str:
    return html.escape(str(s), quote=False)


def env_file(path: str) -> dict[str, str]:
    """KEY=VALUE lines (quotes optional): the sites' URL and secret come from the fleet's own files."""
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


class Site:
    """One Strike City site (staging or production): link codes, linked owners, the public alerts document."""

    def __init__(self, env: str, url: str, secret: str, http=request_json):
        self.env, self.url, self.secret, self.http = env, url.rstrip("/"), secret, http

    def _req(self, method: str, path: str, body: bytes | None = None) -> dict:
        ts = str(int(time.time() * 1000))
        payload = body.decode() if body is not None else f"{method} {path}"
        sig = hmac.new(self.secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
        _, doc, _ = self.http(method, self.url + path, body=body, headers={"Content-Type": "application/json", "X-SF-Time": ts,
                                                                             "X-SF-Signature": sig, "User-Agent": "smartflow-alerts/1.0"},
                              timeout=20, retries=1, retry_non_idempotent=True)
        return doc if isinstance(doc, dict) else {}

    def lookup(self, code: str) -> dict:
        return self._req("GET", f"/api/internal/telegram?code={code}")

    def linked(self) -> list[dict]:
        return self._req("GET", "/api/internal/telegram?sync=1").get("users") or []

    def claim(self, code: str, chat: str, label_: str) -> dict:
        return self._req("POST", "/api/internal/telegram", json.dumps({"claim": {"code": code, "chat": chat, "label": label_}}).encode())

    def unlink(self, user: str, chat: str) -> dict:
        return self._req("POST", "/api/internal/telegram", json.dumps({"unlink": {"userId": user, "chat": chat}}).encode())

    def alerts(self, doc: dict) -> dict:
        return self._req("POST", "/api/internal/alerts", json.dumps(doc, separators=(",", ":")).encode())


class AlertsBot:
    def __init__(self, tg: Telegram, sites: dict[str, Site], state_dir: Path, runs: Path, copy_dir: Path, news_path: Path,
                 strikes: dict[str, StrikePublic] | None = None, hl=hl_state, log=print):
        self.tg, self.sites, self.dir, self.log = tg, sites, state_dir, log
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "bot.json"
        self.strikes = strikes or {"mainnet": StrikePublic(MAINNET), "testnet": StrikePublic(TESTNET)}
        self.copy_dir, self.news_path = copy_dir, news_path
        self.watch = StrikeWatch(self.dir / "strike.json", self.strikes["mainnet"], news=self._news, copy=self._copy_doc, log=log)
        self.agents = AgentWatch(runs, copy_dir)
        self.hl = hl
        self.lock = threading.RLock()
        self.state = {"offset": 0, "chats": {}}
        try:
            self.state.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        self.posted_at = 0

    # ---------------------------------------------------------------- state
    def save(self) -> None:
        with self.lock:
            for _ in range(3):   # the minute's checks may be writing a chat's memory meanwhile: try again
                try:
                    raw = json.dumps(self.state)
                    break
                except RuntimeError:
                    time.sleep(0.05)
            else:
                return
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(raw, encoding="utf-8")
            tmp.replace(self.path)
            self.watch.save()

    def _news(self) -> dict | None:
        try:
            return json.loads(self.news_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _copy_doc(self) -> dict | None:
        try:
            return json.loads((self.copy_dir / "copy.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def chat(self, cid: str, lang: str | None = None, name: str = "") -> dict:
        c = self.state["chats"].get(cid)
        if c is None:
            c = self.state["chats"][cid] = {"lang": "es" if (lang or "").startswith("es") else "en", "name": name, "since": int(time.time() * 1000),
                                            "strike": True, "prefs": {k: k not in DEFAULT_OFF for k in STRIKE_KINDS + MINE_KINDS},
                                            "scope": "all", "mute": 0, "user": None, "watch": [], "mem": {}}
        return c

    def t(self, c: dict, key: str, **kw) -> str:
        s = T[c.get("lang", "en")].get(key) or T["en"][key]
        return s.format(**kw) if kw else s

    # ---------------------------------------------------------------- sending
    def send(self, cid: str, text: str, buttons=None, silent=False) -> bool:
        try:
            self.tg.send(cid, text, buttons, silent)
            time.sleep(0.05)
            return True
        except TelegramError as e:
            if e.status in (400, 403) and ("blocked" in e.text or "chat not found" in e.text or "deactivated" in e.text):
                with self.lock:   # it left: forget the chat
                    self.state["chats"].pop(cid, None)
            self.log(f"telegram: {str(e)[:160]}")
            return False

    def city_url(self, c: dict) -> str:
        env = (c.get("user") or {}).get("env") or "mainnet"
        return SITES[env] + "/#/city?alerts"

    def deliver_public(self, alerts: list[dict]) -> int:
        n = 0
        now = int(time.time() * 1000)
        for cid, c in list(self.state["chats"].items()):
            if not c.get("strike"):
                continue
            for a in alerts:
                kind = "listing" if a["kind"] == "status" else a["kind"]
                if not c["prefs"].get(kind, True):
                    continue
                if c.get("scope") == "majors" and a.get("market") and a["market"] not in MAJORS:
                    continue
                if c.get("mute", 0) > now and a["level"] != "alert":
                    continue
                lang = c.get("lang", "en")
                text = f"{KIND_ICON.get(a['kind'], ICON[a['level']])} <b>{esc(a['title'][lang])}</b>\n{esc(a['body'][lang])}"
                n += self.send(cid, text, [[{"text": self.t(c, "b_city"), "url": self.city_url(c)}]], silent=a["level"] == "info")
        return n

    def deliver_mine(self, cid: str, c: dict, msgs: list[dict]) -> int:
        n, now = 0, int(time.time() * 1000)
        sent = c["mem"].setdefault("sent", {})
        for m in msgs:
            if m["key"] in sent:
                continue
            sent[m["key"]] = now
            if not c["prefs"].get(m["kind"], True):
                continue
            urgent = m["level"] == "alert" and m["kind"] in ("risk", "copy")
            if c.get("mute", 0) > now and not urgent:
                continue
            title, body = m[c.get("lang", "en")]
            buttons = [[{"text": self.t(c, "b_app"), "url": m["url"]}]] if m.get("url") else None
            n += self.send(cid, f"{ICON[m['level']]} <b>{esc(title)}</b>\n{esc(body)}", buttons, silent=m["level"] == "info")
        if len(sent) > 400:
            for k in sorted(sent, key=sent.get)[:-300]:
                del sent[k]
        return n

    # ---------------------------------------------------------------- the minute: Strike for everyone
    def strike_minute(self) -> list[dict]:
        new = self.watch.tick()
        now = int(time.time() * 1000)
        if new or now - self.posted_at > 10 * 60_000:
            doc = self.watch.doc(now)
            for s in self.sites.values():
                try:
                    s.alerts(doc)
                except HttpError as e:
                    self.log(f"alerts: posting to {s.env} failed: {str(e)[:120]}")
            self.posted_at = now
        if new:
            self.deliver_public(new)
        return new

    # ---------------------------------------------------------------- every two minutes: each person's own
    def people(self) -> int:
        n = 0
        listed = {"mainnet": set(self.watch.tickers), "testnet": set()}
        for cid, c in list(self.state["chats"].items()):
            msgs: list[dict] = []
            u = c.get("user")
            if u:
                env = u.get("env", "mainnet")
                if not listed.get(env):
                    try:
                        listed[env] = set(self.strikes[env].tickers())
                    except HttpError:
                        listed[env] = set()
                mem = c["mem"].setdefault("agent", {})
                try:
                    msgs += self.agents.check(u["userId"], env, u.get("name") or "Your agent", mem)
                except (OSError, ValueError, KeyError) as e:
                    self.log(f"alerts: agent {u.get('userId')}: {e}")
                if u.get("accountId"):
                    aw = AccountWatch(self.strikes[env], listed[env], self.hl, self.copy_dir / "copy.db" if env == "mainnet" else None)
                    known = self._pilot_copy(u["userId"], env)
                    try:
                        coll = copies_from_collector(self.copy_dir / "copy.db", set(aw.accounts(u["accountId"]))) if env == "mainnet" else []
                        copies = {(x["lead"].lower(), x["follower"]): x for x in coll + known}
                        msgs += aw.check(u["accountId"], c["mem"].setdefault("acct", {}), list(copies.values()))
                    except (HttpError, OSError, ValueError, KeyError) as e:
                        self.log(f"alerts: account of {u.get('userId')}: {str(e)[:120]}")
            for w in c.get("watch") or []:
                aw = AccountWatch(self.strikes[w.get("env", "mainnet")], listed.get(w.get("env", "mainnet")) or listed["mainnet"], self.hl,
                                  self.copy_dir / "copy.db")
                try:
                    msgs += aw.check(w["account"], c["mem"].setdefault(f"w:{w['account']}", {}), None, w.get("label", ""), w.get("label", ""))
                except (HttpError, OSError, ValueError, KeyError) as e:
                    self.log(f"alerts: watch {short(w['account'])}: {str(e)[:120]}")
            if msgs:
                n += self.deliver_mine(cid, c, msgs)
        return n

    def _pilot_copy(self, user: str, env: str) -> list[dict]:
        try:
            st = (json.loads((self.copy_dir / f"pilot-{env}.json").read_text(encoding="utf-8")) or {}).get(user) or {}
        except (OSError, ValueError):
            return []
        if st.get("subAcct") and st.get("lead"):
            return [{"lead": st["lead"], "follower": st["subAcct"], "platform": st.get("platform") or "strike",
                     "status": "active" if st.get("sub") and not st.get("halted") else "stopped", "since": st.get("since")}]
        return []

    def sync_links(self) -> None:
        """Owners who unlinked on the site: their chats forget the agent."""
        for env, s in self.sites.items():
            try:
                users = {u["userId"]: u for u in s.linked()}
            except HttpError as e:
                self.log(f"alerts: sync with {env} failed: {str(e)[:120]}")
                continue
            for cid, c in list(self.state["chats"].items()):
                u = c.get("user")
                if not u or u.get("env") != env:
                    continue
                cur = users.get(u["userId"])
                if not cur or cid not in (cur.get("chats") or []):
                    c["user"] = None
                    c["mem"].pop("agent", None)
                    c["mem"].pop("acct", None)
                    self.send(cid, self.t(c, "unlinked"))
                else:
                    u.update(name=cur.get("name") or u.get("name"), accountId=cur.get("accountId") or u.get("accountId"))

    # ---------------------------------------------------------------- what people send
    def menu(self, c: dict) -> tuple[str, list]:
        now = int(time.time() * 1000)
        lines = [self.t(c, "hello"), "", self.t(c, "menu_strike", state=self.t(c, "on" if c.get("strike") else "off")),
                 self.t(c, "menu_agent", name=esc(c["user"]["name"])) if c.get("user") else self.t(c, "menu_noagent"),
                 self.t(c, "menu_watch", n=len(c.get("watch") or []))]
        if c.get("mute", 0) > now:
            lines.append(self.t(c, "menu_muted", t=time.strftime("%H:%M", time.gmtime(c["mute"] / 1000))))
        b = [[{"text": self.t(c, "b_strike") + (" ✅" if c.get("strike") else " ▫️"), "callback_data": "strike"},
              {"text": self.t(c, "b_now"), "callback_data": "now"}],
             [{"text": self.t(c, "b_agent"), "callback_data": "agent"}, {"text": self.t(c, "b_watch"), "callback_data": "watch"}],
             [{"text": self.t(c, "b_settings"), "callback_data": "settings"}, {"text": self.t(c, "b_help"), "callback_data": "help"}],
             [{"text": self.t(c, "b_unmute") if c.get("mute", 0) > now else self.t(c, "b_mute8"), "callback_data": "unmute" if c.get("mute", 0) > now else "mute:8"},
              {"text": self.t(c, "b_city"), "url": self.city_url(c)}]]
        return "\n".join(lines), b

    def settings(self, c: dict) -> tuple[str, list]:
        rows, p = [], c["prefs"]
        kinds = [k for k in STRIKE_KINDS] + list(MINE_KINDS)
        for i in range(0, len(kinds), 2):
            rows.append([{"text": ("✅ " if p.get(k, True) else "▫️ ") + self.t(c, "k_" + k), "callback_data": f"t:{k}"} for k in kinds[i:i + 2]])
        rows.append([{"text": self.t(c, "b_scope_majors") if c.get("scope") == "majors" else self.t(c, "b_scope_all"), "callback_data": "scope"},
                     {"text": "English" if c.get("lang") == "es" else "Español", "callback_data": "lang"}])
        rows.append([{"text": self.t(c, "b_back"), "callback_data": "menu"}])
        return self.t(c, "settings"), rows

    def now_text(self, c: dict) -> str:
        s = self.watch.snapshot()
        lines = [self.t(c, "now")]
        for sym, t in s["majors"].items():
            lines.append(f"<b>{label(sym)}</b> {price(t['price'])} ({pct(t['change'])})")
        if s["movers"]:
            lines.append(f"\n{self.t(c, 'now_movers')}: " + " · ".join(f"{label(m)} {pct(ch)}" for m, ch in s["movers"]))
        if s["funding"]:
            m, r = s["funding"][0]
            lines.append(f"{self.t(c, 'now_funding')}: {label(m)} {r * 100:+.3f}% {self.t(c, 'per_hour')}")
        if s["near"]:
            p = s["near"][0]
            lines.append(f"{self.t(c, 'now_near')}: {usd(p['notional'])} {p['side'].upper()} {label(p['symbol'])}, {p['dist'] * 100:.1f}% {self.t(c, 'to_liq')}")
        if s["oi"] and s["long_share"] is not None:
            lines.append(self.t(c, "now_oi", oi=usd(s["oi"]), share=f"{s['long_share'] * 100:.0f}%"))
        if s["volume"]:
            lines.append(self.t(c, "now_vol", v=usd(s["volume"])))
        news = self._news() or {}
        r = ((news.get("markets") or {}).get("BTC-USD") or {}).get("label")
        if r:
            lines.append(self.t(c, "now_news", r=esc(r)))
        nxt = [e for e in (news.get("events") or {}).get("next") or [] if e.get("kind") in ("fomc", "cpi", "nfp", "pce", "gdp")]
        if nxt:
            e = nxt[0]
            lines.append(self.t(c, "now_next", e=f"{esc(e.get('name'))}, {time.strftime('%d/%m %H:%M', time.gmtime(e['t'] / 1000))} UTC"))
        return "\n".join(lines)

    def status_text(self, c: dict) -> str:
        parts = []
        u = c.get("user")
        targets = ([(u["name"], u["env"], u["accountId"], "status_title")] if u and u.get("accountId") else []) + \
                  [(w.get("label") or short(w["account"]), w.get("env", "mainnet"), w["account"], "status_watch") for w in c.get("watch") or []]
        if not targets:
            return self.t(c, "noagent")
        for name, env, acc, head in targets:
            st = self.strikes[env]
            aw = AccountWatch(st, set(), self.hl)
            lines = [self.t(c, head, name=esc(name))]
            try:
                accts = aw.accounts(acc)
                pos = []
                for a, an in accts.items():
                    for p in (position_view(x) for x in st.positions(a)):
                        if p:
                            d = f" · {p['dist'] * 100:.1f}% {self.t(c, 'to_liq')}" if p["dist"] is not None else ""
                            pos.append(f"• {p['side'].upper()} {label(p['symbol'])} {p['size']:g} @ {price(p['entry'])} ({usd(p['notional'])}){d} — {esc(es_name(an) if c.get('lang') == 'es' else an)}")
                lines.append(f"{self.t(c, 'status_pos')}:\n" + "\n".join(pos) if pos else self.t(c, "status_none"))
                doc = st.account(acc)
                mb, mm = doc.get("margin_balance"), doc.get("maintenance_margin")
                if mb and float(mb) > 0 and mm is not None:
                    lines.append(self.t(c, "status_margin", r=f"{float(mm) / float(mb) * 100:.0f}%"))
            except HttpError:
                lines.append("—")
            if head == "status_title":
                cp = self._pilot_copy(u["userId"], env)
                lines.append(self.t(c, "status_copy", s=f"{short(cp[0]['lead'])} ({cp[0]['status']})" if cp else self.t(c, "copy_none")))
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    def link(self, cid: str, c: dict, code: str, who: str) -> str:
        site = self.sites.get("testnet" if code.startswith("q") else "mainnet")
        if not site:
            return self.t(c, "link_bad")
        try:
            u = site.lookup(code)
        except HttpError:
            u = {}
        if not u.get("userId"):
            return self.t(c, "link_bad")
        try:
            site.claim(code, cid, who)
        except HttpError:
            return self.t(c, "link_bad")
        c["user"] = {"userId": u["userId"], "env": site.env, "name": u.get("name") or "Your agent", "accountId": u.get("accountId"),
                     "address": u.get("address")}
        if u.get("lang") in ("en", "es"):
            c["lang"] = u["lang"]
        c["mem"].pop("agent", None)
        c["mem"].pop("acct", None)
        return self.t(c, "linked", name=esc(c["user"]["name"]), env="Strike testnet" if site.env == "testnet" else "Strike mainnet")

    def add_watch(self, c: dict, arg: str) -> str:
        if len(c.get("watch") or []) >= MAX_WATCH:
            return self.t(c, "watch_max", n=MAX_WATCH)
        env = "testnet" if arg.startswith("addr_test1") else "mainnet"
        st = self.strikes[env]
        try:
            doc = st.account(arg) if ACCOUNT.match(arg) else st.account(address=arg) if ADDRESS.match(arg) else {}
        except HttpError:
            doc = {}
        acc = doc.get("account_id")
        if not acc:
            return self.t(c, "watch_bad")
        if not any(w["account"] == acc for w in c["watch"]):
            c["watch"].append({"env": env, "account": acc, "label": short(acc)})
        subs = len(doc.get("sub_accounts") or [])
        return self.t(c, "watch_ok", name=esc(short(acc)), subs=self.t(c, "watch_subs", n=subs) if subs else "")

    def handle(self, upd: dict) -> None:
        with self.lock:
            if upd.get("callback_query"):
                return self._callback(upd["callback_query"])
            m = upd.get("message") or {}
            text, chat, frm = (m.get("text") or "").strip(), m.get("chat") or {}, m.get("from") or {}
            if not text or chat.get("type") != "private":
                return
            cid = str(chat["id"])
            c = self.chat(cid, frm.get("language_code"), frm.get("first_name") or "")
            cmd, _, arg = text.partition(" ")
            cmd, arg = cmd.split("@")[0].lower(), arg.strip()
            who = (frm.get("first_name") or "") + (f" (@{frm['username']})" if frm.get("username") else "")
            if cmd == "/start":
                if arg and CODE.match(arg):
                    self.send(cid, self.link(cid, c, arg, who[:60]))
                if arg == "strike":
                    c["strike"] = True
                self.send(cid, *self.menu(c))
            elif cmd == "/menu":
                self.send(cid, *self.menu(c))
            elif cmd in ("/strike", "/now"):
                self.send(cid, self.now_text(c), [[{"text": self.t(c, "b_city"), "url": self.city_url(c)}]])
            elif cmd == "/status":
                self.send(cid, self.status_text(c))
            elif cmd == "/watch":
                self.send(cid, self.add_watch(c, arg) if arg else self.t(c, "watch_ask"))
            elif cmd in ("/unwatch", "/list"):
                ws = c.get("watch") or []
                hit = [w for w in ws if arg and (w["account"] == arg or w["label"] == arg)] or (ws if arg == "all" else [])
                if cmd == "/unwatch" and hit:
                    c["watch"] = [w for w in ws if w not in hit]
                    for w in hit:
                        c["mem"].pop(f"w:{w['account']}", None)
                    self.send(cid, self.t(c, "unwatch_ok", name=", ".join(esc(w["label"]) for w in hit)))
                else:
                    items = "\n".join(f"• <code>{esc(w['account'])}</code>" for w in ws)
                    self.send(cid, self.t(c, "watch_list", items=items) + ("\n/unwatch &lt;account&gt; · /unwatch all" if ws else "") if ws else self.t(c, "watch_none"))
            elif cmd == "/settings":
                self.send(cid, *self.settings(c))
            elif cmd == "/mute":
                h = max(1, min(72, int(arg))) if arg.isdigit() else 8
                c["mute"] = int(time.time() * 1000) + h * 3_600_000
                self.send(cid, self.t(c, "muted", h=h))
            elif cmd == "/unmute":
                c["mute"] = 0
                self.send(cid, self.t(c, "unmuted"))
            elif cmd == "/unlink":
                self._unlink(cid, c)
            elif cmd == "/lang":
                c["lang"] = "es" if arg.startswith("es") else "en"
                self.send(cid, *self.menu(c))
            elif cmd == "/help":
                self.send(cid, self.t(c, "help"))
            elif cmd == "/stop":
                self.state["chats"].pop(cid, None)
                self.send(cid, T[c.get("lang", "en")]["stopped"])
            elif ACCOUNT.match(text) or ADDRESS.match(text):   # an account pasted on its own: watch it
                self.send(cid, self.add_watch(c, text))
            else:
                self.send(cid, self.t(c, "unknown"))

    def _unlink(self, cid: str, c: dict) -> None:
        u = c.get("user")
        if u and u.get("env") in self.sites:
            try:
                self.sites[u["env"]].unlink(u["userId"], cid)
            except HttpError:
                pass
        c["user"] = None
        c["mem"].pop("agent", None)
        c["mem"].pop("acct", None)
        self.send(cid, self.t(c, "unlinked"))

    def _callback(self, q: dict) -> None:
        cid, data = str(((q.get("message") or {}).get("chat") or {}).get("id")), q.get("data") or ""
        mid = (q.get("message") or {}).get("message_id")
        c = self.chat(cid, (q.get("from") or {}).get("language_code"))
        try:
            self.tg.answer(q["id"])
        except TelegramError:
            pass
        view = "menu"
        if data.startswith("t:") and data[2:] in STRIKE_KINDS + MINE_KINDS:
            c["prefs"][data[2:]] = not c["prefs"].get(data[2:], True)
            view = "settings"
        elif data == "scope":
            c["scope"] = "all" if c.get("scope") == "majors" else "majors"
            view = "settings"
        elif data == "lang":
            c["lang"] = "en" if c.get("lang") == "es" else "es"
            view = "settings"
        elif data == "strike":
            c["strike"] = not c.get("strike")
        elif data.startswith("mute:"):
            c["mute"] = int(time.time() * 1000) + int(data[5:]) * 3_600_000
        elif data == "unmute":
            c["mute"] = 0
        elif data in ("settings", "menu"):
            view = data
        elif data == "now":
            self.send(cid, self.now_text(c), [[{"text": self.t(c, "b_city"), "url": self.city_url(c)}]])
            return
        elif data == "agent":
            self.send(cid, self.status_text(c) if c.get("user") else self.t(c, "noagent"))
            return
        elif data == "watch":
            self.send(cid, self.t(c, "watch_ask") + "\n\n" + (self.t(c, "watch_list", items="\n".join(f"• <code>{esc(w['account'])}</code>" for w in c["watch"]))
                                                             if c.get("watch") else self.t(c, "watch_none")))
            return
        elif data == "help":
            self.send(cid, self.t(c, "help"))
            return
        text, buttons = self.settings(c) if view == "settings" else self.menu(c)
        if mid:
            try:
                self.tg.edit(cid, mid, text, buttons)
            except TelegramError:
                self.send(cid, text, buttons)

    # ---------------------------------------------------------------- run
    def setup(self) -> None:
        for lang, items in (("en", [("menu", "Alerts and settings"), ("strike", "Strike right now"), ("status", "My agent, accounts and copies"),
                                     ("watch", "Watch a Strike account"), ("settings", "Choose your alerts"), ("mute", "Silence for some hours"),
                                     ("help", "What I do")]),
                            ("es", [("menu", "Alertas y ajustes"), ("strike", "Strike ahora mismo"), ("status", "Mi agente, cuentas y copias"),
                                    ("watch", "Vigilar una cuenta de Strike"), ("settings", "Elegir tus alertas"), ("mute", "Silencio unas horas"),
                                    ("help", "Qué hago")])):
            try:
                self.tg.commands(None if lang == "en" else lang, items)
            except TelegramError as e:
                self.log(f"telegram: commands: {e}")
        # what Telegram shows before Start, and on the bot's profile
        for lang, desc, line in (
                (None, "Strike Finance's moments worth a look: big moves, extreme funding, large positions close to liquidation, whales, new "
                       "and halted markets, the security alarm, the big US releases, the Copy Arena's top traders. And everything about your "
                       "own agent, account and copies: liquidation risk, a trade your copy didn't take, a position the trader already left, "
                       "the trader in trouble. By EdgeCraft-StrikeCity.",
                 "Strike Finance alerts, and your own agent, accounts and copies watched every minute."),
                ("es", "Los momentos de Strike Finance que merecen un vistazo: grandes movimientos, funding extremo, posiciones grandes cerca de "
                       "la liquidación, ballenas, mercados nuevos y pausados, la alarma de seguridad, los grandes datos de EE. UU., los mejores "
                       "traders de la Copy Arena. Y todo sobre tu agente, tu cuenta y tus copias: riesgo de liquidación, una operación que tu "
                       "copia no tomó, una posición que el trader ya cerró, el trader en apuros. Por EdgeCraft-StrikeCity.",
                 "Alertas de Strike Finance, y tu agente, tus cuentas y tus copias vigilados cada minuto.")):
            try:
                self.tg.call("setMyDescription", description=desc, language_code=lang)
                self.tg.call("setMyShortDescription", short_description=line, language_code=lang)
            except TelegramError as e:
                self.log(f"telegram: description: {e}")

    def poll_forever(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                ups = self.tg.updates(self.state.get("offset", 0), wait=25)
            except TelegramError as e:
                self.log(f"telegram: updates: {str(e)[:160]}")
                stop.wait(5)
                continue
            for u in ups:
                self.state["offset"] = max(self.state.get("offset", 0), u["update_id"] + 1)
                try:
                    self.handle(u)
                except Exception as e:   # one bad message never stops the bot
                    self.log(f"telegram: handling {u.get('update_id')}: {type(e).__name__}: {str(e)[:160]}")
            if ups:
                self.save()

    def run(self, every: float = 60.0, people_every: float = 120.0, sync_every: float = 600.0) -> None:
        self.setup()
        stop = threading.Event()
        threading.Thread(target=self.poll_forever, args=(stop,), daemon=True, name="telegram-poll").start()
        last_people = last_sync = 0.0
        while True:
            t0 = time.time()
            try:   # without the lock: replies to people never wait for these reads
                new = self.strike_minute()
                sent = 0
                if t0 - last_people >= people_every:
                    sent = self.people()
                    last_people = t0
                if t0 - last_sync >= sync_every:
                    self.sync_links()
                    last_sync = t0
                self.save()
                if new or sent:
                    self.log(f"alerts: {len(new)} Strike alerts, {sent} personal messages, {len(self.state['chats'])} chats")
            except Exception as e:   # keep watching: the next minute is another chance
                self.log(f"alerts: cycle failed: {type(e).__name__}: {str(e)[:200]}")
            time.sleep(max(1.0, every - (time.time() - t0)))
