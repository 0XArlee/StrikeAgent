# EdgeCraft-StrikeCity at the Strike Hackathon

Strike asked builders for something that integrates with, extends or enhances the Strike ecosystem, with a working
prototype, documentation, a demo and the code. This page explains what we brought, what we built during the
hackathon (21 to 23 October 2026), and where to look to judge it.

## Where we started

We came to the hackathon with a working base, which the rules allow for projects that add meaningful new
functionality:

- **Smart Flow**, a trend-breakout strategy, its signal engine and its research, with agents that trade on Strike.
- **Onboarding through Strike's builder connect**: a Cardano wallet signs once and the agent trades the user's own
  Strike account under our builder code.
- **A first version of the city** with the official agents, and the **strategy marketplace** on the landing page.

## What we built during the hackathon

Three days, more than 40 commits and more than 12,000 new lines of code (Python, TypeScript and CSS), all of it
live on Strike mainnet with a staging copy on testnet. Twenty-five of the 46 Strike endpoints the project uses were
integrated during these days: the whole of Strike's copy trading, Strike's own statistics, and its live trades.

### 1. The Copy Arena: Strike's copy trading, made visible

A copy-trading leaderboard shows a trader's own return. It does not show what happened to the people who copied them,
which is what someone about to copy needs to know. The Copy Arena puts that in front of them.

- **A collector for Strike's copy trading.** It reads Strike's traders, the leaderboard of every copy relationship and
  how it ended (active, stopped, liquidated), who copies whom, the traders' open positions and Strike's own
  copy-trading dashboard with its six daily series. It keeps the history beyond the 30 days Strike's API returns, and it
  holds no keys.
- **Every trader, linked properly.** Traders are matched by account: a sub-account opens its main account, Strike's
  own names and gold and silver badges are shown, and accounts that only copy others are left out, because Strike never
  passes their copied orders on to whoever copies them.
- **Traders who walk the city.** Each trader is a character with a pink ring and a score over their head. They walk to
  the tower of their biggest position, run to Strike Finance when they open, close, flip or resize on Strike, and wait at
  the Copy Arena's door while they hold nothing. The people copying them right now walk behind them in a line.
- **The arena itself.** A building with an interior: the leaderboard on an LED wall, the three best on a podium, the
  copiers' wall with the copies that went best, and Strike's copy-trading totals. The landing page has a section with
  the hall live inside it, and the Ranking tab of Results shows the three best traders to copy.
- **Clear numbers on every card.** Who copies a trader now, how many copies they have had in total, and how many of
  those ended in profit, kept apart so nobody confuses one with the other.

### 2. The Strike City score, tested on every copy

- **A study of every published copy.** Each copy on Strike's leaderboard was scored only with what was known before it
  started, then compared with how it ended. What earlier copiers made predicted outcomes best; Strike's own copy score
  alone did not; and smooth PnL curves, often market makers, were the hardest to copy.
- **A score built from that evidence**: earlier copies in profit (30 %), Strike's copy score (30 %), the length of the
  record (20 %) and the account's size (20 %), with the deepest fall shown but not weighted. Every trader's profile
  shows each part, so nobody has to take the number on trust.
- **A public, hourly re-test.** The collector repeats the study every hour on every copy it has seen, and the arena
  shows the result live. At the time of writing, on 389 copies of 70 traders, a copy in profit outscored one at a loss
  59 % of the time with our score, against 50 % (a coin toss) with Strike's alone.

### 3. Copy with your agent

- **Signed copy plans.** Choose one trader, or let your agent choose by your rules (a minimum score, the platforms you
  accept, how often it reviews its choice, how many changes a week). Add the amount, a stop-loss, the leverage, markets
  to avoid and an end date. The plan is signed with your wallet, in plain words.
- **Carried out on Strike's own copy trading.** The copy pilot asks Strike to start a managed copy: Strike creates a
  sub-account for it, funds it from your account, copies the trader and enforces the stop-loss on its side. Limits can
  be changed or the copy stopped; every request is idempotent; a copy Strike stopped or refused halts the plan until you
  sign again; deleting an agent turns off its Strike connection and stops its copy.
