# Quality and QA

This project moves real money, so we treat "it works" as something to prove, not to assume. Every change goes through
the same path: build it, ship it to a staging copy of the whole product running on Strike testnet, check it there in a
real browser, then ship it to production and check it again.

## Two environments, one codebase

| | Production | Staging (QA) |
|---|---|---|
| Site | edgecraft-strikecity.pages.dev | qa.edgecraft-strikecity.pages.dev |
| Strike | mainnet | testnet |
| Wallets | Cardano mainnet | Cardano Preprod |
| Database | its own D1 | its own D1 |
| Host services | mainnet fleet, mainnet copy pilot, production push | testnet fleet, testnet copy pilot, staging push |

Staging is not a mock-up. It runs the same code against Strike's testnet, with its own database, its own secrets and
its own services on the host, so a whole user journey can be exercised end to end, including real requests to Strike,
without touching anyone's money. Features that need extra care, such as copy with your agent, are switched on in
staging first and only reach production once a real run has been verified there.

## The test suite

174 Python tests (`pytest`) cover the parts where a mistake would cost money or trust:

| Area | What is checked |
|---|---|
| Signal engine | Pine primitives against reference formulas, hand-built signal scenarios, no lookahead (a test feeds growing prefixes of history and requires identical past signals), higher-timeframe alignment |
| Risk and lifecycle | Position size from the stop with a slippage margin, daily and weekly loss limits on marked-to-market equity, leverage that fits Strike's margin, the pyramid policy end to end, an empty account and later deposits |
| Strike adapter | Ed25519 request signing, the builder fee header on order-creating requests, tolerant parsing of Strike's answers (no network) |
| Users' agents | The encrypted key pool (keys never reused, signatures verifiable with the public key), the fleet, strategy health and the safety hold |
| Copy trading | History kept beyond Strike's 30 days, position changes, who copies whom, the score, and the copy pilot carrying out signed plans against a fake Strike |
| News | Feeds, de-duplication by story, reactions measured on Strike, the per-market reading and the scoreboard |
| Audit trail | Hash-chained logs, tamper detection, the report that answers a user's claim |
| Strategy registry | Every strategy in one place, and a new entry turning into working agents with no other change |
| Efficiency | Shared candle downloads, one positions call per turn, no rebuild of the city when nothing changed |

## Proving the engine is the strategy

- **An independent re-translation.** The original Pine script was re-translated separately into PyneCore, without
  looking at our engine, and both were run over the same history: identical signals across 6,000 four-hour candles
  (`verify_pyne/`).
- **TradingView exports.** `smartflow verify-tv` compares the engine bar by bar with TradingView's own output.
- **Live replay.** The agents' journals are replayed candle by candle against the backtest engine
  (`smartflow.verify.replay`); in the last full check, 200 of 200 candles matched.

## Proving the Strike integration

| Check | What it proves |
|---|---|
| `smartflow strike-check` | Strike's public API answers in the formats the client expects (markets, fee tiers, book ticker, depth, premium index) |
| `smartflow auth-check` | Signed reads work end to end: account, positions, open orders, fills, sub-accounts |
| Testnet order probe | Order mechanics on Strike testnet: brackets with `tp_order` / `sl_order`, a duplicate `client_order_id`, cancel-all |
| Mainnet test trade | The full loop on a real account: Strike's minimum order with its stop and the 20 bp builder fee, held two minutes, then closed |
| `test_server_crypto.py` | The server's BLAKE2b and CIP-30 verification against Python references (33 of 33 vectors, 10 of 10 valid and tampered signatures) |
| First real copy on testnet | A signed pilot plan made Strike create a managed sub-account, fund it with 100 $ from the owner's account and start the copy; checked on Strike's API, on the host, in "My agent" and in the city |

## Real-browser verification

Scripts in `web/scripts/` drive Chromium with Playwright, take screenshots and run axe-core (WCAG 2.2 AA) on each
screen. They wait for the city to be ready rather than for the network to go quiet, because the chart widget keeps
connections of its own open.

| Script | Checks | Environment |
|---|---|---|
| `verify_city_ui.py` | Every panel, button and dialog of the city, text cut off or overflowing, the dock fitting from 320 to 412 px, axe on each surface: 246 checks per language | staging and production |
| `verify_city.py` | The map paints and animates, panels, keyboard control, deep links, reduced motion, no horizontal overflow: 56 checks | both |
| `verify_city_live.py` | What the city shows matches the API and Strike: agents and traders counted apart, every trader people can copy listed, real accounts and paper agents ranked apart: 46 checks | both |
| `verify_city_cars.py` | The cars are Strike's real trades: the city reads `/price/v2/trades`, a car drives in, stops under the mouse, and pressing it shows its trade; the top bar counts what each site should: 12 checks | both |
| `verify_city_hq.py` | Strike Finance and the screens: STRIKE on the building's screen, TradingView on every tower once in view, the building's card takes you inside, Strike's figures, the daily volume as bars and the open interest are there, every spot answers, axe on the hall, nothing overflows at 390 px, the deep link and the way out: 29 checks | both |
| `verify_onboarding_live.py` | Creates an agent with a test wallet on Strike testnet, edits it, hides it, signs in again, switches wallets and deletes it, at 1440 and 390 px: over 100 checks | staging only |
| `verify_copy_live.py` | A signed copy plan carried out on Strike testnet, then stopped | staging only |

The last full run before this submission (23 October 2026, on staging and again on production) passed everywhere: 246
of 246 checks in English and in Spanish, 56 of 56, 46 of 46, 12 of 12 for the cars and 29 of 29 for Strike Finance and
the screens. The last onboarding run on staging (22 October) passed every check.

## Accessibility

- Zero axe-core violations (WCAG 2.2 AA) on every surface the scripts reach, in both languages.
- The map has a text description and keyboard control; dialogs keep focus and return it; changes are announced.
- Reduced motion is respected; colour tokens were chosen for contrast (body text above 5.9:1).

## In production

- A **watchdog** every five minutes (stopped services, a site without fresh data, an agent that stopped checking
  candles, a full disk), plus an **external watchdog** in GitHub Actions, ready to check the public site from
  outside.
- **Strategy health** every hour, with an automatic safety hold if live results leave the backtest's range.
- **Daily backups** of the audit trail with a check of every hash chain.
