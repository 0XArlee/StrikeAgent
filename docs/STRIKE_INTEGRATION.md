# How EdgeCraft-StrikeCity uses Strike

Strike is not a data source here; it is the venue. Users' agents trade on Strike, copies run on Strike's copy trading,
fees are earned through Strike's builder code, and the city draws Strike's market in real time. This page lists every
Strike call the product makes and what it is for.

Base URLs: mainnet `https://api.strikefinance.org`, testnet `https://api-v2-testnet.strikefinance.org`. The production
site runs on mainnet; the staging site (`qa.`) runs the same code on testnet.

## 1. Onboarding: builder connect

A user's agent trades the user's own Strike account through an API wallet that Strike authorises for our builder code.

| Step | Call | Who |
|---|---|---|
| Reserve a fresh API-wallet public key (generated on our host, private key never leaves it) | — | site (`web/server/live.ts`) |
| Ask Strike for the message the user's wallet must sign | `POST /auth/builder/request-signature` (`address`, `chain: cardano`, `code`, `fee_share_bps`, `public_key`) | site |
| The user's Cardano wallet signs Strike's message (CIP-30 `signData`) | — | browser |
| Send the signature to Strike, which links the account to our API wallet | `POST /auth/builder/verify-signature` | site |
| Check Strike linked **exactly** our key, builder code (`SmartFlowAgent-EdgeCraft`) and fee (20 bps); otherwise burn the key and save nothing | — | site |

The same wallet signature also proves the user owns the wallet, so creating an agent takes a single signature. Every
attempt, accepted or refused, is recorded with Strike's exact message and the signature.

## 2. Trading: the agents

Every user's agent and every official paper agent runs the same engine (`src/smartflow/agent/`). Requests are signed
with Ed25519 API-wallet keys (`src/smartflow/strike/auth.py`), with the server clock synced first.

| Purpose | Endpoints |
|---|---|
| Health and clock | `GET /v2/ping`, `GET /v2/time` |
| Markets, fees, limits | `GET /v2/markets`, `GET /v2/fee-tiers` |
| Executable prices and impact | `GET /price/v2/depth`, `GET /price/v2/ticker/bookTicker`, `GET /price/v2/premiumIndex` (mark price) |
| Account state, positions, open orders | `GET /v2/account`, `GET /v2/positions`, `GET /v2/openOrders` |
| Order lookup (idempotent retries by deterministic `client_order_id`) | `GET /v2/order` |
| Entries with their protective stop attached | `POST /v2/order` (limit IOC), `POST /v2/order/strategy` (stop / take-profit legs) |
| Stop management and exits | `DELETE /v2/order/cancel`, `DELETE /v2/order/cancel-all` |
| Leverage and margin | `POST /v2/leverage`, `POST /v2/marginMode` |
| Results that leave deposits out | `GET /v2/history/fill`, `GET /v2/history/transaction` (deposits, withdrawals, transfers), `GET /v2/history/funding` |

Every order-creating request carries the builder fee header (`X-Builder-Fee-Bps: 20`), so the execution is attributed
to our builder code; an agent that sees a fill attributed differently raises an error alert to the operator. The test trade in "My agent" opens
Strike's minimum order with its stop, holds it two minutes and closes it, so a new user can see the whole loop work.

Signals come from closed Binance candles (the design feed of the indicator, with full volume history); execution,
risk valuation and stops use Strike's book and mark price. See [STRATEGY.md](STRATEGY.md).

## 3. Copy trading

### The collector (read only, no keys)

`smartflow copy` on the host builds the Copy Arena's data and keeps history beyond the 30 days Strike's API shows:

| Purpose | Endpoints |
|---|---|
| Traders to copy, on Strike and on Hyperliquid through Strike | `GET /v2/copy/discover` |
| Every copy relationship and how it went (active, stopped, liquidated) | `GET /v2/copy/leaderboard` |
| A trader's account, name, sub-accounts, whom they copy | `GET /v2/account`, `GET /v2/copy/subscriptions` |
| The leads' open positions (they walk to that market's tower) | `GET /v2/positions` (Strike), `clearinghouseState` (Hyperliquid public API) |
| Strike's copy-trading totals | `GET /stat/v1/dashboard/copy-trading-summary`, `-volumes`, `-subscriptions`, `-profits`, `-liquidations`, `-allocated`, `-open-interest` |

From this it computes the **Strike City score** (0-100) and re-tests it every hour against every copy Strike has
published (see [STRATEGY.md](STRATEGY.md#the-strike-city-score)).

### Copy with your agent (signed by the owner, run on Strike)

`smartflow copypilot` carries out each owner's signed copy plan with that owner's API wallet:

| Purpose | Endpoints |
|---|---|
| Start a managed copy: Strike creates a sub-account for it and funds it from the owner's account (or from the last copy's sub-account) | `POST /v2/copy/subscribe` (`auto_create_sub_account`, `source_account_id`, fixed ratio or fixed margin, `stop_loss_amount`, `excluded_symbols`, isolated `margin_settings`, idempotent `request_id`) |
| Change the limits of a running copy | `PATCH /v2/copy/subscribe/{subscription_id}` |
| Stop a copy | `DELETE /v2/copy/subscribe/{subscription_id}` |
| Where each copy really is (Strike's own reading) | `GET /v2/copy/subscriptions?scope=all` |
| Balances before asking, so the owner is told plainly when the money is not there | `GET /v2/account` (main account and sub-accounts) |

Strike applies the stop-loss on its side. A copy Strike stopped at its stop-loss, or refused, halts the plan until the
owner signs again. Nothing here moves money out of Strike.

## 4. Market data in the city (browser, public)

| What you see | Endpoint |
|---|---|
| Prices and 24h change on the towers and the top bar | `GET /price/v2/ticker/24hr` |
| Funding colour of the fountain, mark prices | `GET /price/v2/premiumIndex` |
| The BTC order book on the Strike Exchange's big screen | `GET /price/v2/depth` |
| News reactions, measured after each headline | Strike's 1-minute mark-price candles (`GET /price/v2/klines`), on the host |

If Strike's public price endpoints cannot be reached, the city says so on screen and falls back to Binance for prices
only (the agents never trade on that fallback).

## 5. What it gives back to Strike

- **Volume and fees** through the builder code on every execution of every user's agent and every copy it runs.
- **New users** onboarded straight from a Cardano wallet into a funded, trading Strike account.
- **A better way to choose whom to copy**, tested on Strike's own copies, and a place where copy trading is visible
  and social.
- **Open data**: `GET /api/copy` (traders, scores, evidence) and `GET /api/city` (agents) are public JSON.
