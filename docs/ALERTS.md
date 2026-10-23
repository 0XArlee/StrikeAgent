# Alerts: Strike Finance for everyone, your agent and your copies for you

EdgeCraft-StrikeCity watches Strike every minute and says when something deserves a look: on Telegram
([@EdgeCraftStrikeCityBot](https://t.me/EdgeCraftStrikeCityBot)) and in the city, where each fresh alert glows over the
building it concerns. Two kinds of alerts, because they are different things:

- **Strike Finance's moments**: public, the same for everyone, so the city shows them too.
- **Your own**: your agent, your Strike account and sub-accounts, your copies. Private, so only on your Telegram.

## Strike Finance, for everyone

Read from Strike's public API once a minute (`smartflow/alerts/strike.py`). Each alert is said once per moment, in
English and Spanish.

| Alert | When | In the city |
|---|---|---|
| Big move | A market moves more than it usually does in an hour: BTC 2 %, ETH and SOL 3 %, indices and gold 1.5 %, oil and silver 2.5 %, stocks 4 %, other crypto 5 %. Again only if it goes another step further | its tower, or Strike Finance |
| Extreme funding | One side pays more than 0.03 % an hour (about 260 % a year) | the Funding Cafe |
| Liquidation radar | A position of 50,000 $ or more within 3 % of its liquidation price, from Strike's own list of live positions; again if it halves the distance | Liquidation Alley |
| Whale | A new position of 150,000 $ or more | its tower |
| Crowded market | 80 % of a market's positions on one side (counted in positions: open interest is the same on both sides) | its tower |
| New or halted market | Strike lists a market, or changes its status | Strike Finance |
| Security alarm | The News Tower scores a hack or an exchange going down at -30 or worse | the News Tower |
| US macro | 30 minutes before the Fed's decision, CPI, jobs, PCE or GDP | the News Tower |
| News reading | A market's news reading turns very bullish or very bearish (off by default) | the News Tower |
| Copy Arena | One of the five best traders by the Strike City score opens a position | the Copy Arena |

The bot sends each one to whoever chose it; the site keeps the latest 60 (`/api/alerts`), the Alerts tab lists them
with a link to their building, and a new one shows for a few seconds as a toast.

## Your agent, your accounts, your copies

**Linking.** Signed in, the Alerts tab asks the site for a one-time link (`POST /api/me/telegram`, ten minutes, made
with the owner's session) and opens `t.me/EdgeCraftStrikeCityBot?start=<code>`. Pressing Start sends the bot that code;
the bot asks the site whose it is and claims it (HMAC, like every request from the agents' host). The owner sees the
linked chat in the Alerts tab and can disconnect it there, or with `/unlink` in Telegram.

**What it watches, every two minutes** (`smartflow/alerts/watch.py`):

- **Liquidation risk.** Every position of the main account and each sub-account: a word at 15 % from its liquidation
  price, a warning at 7 %, an alarm at 3 %, with the mark, the liquidation price and what to do. And the account's
  margin: a warning at 60 % used, an alarm at 85 %.
- **Each copy.** A trade the trader made that the copy did not take (a market the copy excludes, not enough margin,
  below Strike's minimum), only for markets Strike lists and confirmed on two checks in a row; a position the copy still
  holds that the trader already left; the trader itself close to liquidation or out of margin, on Strike or on
  Hyperliquid; the copy stopping or being liquidated.
- **The agent.** Its entries (size, price, stop), its exits with the result in R and dollars, problems from its own
  journal (Strike not answering, a position it does not track), a signal it had to skip and why, a pause, a resume.
- **Its copy pilot.** A copy starting, stopping, refused or waiting for money, a free sub-account used with less than
  the plan's amount, and the pauses for the security alarm or a US release.

**Without an agent.** `/watch <account id or wallet address>` does the same account and copy checks for any Strike
account (up to five), from public data only.

## The bot

`/menu` · `/strike` (Strike right now: BTC, ETH, SOL, the biggest moves, the most extreme funding, the large position
closest to liquidation, open interest and how many positions are long, the 24-hour volume, the News Tower's reading,
the next US release) · `/status` (your positions with their distance to liquidation, margin used, the copy) ·
`/watch` · `/unwatch` · `/settings` (each kind on or off, BTC/ETH/SOL only or every market, the language) ·
`/mute 8` · `/unmute` · `/unlink` · `/stop`.

Urgent warnings about your own positions (liquidation, a copy's trader in trouble) arrive even muted. A chat that
blocks the bot is forgotten.

## How it runs

One service on the agents' host for both networks (`smartflow telegram`, `deploy/smartflow-telegram.service`):
long polling to Telegram, signed requests to the staging and production sites, public reads of Strike and
Hyperliquid; it opens no port. The token and both sites' secrets are in a root-only file and never logged (an error
names the Bot API method, never its URL). State in `/var/lib/smartflow/alerts`.

Tests: `tests/test_alerts.py` (every Strike alert, the liquidation levels, a copy's mismatches confirmed and reset,
the agent's journal from the moment of linking, the bot's links, settings, mute and HTML escaping, and the token kept
out of errors). `web/scripts/verify_telegram_link.py` links a test agent on staging through the bot's own client.
