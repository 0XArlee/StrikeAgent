# Scheduled macro releases and the strategies

Generated 2026-10-21 by `python -m smartflow.backtest.event_study`. Releases: Fed decisions (14:00 New York), US CPI and jobs reports (08:30 New York), official calendars in `config/macro_events.json`. Stress: stops filled in a candle with a release cost 30 bps more.

Pre-registered: a rule is adopted only if the trades it removes are clearly worse (95 % interval of the difference of mean R below 0) and the account (yearly growth / drawdown) improves on dev and is not worse on val and test. Added after the first run: it must also remove at least 10 trades (that run "adopted" a rule for Pyramid on 2 trades, where the interval means nothing).

How to read it: trades that stayed open through a release look far better than the rest only because long trades are the ones that span releases, and long trades are this trend strategy's winners; it says nothing about the releases. Smart Flow opens almost nothing right before a release: the hours before one are quiet, and its breakout needs a wide candle on 1.5x volume.

## smartflow (risk 1.0 % per trade)

152 releases and 297 trades in 2022-01 → 2026-10; 10 stops filled in a candle with a release.

| group | trades | mean R | 95 % interval | win rate |
|---|---|---|---|---|
| opened right before a release | 0 | None | None | None |
| signal candle held a release | 9 | 1.058 | [-0.525, 3.39] | 0.556 |
| a release while open | 71 | 2.869 | [1.721, 4.167] | 0.662 |
| none | 219 | -0.078 | [-0.435, 0.36] | 0.237 |

Opened right before, by kind: fomc 0 trades, mean None R, cpi 0 trades, mean None R, nfp 0 trades, mean None R

### Rules, backtest costs

| rule | window | trades | removed | mean R kept | mean R removed | diff (95 %) | yearly | drawdown | ratio |
|---|---|---|---|---|---|---|---|---|---|
| ref | full | 297 | 0 | 0.624 | None |  | 29.7 % | 25.7 % | 1.16 |
| ref | dev | 116 | 0 | 0.727 | None |  | 34.4 % | 25.7 % | 1.34 |
| ref | val | 100 | 0 | 0.385 | None |  | 17.5 % | 20.7 % | 0.84 |
| ref | test | 81 | 0 | 0.771 | None |  | 37.7 % | 23.5 % | 1.61 |
| R1 | full | 297 | 0 | 0.624 | None |  | 29.7 % | 25.7 % | 1.16 |
| R1 | dev | 116 | 0 | 0.727 | None |  | 34.4 % | 25.7 % | 1.34 |
| R1 | val | 100 | 0 | 0.385 | None |  | 17.5 % | 20.7 % | 0.84 |
| R1 | test | 81 | 0 | 0.771 | None |  | 37.7 % | 23.5 % | 1.61 |
| R2 | full | 288 | 9 | 0.61 | 1.058 | +0.45 (-1.24 … +2.82) | 27.9 % | 24.0 % | 1.17 |
| R2 | dev | 110 | 6 | 0.682 | 1.548 | +0.87 (-1.62 … +4.39) | 30.1 % | 24.0 % | 1.26 |
| R2 | val | 99 | 1 | 0.401 | -1.191 | -1.59 (-2.37 … -1.00) | 18.3 % | 20.7 % | 0.88 |
| R2 | test | 79 | 2 | 0.773 | 0.711 | -0.06 (-1.21 … +0.91) | 36.5 % | 23.5 % | 1.56 |
| R3 | full | 288 | 9 | 0.61 | 1.058 | +0.45 (-1.24 … +2.82) | 27.9 % | 24.0 % | 1.17 |
| R3 | dev | 110 | 6 | 0.682 | 1.548 | +0.87 (-1.62 … +4.39) | 30.1 % | 24.0 % | 1.26 |
| R3 | val | 99 | 1 | 0.401 | -1.191 | -1.59 (-2.37 … -1.00) | 18.3 % | 20.7 % | 0.88 |
| R3 | test | 79 | 2 | 0.773 | 0.711 | -0.06 (-1.21 … +0.91) | 36.5 % | 23.5 % | 1.56 |

Verdict: R1: 0 removed (too few), clearly worse False, account better False → **no**; R2: 9 removed (too few), clearly worse False, account better False → **no**; R3: 9 removed (too few), clearly worse False, account better False → **no**

### Rules, with the stress

