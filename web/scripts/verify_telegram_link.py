"""Linking an agent to the alerts bot, end to end on the QA site: a throwaway agent made with a test wallet asks for a
one-time link (/api/me/telegram), the agents' host (the bot's own client) looks the code up and claims it, the owner
sees the chat, a used code is refused, the owner unlinks, and the agent is deleted. Telegram itself is not involved:
pressing Start only sends the bot that code.

    python web/scripts/verify_telegram_link.py <qa_base_url> <host_check_command...>

The host check command receives the code as its last argument (it runs ct_tg_claim.sh on the agents' host).
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cip30_test_wallet import TestWallet  # noqa: E402

BASE, HOST = sys.argv[1].rstrip("/"), sys.argv[2:]
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""))


def call(method, path, data=None, token=None):
    h = {"Content-Type": "application/json", "User-Agent": "smartflow-verify/1.0", **({"Authorization": f"Bearer {token}"} if token else {})}
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode() if data is not None else None, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, {}


w = TestWallet(network=0, base=True)
ask = {"address": w.address, "chain": "cardano", "risk": "standard", "markets": ["BTC-USD", "ETH-USD"], "name": "QA Alerts T", "public": False,
       "strategy": "smartflow"}
code, ch = call("POST", "/api/connect/challenge", ask)
code, linked = call("POST", "/api/connect/verify", {"sessionId": ch.get("sessionId", ""), "walletSignature": w.sign_data(ch.get("messageToSign", "").encode())})
token, aid = linked.get("token", ""), linked.get("accountId", "")
check("a test agent signs in", code == 200 and token and aid.startswith("u-"), f"{code} {linked.get('error', '')}")
try:
    check("without a session no link is made", call("POST", "/api/me/telegram", {"lang": "es"})[0] == 401)
    code, st = call("GET", "/api/me/telegram", token=token)
    check("no chat linked yet", code == 200 and st.get("chats") == [] and st.get("bot") == "EdgeCraftStrikeCityBot", json.dumps(st))
    code, ln = call("POST", "/api/me/telegram", {"lang": "es"}, token=token)
    url = ln.get("url", "")
    tg_code = url.rsplit("start=", 1)[-1]
    check("a one-time link to the bot, for this network", code == 200 and url.startswith("https://t.me/EdgeCraftStrikeCityBot?start=q") and len(tg_code) >= 17, url)
    run = subprocess.run(HOST + [tg_code], capture_output=True, text=True, timeout=120)
    out = run.stdout
    if run.returncode:
        print(run.stderr[-800:])
    lines = {ln.split(" ", 1)[0]: ln.split(" ", 1)[1] for ln in out.splitlines() if " " in ln}
    look = json.loads(lines.get("LOOKUP", "{}"))
    check("the bot learns whose code it is", look.get("userId") == aid and look.get("name") == "QA Alerts T" and look.get("env") == "testnet"
          and look.get("lang") == "es", lines.get("LOOKUP", out[:200]))
    check("the bot claims it", json.loads(lines.get("CLAIM", "{}")).get("userId") == aid, lines.get("CLAIM", ""))
    check("a used code says nothing", lines.get("AGAIN") == "{}", lines.get("AGAIN", ""))
    check("the bot's sync lists the owner and the chat", lines.get("SYNC") == "True", lines.get("SYNC", ""))
    code, st = call("GET", "/api/me/telegram", token=token)
    check("the owner sees the linked chat", [c["label"] for c in st.get("chats", [])] == ["E2E test (@e2e)"], json.dumps(st))
    code, _ = call("DELETE", "/api/me/telegram", token=token)
    check("the owner unlinks it", code == 200 and call("GET", "/api/me/telegram", token=token)[1].get("chats") == [])
finally:
    code, ch = call("POST", "/api/action/challenge", {"accountId": aid, "action": "revoke"})
    code, r = call("POST", "/api/action", {"sessionId": ch.get("sessionId", ""), "walletSignature": w.sign_data(ch.get("messageToSign", "").encode())})
    check("the test agent is deleted", code == 200, f"{code} {r.get('error', '')}")
print(f"{sum(results)}/{len(results)} checks passed")