- **Proven before it was opened.** The first real copy ran on Strike testnet (Strike created and funded the
  sub-account, and we checked it on Strike's API, on the host, in "My agent" and in the city). Then came the security
  review, and only then was the feature opened on mainnet.

### 4. The News Tower: news measured on Strike

- **A news service a trading desk would trust.** Official sources and tier-one outlets, search feeds filtered to the
  outlets we list, a model that scores each headline on a fixed scale and keeps catalysts only, one vote per story
  however many outlets carry it, and a reaction measured on Strike's 1-minute mark candles against each market's normal
  move. It covers geopolitics with each headline's region, the US macro calendar to 2027, and warns before US releases.
- **A reading per market**, from very bearish to very bullish, with what pushes it up or down, every story that counts
  and a scoreboard of how past readings turned out.
- **A building you walk into.** Six floors with a lift (the newsroom, Fed and macro, geopolitics, regulation and
  courts, money and flows, security and exchanges), an LED marquee on the facade, and your agent walking in with you.
  When the reading of a market changes level, the agents trading it walk over to read it. The strategies never trade
  on news; the news protects copies: a copy pauses during the security alarm (a major hack, an exchange going down) and,
  if its owner chose, around the big US releases on the tower's calendar.

### 5. Strike Finance, from the inside

- **The exchange's building, opened.** The building at the centre of the city is now called Strike Finance, and you can
  walk into it: a hall drawn with the same licensed art, where your agent walks to whatever you choose.
- **Strike's own numbers, live.** On the volume wall, each day's trading volume as bars; beside it every user, every
  trade, the TVL, revenue and deposits; on the console, the open interest and how many positions are long or short; at
  the desks, Strike's funding rate next to Binance's, Bybit's and OKX's; and Strike's vaults. All of it comes from
  Strike's public statistics API (11 endpoints new to the project), read straight from the browser.
- **Measured honestly.** Every long on a perpetuals exchange has a short on the other side, so the hall shows the open
  interest as one side's value and the mood as how many positions are long; Strike's summary reads zero open interest
  today, so the hall computes it from the live positions and the daily series.
- **STRIKE on its screen.** Outside, the building's screen shows STRIKE, Strike Finance's own token on Cardano, through
  DEX Screener's chart (TradingView has no chart of it), next to Strike's live order book.

### 6. Your money, clearly

- **Sub-accounts reused, or chosen.** A sub-account runs one copy at a time, so a new copy reuses one of the owner's
  that copies nobody and has the money (or the one they choose when signing), and only when none does Strike creates a
  new one. My agent lists every sub-account with its balance and whom it copies, and links to Strike's app to top one
  up (Strike keeps transfers between accounts to its app).
- **An account chart that never lies.** A tab per account: the result (deposits, withdrawals and money moved into a
  copy left out), every account together, the main account as it is, and each copy's sub-account. Money moved into a
  copy shows as a drop only on the main account's tab, explained there. Gradient, grid, dates and a point readout with
  the pointer, a finger or the arrow keys.
- **Strategy and copy independent.** Pausing the strategy keeps a copy going and stopping a copy keeps the strategy
  trading; My agent says so next to both.
- **Fees stated plainly.** The 0.20 % builder fee applies to the marketplace strategies' trades only; copies pay none to us.

### 7. The city, rebuilt and alive

- **New art.** The whole map redrawn with LimeZu's licensed Modern Exteriors, with every door checked to be reachable on
  foot, and a character creator built on LimeZu's generator.
- **Characters with a life.** Every agent has a personality (its voice) and a trade (chartist, reporter, tape reader,
  risk keeper) whose building it visits in shifts, showing the real data it reads there. A "Meet your agent" card closes
  the onboarding.
- **Strike's trades on the streets.** Every car in the city is a real trade on Strike mainnet: green when the taker
  bought, red when they sold, a truck from 5,000 $. A car stops under the mouse, and pressing it shows the trade.
- **A chart on every tower.** The BTC, ETH and SOL towers carry TradingView's live chart of their market on a screen on
  top, loaded only once the tower comes into view; at night the screens light themselves and no window shines over
  them.
- **Everything Strike lists.** Markets shows all 33 of Strike's markets with their names and maximum leverage, and
  Agents lists every trader people can copy on Strike.
- **Real accounts only in production.** Production shows and counts real accounts only; the paper agents that test
  the strategies live on staging, where paper and testnet trading belong and count.
- **A Results hub.** One button with tabs: a summary, the marketplace strategies (live results next to each backtest),
  the copy pilot (which agent copies whom), Strike's copy trading, and the ranking.
- **Questions by topic.** The landing's questions grouped in five topics, each one a short list of answers that open in
  place, covering everything new.
- **Polish where people look.** Readable building signs, a top bar that never overflows, characters that never stand
  cut off at the edge of the map, Connect wallet right in the dock (My agent once a wallet is in), a complete Guide, and
  a Suggest button that takes feedback with a screenshot.

### 8. A security review before mainnet

The copy feature moves real money, so before opening it we reviewed authentication and signatures, builder connect,
copy plans end to end, the host's endpoints, uploads, security headers, dependencies and the repository's history.
Result: no critical or high findings, 0 known vulnerabilities in production dependencies, no secrets in the code or its
history, and the server's signature checks cross-checked against independent references. The review and its hardening
backlog are published in [SECURITY.md](SECURITY.md#security-review-22-october-2026).

### 9. Verification, every step of the way

- Every change went to staging on Strike testnet first, was checked there in a real browser, then went to production
  and was checked again.
- `verify_city_ui.py` now walks every panel, button and dialog of the city in both languages (248 checks each), and new
  checks cover the cars, the Strike Finance hall and the screens, the separation of real and paper results, and every bug reported during testing, at desktop and phone
  sizes, with axe-core accessibility audits on every surface ([QUALITY.md](QUALITY.md)).

### 10. Clean code and documentation

- One checked bech32 decoder shared by the page and the server, typed agent voice moments, and no unused code.
- Documentation in English: this folder, the README with screenshots, every Strike call explained, diagrams generated
  from code (`web/scripts/build_diagrams.py`), and a designed project book (PDF) with an automatic index.

## How it answers the judging criteria

**Innovation and creativity.** Strike's market becomes a place you can walk around. Every character is real state (an
agent waiting for a candle, a trader holding a position, the people copying them right now) and every car is a real
trade, so the city doubles as a live dashboard people enjoy watching. The Strike City score is measured, not guessed:
it was built from the copies Strike publishes and is re-tested every hour in public.

**Integration with Strike.** 46 endpoints across six areas: builder connect and the builder code for onboarding and
revenue, the v2 trading API for the agents, the whole of copy trading (discovery, history, the dashboard, and managed
copies with sub-accounts Strike creates), Strike's live market data drawn into the city, Strike's own statistics inside
its building, and links into Strike's app.
Mainnet and testnet, both live. Every call is listed and explained in [STRIKE_INTEGRATION.md](STRIKE_INTEGRATION.md).

![Every Strike integration: 46 endpoints in six areas](images/diagram-integration.svg)

**Utility and impact.** Only about one copy in five on Strike ends in profit, and a leaderboard number does not tell
you who is worth copying. The Copy Arena shows what copying each trader actually did, and copy with your agent turns a
choice into a signed, limited, automatic plan. For Strike, every marketplace strategy trades through the builder code, every
copy it starts brings money and copiers into Strike's own copy trading, and every user who joins through us has their
Strike account working with an agent from the first minute.

**Technical execution.** Live on mainnet, with a staging copy on testnet. One engine for backtest and live, keys that
never leave the host, wallet signatures verified server-side, hash-chained audit logs anchored off the host, 180
tests, and real-browser checks with accessibility audits on every surface in two languages
([QUALITY.md](QUALITY.md)).

**Future potential.** The pieces line up with Strike's 2026 roadmap: agent vaults with a verifiable record, a
creators' marketplace on top of the strategy registry, new districts for spot and real-world assets, and a social layer
around everything that trades on Strike ([ROADMAP.md](ROADMAP.md)).

## A guide for judges

**In five minutes, no wallet needed**
1. Open https://edgecraft-strikecity.pages.dev/#/city and click a character with a pink ring: a trader people copy on
   Strike, with the people copying them behind.
2. Rest the mouse on a car and press it: a real trade on Strike, a few seconds or minutes old.
3. Click the **Strike Finance** building and go inside: Strike's own volume, open interest, users and funding, live.
   Then open **Results**, its **Ranking** tab, enter the **Copy Arena** and visit the podium and the leaderboard.
4. Click the **News Tower** and go inside; try the lift.
5. Open **Markets** for all of Strike's markets, and the
   [strategy catalogue](https://edgecraft-strikecity.pages.dev/#strategies) on the landing page.

**With a Cardano wallet**, create an agent on your own Strike account from **Connect wallet**. On staging
(https://qa.edgecraft-strikecity.pages.dev) the same flow runs on Strike testnet with a Preprod wallet.

**In the code**

| To see | Read |
|---|---|
| How a character decides where to walk | `web/src/city/agents.ts` |
| The city engine, the cars and the screens included | `web/src/city/engine.ts` |
| Strike Finance's hall and Strike's statistics | `web/src/city/StrikeView.tsx`, `web/src/city/strikestats.ts` |
| What the browser reads from Strike | `web/src/city/store.ts` |
| Builder connect and its checks | `web/server/live.ts` |
| Wallet signature verification | `web/server/cardano.ts` |
| Signed copy plans | `web/server/copyplan.ts` |
| The copy pilot on Strike | `src/smartflow/copytrade/pilot.py` |
| The collector and the score | `src/smartflow/copytrade/service.py` |
| An agent's loop and its risk engine | `src/smartflow/agent/runner.py`, `src/smartflow/agent/risk.py` |
| The Strike client | `src/smartflow/strike/client.py` |
| The news reading | `src/smartflow/news/score.py` |

## Submission checklist

| Requirement | Where |
|---|---|
| Builds on Strike in a meaningful way | 46 endpoints: builder code, trading API, copy trading, market data, Strike's own statistics ([STRIKE_INTEGRATION.md](STRIKE_INTEGRATION.md)) |
| Working prototype | Live on mainnet: https://edgecraft-strikecity.pages.dev |
| Documentation | This folder, the [README](../README.md) and the project book ([PDF](EdgeCraft-StrikeCity.pdf)) |
| Demonstration | The demo video, and the live app itself |
| Source code | This repository |
