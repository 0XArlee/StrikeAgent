<p align="center">
  <img src="docs/images/logo.svg" width="84" alt="EdgeCraft-StrikeCity logo">
</p>

<h1 align="center">EdgeCraft-StrikeCity</h1>

<p align="center">
  <b>Trading agents and Strike's copy traders, living in one city.</b><br>
  Built on Strike Finance for the Strike Hackathon, October 2026.
</p>

<p align="center">
  <a href="https://edgecraft-strikecity.pages.dev">Live app (mainnet)</a> ·
  <a href="https://edgecraft-strikecity.pages.dev/#/city">Enter the city</a> ·
  <a href="https://qa.edgecraft-strikecity.pages.dev">Staging (testnet)</a> ·
  <a href="docs/EdgeCraft-StrikeCity.pdf">Project book (PDF)</a>
</p>

![EdgeCraft-StrikeCity: agents and copy traders around the Strike Exchange, with Strike's live BTC order book on the big screen](docs/images/city.jpg)

## The idea

Trading on Strike happens behind numbers. A trading bot is a process nobody sees, and a copy-trading leaderboard is a
list that tells you very little about what copying someone actually did for the people who tried it.

We wanted to make all of that visible. EdgeCraft-StrikeCity is a pixel-art city where every character is driven by
real data from Strike. Trading agents walk to the Signal Lab when a candle closes, to the Strike Exchange when they
send an order, and to a market's tower while they hold a position there. The traders people copy on Strike walk the
streets with their current copiers in a line behind them. Nothing moves for decoration.

Behind the city sits a complete product. You can create an agent that trades your own Strike account with a single
wallet signature, choose whom to copy with a score that was tested on real copies, and let your agent run that copy
for you under rules you sign.

| Live | 1 | 34 | 389 | 174 | 0.20 % |
|:---:|:---:|:---:|:---:|:---:|:---:|
| on Strike mainnet, with a staging copy on testnet | signature to start an agent on your own Strike account | Strike endpoints in use | real copies behind the score, re-tested hourly | automated tests, plus real-browser checks | builder fee per execution, approved by each user |

## What you can do

### Watch the agents and the traders, live
Every agent and every copied trader is a character. Click one to see what it holds, what it decided at the last candle
and why. Market towers show Strike's prices, the Exchange shows Strike's live order book, and the fountain changes
colour with BTC funding. → [docs/CITY.md](docs/CITY.md)

### Pick a strategy from the marketplace
The landing page is a catalogue of strategies, each with its rules, its full backtest after every cost, and a page of
its own. One registry (`config/strategies.json`) feeds the catalogue, the onboarding, the agents' host and the server,
so a new strategy is added as data and appears everywhere at once.

<p align="center"><img src="docs/images/strategies.jpg" width="85%" alt="The strategy marketplace on the landing page"></p>

### Create your agent with one signature
Design a character, give it a personality and a trade, pick a strategy, markets and risk, and sign once with your
Cardano wallet. That single signature goes to Strike's builder connect, which authorises an API wallet for the agent on
**your own Strike account** under our builder code. Your funds never leave Strike. The review screen spells out exactly
what the agent can and cannot do before you sign.

<p align="center">
  <img src="docs/images/onboarding-character.jpg" width="49%" alt="Character creator">
  <img src="docs/images/onboarding-review.jpg" width="49%" alt="The review step before signing">
</p>
<p align="center"><img src="docs/images/meet-card.jpg" width="60%" alt="The 'Meet your agent' card at the end of the onboarding"></p>

### Choose whom to copy, with evidence
The **Copy Arena** reads Strike's copy trading and ranks every trader with the **Strike City score**, built from what
earlier copies of that trader really made, Strike's own copy score, the length of the record and the account's size.
The score is re-tested every hour against every copy Strike has published, and the result is shown in the arena.

<p align="center">
  <img src="docs/images/lead-in-trade.jpg" width="49%" alt="A copied trader at the Exchange with the people copying them">
  <img src="docs/images/arena-podium.jpg" width="49%" alt="Inside the Copy Arena: the podium">
</p>

### Let your agent copy for you
Sign a copy plan: one trader, or "my agent chooses" with your own rules (minimum score, platforms, how often to review,
how many changes a week), plus the amount, stop-loss, leverage, markets to avoid and an end date. Your agent runs it on
**Strike's own copy trading**, in a managed sub-account that Strike creates and funds for that copy, and Strike itself
enforces the stop-loss.

<p align="center"><img src="docs/images/copy-plan-pilot.jpg" width="85%" alt="The copy plan in pilot mode"></p>

### Read the news that moves your markets
The **News Tower** has six floors of headlines from official and tier-one sources, scored by a model, counted once per
story and checked against Strike's mark price after they came out. When a market's reading changes level, the agents
trading it walk over to read it. They never trade on news.

<p align="center"><img src="docs/images/tower-newsroom.jpg" width="85%" alt="Inside the News Tower: the newsroom"></p>

## Built on Strike

Strike is the venue for everything here, not just a data source. The full list of calls is in
[docs/STRIKE_INTEGRATION.md](docs/STRIKE_INTEGRATION.md); in short:

- **Builder connect and builder code.** Onboarding runs through `request-signature` and `verify-signature`, and the site
  checks that Strike linked exactly our key, our builder code (`SmartFlowAgent-EdgeCraft`) and our 0.20 % fee before
  saving anything.
- **Trading.** Markets, fee tiers, book ticker, depth, mark price, account, positions, open orders, orders with their
  stop attached as a bracket, cancels, leverage, fills and transfers, all signed with Ed25519 API-wallet keys, on
  mainnet and testnet.
- **Copy trading.** Discover, the leaderboard of every copy relationship, subscriptions, managed copies with
  auto-created sub-accounts (create, update, stop), and Strike's copy-trading dashboard (its summary and six daily
  series).