| rule | window | trades | removed | mean R kept | mean R removed | diff (95 %) | yearly | drawdown | ratio |
|---|---|---|---|---|---|---|---|---|---|
| ref | full | 297 | 0 | 0.621 | None |  | 29.5 % | 25.8 % | 1.15 |
| ref | dev | 116 | 0 | 0.725 | None |  | 34.3 % | 25.8 % | 1.33 |
| ref | val | 100 | 0 | 0.379 | None |  | 17.1 % | 21.0 % | 0.82 |
| ref | test | 81 | 0 | 0.77 | None |  | 37.6 % | 23.5 % | 1.6 |
| R1 | full | 297 | 0 | 0.621 | None |  | 29.5 % | 25.8 % | 1.15 |
| R1 | dev | 116 | 0 | 0.725 | None |  | 34.3 % | 25.8 % | 1.33 |
| R1 | val | 100 | 0 | 0.379 | None |  | 17.1 % | 21.0 % | 0.82 |
| R1 | test | 81 | 0 | 0.77 | None |  | 37.6 % | 23.5 % | 1.6 |
| R2 | full | 288 | 9 | 0.607 | 1.049 | +0.44 (-1.24 … +2.82) | 27.8 % | 24.0 % | 1.15 |
| R2 | dev | 110 | 6 | 0.681 | 1.535 | +0.85 (-1.63 … +4.38) | 30.0 % | 24.0 % | 1.25 |
| R2 | val | 99 | 1 | 0.394 | -1.191 | -1.59 (-2.36 … -0.99) | 17.9 % | 21.0 % | 0.85 |
| R2 | test | 79 | 2 | 0.772 | 0.711 | -0.06 (-1.21 … +0.91) | 36.4 % | 23.5 % | 1.55 |
| R3 | full | 288 | 9 | 0.607 | 1.049 | +0.44 (-1.24 … +2.82) | 27.8 % | 24.0 % | 1.15 |
| R3 | dev | 110 | 6 | 0.681 | 1.535 | +0.85 (-1.63 … +4.38) | 30.0 % | 24.0 % | 1.25 |
| R3 | val | 99 | 1 | 0.394 | -1.191 | -1.59 (-2.36 … -0.99) | 17.9 % | 21.0 % | 0.85 |
| R3 | test | 79 | 2 | 0.772 | 0.711 | -0.06 (-1.21 … +0.91) | 36.4 % | 23.5 % | 1.55 |

Verdict: R1: 0 removed (too few), clearly worse False, account better False → **no**; R2: 9 removed (too few), clearly worse False, account better False → **no**; R3: 9 removed (too few), clearly worse False, account better False → **no**

## pyramid (risk 1.0 % per trade)

152 releases and 482 trades in 2022-01 → 2026-10; 20 stops filled in a candle with a release.

| group | trades | mean R | 95 % interval | win rate |
|---|---|---|---|---|
| opened right before a release | 2 | -0.956 | [-1.188, -0.725] | 0.0 |
| signal candle held a release | 13 | 0.567 | [-0.561, 2.314] | 0.462 |
| a release while open | 120 | 2.975 | [2.055, 3.953] | 0.633 |
| none | 349 | -0.112 | [-0.371, 0.188] | 0.238 |

Opened right before, by kind: fomc 0 trades, mean None R, cpi 0 trades, mean None R, nfp 2 trades, mean -0.956 R

### Rules, backtest costs

