# Architecture

Three parts, each doing one job: a static site with a small serverless API on Cloudflare, a host that runs everything
that needs keys or a long-lived process, and Strike. Nothing at home listens to the internet: the host only makes
outbound, signed requests.

![How EdgeCraft-StrikeCity is built: the browser, Cloudflare, the agents' host and Strike](images/diagram-architecture.svg)

## The site (`web/`)

- **Front end** (`web/src`): React 18 + Vite. The landing with the strategy marketplace, the onboarding (character,
  personality, strategy, review, one signature), "My agent" (positions, decisions, settings, copy plan), and the city.
  English and Spanish throughout.
- **The strategy marketplace**: every strategy users can pick lives in one registry, `config/strategies.json`, read by
  the landing's catalogue, each strategy's own page, the onboarding, the server's checks and the agents' host. A
  strategy is listed only with its backtest figures (`config/figures/<id>.json`, generated with the agents' own account
  model), and an entry can name its creator and a revenue share, ready for third-party strategies.
- **The city engine** (`web/src/city/engine.ts`, `agents.ts`, `world.ts`): a tile map with roads, crossings and doors,
  A* paths, sprite animation, day and night, weather, building signs and screens drawn from live data, cars that are
  Strike's real trades, and a camera that follows a character and keeps it clear of open panels. Each character's
  position is a function of real state (see [CITY.md](CITY.md)).
- **The city's store** (`web/src/city/store.ts`): reads the site's snapshots (`/api/city`, `/api/copy`, `/api/news`)
  and Strike's public market data straight from the browser (tickers, every market, funding, the order book and the
  latest trades), so what the city shows of Strike's market is Strike's own data with nothing of ours in between. On
  production the top bar and Ranks count real accounts only; staging counts the paper agents too.
- **Functions** (`web/server`, routed by `web/functions/api`): every endpoint is small and explicit. Public: `info`,
  `city`, `copy`, `news`. Owners (bearer session from a wallet signature): `me`, `action/challenge` + `action` (every
  change is a fresh signature over a one-time message), `live/*` (connect, stop), `feedback`. Host only (HMAC):
  `internal/push`, `live`, `keys`, `copyplans`, `copystatus`, `copy`, `news`, `anchors`, `heads`, `audit`,
  `feedback`.
- **D1 schema**: `web/migrations/001-008`. The `audit` table has triggers that refuse updates and deletes.
- **Edge cache**: `/api/city`, `/api/copy` and `/api/news` are cached at the edge for 15-30 s and purged on change.

## The agents' host (`src/smartflow`)

Python 3.13, standard library HTTP, one runtime dependency (`cryptography`). Layers only import downwards.

| Package | What it does |
|---|---|
| `core/` | The Smart Flow signal engine: Pine v6 semantics, the signal, the higher-timeframe bias without lookahead, the exit rules. Pure: no I/O, no clock. The same engine runs the backtest and the live agents, bar by bar. |
| `agent/` | The runner (one agent, many markets), the risk engine (size from the stop, daily and weekly loss limits, leverage rule, safety hold), the trade lifecycle, execution (Strike or paper on Strike's real book), the hash-chained journal. |
| `strike/` | Strike client (official REST v2), Ed25519 request signing, API-wallet keys, conformance checks. |
| `live/` | The fleet (starts and stops one agent per connected user from the site's list), the encrypted key pool, strategy health against the backtest, the watchdog. |
| `copytrade/` | The Copy Arena collector and score (`service.py`, `store.py`), and the copy pilot (`pilot.py`). |
| `news/` | Feeds, model classification, de-duplication by story, reaction on Strike's mark price, per-market reading, scoreboard. |
| `api/` | The city snapshot (`city.py`: what is public from each journal) and the signed push to the site (`push.py`). |
| `backtest/`, `verify/` | Realistic simulator and studies; checks against TradingView exports and a replay of live journals. |

### Services (systemd, all hardened: `NoNewPrivileges`, `ProtectSystem=strict`, private tmp, memory caps)

| Unit | Runs |
|---|---|
| `smartflow-paper@<id>` | An official paper agent (Smart Flow, Pyramid and internal variants), on Strike's real order book |
| `smartflow-fleet` / `-mainnet` | Users' agents on testnet / mainnet (mainnet needs `--allow-mainnet` and an explicit acknowledgement in its settings) |
| `smartflow-copy` | Copy Arena collector, outbound only, no keys |
| `smartflow-copypilot` / `-mainnet` | Owners' signed copy plans on Strike testnet / mainnet |
| `smartflow-news` | The News Tower's data, every 5 minutes |
| `smartflow-push` / `-qa` | Signed snapshots of the city, the news and the Copy Arena to production / staging; forwards suggestions to the operator |
| `smartflow-watchdog.timer` | Every 5 min: a stopped service, a site without fresh data, an agent that stopped checking candles, a full disk |
| `smartflow-health.timer` | Every hour: each strategy's paper agent against its backtest; can put a strategy on a safety hold |
| `smartflow-data.timer` | Daily candle sync |
| `smartflow-backup.timer` | Daily backup of `runs/` and a check of every hash chain |

## Key design decisions

| Decision | Why |
|---|---|
| One engine for backtest and live, fed bar by bar | The live signal is the backtested signal by construction; a prefix-invariance test guards against lookahead. |
| Signal on Binance closes, execution on Strike's book, stops on Strike's mark | Explicit separation of signal price, risk price and executable price; the basis is bounded. |
| Entries are limit IOC with the stop attached, confirmed on the book before the trade is "protected" | Bounded slippage, protection from the first fill, a fallback stop if one is ever missing. |
| Deterministic `client_order_id` per trade and purpose | Retries are idempotent: the agent looks the order up before sending it again. |
| Risk before execution, always | No order without the risk engine; autonomous mode needs config, an environment acknowledgement and, on mainnet, a separate switch. |
| Keys only on the host, public keys on the site | A compromise of the site cannot sign anything on Strike. |
| Host pulls, never listens | No inbound ports, no tunnel: the host polls the site and pushes signed snapshots. |
| Append-only, hash-chained logs with heads anchored on the site | Any claim can be answered with evidence, and a rewrite on the host would no longer match the site. |
| A strategy registry (`config/strategies.json`) read by the host, the site and the server | Adding a strategy is data, not code, and an unknown strategy is never run as another one. |

## Environments

| | Production | Staging (QA) |
|---|---|---|
| Site | edgecraft-strikecity.pages.dev | qa.edgecraft-strikecity.pages.dev |
| Strike | mainnet | testnet |
| Cardano wallets | mainnet | Preprod |
| D1 | `smartflow-city` | `smartflow-city-qa` |
| Host services | `-mainnet` units, `push` | testnet units, `push-qa` |

Every change goes to staging first and is verified there in a real browser before production: see
[QUALITY.md](QUALITY.md).
