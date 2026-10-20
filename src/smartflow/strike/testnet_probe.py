"""Testnet-only probe of order mechanics WITHOUT fills (resting post-only limits away from the book).

    python -m smartflow.strike.testnet_probe          (needs secrets/strike_testnet.env)

Verifies, and records in reports/testnet_probe_<ts>.json: order creation format, lookup by client_order_id,
duplicate client_order_id behaviour, cancel, bracket (/v2/order/strategy) format and leg behaviour before the primary
fills, cancel of the primary, leverage update, and how the API reacts to X-Builder-Fee-Bps on a non-builder wallet.
Everything it creates is cancelled at the end (cancel-all on the probe symbol). Refuses to run against mainnet.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from ..net import HttpError, request_json
from .auth import ApiWalletSigner, serialize_body
from .client import TESTNET, StrikeClient


def _load_env() -> None:
    from .. import secretstore
    f = Path("secrets") / "strike_testnet.env"
    if secretstore.exists(f):
        for ln in secretstore.read_text(f).splitlines():
            if "=" in ln and not ln.startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    _load_env()
    c = StrikeClient(TESTNET, ApiWalletSigner.from_env())
    assert c.base == TESTNET, "probe is testnet-only"
    c.sync_clock()
    out: dict = {"base": c.base, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "steps": []}

    def step(name, fn):
        t0 = time.time()
        try:
            r = fn()
            rec = {"step": name, "ok": True, "result": r}
        except HttpError as e:
            rec = {"step": name, "ok": False, "status": e.status, "error": e.body[:400]}
        except Exception as e:
            rec = {"step": name, "ok": False, "error": repr(e)}
        rec["ms"] = int(1000 * (time.time() - t0))
        out["steps"].append(rec)
        print(f"[{'OK ' if rec['ok'] else 'ERR'}] {name}: " + json.dumps(rec.get("result", rec.get("error")),
                                                                          default=str)[:300])
        return rec

    sym = "SOL-USD"
    spec = c.markets()[sym]
    mark = c.premium(sym)["mark"]
    book = c.depth(sym, 20)
    best_bid = float(book["bids"][0][0]) if book["bids"] else 0.0
    # a SELL limit 3 % above mark rests (bids are far below) and stays inside the 5 % price band
    price = str(spec.round_price(mark * 1.03, side_up=True))
    size = "0.15"
    out["context"] = {"symbol": sym, "mark": mark, "best_bid": best_bid, "probe_price": price, "size": size}
    tag = uuid.uuid4().hex[:8]
    cid_a = f"sfprobe-{tag}-a"

    def order_body(cid):
        return {"client_order_id": cid, "symbol": sym, "side": "sell", "type": "limit", "size": size, "price": price,
                "time_in_force": "GTC", "post_only": True}

    step("set leverage 2x", lambda: c.set_leverage(sym, 2))
    step("create resting post-only limit (A)", lambda: c.create_order(order_body(cid_a)))
    time.sleep(1.5)
    ra = step("lookup A by client_order_id", lambda: _o(c.order(sym, client_order_id=cid_a)))
    step("create DUPLICATE client_order_id (A again)", lambda: c.create_order(order_body(cid_a)))
    time.sleep(1.5)
    step("open orders after duplicate", lambda: [_o(o) for o in c.open_orders(sym) if o.client_order_id == cid_a])
    for o in c.open_orders(sym):
        if o.client_order_id == cid_a:
            step(f"cancel A id={o.order_id}", lambda o=o: c.cancel_order(sym, o.order_id))
    time.sleep(1.0)
    step("lookup A after cancel", lambda: _o(c.order(sym, client_order_id=cid_a)))

    # bracket with objects tp_order/sl_order (OpenAPI form) on a resting primary
    cid_b = f"sfprobe-{tag}-b"
    sl = str(spec.round_price(mark * 1.10, side_up=True))
    tp = str(spec.round_price(mark * 0.90, side_up=False))
    bracket = {"strategy_id": f"sfprobe-{tag}", **order_body(cid_b),
               "sl_order": {"client_order_id": f"sfprobe-{tag}-sl", "type": "stop", "size": size, "stop_price": sl,
                            "working_type": "mark_price"},
               "tp_order": {"client_order_id": f"sfprobe-{tag}-tp", "type": "take_profit", "size": size,
                            "stop_price": tp, "working_type": "mark_price"}}
    step("create bracket (tp_order/sl_order objects), resting primary", lambda: c.create_strategy_order(bracket))
    time.sleep(1.5)
    step("open orders: primary + legs?", lambda: [_o(o) for o in c.open_orders(sym)])
    step("lookup SL leg by client id", lambda: _o(c.order(sym, client_order_id=f"sfprobe-{tag}-sl")))
    for o in c.open_orders(sym):
        if o.client_order_id == cid_b:
            step(f"cancel bracket primary id={o.order_id}", lambda o=o: c.cancel_order(sym, o.order_id))
    time.sleep(1.5)
    step("open orders after cancelling primary", lambda: [_o(o) for o in c.open_orders(sym)])
    step("lookup SL leg after cancel", lambda: _o(c.order(sym, client_order_id=f"sfprobe-{tag}-sl")))

    # builder fee header on a wallet that never approved a builder
    cid_c = f"sfprobe-{tag}-c"

    def with_builder_header():
        body = order_body(cid_c)
        s = serialize_body(body)
        h = c.signer.headers("POST", "/v2/order", s, timestamp=int(time.time() + c.clock_offset_s))
        h.update({"Content-Type": "application/json", "X-Builder-Fee-Bps": "10"})
        return request_json("POST", c.base + "/v2/order", body=s.encode(), headers=h, retries=0)[1]
    step("order with X-Builder-Fee-Bps=10 from a non-builder wallet", with_builder_header)
    time.sleep(1.0)
    step("lookup C (builder attribution field)", lambda: _o(c.order(sym, client_order_id=cid_c)))

    step("cleanup: cancel-all on probe symbol", lambda: c.cancel_all(sym))
    time.sleep(1.0)
    step("final open orders", lambda: [_o(o) for o in c.open_orders(sym)])
    step("final positions", lambda: [(p.symbol, p.size) for p in c.positions()])
    out["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p = Path("reports") / f"testnet_probe_{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print("->", p)
    return 0


def _o(o):
    if o is None:
        return None
    return {"id": o.order_id, "cid": o.client_order_id, "type": o.type, "side": o.side, "status": o.status,
            "size": o.size, "filled": o.filled, "price": o.price, "stop": o.stop_price, "reduce_only": o.reduce_only,
            "strategy": o.strategy_id, "builder": o.builder_code, "builder_bps": o.builder_fee_bps}


if __name__ == "__main__":
    raise SystemExit(main())
