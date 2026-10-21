# Interview Walkthrough — Kalshi LoL Trading Bot (≈7 minutes)

A structured technical walkthrough for a product/technical-management interview. Each section names the exact files and functions to screen-share. Timing guidance is indicative.

> **Tone guidance:** be precise about what is *live* vs. *shadow/not-live*, and do **not** overstate profitability, reliability, or production-readiness. This is a small-scale, experimental live system.

---

## 0. One-sentence pitch

"I built an automated trading bot that models professional League of Legends match outcomes from public data and trades Kalshi's match-winner markets — discovering markets, predicting a calibrated winner probability, and placing risk-managed orders when the model's edge clears a threshold."

**Screen-share:** `README.md` (top) and the Mermaid diagram in `docs/architecture.md`.

---

## 1. The problem I wanted to solve (≈45s)

Prediction markets like Kalshi price binary outcomes ("Will team A beat team B?") based on crowd sentiment. My hypothesis: public, pre-match LoL data (team form, Elo, per-player champion statistics) contains signal the crowd underweights, which should show up as a persistent gap between a well-calibrated model's probability and the market price.

I chose LoL because it has clean, structured public data (Oracle's Elixir) and a deep but not-yet-crowded esports market on Kalshi.

**Screen-share:**
- `docs/research_plan.md` §1 (economic hypothesis, "what constitutes evidence of an edge")
- `docs/oracle_elixir_dataset_report.md` (dataset size/quality)

---

## 2. The system's architecture (≈75s)

A single-process, single-threaded bot loops on a ~2-minute cadence inside an 08:00–24:00 CST scanning window. Talk through the data flow left-to-right:

1. **Offline:** Oracle's Elixir → feature builder → walk-forward training → pickled Random Forest + Platt calibration.
2. **Live loop:** scan `KXLOLGAME` → parse teams → coverage check → predict → edge → risk gate → buy-YES order → settle from real fills.
3. **State:** everything persists to SQLite so restarts recover bankroll and open positions.

Emphasize the two-model setup: a primary recency-trained model and a shadow baseline for divergence detection.

**Screen-share:**
- `docs/architecture.md` §2 (Mermaid diagram) — walk the arrows
- `src/prediction_bot/trading/match_winner_bot.py` → `run()` (line ~1180) and `_scan_cycle()` (line ~1432)

---

## 3. The most important technical decisions (≈75s)

1. **Random Forest + Platt calibration over logistic regression.** The original plan specified logistic regression; RF captured non-linear team/player interactions better, and Platt scaling fixes probability calibration. *(Screen-share: `models/map_winner_v2_shadow/FREEZE_SPEC.md` for the model spec; `scripts/map_winner_pipeline.py` for training.)*
2. **Map-level model reused for series markets.** Oracle's Elixir labels individual *maps*; Kalshi settles on *series* winner. Instead of training a separate series model, I convert analytically. *(Screen-share: `match_winner_bot.py` → `map_to_series_prob()` line ~122.)*
3. **Deterministic risk rules instead of an LLM review layer.** The plan had a "Hermes decision agent"; I replaced it with explicit, testable gates — lower variance and easier to audit. *(Screen-share: `match_winner_bot.py` → `RiskController` line ~582; `model_coverage.py`.)*
4. **Buy-YES only.** Kalshi deprecated the `outcome_side` field, so "bet against team" means buying the opposing YES contract.

---

## 4. A challenging engineering problem and how I addressed it (≈90s)

**Pick one of these two; lead with the one you can speak to most concretely.**

**Option A — leakage-safe walk-forward training.** In sports betting, the classic failure is leaking future information into training (using data "from the future" to predict the past), which inflates backtests and loses money live. I enforced timestamp-gated features and walk-forward validation so a model is only ever trained on data available *before* the match it predicts.

**Screen-share:** `docs/feature_leakage_rules.md`, `src/prediction_bot/esports/dataset.py`, and the validation loop in `scripts/map_winner_pipeline.py`.

**Option B — restart-safe order dedup.** The bot restarts automatically (systemd), and re-discovering already-bought markets would double-position. On startup it restores every open position from SQLite into the risk engine before the first scan, so re-discovery is treated as "already held" rather than "new opportunity."

**Screen-share:** `match_winner_bot.py` → `_restore_pending_positions()` (line ~1150), `_restore_bankroll()` (line ~1118).

Whichever you pick, close with: *"the test of the fix is a regression test that would fail on the bug."*

---

## 5. Reliability, monitoring, and failure recovery (≈60s)

- **Startup validation** — six checks (gateway health, Kalshi API, market discovery, model load, risk engine, auth) gate the first order; any failure halts the bot. *(Screen-share: `run_startup_validation()` line ~303.)*
- **Risk tiers** — fractional Kelly scaled down with drawdown (0.375 → 0.25 → 0.10), hard halt at 50%. *(Screen-share: `RiskController`.)*
- **Settlement from real fills** — P&L is computed from Kalshi's actual fill cost/count, not theoretical prices, to keep local state consistent with the exchange. *(Screen-share: `_check_settlements()` line ~1909.)*
- **Alerting** — Discord alerts for trades, settlements, drawdown, errors, and a daily summary. *(Screen-share: `discord_alert()` / `discord_daily_summary()` line ~259.)*

**Screen-share the deployment:** `systemctl status lol-match-bot.service` (or show the unit file) to demonstrate it's actually running.

---

## 6. Results and current limitations (≈45s)

**What the model shows (backtest, not live returns):**
- Primary model OOB accuracy ≈ 0.64; the newer "Model D" candidate reports Brier ≈ 0.216, ECE ≈ 0.014, AUC ≈ 0.71 on walk-forward.

**Honest limitations:**
- Trained on *map* winners, deployed on *series* markets (Bo3 independence assumption).
- Single model family; no ensemble or uncertainty estimate in the live path.
- Edge doesn't model fees/slippage beyond the spread.
- Buy-YES only; small bankroll; conservative sizing.

**Screen-share:** `models/recency_model/metadata.json`, `models/map_winner_v2_shadow/FREEZE_SPEC.md` (ablation numbers), and the "Current limitations" section of `README.md`.

---

## 7. What I'd improve for production-grade infra (≈45s)

1. **Model:** series-level model, ensemble + uncertainty, out-of-distribution detection feeding the risk engine.
2. **Cost:** explicit fee/slippage model in edge calculation.
3. **Risk:** external kill-switch (independent of the bot process), cross-market exposure netting.
4. **Backtests:** drawdown/compounding caps (current metadata shows unrealistic compounding).
5. **Ops:** dedicated order-reconciliation layer, CI/CD with regression gates, secrets via a vault (not `.env`).

**Screen-share:** `PROJECT.md` "Remaining Engineering Challenges".

---

## 10 Likely Follow-up Questions (with talking points)

**1. "Why Random Forest and not a neural net or XGBoost?"**
Tabular data with ~30–50 features and ~10k rows; RF is robust to non-linearity, less prone to overfitting, and its OOB + Platt pipeline gives calibrated probabilities. Diminishing returns to complexity at this data size.

**2. "How do you know you're not overfitting?"**
Temporal holdout (baseline trained 2024–2025, evaluated on 2026; map models use walk-forward with a rolling window and monthly retrains), leakage rules, OOB score, Platt calibration trained only on OOB predictions, and a live shadow-model divergence check.

**3. "How do you handle the map-vs-series label mismatch?"**
Analytical conversion from per-map probability to series probability (Bo3 default; Bo5 supported analytically), assuming independent maps. This is a known approximation — a dedicated series model is on the roadmap.

**4. "What happens if Kalshi is down or in maintenance?"**
A health check reads the exchange status and pauses execution (`EXECUTION_PAUSED`) rather than erroring; startup validation refuses to launch into an inactive exchange.

**5. "How do you prevent duplicate or double orders?"**
Ticker-level dedup + event-level reservation (one position per match); on restart, open positions are restored from SQLite before the first scan.

**6. "What's your position sizing / risk model?"**
Fractional Kelly (0.375 Tier-B reduced) with drawdown-scaled tiers down to 0.10, max 10% of bankroll per position, 3% min edge, and a 50% drawdown halt.

**7. "How do you compute P&L?"**
From Kalshi's real fill data (`taker_fill_cost_dollars` / `maker_fill_cost_dollars` and `fill_count_fp`) — winning contracts pay $1 each; P&L = fills×$1 − cost. Never from theoretical entry price.

**8. "Why buy-YES only?"**
Kalshi deprecated `outcome_side`; buying the opposing YES contract is the clean equivalent of a NO position and avoids a deprecated API field.

**9. "What's the biggest risk you haven't solved?"**
Honest answers: (a) the map→series approximation, (b) no uncertainty/OOD detection in the live path, (c) no external kill-switch, (d) backtests with unrealistic compounding.

**10. "Would this work in a real trading firm / production environment?"**
The *idea* transfers; the *implementation* needs hardening — an ensemble, fee/slippage modeling, a reconciliation layer, an independent risk/ops process, and proper secrets management. The current system is a deliberately small-scale experiment.
