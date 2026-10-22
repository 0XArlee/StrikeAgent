# The future: roadmap and scaling

EdgeCraft-StrikeCity is meant to become **the social layer of Strike**: the place where trading on Strike is visible,
shareable and verifiable, where people and their agents live side by side, and where choosing whom to follow is based
on evidence rather than on a leaderboard's headline number. This page describes where it goes next, how it fits
Strike's own 2026 roadmap, and how every part of it scales.

## 1. Where it fits in Strike's roadmap

Strike's 2026 roadmap (V2 CLOB and mobile, then spot and RWAs, fiat ramps, vaults and a trading-tools platform, then
cross-chain lending) maps one-to-one onto things this project already prepares for. The city even has buildings
waiting for them.

| Strike's roadmap | What EdgeCraft-StrikeCity adds | Already in place |
|---|---|---|
| **Vaults** (allocate to vetted trading firms) | **Agent vaults**: a strategy agent as a vault anyone can join, with a verifiable record (hash-chained journals anchored outside the host) and a live character in the city. The **Vault Bank** building becomes the place to see them. | Strategy registry, paper agents as public track records, strategy health and safety hold, audit trail |
| **Trading tools platform** (publish and rent tools) | A **strategy marketplace**: creators publish strategies that run first as paper agents, are gated by health against their backtest, and earn a share of the builder fee. **Smart Flow HQ** becomes the creators' building. | The registry already has a `creator` and `revenue_share_bps` per strategy; the host refuses to run what it cannot run |
| **Spot and RWAs** | New districts: an equities quarter, RWA towers, News Tower floors for earnings and rates. Agents and leads walk there as they do today. | Copied traders already hold equities and commodities through Hyperliquid (shown in their cards) |
| **Mobile app and fiat ramps** | Onboarding without a crypto wallet through Strike's ramps; the city as an embeddable view in Strike's app; push notifications ("your agent opened BTC", "your copy hit its stop"). | Fully responsive city and onboarding (tested at 320-1920 px), alert pipeline (`notify.py`) |
| **Cross-chain lending** | Agents that use lending collateral as margin, shown in the Vault Bank; risk rules that understand borrowed margin. | Risk engine with margin-aware leverage |
| **Copy trading growth** | Copy with your agent from anywhere Strike users are (Discord, X), a public score API, and a portfolio pilot that spreads a budget over several traders. | Copy pilot (manual and automatic), the Strike City score re-tested hourly, public `GET /api/copy` |

## 2. Product roadmap

### Next weeks
- **Copy pilot portfolios**: one plan, several traders, a budget split by score and correlation, rebalanced on the
  review period, with per-trader stop-losses.
- **Notifications per user** (Telegram, Discord, email): entries, exits, copies started or stopped, safety holds.
- **Embeddable widgets**: "Top 3 to copy", a trader's card, a live mini-city, for Strike's site, Discord and creators.
- **Score API**: the Strike City score and its evidence as documented, versioned public endpoints.
- **More markets** as Strike lists them: the strategy registry and the city pick them up from configuration.

### Next months
- **Seasons and leagues**: monthly seasons for agents and copy traders, ranked on risk-adjusted, verified results;
  the **Clan Hall** hosts teams (friends pooling agents, communities with a shared leaderboard).
- **Creator strategies** (see vaults and marketplace above), with a paper probation period and automatic holds.
- **Spectator and event modes**: macro releases and big liquidations become live events in the city; a "replay" of a
  day on Strike.
- **More languages** beyond English and Spanish (all text already lives in dictionaries).

### Longer term
- **On-chain anchoring** of the audit chains' heads (Cardano transaction metadata), so anyone can verify an agent's or a
  vault's history without trusting us.
- **Agent-to-agent economy**: agents that follow, hedge or copy other agents, with every relationship visible in the
  city.

## 3. More we can build on what exists

Each of these reuses something already running, which is why they are realistic:

- **Agents as copy-trading leads on Strike.** An agent trades its own Strike account, so it can become a lead in
  Strike's copy trading. Anyone could copy a Smart Flow agent from Strike's own app, and Strike gets new leads with a
  public, audited record.
