"""Copy with your agent: each owner's copy plan, signed with their wallet on the site, carried out on Strike's own copy
trading. The site keeps the plans (``GET /api/internal/copyplans``, HMAC); this service, on the agents' host where the
users' API-wallet keys are, does what each plan asks and reports how it goes (``POST /api/internal/copystatus``).

Every copy runs in a sub-account of its own that Strike creates and funds from the owner's account (managed copy): the
agent's trading account never mixes with the copy, and what the copy can lose is what went into it. Strike itself ends
the copy at the owner's stop-loss. The plan says:

- whom: one trader (manual), or let the agent choose (pilot): the best by Strike City's score among the traders the
  owner's rules allow, kept while it still meets them, reviewed every few hours, changed at most a few times a week;
- when: until a date, paused while the News Tower's security alarm is on (a hack, an exchange's halt or insolvency),
  and, if the owner wants, around the big scheduled US releases (Fed decisions, CPI, jobs, PCE, GDP);
- how: fixed ratio (an amount, every lead order scaled to it) or fixed margin per entry, the stop-loss, the leverage
  of the copy's sub-account and the markets never to open;
- where: a sub-account the owner chose, or automatically one of theirs that copies nobody and has the money (the last
  one used first), and only when none does, a new one that Strike creates and funds from the main account. A
  sub-account runs one copy at a time, so a new copy reuses a free one instead of piling up sub-accounts.

Balances are read before asking, so the owner is told plainly when the money is not there. Money only moves between an
owner's accounts in Strike's own app (Strike keeps those transfers to it), so a sub-account is topped up there.

A stop-loss Strike applied, or a copy Strike refused, halts the plan until its owner signs it again. Nothing here
moves money out of Strike: what is left in the copy's sub-account goes back to the main account from Strike's app.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Callable

from ..net import HttpError

HOUR = 3_600_000
DAY = 24 * HOUR
WEEK = 7 * DAY
PILOT_KEEP_TOP = 5          # the pilot keeps its trader while it is still among the best few that meet the rules
ALARM_MS = DAY              # a security alarm counts for a day (the News Tower's rule)
MIN_COPY = 20.0             # $: Strike's minimum copy amount and margin per entry (GET /v2/copy/lead-traders)
MAX_COPIERS = 40            # Strike's limit of copiers per trader
LOG_KEEP = 30
ALARM_CATS = ("security", "exchange")   # a hack; an exchange's halt or insolvency
MACRO_KINDS = ("fomc", "cpi", "nfp", "pce", "gdp")
MACRO_BEFORE, MACRO_AFTER = 30 * 60_000, HOUR   # the copy waits from 30 min before a release to an hour after it
HIST_EVERY, HIST_KEEP = 2 * HOUR, 84            # each sub-account's equity: a point every 2 hours, a week of them
ACCOUNTS_KEEP = 6


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def security_alarm(news: dict | None, now: int) -> dict | None:
    """The News Tower's security alarm (any market): a hack, or an exchange's halt or insolvency, scored -30 or worse
    in the last day."""
    for h in (news or {}).get("headlines") or []:
        if h.get("cat") in ALARM_CATS and h.get("catalyst") and (h.get("score") or 0) <= -30 and now - int(h.get("t") or 0) <= ALARM_MS:
            return h
    return None


def macro_window(news: dict | None, now: int) -> dict | None:
    """A big scheduled US release on the News Tower's calendar, from 30 minutes before it to an hour after."""
    ev = (news or {}).get("events") or {}
    for e in list(ev.get("next") or []) + list(ev.get("just") or []):
        if e.get("kind") in MACRO_KINDS and -MACRO_AFTER <= int(e.get("t") or 0) - now <= MACRO_BEFORE:
            return e
    return None


def candidates(doc: dict | None, plan: dict) -> list[dict]:
    """The traders the pilot may choose, best first: Strike City's score at or above the owner's minimum, on the
    platforms they allow, a copy amount Strike can work with for their budget, and not someone whose copiers lost."""
    p = plan.get("pilot") or {}
    platforms = set(p.get("platforms") or ["strike", "hyperliquid"])
    budget = plan["sizing"].get("amount") if plan["sizing"].get("kind") == "ratio" else plan["sizing"].get("funding")
    out = []
    for t in (doc or {}).get("traders") or []:
        if t.get("platform") not in platforms or (t.get("city") or 0) < float(p.get("minScore") or 0):
            continue
        if t.get("direction") not in (None, "copy"):
            continue
        rec = t.get("recommended")
        if rec and budget and rec > budget:
            continue
        c = t.get("copiers") or {}
        if (c.get("n", 0) >= 3 and c.get("pnl", 0) < 0) or c.get("active", 0) >= MAX_COPIERS:
            continue
        out.append(t)
    return sorted(out, key=lambda t: -(t.get("city") or 0))


