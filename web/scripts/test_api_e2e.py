"""End-to-end test of the EdgeCraft-StrikeCity API (Pages Functions + D1) on `wrangler pages dev` or a deployed site.

    python web/scripts/test_api_e2e.py <base_url> <push_secret_file> [--keep]

The push secret file holds PUSH_SECRET=... (web/.dev.vars locally). Uses a throwaway test wallet (no funds) and the
real push client of the agents' host (smartflow.api.push). Without --keep the test agent is deleted at the end.
On the QA site (testnet, builder code set) it also connects the test wallet to Strike testnet through the builder code;
that needs free API wallets offered by the fleet on the agents' host. --hold N keeps the connection N seconds, so the
fleet can be seen starting the agent before the test stops it.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))
from cip30_test_wallet import TestWallet  # noqa: E402
from smartflow.api.push import encode, post, sign  # noqa: E402

BASE = sys.argv[1].rstrip("/")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from smartflow.secretstore import read_text  # noqa: E402  (the file may be encrypted at rest: secrets/*.dpapi)
SECRET = next(ln.split("=", 1)[1].strip() for ln in read_text(Path(sys.argv[2])).splitlines() if ln.startswith("PUSH_SECRET="))
KEEP = "--keep" in sys.argv
HOLD = int(sys.argv[sys.argv.index("--hold") + 1]) if "--hold" in sys.argv else 0
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""))


def call(method, path, data=None, token=None, headers=None, raw=None):
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    h = {"Content-Type": "application/json", "User-Agent": "smartflow-e2e/1.0", **(headers or {})}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        txt = e.read()
        try:
            return e.code, json.loads(txt)
        except json.JSONDecodeError:
            return e.code, {"raw": txt[:120]}


now = int(time.time() * 1000)
# ---------------------------------------------------------------- push from the agents' host
ref = {"id": "sf-reference", "name": "Smart Flow · Reference", "owner": "Smart Flow", "kind": "paper", "env": "mainnet", "tf": "240",
       "variant": "reference", "changes": [], "markets": ["BTC-USD", "ETH-USD", "SOL-USD"], "riskPct": 0.5, "feeBps": 10,
       "equity0": 10000, "cash": 10000, "since": now - 86400_000, "lastCheck": now - 600_000, "nextCheck": now + 3600_000,
       "status": "waiting", "alerts": [], "positions": [], "trades": [],
       "checks": {"BTC-USD": {"time": now - 600_000, "args": {"r": "volume", "vol": 0.9, "vmin": 1.5}, "text": "volume too low"}},
       "decisions": [{"time": now - 600_000, "market": "BTC-USD", "kind": "analysis", "code": "check", "args": {"r": "volume", "vol": 0.9, "vmin": 1.5}}]}
doc = {"generated": now, "engine": "1.0.0", "agents": [ref]}
code, r = post(BASE + "/api/internal/push", SECRET, encode(doc))
check("host push with the right secret is accepted", code == 200 and r and "ok" in r, f"{code} {r}")
code, r = post(BASE + "/api/internal/push", "x" * 64, encode(doc))
check("push with a wrong secret is refused", code == 401, str(code))
old = str(now - 10 * 60_000)
code, _ = call("POST", "/api/internal/push", raw=encode(doc), headers={"X-SF-Time": old, "X-SF-Signature": sign(SECRET, old, encode(doc))})
check("push with a stale timestamp is refused", code == 401, str(code))

code, info = call("GET", "/api/info")
check("info: paper mode, real trading not enabled yet", code == 200 and info.get("paper") is True and info.get("connect") is False and info.get("agentHealthy") is True, json.dumps(info)[:160])

# ---------------------------------------------------------------- sign in with a wallet
NET = 0 if info.get("env") == "testnet" else 1    # the QA site is the testnet world (Preprod wallets)
w, intruder = TestWallet(network=NET, base=True), TestWallet(network=NET)
LOOK = {"skin": "#7a4a33", "eyes": "#4efab0", "hair": "afro", "hairColor": "#ec4899", "top": "jacket", "topColor": "#172554",
        "top2": "#facc15", "accent": "#4efab0", "bottom": "shorts", "pants": "#334155", "shoes": "#f43f5e", "face": "visor",
        "faceColor": "#4efab0", "head": "crown", "headColor": "#facc15", "back": "cape", "backColor": "#7c3aed"}
ask = {"address": w.address, "chain": "cardano", "risk": "standard", "markets": ["BTC-USD", "ETH-USD"], "name": "Nova Test", "public": True,
       "look": LOOK, "strategy": "pyramid"}
LIVE = info.get("live") or {}


def with_key(do):
    """Where real trading is offered each Strike request takes a fresh API wallet from the fleet's pool (3 free, topped
    up every minute): wait for one instead of failing when a previous run used them."""
    for _ in range(10):
        code, r = do()
        if code != 503:
            return code, r
        time.sleep(15)
    return code, r


code, ch = with_key(lambda: call("POST", "/api/connect/challenge", ask))
check("challenge issued", code == 200 and "Nonce:" in ch.get("messageToSign", "") and w.address in ch["messageToSign"], f"{code} {ch.get('error', '')}")
msg = ch["messageToSign"]
if LIVE.get("enabled"):   # creating the agent is connecting it: the only message is Strike's builder connect
    check("creating the agent signs Strike's builder connect", ch.get("live") is True and f'builder "{LIVE.get("code")}"' in msg and "0.2% fee" in msg
          and ch.get("feeBps") == 20, msg[:80])
else:
    check("message says it cannot move funds", "cannot move funds" in msg and "Mode: paper" in msg)
    check("message names the character being saved", "Character: " in msg and "Character: automatic" not in msg)
code, r = call("POST", "/api/connect/verify", {"sessionId": ch["sessionId"], "walletSignature": intruder.sign_data(msg.encode())})
check("someone else's signature is refused", code == 401, f"{code} {r.get('error')}")
code, r = call("POST", "/api/connect/verify", {"sessionId": ch["sessionId"], "walletSignature": w.sign_data(msg.encode())})
check("the challenge is single use (a failed attempt burns it)", code == 410, str(code))
code, ch = with_key(lambda: call("POST", "/api/connect/challenge", ask))
code, linked = call("POST", "/api/connect/verify", {"sessionId": ch["sessionId"], "walletSignature": w.sign_data(ch["messageToSign"].encode())})
check("owner's signature links the agent", code == 200 and linked.get("token") and linked.get("accountId", "").startswith("u-"), f"{code} {linked.get('error', '')}")
if LIVE.get("enabled"):
    check("it starts already trading on the owner's Strike account", linked.get("mode") == "live" and (linked.get("live") or {}).get("status") == "active"
          and (linked.get("live") or {}).get("env") == info["env"], json.dumps(linked.get("live"))[:160])
token, aid = linked.get("token", ""), linked.get("accountId", "")
code, r = call("POST", "/api/connect/verify", {"sessionId": ch["sessionId"], "walletSignature": w.sign_data(ch["messageToSign"].encode())})
check("replaying the same signature fails", code == 410, str(code))

code, city = call("GET", "/api/city")
mine = [a for a in city.get("agents", []) if a.get("id") == aid]
check("the agent appears in the city", code == 200 and len(mine) == 1 and mine[0]["name"] == "Nova Test", f"{len(city.get('agents', []))} agents")
if mine:
    a = mine[0]
    # on a site with real trading, creating it connected it: a real agent (starting until the host pushes it), never paper
    kind = "live" if LIVE.get("enabled") else "paper"
    check(f"its markets and risk are the owner's, {kind}", a["markets"] == ["BTC-USD", "ETH-USD"] and a["riskPct"] == 0.5 and a["kind"] == kind,
          f"{a.get('kind')} {a.get('markets')} {a.get('riskPct')}")
    check("its strategy is the owner's", a.get("strategy") == "pyramid", str(a.get("strategy")))
    check("no wallet address in the public city", w.address not in json.dumps(city))
    check("its character is the one the owner made", a.get("look") == LOOK, json.dumps(a.get("look"))[:120])

code, me = call("GET", "/api/me", token=token)
check("me with the session token", code == 200 and me.get("name") == "Nova Test" and me.get("public") is True
      and me.get("mode") == ("live" if LIVE.get("enabled") else "paper") and me.get("strategy") == "pyramid", f"{code} {me.get('mode')} {me.get('strategy')}")
if LIVE.get("enabled"):
    check("connected and starting: no paper numbers in the meantime", (me.get("live") or {}).get("status") == "active" and me.get("equity0") in (None, 10000)
          and not me.get("openPositions"), json.dumps({k: me.get(k) for k in ("live", "equity", "equity0")})[:200])
check("me without a token is refused", call("GET", "/api/me")[0] == 401)
check("me with a forged token is refused", call("GET", "/api/me", token=f"{aid}.{now + 9e9:.0f}.{'0' * 64}")[0] == 401)

# ---------------------------------------------------------------- the reference agent trades: a paper user's agent follows from its start
created = me.get("createdAt", now)
PAPER = not LIVE.get("enabled")
ref2 = dict(ref, status="in_trade",
            positions=[{"market": "BTC-USD", "side": "long", "entry": 80000, "stop": 78800, "trail": 79500, "qty": 0.04, "openedAt": created + 1000},
                       {"market": "SOL-USD", "side": "short", "entry": 100, "stop": 103, "trail": 103, "qty": 5, "openedAt": created + 1000}],
            trades=[{"market": "ETH-USD", "side": "long", "entry": 2400, "exit": 2500, "stop": 2350, "r": 1.9, "reason": "trail", "openedAt": created + 500, "time": created + 900},
                    {"market": "BTC-USD", "side": "short", "entry": 81000, "exit": 81600, "stop": 81500, "r": -1.1, "reason": "stop", "openedAt": created - 86400_000, "time": created - 3600_000}])
code, _ = post(BASE + "/api/internal/push", SECRET, encode({"generated": int(time.time() * 1000), "engine": "1.0.0", "agents": [ref2]}))
code, me = call("GET", "/api/me", token=token)
pos = me.get("openPositions", [])
if PAPER:
    check("follows the reference position in its markets only (BTC yes, SOL no)", [p["market"] for p in pos] == ["BTC-USD"], json.dumps(pos)[:160])
    check("trades before it started do not count", me.get("trades") == 1, str(me.get("trades")))
    check("paper equity compounds +1.9R at 0.5% risk", abs((me.get("equity") or 0) - 10000 * (1 + 1.9 * 0.005)) < 0.01, str(me.get("equity")))
else:
    check("a connected agent never copies the paper reference", not pos and me.get("mode") == "live", json.dumps(pos)[:120])
if pos and PAPER:
    want = (me["equity"] * 0.005) / (80000 - 78800)
    check("position sized at the owner's risk", abs(pos[0]["size"] - want) < 1e-9, f"{pos[0]['size']:.6f} vs {want:.6f}")


# ---------------------------------------------------------------- actions need a fresh signature
def act(action, wallet=w):
    code, ch = call("POST", "/api/action/challenge", {"accountId": aid, "action": action})
    if code != 200:
        return code, ch
    return call("POST", "/api/action", {"sessionId": ch["sessionId"], "walletSignature": wallet.sign_data(ch["messageToSign"].encode())})


code, ch_bad = call("POST", "/api/action/challenge", {"accountId": aid, "action": "look", "look": "dragon"})
check("an invalid character is refused", code == 400, str(code))
NEW = dict(LOOK, hair="mohawk", head="headphones", top="suit")
code, ch = call("POST", "/api/action/challenge", {"accountId": aid, "action": "look", "look": NEW})
code, r = call("POST", "/api/action", {"sessionId": ch["sessionId"], "walletSignature": w.sign_data(ch["messageToSign"].encode())})
check("owner changes the character with a signature", code == 200 and (r.get("look") or {}).get("hair") == "mohawk", str(code))
code, ch = call("POST", "/api/action/challenge", {"accountId": aid, "action": "look", "look": dict(NEW, hair="long")})
code, r = call("POST", "/api/action", {"sessionId": ch["sessionId"], "walletSignature": intruder.sign_data(ch["messageToSign"].encode())})
check("someone else cannot change it", code == 401, str(code))

code, r = act("pause", intruder)
check("someone else cannot pause it", code == 401, str(code))
code, r = act("pause")
check("owner pauses it", code == 200 and r.get("status") == "paused", str(code))
code, r = act("resume")
check("owner resumes it", code == 200 and r.get("status") == "active", str(code))
code, r = act("hide")
check("owner hides it from the city", code == 200 and r.get("public") is False, str(code))
time.sleep(1)
code, city = call("GET", "/api/city")
check("hidden agent is not in the city", not any(a.get("id") == aid for a in city.get("agents", [])))
act("show")

# ---------------------------------------------------------------- builder connect (QA site: Strike testnet)
def host_live():
    ts = str(int(time.time() * 1000))
    return call("GET", "/api/internal/live", headers={"X-SF-Time": ts, "X-SF-Signature": sign(SECRET, ts, b"GET /api/internal/live")})


if LIVE.get("enabled"):
    check("live connect needs the session", call("POST", "/api/live/challenge", {})[0] == 401)
    code, r = host_live()
    check("host sees the builder code and the fee", code == 200 and r.get("builderCode") == LIVE.get("code") and r.get("feeBps") == 20 and r.get("env") == info["env"], f"{code} {str(r)[:120]}")
    check("host view refuses a wrong secret", call("GET", "/api/internal/live", headers={"X-SF-Time": str(int(time.time() * 1000)), "X-SF-Signature": "0" * 64})[0] == 401)
    lk = [x for x in r.get("links", []) if x.get("userId") == aid]
    check("host gets the new agent's link: key, markets, risk, active", len(lk) == 1 and lk[0]["status"] == "active" and len(lk[0]["pub"]) == 64
          and lk[0]["markets"] == ["BTC-USD", "ETH-USD"] and lk[0]["risk"] == "standard" and lk[0]["feeBps"] == 20, json.dumps(lk)[:200])
    check("host view never carries the wallet address", w.address not in json.dumps(r))
    check("me shows it connected", (call("GET", "/api/me", token=token)[1].get("live") or {}).get("status") == "active")
    check("a second connect is refused while active", call("POST", "/api/live/challenge", {}, token=token)[0] == 409)
    check("the host runs the strategy the owner picked", lk and lk[0].get("strategy") == "pyramid", json.dumps(lk)[:200])
    # change strategy, markets and risk later, with a signature
    code, sch = call("POST", "/api/action/challenge", {"accountId": aid, "action": "settings", "strategy": "smartflow",
                                                       "markets": ["BTC-USD"], "risk": "conservative"})
    check("settings change asks for a signature that lists them", code == 200 and "Strategy: Smart Flow" in sch.get("messageToSign", "")
          and "Markets: BTC-USD" in sch.get("messageToSign", ""), sch.get("messageToSign", "")[:120])
    code, r2 = call("POST", "/api/action", {"sessionId": sch.get("sessionId", ""), "walletSignature": w.sign_data(sch.get("messageToSign", "").encode())})
    check("the owner's signature changes them", code == 200 and r2.get("strategy") == "smartflow" and r2.get("risk") == "conservative", f"{code} {str(r2)[:120]}")
    lk = [x for x in host_live()[1].get("links", []) if x.get("userId") == aid]
    check("the host gets the new settings (it restarts the agent with them)", lk and lk[0]["strategy"] == "smartflow" and lk[0]["markets"] == ["BTC-USD"]
          and lk[0]["risk"] == "conservative", json.dumps(lk)[:200])
    code, tch = call("POST", "/api/action/challenge", {"accountId": aid, "action": "test"})
    check("a test trade is refused on testnet (its book cannot close positions)", code == 409 if info["env"] == "testnet" else code == 200, f"{code} {tch}")
    check("an unknown strategy is refused", call("POST", "/api/action/challenge", {"accountId": aid, "action": "settings", "strategy": "x",
                                                                                              "markets": ["BTC-USD"], "risk": "standard"})[0] == 400)
    code, again = call("POST", "/api/connect/challenge", ask)
    check("signing in again does not ask Strike again", code == 200 and not again.get("live") and "sign in to my agent" in again.get("messageToSign", "")
          and "already connected" in again.get("messageToSign", ""), again.get("messageToSign", "")[:60])
    if HOLD:
        print(f"     holding the connection {HOLD} s for the fleet…")
        time.sleep(HOLD)
    code, v = call("POST", "/api/live/off", {}, token=token)
    check("owner stops real trading with the session only", code == 200 and v.get("status") == "off", f"{code} {v}")
    lk = [x for x in host_live()[1].get("links", []) if x.get("userId") == aid]
    check("host sees it stopped", len(lk) == 1 and lk[0]["status"] == "paused", json.dumps(lk)[:120])
    # My agent can connect it again (the button on the dashboard)
    code, lch = with_key(lambda: call("POST", "/api/live/challenge", {}, token=token))
    lmsg = lch.get("messageToSign", "")
    check("My agent asks Strike again for this wallet", code == 200 and f'builder "{LIVE.get("code")}"' in lmsg and w.address in lmsg, f"{code} {lch.get('error', '')}")
    code, v = call("POST", "/api/live/verify", {"sessionId": lch.get("sessionId", ""), "walletSignature": intruder.sign_data(lmsg.encode())}, token=token)
    check("Strike refuses someone else's signature (nothing linked)", code in (400, 401, 502) and v.get("status") is None, f"{code} {v.get('error', '')}")
    code, lch = with_key(lambda: call("POST", "/api/live/challenge", {}, token=token))
    code, v = call("POST", "/api/live/verify", {"sessionId": lch.get("sessionId", ""), "walletSignature": w.sign_data(lch.get("messageToSign", "").encode())}, token=token)
    check("owner's signature connects it again", code == 200 and v.get("status") == "active", f"{code} {v.get('error', v)}")
    code, _ = call("POST", "/api/live/verify", {"sessionId": lch.get("sessionId", ""), "walletSignature": w.sign_data(lch.get("messageToSign", "").encode())}, token=token)
    check("the Strike session is single use", code == 410, str(code))
    code, v = call("POST", "/api/live/off", {}, token=token)
    check("and stops again", code == 200 and v.get("status") == "off", str(code))
    if LIVE.get("enabled"):   # open to everyone: a stopped agent is shown stopped, never as a paper agent
        code, me = call("GET", "/api/me", token=token)
        check("stopped: My agent shows it stopped, not paper", code == 200 and me.get("mode") == "live" and me.get("agentStatus") == "paused"
              and not me.get("openPositions") and me.get("equity") is None, f"{code} {me.get('mode')} {me.get('agentStatus')} {me.get('equity')}")
else:
    check("real trading not offered on this site", call("POST", "/api/live/challenge", {}, token=token)[0] == 501)

# ---------------------------------------------------------------- a wallet that already has an agent only signs in
code, st = call("GET", f"/api/live/eligible?address={w.address}")
check("the site knows this wallet already has an agent", code == 200 and st.get("agent") is True, f"{code} {st}")
fresh = TestWallet(network=NET)
code, st = call("GET", f"/api/live/eligible?address={fresh.address}")
check("and that a new wallet has none", code == 200 and st.get("agent") is False, f"{code} {st}")
check("signing in needs an agent", call("POST", "/api/connect/challenge", {"address": fresh.address, "chain": "cardano", "signin": True})[0] == 404)
code, ch = call("POST", "/api/connect/challenge", {"address": w.address, "chain": "cardano", "signin": True})
smsg = ch.get("messageToSign", "")
check("sign-in message: proves the wallet and changes nothing", code == 200 and ch.get("signin") is True and "sign in to my agent" in smsg
      and "changes nothing" in smsg and "Agent name: Nova Test" in smsg, f"{code} {ch.get('error', '')} {smsg[:60]}")
code, s = call("POST", "/api/connect/verify", {"sessionId": ch.get("sessionId", ""), "walletSignature": w.sign_data(smsg.encode())})
ag = s.get("agent") or {}
check("signing in returns the agent as it is", code == 200 and s.get("signin") is True and s.get("accountId") == aid and ag.get("name") == "Nova Test"
      and ag.get("strategy") in ("smartflow", "pyramid"), f"{code} {s.get('error', '')} {ag}")
code, before = call("GET", "/api/me", token=s.get("token", ""))
check("its session opens My agent", code == 200 and before.get("accountId") == aid, str(code))
# a page that still sends the creation form for this wallet: it only signs in, nothing is overwritten
code, ch = call("POST", "/api/connect/challenge", {**ask, "name": "Other Name", "markets": ["BTC-USD"], "risk": "conservative", "strategy": "smartflow"})
check("creating again with a wallet that has an agent is only a sign-in", code == 200 and ch.get("signin") is True
      and "Other Name" not in ch.get("messageToSign", ""), f"{code} {ch.get('error', '')}")
code, s = call("POST", "/api/connect/verify", {"sessionId": ch.get("sessionId", ""), "walletSignature": w.sign_data(ch.get("messageToSign", "").encode())})
code, me = call("GET", "/api/me", token=s.get("token", ""))
check("nothing about the agent changed", code == 200 and all(me.get(k) == before.get(k) for k in ("name", "markets", "risk", "strategy", "public", "look")),
      f"{me.get('name')} {me.get('markets')} {me.get('risk')} {me.get('strategy')}")

# ---------------------------------------------------------------- validation and limits
ask = {**ask, "address": fresh.address}   # creating: a wallet without an agent
bad = [("reserved name", {**ask, "name": "Smart Flow Pro"}), ("empty markets", {**ask, "markets": []}),
       ("a character that is not an object", {**ask, "look": "dragon"}),
       ("unknown market", {**ask, "markets": ["DOGE-USD"]}), ("bad risk", {**ask, "risk": "yolo"}),
       ("a wallet on the other network", {**ask, "address": TestWallet(network=1 - NET).address}), ("garbage address", {**ask, "address": "addr1qqq"}),
       ("html in name", {**ask, "name": "<script>"})]
for nm, q in bad:
    code, r = call("POST", "/api/connect/challenge", q)
    check(f"rejects {nm}", code == 400, f"{code} {r.get('error', '')}")
codes = [call("POST", "/api/connect/challenge", {**ask, "address": w.address})[0] for _ in range(6)]   # sign-ins: never reach Strike
check("throttles repeated sign-in attempts", 429 in codes, str(codes))
check("unknown API path is a JSON 404", call("GET", "/api/nope")[0] == 404)

if not KEEP:
    code, r = act("revoke")
    check("owner deletes the agent", code in (200, 429) and (r.get("deleted") is True or code == 429), f"{code} {r}")
    if code == 200:
        check("deleted agent is gone", call("GET", "/api/me", token=token)[0] == 404)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
