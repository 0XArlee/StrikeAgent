"""Smallest possible REAL round trip on Strike, to verify what testnet cannot (its books are broken):
bracket entry fill -> stop leg resting -> reduce-only exit -> leftover legs cancelled -> fills and fees.

    python -m smartflow.strike.live_probe mainnet --confirm "I ACCEPT A REAL ~10 USD ORDER"

Hard limits: one market (BTC-USD by default), notional capped at MAX_NOTIONAL_USD, spread must be tight, the account
must be flat in that market and have no open orders there. Uses secrets/strike_<env>.env, or with --pool-key PUB a
user's API wallet from the fleet's key pool (builder connect; run it on the agents' host, the key never leaves it).
Writes <out>/live_probe_<ts>.json (--out, default reports). Cost: two taker fees on ~10 USD (~0.01 USD) plus spread.
"""

from __future__ import annotations

import json
import math
import sys
import time
import uuid
from decimal import ROUND_UP, Decimal
from pathlib import Path

from .auth import ApiWalletSigner
from .client import MAINNET, TESTNET, BuilderFee, StrikeClient

MAX_NOTIONAL_USD = 15.0
CONFIRM = "I ACCEPT A REAL ~10 USD ORDER"


def main(argv: list[str]) -> int:
    env = argv[1] if len(argv) > 1 else "mainnet"
    if "--confirm" not in argv or argv[argv.index("--confirm") + 1] != CONFIRM:
        print(f'refusing: add --confirm "{CONFIRM}"')
        return 2
    symbol = argv[argv.index("--symbol") + 1] if "--symbol" in argv else "BTC-USD"
    builder = None
    if "--builder" in argv:   # --builder CODE:BPS  (verifies attribution once you are a registered builder)
        code, bps = argv[argv.index("--builder") + 1].split(":")
        builder = BuilderFee(code, int(bps), approved_bps=int(bps))
    max_spread = float(argv[argv.index("--max-spread") + 1]) if "--max-spread" in argv else 5.0
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else Path("reports")
    if "--pool-key" in argv:   # a connected user's API wallet (the fleet's encrypted pool on this host)
        from ..live.keypool import KeyPool
        keys = argv[argv.index("--keys") + 1] if "--keys" in argv else "/var/lib/smartflow/keys"
        master = argv[argv.index("--master") + 1] if "--master" in argv else "/etc/smartflow/keys.key"
        signer = KeyPool.from_files(Path(keys), Path(master), env).signer(argv[argv.index("--pool-key") + 1])
    else:
        from ..cli import _load_secrets
        _load_secrets(env)
        signer = ApiWalletSigner.from_env()
    c = StrikeClient(MAINNET if env == "mainnet" else TESTNET, signer, builder)
    c.sync_clock()
    log: dict = {"env": env, "symbol": symbol, "builder": builder and [builder.code, builder.fee_bps], "steps": []}

    def rec(name, value):
        log["steps"].append({"t": time.time(), "step": name, "value": value})
        print(f"- {name}: {json.dumps(value, default=str)[:300]}")
        return value

    spec = c.markets()[symbol]
    bt = c.book_ticker(symbol)
    bid, ask = float(bt["bidPrice"]), float(bt["askPrice"])
    spread_bps = (ask - bid) / ((ask + bid) / 2) * 1e4
    rec("book", {"bid": bid, "ask": ask, "spread_bps": round(spread_bps, 2)})
    acct = c.account()
    rec("account before", {"account": acct.account_id[:8], "balance": acct.wallet_balance, "margin": acct.margin_balance})
    if spread_bps > max_spread:
        print("refusing: spread too wide")
        return 1
    if c.positions(symbol) or c.open_orders(symbol):
        print(f"refusing: account not flat / has open orders on {symbol}")
        return 1
    qty = max(Decimal(str(spec.min_notional * 1.08 / ask)), spec.min_qty)
    qty = (qty / spec.step).to_integral_value(ROUND_UP) * spec.step
    notional = float(qty) * ask
    rec("size", {"qty": str(qty), "notional": round(notional, 2)})
    if notional > MAX_NOTIONAL_USD:
        print("refusing: notional above the probe cap")
        return 1
    tag = uuid.uuid4().hex[:8]
    limit = spec.round_price(ask * 1.002, side_up=True)
    stop = spec.round_price(bid * 0.95, side_up=False)
    body = {"strategy_id": f"sflive-{tag}", "client_order_id": f"sflive-{tag}-e", "symbol": symbol, "side": "buy",
            "type": "limit", "time_in_force": "IOC", "size": str(qty), "price": str(limit),
            "sl_order": {"client_order_id": f"sflive-{tag}-sl", "type": "stop", "size": str(qty),
                         "stop_price": str(stop), "working_type": "mark_price"}}
    c.set_leverage(symbol, 1)
    rec("entry response", c.create_strategy_order(body))
    time.sleep(3)
    o = c.order(symbol, client_order_id=f"sflive-{tag}-e")
    rec("entry order", o and {"status": o.status, "filled": o.filled, "builder": [o.builder_code, o.builder_fee_bps]})
    pos = [p for p in c.positions(symbol) if p.size]
    rec("position", [(p.size, p.entry_price, p.liquidation_price) for p in pos])
    legs = c.open_orders(symbol)
    rec("resting legs", [(x.client_order_id, x.type, x.status, x.stop_price, x.reduce_only, x.builder_fee_bps) for x in legs])
    if pos:
        ex = {"client_order_id": f"sflive-{tag}-x", "symbol": symbol, "side": "sell", "type": "market",
              "size": str(abs(Decimal(str(pos[0].size)))), "reduce_only": True, "slippage": "0.01"}
        rec("exit response", c.create_order(ex))
        time.sleep(3)
        still = [(p.size, p.entry_price) for p in c.positions(symbol) if p.size]
        rec("position after exit", still)
        left = c.open_orders(symbol)
        rec("legs after exit (auto-cancelled?)", [(x.client_order_id, x.status) for x in left])
        if still:   # the exit did not fill (testnet 2026-10-20: price floor vs mark): never leave it without its stop
            print("exit not filled: the position keeps its stop leg; close it by hand")
            return 1
        for x in left:
            c.cancel_order(symbol, x.order_id)
        time.sleep(1)
        rec("orders after cleanup", [(x.client_order_id, x.status) for x in c.open_orders(symbol)])
    fills = c.fills(symbol, limit=10)
    # Strike (2026-10-19): `fee` here is the trading fee only; the builder fee is not included. Check it as
    # BuilderReward in GET /v2/builder/fills (builder account) or builder_fee on WebSocket trade events.
    rec("fills", [{"side": f.side, "role": f.role, "price": f.price, "size": f.size, "fee": f.fee,
                   "fee_bps": round(1e4 * f.fee / (f.price * f.size), 2) if f.price and f.size else math.nan,
                   "raw_keys": sorted(f.raw)} for f in fills[:4]])
    acct = c.account()
    rec("account after", {"account": acct.account_id[:8], "balance": acct.wallet_balance, "margin": acct.margin_balance})
    p = out / f"live_probe_{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(log, indent=1, default=str), encoding="utf-8")
    print("->", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