| rule | window | trades | removed | mean R kept | mean R removed | diff (95 %) | yearly | drawdown | ratio |
|---|---|---|---|---|---|---|---|---|---|
| ref | full | 482 | 0 | 0.648 | None |  | 40.2 % | 34.0 % | 1.18 |
| ref | dev | 185 | 0 | 0.737 | None |  | 44.7 % | 34.0 % | 1.31 |
| ref | val | 166 | 0 | 0.55 | None |  | 35.6 % | 32.9 % | 1.08 |
| ref | test | 131 | 0 | 0.647 | None |  | 38.9 % | 28.7 % | 1.36 |
| R1 | full | 480 | 2 | 0.655 | -0.956 | -1.61 (-2.08 … -1.17) | 40.7 % | 33.4 % | 1.22 |
| R1 | dev | 184 | 1 | 0.747 | -1.188 | -1.93 (-2.47 … -1.45) | 45.4 % | 33.4 % | 1.36 |
| R1 | val | 166 | 0 | 0.55 | None |  | 35.6 % | 32.9 % | 1.08 |
| R1 | test | 130 | 1 | 0.658 | -0.725 | -1.38 (-2.06 … -0.78) | 39.6 % | 28.7 % | 1.38 |
| R2 | full | 469 | 13 | 0.65 | 0.567 | -0.08 (-1.30 … +1.65) | 40.5 % | 32.9 % | 1.23 |
| R2 | dev | 178 | 7 | 0.716 | 1.251 | +0.53 (-1.55 … +3.53) | 44.3 % | 32.5 % | 1.36 |
| R2 | val | 163 | 3 | 0.574 | -0.738 | -1.31 (-2.22 … -0.34) | 37.2 % | 32.9 % | 1.13 |
| R2 | test | 128 | 3 | 0.656 | 0.276 | -0.38 (-1.39 … +0.56) | 38.5 % | 28.7 % | 1.34 |
| R3 | full | 467 | 15 | 0.657 | 0.364 | -0.29 (-1.40 … +1.31) | 41.0 % | 32.9 % | 1.24 |
| R3 | dev | 177 | 8 | 0.727 | 0.946 | +0.22 (-1.67 … +3.09) | 45.0 % | 31.8 % | 1.41 |
| R3 | val | 163 | 3 | 0.574 | -0.738 | -1.31 (-2.22 … -0.34) | 37.2 % | 32.9 % | 1.13 |
| R3 | test | 127 | 4 | 0.667 | 0.026 | -0.64 (-1.63 … +0.31) | 39.2 % | 28.7 % | 1.36 |

Verdict: R1: 2 removed (too few), clearly worse False, account better True → **no**; R2: 13 removed, clearly worse False, account better True → **no**; R3: 15 removed, clearly worse False, account better True → **no**

### Rules, with the stress

| rule | window | trades | removed | mean R kept | mean R removed | diff (95 %) | yearly | drawdown | ratio |
|---|---|---|---|---|---|---|---|---|---|
| ref | full | 482 | 0 | 0.644 | None |  | 39.9 % | 34.2 % | 1.17 |
| ref | dev | 185 | 0 | 0.733 | None |  | 44.4 % | 34.2 % | 1.3 |
| ref | val | 166 | 0 | 0.543 | None |  | 35.0 % | 33.3 % | 1.05 |
| ref | test | 131 | 0 | 0.646 | None |  | 38.8 % | 28.7 % | 1.35 |
| R1 | full | 480 | 2 | 0.651 | -1.008 | -1.66 (-2.18 … -1.16) | 40.4 % | 33.5 % | 1.21 |
| R1 | dev | 184 | 1 | 0.744 | -1.291 | -2.04 (-2.58 … -1.56) | 45.2 % | 33.5 % | 1.35 |
| R1 | val | 166 | 0 | 0.543 | None |  | 35.0 % | 33.3 % | 1.05 |
| R1 | test | 130 | 1 | 0.657 | -0.725 | -1.38 (-2.05 … -0.78) | 39.4 % | 28.7 % | 1.37 |
| R2 | full | 469 | 13 | 0.647 | 0.561 | -0.09 (-1.30 … +1.65) | 40.2 % | 33.3 % | 1.21 |
| R2 | dev | 178 | 7 | 0.713 | 1.24 | +0.53 (-1.55 … +3.53) | 44.1 % | 32.6 % | 1.35 |
| R2 | val | 163 | 3 | 0.567 | -0.738 | -1.31 (-2.21 … -0.33) | 36.6 % | 33.3 % | 1.1 |
| R2 | test | 128 | 3 | 0.655 | 0.276 | -0.38 (-1.39 … +0.56) | 38.4 % | 28.7 % | 1.34 |
| R3 | full | 467 | 15 | 0.654 | 0.352 | -0.30 (-1.41 … +1.29) | 40.6 % | 33.3 % | 1.22 |
| R3 | dev | 177 | 8 | 0.725 | 0.924 | +0.20 (-1.69 … +3.07) | 44.9 % | 31.9 % | 1.41 |
| R3 | val | 163 | 3 | 0.567 | -0.738 | -1.31 (-2.21 … -0.33) | 36.6 % | 33.3 % | 1.1 |
| R3 | test | 127 | 4 | 0.666 | 0.026 | -0.64 (-1.63 … +0.31) | 39.0 % | 28.7 % | 1.36 |

Verdict: R1: 2 removed (too few), clearly worse False, account better True → **no**; R2: 13 removed, clearly worse False, account better True → **no**; R3: 15 removed, clearly worse False, account better True → **no**

