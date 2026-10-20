"""Live conformance checks of the Strike API against what the adapter expects (read-only; no orders, ever)."""

from __future__ import annotations

import time

from ..net import HttpError
from .auth import ApiWalletSigner
from .client import MAINNET, TESTNET, StrikeClient


def _p(ok: bool | None, label: str, detail: str = "") -> bool:
    tag = {True: "PASS", False: "FAIL", None: "NOTE"}[ok]
    print(f"[{tag}] {label}" + (f" - {detail}" if detail else ""))
    return ok is not False


def run_public_checks(env: str) -> int:
    c = StrikeClient(TESTNET if env == "testnet" else MAINNET)
    ok = True
    try:
        off = c.sync_clock()
        ok &= _p(abs(off) < 60, "server time / clock drift", f"{off:+.2f}s (signatures need < 180s)")
        mk = c.markets()
        ok &= _p(all(s in mk for s in ("BTC-USD", "ETH-USD", "SOL-USD")), "markets BTC/ETH/SOL listed",
                 f"{len(mk)} markets")
        for s in ("BTC-USD", "ETH-USD", "SOL-USD"):
            if s in mk:
                m = mk[s]
                _p(m.tradable, f"{s} tradable", f"status={m.status} tick={m.tick} step={m.step} min_qty={m.min_qty} "
                                                f"min_notional={m.min_notional} tier0 max lev={m.tiers[0].max_leverage}x")
        ft = c.fee_tiers()
        raw = c._public("/v2/fee-tiers")
        pascal = isinstance(raw, dict) and raw.get("feeTiers") and "Tier" in raw["feeTiers"][0]
        _p(None if pascal else True, "fee tiers parsed", f"tier0 taker {ft[0].taker:.5f} maker {ft[0].maker:.5f}"
           + (" (live keys are PascalCase; OpenAPI says camelCase)" if pascal else ""))
        pr = c.premium("BTC-USD")
        _p(pr["mark"] > 0, "premiumIndex BTC-USD", f"mark {pr['mark']} index {pr['index']} funding/h "
                                                   f"{pr['funding_rate']:+.7f} (list + 'fundingRate', not the documented object)")
        bt = c.book_ticker("BTC-USD")
        bid, ask = float(bt["bidPrice"]), float(bt["askPrice"])
        _p(ask > bid > 0, "bookTicker BTC-USD", f"spread {(ask - bid) / ((ask + bid) / 2) * 1e4:.2f} bps")
        for pt in ("last", "mark", "index"):
            k = c.klines("BTC-USD", "4h", limit=300, price_type=pt)
            zero = sum(1 for x in k if float(x[5]) == 0)
            _p(len(k) > 0, f"klines BTC-USD 4h priceType={pt}", f"{len(k)} bars, zero-volume {zero} "
               f"({100 * zero / max(1, len(k)):.0f}%), first {time.strftime('%Y-%m-%d', time.gmtime(k[0][0] / 1000))}")
    except HttpError as e:
        ok = _p(False, "request failed", str(e))
    print("RESULT:", "OK" if ok else "PROBLEMS")
    return 0 if ok else 1


def run_auth_checks(env: str) -> int:
    try:
        signer = ApiWalletSigner.from_env()
    except Exception as e:
        _p(False, "API wallet keys", f"{e} - run `smartflow keys {env}` and register the public key")
        return 1
    c = StrikeClient(TESTNET if env == "testnet" else MAINNET, signer)
    c.sync_clock()
    ok = True
    print(f"API wallet public key {signer.public_key[:10]}… on {env}")
    try:
        a = c.account()
        ok &= _p(True, "GET /v2/account", f"account {a.account_id[:8]}… margin balance {a.margin_balance:.2f} "
                                          f"available {a.available_balance:.2f}")
        ps = c.positions()
        _p(True, "GET /v2/positions", f"{len(ps)} open: " + ", ".join(f"{p.symbol} {p.size:+g}@{p.entry_price:g}" for p in ps))
        oo = c.open_orders()
        _p(True, "GET /v2/openOrders", f"{len(oo)} open orders" + (f"; builder on first: {oo[0].builder_code}" if oo else ""))
        f = c.fills(limit=5)
        _p(True, "GET /v2/history/fill", f"{len(f)} recent fills")
        try:
            sub = c._signed("GET", "/v2/sub-accounts")
            subs = sub.get("sub_accounts", []) if isinstance(sub, dict) else []
            _p(None, "GET /v2/sub-accounts", f"{len(subs)} sub-accounts (empty if this key is bound to a sub-account)")
        except HttpError as e:
            _p(None, "GET /v2/sub-accounts", str(e)[:120])
    except HttpError as e:
        ok = _p(False, "signed request", f"{e.status} {e.body[:160]} (is the public key registered on this env?)")
    print("RESULT:", "AUTH OK (read-only)" if ok else "PROBLEMS")
    return 0 if ok else 1
