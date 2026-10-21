# PROJECT.md — Kalshi LoL Trading Bot

## Purpose

Automated trading of Kalshi League of Legends match/series-winner markets (`KXLOLGAME`). The system models professional LoL match outcomes from public data, estimates a series-winner probability, and places risk-managed buy-YES orders when the model's edge over the market price clears a threshold.

## Current Implemented Scope

**Live (deployed as `lol-match-bot.service`):**

- Kalshi `KXLOLGAME` market discovery and execution (Trade API v2, RSA-PSS signing).
- Calibrated Random Forest series-winner model (recency-trained, 30 features; Platt calibration).
- Model-coverage gating to reject under-covered teams.
- Map→series probability conversion (Bo3 default; Bo5 supported).
- Fractional-Kelly position sizing with drawdown-scaled tiers (0.375 → 0.25 → 0.10 → halt).
- Buy-YES limit order execution, stale-order re-pricing, and settlement from real fill data.
- SQLite persistence with restart recovery; Discord alerts and daily summaries.

**Shadow / not live:**

- Per-map winner model "Model D" (48 features) and a map-winner bot (`KXLOLMAP`) — trained and evaluated, not deployed.
- "Unified Platform v2" (`lol-match-platform.service`) — disabled shadow mode.

**Explicitly out of scope here:** the Polymarket→Kalshi copy-trading system and other strategies.

## Major Technical Decisions

1. **Random Forest + Platt calibration over logistic regression.** The original plan (`docs/task_plan.md`) specified a calibrated logistic-regression model; the production model is an RF with Platt-scaled probabilities, which better captures non-linear team/player interactions.

2. **Temporal validation (no leakage).** Evaluation always respects time: the shadow baseline is trained on 2024–2025 and held out on 2026, and the map-winner models (and "Model D") use walk-forward evaluation with a rolling 365-day window and a 180-day recency half-life. No random train/test splits.

3. **Map-level model reused for series markets.** Oracle's Elixir labels individual maps; Kalshi settles on series winner. Rather than train a separate series model, the map probability is converted to a series probability analytically (Bo3: `3p²−2p³`; Bo5: `10p³−15p⁴+6p⁵`).

4. **Deterministic risk rules instead of an LLM review layer.** The planned Hermes decision agent was superseded by explicit, testable gates (coverage, edge, time-window, liquidity, drawdown-scaled Kelly).

5. **Pickle-serialized models carrying scaler + calibrator**, so live inference is decoupled from training code and survives code changes.

6. **Single-process, single-threaded bot** with a fixed ~2-minute scan cadence during the 08:00–24:00 CST scanning window, chosen for simplicity and auditability over concurrency.

7. **Buy-YES only**, reflecting Kalshi's deprecated `outcome_side` field; a "bet against" is expressed by buying the opposing YES contract.

## Operational Status (to the extent verifiable)

- The match-winner bot is **running** as a systemd service (`lol-match-bot.service`, active since 2026-09-30) and its SQLite DB is actively written to.
- It operates with a small configured bankroll and conservative Tier-B Kelly sizing — a live but deliberately small-scale, experimental deployment.
- Exact balances, P&L, and account data are intentionally **not** documented in the repository.

## Remaining Engineering Challenges

- **Label mismatch** — map-level training labels vs. series-level settlement (the Bo3 independence assumption is a known approximation).
- **Model diversity / uncertainty** — no ensemble or out-of-distribution detection in the live path; a second model is shadow-only.
- **Cost modeling** — edge does not yet account for slippage or fees beyond the bid/ask spread.
- **Backtest realism** — some model metadata shows unbounded compounding (unrealistic bankroll growth); backtests need drawdown/compounding caps.
- **Attribution** — no formal post-settlement edge-vs-luck decomposition (original M12 is unbuilt).
- **Operational hardening** — no external kill-switch; the generic `_request` order path lacks the dedicated reconciliation scaffolding used by other bots.