class Plans:
    """The site's two copy endpoints (the fleet's HMAC scheme)."""

    def __init__(self, site):
        self.site = site

    def plans(self) -> dict:
        return self.site._req("GET", "/api/internal/copyplans", None, "GET /api/internal/copyplans")

    def report(self, env: str, status: list[dict]) -> dict:
        raw = json.dumps({"env": env, "status": status}, separators=(",", ":"))
        return self.site._req("POST", "/api/internal/copystatus", raw.encode(), raw)


class CopyPilot:
    def __init__(self, plans: Plans, client_for: Callable[[str], object], env: str, state_path: Path,
                 copy_doc: Callable[[], dict | None], news_doc: Callable[[], dict | None], log: Callable[[str], None] = print):
        self.plans, self.client_for, self.env = plans, client_for, env
        self.state_path, self.copy_doc, self.news_doc, self.log = Path(state_path), copy_doc, news_doc, log
        self.state: dict[str, dict] = self._load()

    # ------------------------------------------------------------------ state
    def _load(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, self.state_path)

    @staticmethod
    def _note(st: dict, now: int, kind: str, **args) -> None:
        st.setdefault("log", []).append({"t": now, "kind": kind, **{k: v for k, v in args.items() if v is not None}})
        st["log"] = st["log"][-LOG_KEEP:]

    # ------------------------------------------------------------------ one pass
    def tick(self, now: int | None = None) -> dict:
        now = now or int(time.time() * 1000)
        doc = self.plans.plans()
        if doc.get("env") not in (None, self.env):
            raise RuntimeError(f"the site is {doc.get('env')}, this pilot is {self.env}")
        copy, news = self.copy_doc(), self.news_doc()
        out = []
        for p in doc.get("plans") or []:
            uid = p["userId"]
            st = self.state.setdefault(uid, {})
            try:
                self._one(p, st, copy, news, now)
            except HttpError as e:
                st["error"] = f"Strike {e.status}: {str(e.body)[:200]}"
                self._note(st, now, "error", status=e.status, text=str(e.body)[:200])
                self.log(f"{uid}: Strike {e.status} {str(e.body)[:200]}")
            except Exception as e:   # one owner's problem never stops the others
                st["error"] = repr(e)[:200]
                self.log(f"{uid}: {e!r}")
            out.append(self._status(uid, p, st, now))
        self._save()
        if out:
            self.plans.report(self.env, out)
        return {"plans": len(out), "copying": sum(1 for s in out if s["state"] == "copying")}

    def _one(self, p: dict, st: dict, copy: dict | None, news: dict | None, now: int) -> None:
        plan, version = p["plan"], int(p["version"])
        c = self.client_for(p["pub"])
        fresh = st.get("version") != version
        if fresh:   # a plan its owner just signed: whatever halted the last one is cleared
            st.update(version=version, halted=None, error=None)
            self._note(st, now, "plan", mode=plan["mode"])
        self._accounts(c, p, st, now)   # the owner's sub-accounts, which copy whom, and their equity over time
        # where the copy really is: Strike's own reading
        live = None
        if st.get("sub"):
            rows = {r.get("subscription_id"): r for r in c.copy_subscriptions()}
            live = rows.get(st["sub"])
            st["row"] = live
            if live is None or live.get("status") != "active":
                reason = (live or {}).get("stop_reason")
                self._note(st, now, "ended", lead=st.get("lead"), reason=reason or "stopped on Strike")
                st.update(sub=None, lead=None, platform=None)
                if reason == "stop_loss":
                    st["halted"] = "stop_loss"
                live = None
        if st.get("pending"):   # a managed copy still being set up: ask again with the same request
            self._subscribe(c, p, st, None, None, now)
            return
        want, why = self._target(p, st, copy, news, now)
        if live and (want is None or want["id"].lower() != str(st.get("lead") or "").lower()):
            c.copy_stop(st["sub"], st.get("subAcct"))
            self._note(st, now, "stop", lead=st.get("lead"), reason=why)
            if want is not None:
                st.setdefault("switches", []).append(now)
            st.update(sub=None, lead=None, platform=None, row=None)
            live = None
        if live and fresh:   # the same trader with new settings
            if (st.get("sizing") or {}) != plan["sizing"]:
                c.copy_stop(st["sub"], st.get("subAcct"))
                self._note(st, now, "stop", lead=st.get("lead"), reason="new_amount")
                st.update(sub=None, row=None)
                live = None
            else:
                c.copy_update(st["sub"], self._limits(plan) | ({"sub_account_id": st["subAcct"]} if st.get("subAcct") else {}))
                self._note(st, now, "update", lead=st.get("lead"))
        if not live and want is not None:
            why = self._subscribe(c, p, st, want, why, now) or why
        st["why"] = why

    def _target(self, p: dict, st: dict, copy: dict | None, news: dict | None, now: int) -> tuple[dict | None, str]:
        """Whom the plan wants copied right now, and why (or why nobody)."""
        plan = p["plan"]
        if plan["mode"] == "off":
            return None, "off"
        if st.get("halted"):
            return None, st["halted"]
        if plan.get("until") and now >= int(plan["until"]):
            return None, "until"
        if plan.get("alarmPause") and security_alarm(news, now):
            return None, "alarm"
        if plan.get("macroPause") and macro_window(news, now):
            return None, "macro"
        if plan["mode"] == "manual":
            return {"id": plan["lead"], "platform": plan["platform"]}, "manual"
        # the pilot: keep its trader while it still qualifies, review every few hours, change at most a few times a week
        cands = candidates(copy, plan)
        if not cands:
            return None, "none_qualify"
        cur = str(st.get("lead") or "").lower() if st.get("sub") else ""
        ids = [t["id"].lower() for t in cands]
        review = int(float((plan.get("pilot") or {}).get("review") or 24) * HOUR)
        keep = {"id": st.get("lead"), "platform": st.get("platform")}
        if cur in ids:                                   # it still meets the rules
            if now < int(st.get("reviewAt") or 0):
                return keep, "keeps"
            st["reviewAt"] = now + review
            if ids.index(cur) < PILOT_KEEP_TOP:          # reviewed: still among the best few
                return keep, "keeps"
        st["switches"] = [t for t in st.get("switches") or [] if now - t < WEEK]
        if cur and len(st["switches"]) >= int((plan.get("pilot") or {}).get("maxSwitches") or 2):
            # no more changes this week: keep one that still qualifies, stop one that does not
            return (keep, "switch_limit") if cur in ids else (None, "switch_limit")
        st["reviewAt"] = now + review
        best = cands[0]
        return {"id": best["id"], "platform": best["platform"]}, ("better" if cur else "best")

    @staticmethod
    def _limits(plan: dict) -> dict:
        out = {"stop_loss_amount": f"{float(plan['stopLoss']):.2f}", "excluded_symbols": list(plan.get("excluded") or [])}
        if plan["sizing"]["kind"] == "fixed":   # no lump sum reserved: cap what it can hold in all
            out["max_margin_total"] = f"{float(plan['sizing']['funding']):.2f}"
        return out

    def _accounts(self, c, p: dict, st: dict, now: int) -> list[dict]:
        """The owner's active sub-accounts: name, equity, available money, whom each one copies now (a sub-account runs
        one copy at a time), and each one's equity over time for its owner's chart."""
        try:
            rows = c.sub_accounts()
            busy = {r.get("account_id"): r.get("lead_account_id") for r in c.copy_subscriptions()
                    if r.get("status") == "active" and r.get("account_id") and r.get("account_id") != p["accountId"]}
        except HttpError:
            return st.get("accounts") or []
        out = [{"id": r["account_id"], "name": str(r.get("name") or "")[:40], "equity": _num(r.get("equity")),
                "available": _num(r.get("available_balance")) or 0.0, "busy": busy.get(r["account_id"])}
               for r in rows if r.get("account_id") and r.get("status") == "active"]
        hist = st.setdefault("hist", {})
        for a in out:
            pts = hist.setdefault(a["id"], [])
            if a["equity"] is not None and (not pts or now - pts[-1][0] >= HIST_EVERY):
                pts.append([now, round(a["equity"], 2)])
                del pts[:-HIST_KEEP]
        for gone in [k for k in hist if k not in {a["id"] for a in out}]:
            del hist[gone]
        st["accounts"] = out
        return out

    def _subscribe(self, c, p: dict, st: dict, want: dict | None, why: str | None, now: int) -> str | None:
        """Asks Strike for the copy (or for how its setup goes): in a sub-account of the owner's that copies nobody, or
        in a new one Strike creates. "funds" when the money is not there yet, "account_busy" while the chosen sub-account
        still runs another copy."""
        plan = p["plan"]
        use = None   # an existing sub-account the copy runs in
        if st.get("pending"):
            body = st["pending"]
        else:
            s = plan["sizing"]
            body = {"lead_account_id": want["id"].lower() if want["platform"] == "hyperliquid" else want["id"],
                    "platform": want["platform"], **self._limits(plan)}
            total = float(s["amount"] if s["kind"] == "ratio" else s["funding"])
            enough = lambda v: v >= MIN_COPY and (s["kind"] != "fixed" or v >= float(s["margin"]))   # noqa: E731
            subs = st.get("accounts") if st.get("accounts") is not None else self._accounts(c, p, st, now)
            free = sorted((a for a in subs if not a["busy"]), key=lambda a: (a["id"] != st.get("subAcct"), -a["available"]))
            main = _num(c.account_of(None).get("available_balance")) or 0.0
            pick, source, put = plan.get("account") or "auto", None, 0.0
            if pick not in ("auto", "new"):   # the sub-account its owner chose
                a = next((x for x in subs if x["id"] == pick), None)
                if a is None or a["busy"]:
                    kind = "account_gone" if a is None else "account_busy"
                    if (st.get("log") or [{}])[-1].get("kind") != kind:
                        self._note(st, now, kind, lead=a["busy"] if a else None)
                    return kind
                use, put = a, min(total, a["available"])
            else:
                full = [a for a in free if a["available"] >= total]
                some = [a for a in free if enough(a["available"])]
                if pick == "auto" and full:              # a free sub-account that has the money: no new one
                    use, put = full[0], total
                elif pick == "auto" and some:            # one with less: the copy runs with what it holds, never a new
                    use, put = some[0], some[0]["available"]   # sub-account while one is free (topped up in Strike's app)
                    if (st.get("log") or [{}])[-1].get("kind") != "short":
                        self._note(st, now, "short", available=round(put, 2), account=use["name"])
                elif main >= total:                      # a new one, funded from the main account
                    source, put = p["accountId"], total
                elif full:                               # or from a free sub-account that has it
                    source, put = full[0]["id"], total
                else:   # nothing covers it: the most there is, if that is enough for a copy at all
                    best = free[0] if free and free[0]["available"] > main else None
                    if best and pick == "auto":
                        use, put = best, best["available"]
                    else:
                        source, put = (best["id"], best["available"]) if best else (p["accountId"], main)
            if not enough(put):
                # not stopped for good: it tries again each pass, so a deposit (or a transfer in Strike's app) is all it takes
                kind = "no_funds_sub" if use else "no_funds"
                if (st.get("log") or [{}])[-1].get("kind") != kind:
                    self._note(st, now, kind, available=round(use["available"] if use else main, 2), account=use["name"] if use else None)
                return "funds_sub" if use else "funds"
            if s["kind"] == "ratio":
                body.update(copy_mode="fixed_ratio", copy_amount=f"{put:.2f}")
            else:
                body.update(copy_mode="fixed_amount", margin_per_entry_order=f"{float(s['margin']):.2f}")
                if not use:
                    body["funding_amount"] = f"{put:.2f}"
            if use:   # an existing sub-account: Strike copies from it (its own margin settings stay as they are)
                body["sub_account_id"] = use["id"]
                return self._subscribe_in(c, st, body, use, why, now, plan["sizing"])
            body.update(auto_create_sub_account=True, request_id=str(uuid.uuid4()), source_account_id=source,
                        margin_settings={"default_margin_mode": "isolated", "default_leverage": int(plan.get("leverage") or 3)})
            st["pending"] = body   # kept before sending: a timeout is resumed with the same request
            st["wantWhy"] = why
            self._save()
        try:
            r = c.copy_subscribe(body)
        except HttpError as e:
            if 400 <= e.status < 500 and e.status != 429:   # Strike refused it: its owner decides what next
                st.update(pending=None, halted="refused")
                self._note(st, now, "refused", lead=body["lead_account_id"], status=e.status, text=str(e.body)[:200])
                return
            raise
        status = r.get("status")
        if r.get("sub_account_id"):
            st["subAcct"] = r["sub_account_id"]
        if status == "active" and r.get("subscription_id"):
            st.update(pending=None, sub=r["subscription_id"], lead=body["lead_account_id"], platform=body["platform"], since=now,
                      sizing=plan["sizing"], row=None)
            st.pop("accounts", None)   # a new sub-account: read them again on the next pass
            self._note(st, now, "start", lead=body["lead_account_id"], reason=st.pop("wantWhy", None))
        elif status in ("refunded", "refund_failed", "failed"):
            st.update(pending=None, halted="refused")
            self._note(st, now, "refused", lead=body["lead_account_id"], text=r.get("error"))
        elif (st.get("log") or [{}])[-1].get("step") != status:   # still being set up: each step once in its log
            self._note(st, now, "setup", step=status)

    def _subscribe_in(self, c, st: dict, body: dict, use: dict, why: str | None, now: int, sizing: dict) -> str | None:
        """The copy in one of the owner's sub-accounts. Strike answers at once (no setup); a 409 means that account
        still runs a copy (one just stopped can take a moment): the next pass asks again."""
        lead = body["lead_account_id"]
        try:
            r = c.copy_subscribe(body)
        except HttpError as e:
            if e.status == 409:   # maybe it is already copying this trader there: take that copy as it is
                row = next((x for x in c.copy_subscriptions() if x.get("account_id") == use["id"] and x.get("status") == "active"
                            and str(x.get("lead_account_id") or "").lower() == lead.lower()), None)
                if row is None:
                    if (st.get("log") or [{}])[-1].get("kind") != "account_busy":
                        self._note(st, now, "account_busy", text=str(e.body)[:200])
                    return "account_busy"
                r = {"status": "active", "subscription_id": row.get("subscription_id")}
            elif 400 <= e.status < 500 and e.status != 429:   # Strike refused it: its owner decides what next
                st.update(halted="refused")
                self._note(st, now, "refused", lead=lead, status=e.status, text=str(e.body)[:200])
                return None
            else:
                raise
        if r.get("status") == "active" and r.get("subscription_id"):
            st.update(subAcct=use["id"], sub=r["subscription_id"], lead=lead, platform=body["platform"], since=now,
                      sizing=sizing, row=None)
            use["busy"] = lead   # what this pass reports: that sub-account copies this trader now
            self._note(st, now, "start", lead=lead, reason=why, account=use["name"] or None)
        return None

    # ------------------------------------------------------------------ what the owner sees
    def _status(self, uid: str, p: dict, st: dict, now: int) -> dict:
        row = st.get("row") or {}
        state = ("copying" if st.get("sub") else "starting" if st.get("pending") else "halted" if st.get("halted")
                 else "off" if p["plan"]["mode"] == "off" else "waiting")
        return {
            "userId": uid, "state": state, "why": st.get("halted") or st.get("why"), "version": st.get("version"),
            "lead": st.get("lead"), "platform": st.get("platform"), "since": st.get("since") if st.get("sub") else None,
            "subAccount": st.get("subAcct"), "reviewAt": st.get("reviewAt"), "error": st.get("error"),
            "copy": ({k: _num(row.get(k)) for k in ("copy_amount", "margin_per_entry_order", "total_margin", "total_worth", "realized_pnl",
                                                     "pnl", "total_volume", "stop_loss_amount")} | {"orders": row.get("filled_order_count")})
                    if row else None,
            "log": (st.get("log") or [])[-15:], "at": now,
            "accounts": [a | {"history": (st.get("hist") or {}).get(a["id"], [])} for a in (st.get("accounts") or [])[:ACCOUNTS_KEEP]],
        }

    def run(self, every: float = 60) -> None:
        while True:
            try:
                r = self.tick()
                if r["plans"]:
                    self.log(f"copy pilot: {r['plans']} plans, {r['copying']} copying")
            except Exception as e:
                self.log(f"copy pilot: {e!r}")
            time.sleep(every)
