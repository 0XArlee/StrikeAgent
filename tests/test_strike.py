"""Strike adapter: signing, request construction (builder header), tolerant parsing. No network."""

import hashlib

import pytest

from smartflow.strike import client as client_mod
from smartflow.strike.auth import EMPTY_SHA256, ApiWalletSigner, generate_keypair, serialize_body, verify
from smartflow.strike.client import BuilderFee, StrikeClient
from smartflow.strike.models import parse_fee_tiers, parse_market, parse_order, parse_positions, parse_premium

PRIV = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"   # RFC 8032 test vector 1
PUB = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"


def test_rfc8032_vector_and_key_formats():
    s = ApiWalletSigner(PRIV)
    assert s.public_key == PUB
    assert ApiWalletSigner(PRIV + PUB).public_key == PUB          # 128-hex (seed + public) accepted
    with pytest.raises(ValueError):
        ApiWalletSigner(PRIV, "00" * 32)                            # mismatching public key refused
    assert "9d61" not in repr(s)                                    # private key never in repr


def test_message_format_and_signature():
    s = ApiWalletSigner(PRIV)
    body = serialize_body({"symbol": "BTC-USD", "side": "buy", "type": "market", "size": "0.01"})
    assert body == '{"symbol":"BTC-USD","side":"buy","type":"market","size":"0.01"}'
    h = s.headers("POST", "/v2/order", body, timestamp=1712054096, nonce="550e8400-e29b-41d4-a716-446655440000")
    msg = f"POST:/v2/order:1712054096:550e8400-e29b-41d4-a716-446655440000:{hashlib.sha256(body.encode()).hexdigest()}"
    assert ApiWalletSigner.message("post", "/v2/order", 1712054096, "550e8400-e29b-41d4-a716-446655440000", body) == msg
    assert verify(PUB, msg, h["X-API-Wallet-Signature"])
    assert set(h) == {"X-API-Wallet-Public-Key", "X-API-Wallet-Signature", "X-API-Wallet-Timestamp",
                      "X-API-Wallet-Nonce"}
    g = s.headers("GET", "/v2/positions?symbol=BTC-USD", "", timestamp=1, nonce="n")
    assert verify(PUB, f"GET:/v2/positions?symbol=BTC-USD:1:n:{EMPTY_SHA256}", g["X-API-Wallet-Signature"])


def test_generated_keys_roundtrip():
    priv, pub = generate_keypair()
    assert len(priv) == 64 and len(pub) == 64
    s = ApiWalletSigner(priv, pub)
    h = s.headers("GET", "/v2/account", "", timestamp=5, nonce="x")
    assert verify(pub, f"GET:/v2/account:5:x:{EMPTY_SHA256}", h["X-API-Wallet-Signature"])


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, params=None, body=None, headers=None, timeout=None, **kw):
        self.calls.append(dict(method=method, url=url, body=body, headers=headers or {}))
        return 201, {"client_order_id": "x"}, {}