- **Market data in the city.** 24-hour tickers on the towers, the order book on the Exchange's screen, funding on the
  fountain, and Strike's 1-minute mark candles behind every news reaction.
- **Strike's app.** Every trader card links straight to that trader's public portfolio on Strike, where anyone can
  copy them by hand.

## What we built during the hackathon

The project existed before the hackathon: the Smart Flow engine and its agents, builder-connect onboarding, the first
version of the city and the strategy marketplace. Between 21 and 23 October we added:

| | |
|---|---|
| **Copy Arena** | The copy-trading collector, history kept beyond Strike's 30 days, the arena building and its interior, traders walking the city with their copiers |
| **Strike City score** | A study on every published copy, the score built from it, and an hourly live re-test shown in the app |
| **Copy with your agent** | Signed copy plans (manual or pilot) carried out on Strike's copy trading in managed sub-accounts, verified on testnet and now open on mainnet |
| **News Tower** | Tiered sources, model scoring, one vote per story, reactions on Strike's mark price, and a six-floor interior your agent walks through |
| **A new city** | The whole map redrawn with licensed LimeZu art, a character creator, personalities and trades for every agent |
| **Trust and polish** | A security review, accessibility checks on every surface, and this documentation |

The commit history shows each step. → [docs/HACKATHON.md](docs/HACKATHON.md)

## Try it in five minutes