- **Ethereum and Solana wallets.** Strike already supports them; builder connect signs differently on each chain, and
  the onboarding is built around one signature, so opening it to EVM and Solana wallets multiplies who can join.
- **Plain-language explanations.** Every decision already carries its reasons (range, volume, trend, risk check). A
  "why did my agent do that?" answer, and a weekly digest of what it did, are a short step away.
- **A Discord bot and alerts per user.** The alert pipeline exists; pointing it at each user's channel turns the city
  into notifications people act on.
- **A public API and widgets.** `/api/copy` and `/api/city` are already public; versioning them and adding embeddable
  widgets lets other builders, creators and Strike itself show the score and the city anywhere.
- **Research as a service.** The event study, the exit study and the hourly score test are reusable: any strategy in
  the registry, or any lead on Strike, can get the same independent evaluation.

## 4. How it scales

When last measured on the host (20 October), the Smart Flow services together used about 0.3 % of one CPU core and
~420 MB of memory. Per connected user the fleet makes one positions query every 30 s, reads open orders only for markets with trades, and
reads the account every 1-3 minutes. The site runs on Cloudflare's edge and caches its public documents for up to 30 s.

### Users' agents (10 → 10,000)
- **Shard the fleet**: the fleet is already a pure function of the site's list of links. Split it across workers by
  user id, each worker holding a lease per user in the database (no agent ever runs twice), with per-user state moved
  from local files to a shared store.
- **Batch and stream**: batch account and position reads per worker; move to Strike's streaming endpoints as they
  become available so reads stop growing with users.
- **Signal once, trade many**: a signal is computed once per market and strategy and fanned out to every agent on that
  strategy (the engine already caches candles per process).
- **Keys at scale**: move the key pool into a hardware-backed KMS with per-key usage policies; workers request
  signatures, never hold keys.

### The site
- **Live updates by push**: Cloudflare Durable Objects (or WebSockets at the edge) per city district instead of
  polling, so a thousand viewers cost the same as one.
- **Storage**: public snapshots to KV or R2, per-environment D1 databases for accounts, plans and audit, with the audit
  copied off-platform every minute as it is today.

### The city (hundreds → thousands of characters on screen)
- **Level of detail**: beyond a few hundred characters, crowds at a building collapse into a counted group that expands
  on zoom; only what is on screen is drawn and animated (today the engine skips off-screen labels and signs, and stops
  drawing while the city is hidden).
- **Districts**: the map grows by districts (markets, copy trading, vaults, creators), each loaded on demand.
- **Renderer**: the canvas engine draws from sprite atlases; a WebGL path is the next step for very large crowds.

### Data and research
- Copy-trading history moves from SQLite to a columnar store; the score's evidence becomes a scheduled job with a
  public, versioned report.
- Strategy health and the safety hold run per strategy and per creator, automatically.

### Reliability
- **Two hosts** in different locations, active and standby, with leases so a user's agent runs in exactly one place.
- The external watchdog checks the public site from outside; alerts go to the operator's phone.
- Service-level objectives for data freshness (city, copy, news) shown on a public status page.

### Security at scale
- The host re-verifies every signed plan and action against the user's wallet signature, so a compromised site could
  not change what an agent does.
- Per-user key isolation and rotation without user action; anomaly limits per account (order rate, notional).
- Third-party security audit before vaults or creator strategies hold other people's money.

## 5. Business model

- **Builder fee**: 0.20 % per execution on every trade a user's agent makes, credited by Strike to the builder. It
  grows with volume and was chosen so the strategy's edge survives it.
- **Copy trading**: copies started by agents run on Strike's own copy trading, bringing it new money and new copiers.
- **Creators**: a revenue share of the builder fee for strategy creators, paid automatically.
- **For Strike**: a white-label city and score as Strike's official social and discovery layer; the score and widgets
  as an API for other builders.

## 6. What would help from Strike

- Streaming endpoints for accounts, positions and copy subscriptions (fewer polls as users grow).
- Webhooks or an event feed for copy-trading events (new copier, stop-loss hit).
- A builder-rewards endpoint for automatic revenue reporting and creator payouts.
- Builder attribution for copies started through builder connect, so managed copies could carry the builder fee too.
- Vault APIs and a "verified strategy" programme, where an agent's audited record can earn a badge.
