# EdgeCraft-StrikeCity

**A living city where trading agents and Strike's copy traders walk the streets, driven by real data from Strike Finance.**
Create an agent with your Cardano wallet, connect it to your own Strike account with Strike's builder code, watch it
work in the city, and let it copy the best traders on Strike for you, with every rule signed by your wallet.

- **Live:** https://edgecraft-strikecity.pages.dev (Strike mainnet) · **Staging:** https://qa.edgecraft-strikecity.pages.dev (Strike testnet)
- **Built for:** the Strike Hackathon (October 2026)
- **Built by:** EdgeCraft

---

## What it is

| | |
|---|---|
| **Smart Flow agents** | Autonomous trading agents that run the Smart Flow strategy (trend breakouts with volume, 4h) on the user's own Strike account. The user signs one message with their wallet; Strike authorises an API wallet for the agent under our builder code. The agent's private key never leaves our host; Strike locks any withdrawal to the user's own wallet, and our agents never request one. |
| **EdgeCraft-StrikeCity** | A pixel-art city (96 × 64 tiles) where every agent and every copied trader is a character. Nobody moves for show: a candle close sends an agent to the Signal Lab, an order to the Strike Exchange, a risk check to the Risk Office, a stop to Liquidation Alley, an open position to that market's tower. |
| **Copy Arena** | Strike's copy trading, made visible: the traders people copy on Strike walk the city with the people copying them behind them. A leaderboard ranks them with the **Strike City score**, which is weighted on what real copies made and re-tested every hour against every copy Strike has published. |
| **Copy with your agent** | Sign a copy plan with your wallet (a trader, or "my agent chooses" with your rules: minimum score, platforms, review period, amount, stop-loss, leverage, excluded markets, end date) and your agent runs it on Strike's own copy trading, in a managed sub-account that Strike funds from your account, with Strike enforcing the stop-loss. |
| **News Tower** | A six-floor building with the news that moves crypto: headlines from official and tier-one sources, scored by a model, de-duplicated by story, and checked against Strike's mark price after publication. When a market's reading changes level, the agents trading it walk over to read it (they never trade on news). |

## How it uses Strike

Every part of the product reads or writes Strike. In short (the full list of endpoints is in
[docs/STRIKE_INTEGRATION.md](docs/STRIKE_INTEGRATION.md)):

- **Builder connect and builder code** (`SmartFlowAgent-EdgeCraft`, 0.20 % per execution): the onboarding asks Strike for
  the message to sign, the user's wallet signs it, and the site checks that Strike authorised exactly our API wallet,
  builder code and fee before anything is saved.
- **Trading** with the official v2 REST API: markets, order book, orders with a protective stop attached, positions,
  fills, funding and account history, leverage, all signed with Ed25519 API-wallet keys.
- **Copy trading**: discover, leaderboard, lead traders, subscriptions (create, update, stop), managed sub-accounts, and
  the copy-trading dashboard series.
- **Market data in the city**: live prices, the order book on the Exchange's big screen, funding on the fountain, the
  mark price behind every news reaction.

## Architecture at a glance

```
 Browser (React + Vite, canvas city)
        │  HTTPS
 Cloudflare Pages + Functions + D1  ── the site, the API, sessions, signed plans, the public snapshots
        ▲  HMAC-signed push/pull (no open ports at home)
        │
 Agents' host (Linux container, Python 3.13, systemd)
   paper agents · users' agent fleet (testnet / mainnet) · copy collector · copy pilot (testnet / mainnet)
   news service · push · watchdog · strategy health · daily backups
        │  signed requests (API-wallet keys, encrypted at rest)
        ▼
 Strike Finance API (mainnet / testnet)   + Binance candles (signal feed) + Hyperliquid (copied traders' positions)
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Security in one paragraph

Users sign every change with their Cardano wallet (CIP-30, verified server-side: the key must hash to the address). A
copy plan is signed in plain words, once, and is versioned. API-wallet private keys are generated on our host, stored
encrypted and never sent anywhere; the site only knows public keys. The host and the site talk over HMAC-signed requests
with a two-minute window. Agents never request withdrawals (Strike locks them to the user's own wallet anyway), Strike enforces copy stop-losses, and every decision, request
and signature is kept in tamper-evident, hash-chained logs anchored on the site. Review and findings:
[docs/SECURITY.md](docs/SECURITY.md).

## Documentation

| Document | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flows, the agent engine, design decisions |
| [docs/STRIKE_INTEGRATION.md](docs/STRIKE_INTEGRATION.md) | Every Strike endpoint used, and what for |
| [docs/CITY.md](docs/CITY.md) | EdgeCraft-StrikeCity: buildings, what moves each character, accessibility |
| [docs/STRATEGY.md](docs/STRATEGY.md) | Smart Flow, the research behind it, risk levels, the builder fee, the Strike City score |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, controls, the security review and its findings |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Environments, deployment, switches, monitoring, audit trail, runbook |
| [docs/ROADMAP.md](docs/ROADMAP.md) | The future: product roadmap and how it scales |

## Run it locally

Python (agents, research, host services), from the repository root:

```bash
uv venv .venv && uv pip install -e ".[dev]"
.venv/Scripts/python -m pytest                 # the test suite
.venv/Scripts/smartflow data                    # download candles
.venv/Scripts/smartflow backtest --tf 240       # realistic 4h backtest, BTC/ETH/SOL
.venv/Scripts/smartflow analyze --tf 240        # what the strategy sees right now (no orders)
.venv/Scripts/smartflow strike-check --env mainnet
```

Web (Node 20), from `web/`:

```bash
npm install
npm run build && npm run preview                # http://localhost:4173, the city at /#/city
npm run build:cf                                # the Cloudflare build (site + Functions)
```

Real-browser checks (Playwright + axe-core) live in `web/scripts/`: `verify_city.py`, `verify_city_ui.py` (every
surface and button of the city, in English and Spanish), `verify_city_live.py`, `verify_onboarding_live.py` and
`verify_copy_live.py` (these two create and delete a test agent: staging only).

## Repository map

```
src/smartflow/     Python: core (signal engine), agent (runner, risk, execution, journal), strike (API client, auth,
                   keys), live (fleet, health, watchdog), copytrade (collector, score, copy pilot), news, api, backtest
web/src/           The site: landing, onboarding, My agent, the city (engine, agents, buildings, views)
web/server/        Cloudflare Functions: sessions, CIP-30, builder connect, copy plans, host endpoints
web/functions/     Thin route files for Pages Functions
web/migrations/    D1 schema
config/            Strategies registry, paper agents, city, news sources, macro calendar
deploy/            systemd units and install scripts for the agents' host
tests/             pytest suite
reports/           Research outputs (backtests, event and exit studies)
```

## Credits

- City and character art: **LimeZu**, Modern Exteriors and Modern Interiors (https://limezu.itch.io), licensed for
  commercial use; only composed images are published, never the packs.
- Strike Finance API and documentation (https://docs.strikefinance.org). Hyperliquid public API for copied
  traders' positions. Binance public market data for signal candles.
- The Smart Flow indicator is EdgeCraft's own and is not included in this repository.

This repository is private and proprietary to EdgeCraft.
