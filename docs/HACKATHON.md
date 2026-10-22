# EdgeCraft-StrikeCity at the Strike Hackathon

Strike asked builders for something that integrates with, extends or enhances the Strike ecosystem, with a working
prototype, documentation, a demo and the code. This page explains what we brought, what we built during the
hackathon window (21 October, 10:00 EST, to 23 October, 10:00 EST), and where to look to judge it.

## Where we started

We came to the hackathon with a working base, which the rules allow for projects that add meaningful new
functionality:

- **Smart Flow**, a trend-breakout strategy, its signal engine and research, with agents that trade on Strike.
- **Onboarding through Strike's builder connect**: a Cardano wallet signs once and the agent trades the user's own
  Strike account under our builder code.
- **A first version of the city** with the official agents, and the **strategy marketplace** on the landing page.

## What we built during the hackathon

Times are Central European, taken from the commit history.

**Wednesday 21 October**
- 17:10 · A character creator built on LimeZu's licensed character generator.
- 18:15 · The news service: headlines, reactions measured on Strike's mark price, a reading per market, and a first
  view in the city.
- 19:59 – 22:43 · The whole city redrawn with LimeZu's Modern Exteriors, with every door checked to be reachable on foot.
- 23:31 · The news reviewed the way a trading desk would read it: tiered sources, a calibrated model, catalysts only,
  one vote per story, moves compared with each market's normal move.
- 23:54 · News live in production.

**Thursday 22 October**
- 08:14 · The **News Tower** interior: six floors, a lift, and your agent walking to whatever you choose. Geopolitics
  and regions added to the news. **Personalities and trades** for every agent, the "Meet your agent" card, and
  in-app suggestions.
- 09:39 · The **copy-trading collector**: Strike's traders, everyone who copies them and how it went, kept beyond the
  30 days Strike's API returns.
- 10:27 · The **Copy Arena**: traders walking the city with their copiers, the arena building, its leaderboard and podium.
- 12:15 · **Copy with your agent**, and the **Strike City score**, tested on every copy Strike has published.
- 12:44 · Traders linked by account (sub-accounts open their main account), Strike's own names and badges.
- 13:04 · The first real copy run by an agent on Strike testnet: a managed sub-account created and funded by Strike.
- 14:11 – 20:53 · City polish, every Strike trader listed in the city, the News Tower visited when a reading changes,
  copiers shown as "now" and "all time".
- Evening · A security review of the copy feature, end to end, before opening it on mainnet.
- 22:10 · **Copy with your agent open in production**, on Strike mainnet.
- 22:43 – 23:12 · Code cleanup and this documentation.

**Friday 23 October**
- The project book (PDF) and the demo video.

## How it answers the judging criteria

**Innovation and creativity.** Strike's market becomes a place you can walk around. Every character is real state
(an agent waiting for a candle, a trader holding a position, the people copying them right now), so the city doubles as
a live dashboard that people actually enjoy watching. The Strike City score is measured, not guessed: it was built
from the copies Strike publishes and is re-tested every hour in public.

**Integration with Strike.** Builder connect and the builder code for onboarding and revenue, the v2 trading API for
the agents, the copy-trading API for discovery, history and managed copies with auto-created sub-accounts, the
copy-trading dashboard, and Strike's prices, order book, funding and mark candles drawn into the city. Mainnet and
testnet, both live. Every call is listed in [STRIKE_INTEGRATION.md](STRIKE_INTEGRATION.md).

**Utility and impact.** Only about one copy in five on Strike ends in profit, and a leaderboard number does not tell
you who is worth copying. The Copy Arena shows what copying each trader actually did, and copy with your agent turns a choice into a
signed, limited, automatic plan. For Strike, every user's agent trades through the builder code, every copy it starts
brings money and copiers into Strike's own copy trading, and every user who joins through us has their Strike account working with an agent from the first minute.

**Technical execution.** Live on mainnet, with a staging copy on testnet. One engine for backtest and live, keys that
never leave the host, wallet signatures verified server-side, hash-chained audit logs anchored off the host, 174
tests, and real-browser checks with accessibility audits on every surface in two languages
([QUALITY.md](QUALITY.md)).

**Future potential.** The pieces line up with Strike's 2026 roadmap: agent vaults with a verifiable record, a
creators' marketplace on top of the strategy registry, new districts for spot and real-world assets, and a social layer
around everything that trades on Strike ([ROADMAP.md](ROADMAP.md)).

## A guide for judges

**In five minutes, no wallet needed**
1. Open https://edgecraft-strikecity.pages.dev/#/city and click a character with a pink ring.
2. Open **Ranks**, then enter the **Copy Arena** and visit the podium and the leaderboard.
3. Click the **News Tower** and go inside; try the lift.
4. Open the [strategy catalogue](https://edgecraft-strikecity.pages.dev/#strategies) on the landing page.

**With a Cardano wallet**, create an agent on your own Strike account from **Connect wallet**. On staging
(https://qa.edgecraft-strikecity.pages.dev) the same flow runs on Strike testnet with a Preprod wallet.

**In the code**

| To see | Read |
|---|---|
| How a character decides where to walk | `web/src/city/agents.ts` |
| The city engine | `web/src/city/engine.ts` |
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
| Builds on Strike in a meaningful way | Builder code, trading API, copy-trading API, market data: [STRIKE_INTEGRATION.md](STRIKE_INTEGRATION.md) |
| Working prototype | Live on mainnet: https://edgecraft-strikecity.pages.dev |
| Documentation | This folder, the [README](../README.md) and the project book (PDF) |
| Demonstration | The demo video, and the live app itself |
| Source code | This repository |