def test_builder_header_only_on_order_creation(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(client_mod, "request_json", rec)
    c = StrikeClient("https://example.test", ApiWalletSigner(PRIV), BuilderFee("edgecraft", 10, approved_bps=25))
    c.create_order({"symbol": "BTC-USD", "side": "buy", "type": "market", "size": "0.01"})
    c.create_strategy_order({"strategy_id": "s", "symbol": "BTC-USD", "side": "buy", "type": "limit", "size": "1",
                             "price": "1", "sl_order": {"type": "stop", "size": "1", "stop_price": "0.9"}})
    c.cancel_order("BTC-USD", 5)
    c.set_leverage("BTC-USD", 3)
    hdr = [x["headers"].get("X-Builder-Fee-Bps") for x in rec.calls]
    assert hdr == ["10", "10", None, None]
    # the signed body hash matches the bytes actually sent
    sent = rec.calls[0]
    msg = ApiWalletSigner.message("POST", "/v2/order", int(sent["headers"]["X-API-Wallet-Timestamp"]),
                                  sent["headers"]["X-API-Wallet-Nonce"], sent["body"].decode())
    assert verify(PUB, msg, sent["headers"]["X-API-Wallet-Signature"])


def test_builder_fee_caps():
    with pytest.raises(ValueError):
        BuilderFee("c", 101).validate()
    with pytest.raises(ValueError):
        BuilderFee("c", 30, approved_bps=20).validate()
    with pytest.raises(ValueError):
        BuilderFee("c", 30, registered_bps=10).validate()
    BuilderFee("c", 10, approved_bps=10, registered_bps=50).validate()


def test_signed_get_query_is_part_of_signature(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(client_mod, "request_json", rec)
    c = StrikeClient("https://example.test", ApiWalletSigner(PRIV), sub_account_id="abc")
    c._signed("GET", "/v2/positions", {"symbol": "BTC-USD", "sub_account_id": "abc"})
    call = rec.calls[0]
    assert call["url"] == "https://example.test/v2/positions?symbol=BTC-USD&sub_account_id=abc"
    h = call["headers"]
    msg = ApiWalletSigner.message("GET", "/v2/positions?symbol=BTC-USD&sub_account_id=abc",
                                  int(h["X-API-Wallet-Timestamp"]), h["X-API-Wallet-Nonce"], "")
    assert verify(PUB, msg, h["X-API-Wallet-Signature"])
    assert call["body"] is None


def test_no_dangling_question_mark(monkeypatch):
    """Regression (live 401 on testnet): params that are all None must not produce '/v2/positions?'."""
    rec = Recorder()
    monkeypatch.setattr(client_mod, "request_json", rec)
    c = StrikeClient("https://example.test", ApiWalletSigner(PRIV))
    c.positions()
    call = rec.calls[0]
    assert call["url"] == "https://example.test/v2/positions"
    h = call["headers"]
    assert verify(PUB, ApiWalletSigner.message("GET", "/v2/positions", int(h["X-API-Wallet-Timestamp"]),
                                               h["X-API-Wallet-Nonce"], ""), h["X-API-Wallet-Signature"])


def test_tolerant_parsers():
    pascal = {"feeTiers": [{"Tier": 0, "MinVolume": 0, "TakerRate": 0.0005, "MakerRate": -0.00005}]}
    camel = {"feeTiers": [{"tier": 0, "minVolume": 0, "takerRate": 0.0005, "makerRate": -0.00005}]}
    assert parse_fee_tiers(pascal) == parse_fee_tiers(camel)
    prem = [{"symbol": "ETH-USD", "markPrice": "1", "indexPrice": "1", "fundingRate": "0.0001", "nextFundingTime": 1,
             "time": 2}, {"symbol": "BTC-USD", "markPrice": "82262", "indexPrice": "82288.3", "fundingRate": "-0.00003",
                          "nextFundingTime": 3, "time": 4}]
    assert parse_premium(prem, "BTC-USD")["funding_rate"] == -0.00003
    assert parse_premium({"symbol": "X", "markPrice": "2", "lastFundingRate": "0.1"}, "X")["funding_rate"] == 0.1
    o = parse_order({"ID": 7, "ClientOrderID": "sf-1", "Symbol": "BTC-USD", "Side": "buy", "Type": "stop",
                     "Status": "untriggered", "Size": "0.1", "Filled": "0", "StopPrice": "80000", "ReduceOnly": True,
                     "Strategy": {"ID": "s1", "IsPrimary": False}, "Builder": {"Code": "edgecraft", "FeeBps": 10}})
    assert (o.order_id, o.strategy_id, o.builder_code, o.builder_fee_bps, o.reduce_only) == (7, "s1", "edgecraft", 10, True)
    snake = parse_order({"id": 8, "client_order_id": "c", "symbol": "BTC-USD", "side": "sell", "type": "market",
                         "status": "filled", "size": "1", "filled": "1"})
    assert snake.is_terminal and snake.builder_code is None
    ps = parse_positions({"positions": [{"id": 1, "symbol": "BTC-USD", "size": "-0.5", "entry_price": "80000",
                                         "leverage": 3, "margin_mode": "cross", "liquidation_price": "100000"}]})
    assert ps[0].side == -1


def test_market_spec_rounding():
    m = parse_market({"symbol": "BTC-USD", "status": "trading", "order_tick_price": "1",
                      "order_market_step_size": "0.00001", "order_market_min_size": "0.00001",
                      "order_market_max_size": "120", "order_min_notional": "10",
                      "margin_tiers": [{"max_notional": "10000", "max_leverage": 100, "maintenance_margin_rate": "0.004"},
                                       {"max_notional": "50000", "max_leverage": 75, "maintenance_margin_rate": "0.004"}]})
    assert str(m.round_qty(0.0123456)) == "0.01234"
    assert str(m.round_price(82000.6, side_up=False)) == "82000"
    assert str(m.round_price(82000.2, side_up=True)) == "82001"
    assert m.tier_for(20000).max_leverage == 75


def test_null_lists_from_live_api():
    from smartflow.strike.models import parse_fills
    assert parse_fills({"fills": None, "count": 0}) == []
    assert parse_positions({"positions": None}) == []