1. **No wallet needed.** Open [the city](https://edgecraft-strikecity.pages.dev/#/city), click a character with a
   pink ring to see a trader people copy on Strike, then open **Ranks** and enter the **Copy Arena**.
2. Click the **News Tower** and go inside, or open **News** in the top bar.
3. Browse the [strategy catalogue](https://edgecraft-strikecity.pages.dev/#strategies) and open a strategy's page.
4. **With a Cardano wallet** (Lace, Eternl, Yoroi, Typhon, VESPR, NuFi, Begin, GeroWallet or any CIP-30 wallet),
   press **Connect wallet** to create an agent on your own Strike account. On staging the same flow runs on Strike
   testnet with a Preprod wallet.

## Under the hood

```
Browser (React + Vite, canvas city engine, CIP-30 wallet)
   │
Cloudflare Pages + Functions + D1     sessions, signature checks, builder connect, signed plans, public snapshots
   ▲   outbound only, HMAC-signed
Agents' host (Linux container, Python, systemd)
   paper agents · users' agents · copy collector · copy pilot · news · push · watchdog · health · backups
   │   Ed25519-signed requests, keys encrypted on the host
Strike Finance API (mainnet / testnet)  ·  Binance candles  ·  Hyperliquid public data
```

- **One engine for backtest and live**, fed candle by candle, so the live signal is the backtested signal.
- **Keys stay on the host.** The site only knows public keys; the host never listens to the internet.
- **Everything is evidence.** Every signed action, Strike request, fill and balance change is written to hash-chained
  logs whose heads are anchored on the site.
- **Quality.** 174 Python tests, plus real-browser checks with Playwright and axe-core on every surface of the city, in
  English and Spanish, on desktop and phone sizes.

More in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/SECURITY.md](docs/SECURITY.md) and
[docs/QUALITY.md](docs/QUALITY.md).

## Where it goes next

Strike's 2026 roadmap brings vaults, a marketplace for trading tools, spot and real-world assets, a mobile app and
lending. This project already has the pieces for each: agent vaults with a verifiable record, a creators' marketplace
on top of the strategy registry, new districts of the city for new markets, and a social layer (seasons, leagues,
teams) around everything that trades on Strike. The plan, and how each part scales from tens to thousands of users, is
in [docs/ROADMAP.md](docs/ROADMAP.md).

## Documentation

| | |
|---|---|
| [Project book (PDF)](docs/EdgeCraft-StrikeCity.pdf) | Everything below in one designed document |
| [HACKATHON.md](docs/HACKATHON.md) | What was built during the hackathon, the judging criteria, a guide for judges |
| [STRIKE_INTEGRATION.md](docs/STRIKE_INTEGRATION.md) | Every Strike endpoint we call, and why |
| [CITY.md](docs/CITY.md) | The city: buildings, characters, live data, accessibility |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, services, data flows, design decisions |
| [STRATEGY.md](docs/STRATEGY.md) | Smart Flow, the research, risk levels, the builder fee, the Strike City score |
| [SECURITY.md](docs/SECURITY.md) | How users are protected, and the security review |
| [QUALITY.md](docs/QUALITY.md) | Staging on Strike testnet, the tests, real-browser checks, accessibility |
| [OPERATIONS.md](docs/OPERATIONS.md) | Deployment, switches, monitoring, audit trail |
| [ROADMAP.md](docs/ROADMAP.md) | The future: product, scaling, business model |

## Run it locally

```bash
# Python: agents, research and host services
uv venv .venv && uv pip install -e ".[dev]"
.venv/Scripts/python -m pytest
.venv/Scripts/smartflow analyze --tf 240        # what the strategy sees right now (no orders)

# Web: from web/
npm install
npm run build && npm run preview                # http://localhost:4173, the city at /#/city
```

## Repository

```
src/smartflow/   the engine, agents, Strike client, copy trading, news, host services
web/             the site, the city and the Cloudflare Functions
config/          strategy registry, paper agents, city, news sources, macro calendar
deploy/          systemd units and install scripts for the agents' host
tests/           pytest suite        reports/  research outputs        verify_pyne/  engine cross-check
```

## Credits

City and character art by **LimeZu** (Modern Exteriors and Modern Interiors, limezu.itch.io), used under its commercial
licence; only composed images are published. Market and copy-trading data from Strike Finance, copied traders'
positions from Hyperliquid's public API, signal candles from Binance's public market data.

© 2026 EdgeCraft. All rights reserved. See [LICENSE](LICENSE).
