# Research Plan

> Last updated: 2026-07-28
> Author: prediction_bot team
> Companion documents: architecture.md, task_plan.md, PROJECT.md

---

## 1. Research Hypothesis

### 1.1 Economic Hypothesis

**Primary hypothesis**: Pre-match esports outcomes on prediction markets exhibit systematic mispricing that can be identified by a simple, calibrated probability model built from publicly available historical match data. The mispricing arises because:

1. **Retail flow bias**: Kalshi traders overreact to recent results, team brand popularity, and narrative — creating price deviations from fundamental win probability.
2. **Low institutional participation**: Esports prediction markets are thin. Few quantitative participants price these contracts systematically, leaving edges for a disciplined model.
3. **Information asymmetry is addressable**: Public esports data (match results, rosters, patches) contains sufficient signal to estimate pre-match win probabilities that are better-calibrated than crowd prices.

**Secondary hypothesis**: A conservative, uncertainty-adjusted betting strategy using fractional Kelly sizing can convert a small probability calibration edge into positive expected returns over a reasonable sample (200+ matches), without relying on high-leverage or concentrated positions.

### 1.2 What Constitutes Evidence of an Edge

An edge is demonstrated when ALL of the following hold:

1. **Calibration superiority**: Our model's Brier score and log loss on out-of-sample walk-forward data are lower than a naive 0.50 baseline and an Elo-only baseline, AND our calibration curves show better alignment (lower ECE) than market-implied probabilities derived from Kalshi midpoints.

2. **Market comparison**: For matches where our model probability differs from the Kalshi executable price by more than a meaningful threshold (e.g., 5 percentage points), the model's directional call is correct significantly more often than the market's. This is NOT the same as raw accuracy — a model that correctly identifies 60/40 mispricings 65% of the time has an edge even if its overall accuracy is 55%.

3. **Paper P&L positive**: A walk-forward paper-trading simulation using realistic executable prices (not midpoints) and spread costs shows positive cumulative P&L with a Sharpe ratio significantly above zero over at least 200 resolved matches.

4. **Stability across slices**: The edge persists across tournament tiers, regions, and time periods, not concentrated in a single league or patch cycle.

5. **Ex-ante declaration**: All model versions and thresholds are frozen before comparison with Kalshi prices. No parameter is tuned to maximize paper P&L against Kalshi data.

### 1.3 Distinguishing Key Concepts

| Concept | Definition | How We Measure It |
|---------|-----------|-------------------|
| **Model accuracy** | Fraction of match winners correctly predicted. | Classification accuracy: correct / total. |
| **Probability calibration** | Does "70%" really mean 70%? | Reliability diagrams, ECE, Brier score. |
| **Market mispricing** | Gap between our calibrated probability and market price. | p_model - p_market (executable). |
| **Trading profitability** | Do we make money after costs? | Paper P&L, Sharpe ratio, win rate on traded subset. |

**Critical distinction**: A model can have high accuracy but poor calibration (e.g., it predicts 95% on all favorites, wins 70% — accurate direction, terrible probability). Conversely, a model can have good calibration but identify no mispricing (if the market is already efficient). We optimize for calibration first, because mispricing identification depends on well-calibrated probabilities. Profitability is the downstream consequence, not the optimization target.

### 1.4 Assumptions Requiring Testing

These assumptions are NOT accepted as true. They are stated explicitly so they can be tested:

| # | Assumption | How to Test | Risk if False |
|---|-----------|-------------|---------------|
| A1 | Historical match data from 2020+ is representative of current competitive meta. | Compare Elo predictive power on 2020-2022 vs. 2023-2025 data. | Models trained on old data may not generalize. Mitigation: weight recent data higher or restrict training window. |
| A2 | Public data sources (Oracle's Elixir, Leaguepedia, LoL Esports API) are complete and accurate enough for modeling. | Cross-validate match results across sources. Track discrepancy rate. | Missing or incorrect data degrades feature quality. Mitigation: multi-source reconciliation. |
| A3 | Elo ratings with a single K-factor capture sufficient team strength signal. | Compare Elo-only Brier vs. naive baseline. If Elo barely improves, the signal is weak. | Elo may need extensions (Glicko, TrueSkill) or may be insufficient alone. |
| A4 | Roster information is reliably available before match start. | Check roster announcement timing vs. match start for a sample of matches. | Roster-based features may have look-ahead bias or be unavailable pre-match. Mitigation: use only confirmed/announced rosters. |
| A5 | Kalshi esports markets have sufficient liquidity for paper-trading simulation to be informative. | Measure time series of spread and depth for active LoL markets. | If spreads are consistently >10% or depth <$50, edges may not be executable even on paper. |
| A6 | Patch changes do not cause regime shifts that break model calibration. | Monitor calibration drift in the N matches following major patches. | If calibration degrades sharply after patches, models need faster adaptation. |
| A7 | Pre-match probabilities are stationary enough that a single trained model works across tournaments. | Compare calibration by tournament tier and region. | May need per-region or per-tier models. |
| A8 | Fractional Kelly sizing with k=0.25 is appropriate for the variance of esports outcomes. | Simulate with k ∈ {0.1, 0.25, 0.5, 1.0} and compare drawdown characteristics. | Full Kelly may be too aggressive for binary-outcome bets. |

---

## 2. MVP Definition

### 2.1 What Is the MVP?

The Minimum Viable Product is:

> A system that ingests historical League of Legends match data, computes leakage-safe Elo ratings and a small set of baseline features, trains a calibrated logistic regression model using walk-forward validation, compares model probabilities with executable Kalshi prices for at least 20 upcoming matches, and records paper-trading decisions with full post-settlement attribution — all without committing real capital.

### 2.2 Included in MVP

- Data ingestion pipeline for League of Legends historical matches (2023-2025).
- Canonical team and roster tables.
- Leakage-safe Elo rating system with configurable K-factor.
- Elo difference → probability via sigmoid transform (baseline model).
- A small set of validated, leakage-tested features (Elo diff, form, roster continuity, format, patch age).
- Logistic regression model trained via walk-forward validation.
- Platt scaling calibration on held-out calibration folds.
- Walk-forward evaluation: Brier score, log loss, calibration curve, ECE.
- Read-only Kalshi client for market discovery.
- Event matching between internal matches and Kalshi markets.
- Order-book snapshot collection (manual or cron-driven).
- Executable price extraction.
- Edge computation with spread cost deduction.
- Eligibility checks and rejection conditions.
- Fractional Kelly position sizing.
- Paper trade recording.
- Post-settlement P&L attribution report.
- Hermes review layer with structured input/output schemas.
- All code covered by tests (unit, integration, leakage).

### 2.3 Explicitly Excluded from MVP

- Live/real-money trading of any kind.
- In-play or live betting models.
- Esports other than League of Legends.
- Market types other than match/series winner.
- Complex models (gradient boosting, neural networks, ensembles).
- Automated order execution (paper or otherwise).
- Real-time streaming data pipelines.
- Web dashboard or UI.
- Model retraining automation.
- Multi-sport or cross-esport correlation modeling.
- Hedging or portfolio optimization beyond simple exposure caps.

### 2.4 Why League of Legends?

League of Legends is the best starting esport for this research system:

1. **Data availability**: Oracle's Elixir, Leaguepedia, and the LoL Esports API provide structured, machine-readable match data with game-level statistics going back to ~2014. Few other esports have this quality and depth of free public data.

2. **Match volume**: LoL has 4 major regions (LCK, LPL, LEC, LCS) with regular seasons, plus 2 international tournaments (MSI, Worlds) annually. This yields 2000+ pro matches per year — enough for statistically meaningful walk-forward evaluation within a single season.

3. **Structured format**: Matches are discrete, well-scheduled, and have clear winner/loser outcomes. Game-level stats (gold diff, objectives, dragons) provide rich feature candidates.

4. **Kalshi availability**: League of Legends is the most consistently listed esport on Kalshi, with markets for major tournaments and some regular-season matches.

5. **Community knowledge**: Elo-like rating systems are well-studied in LoL. There is prior art to build on and validate against.

6. **Patch cadence**: Patches every 2 weeks create natural regime-change points — a good stress test for model robustness.

**Counterargument**: CS2 and VALORANT also have Kalshi markets and decent data. But LoL's match volume and data depth make it the lowest-risk starting point.

### 2.5 MVP Success Criterion

> After completing walk-forward evaluation on at least 200 held-out matches and comparing model probabilities against executable Kalshi prices, the calibrated logistic regression model achieves: (a) Brier score ≤ 0.22 (vs. 0.25 for naive baseline), (b) ECE ≤ 0.05, and (c) paper-trading simulation on the subset of matches with identified edge shows positive realized edge (average raw_edge on traded matches > 0) — without using Kalshi prices in any model training step.

If (a) and (b) pass but (c) does not, the model is well-calibrated but the market is efficient — a useful negative result. If none pass, we reassess feature engineering before adding model complexity.

---

## 3. Validation Framework

### 3.1 Walk-Forward (Expanding Window) Validation

All evaluation uses temporal walk-forward validation. Random train-test splits are prohibited.

```
Window 1: train on matches Jan 2023 – Jun 2023 → test on Jul 2023
Window 2: train on matches Jan 2023 – Jul 2023 → test on Aug 2023
...
Window N: train on matches Jan 2023 – May 2025 → test on Jun 2025
```

Each window:

1. Features are computed with knowledge deadline = test window start.
2. Model is trained on training window data only.
3. Model makes predictions for test window matches.
4. Predictions are stored with model version and timestamp.

### 3.2 Primary Metrics

| Metric | Formula / Description | Target |
|--------|----------------------|--------|
| Brier score | (1/N) Σ (p_i - y_i)² | ≤ 0.22 (MVP) |
| Log loss | -(1/N) Σ [y_i log(p_i) + (1-y_i) log(1-p_i)] | minimize |
| ECE | Binned |p_pred - freq_actual| | ≤ 0.05 |
| Reliability diagram | Visual: predicted vs actual frequency by bin | near diagonal |

### 3.3 Secondary Metrics

| Metric | Description |
|--------|-------------|
| Accuracy | Correct directional predictions / total. Contextual only. |
| AUC-ROC | Discriminative power. Contextual only. |
| Brier skill score | 1 - Brier_model / Brier_baseline. Positive = better than baseline. |

### 3.4 Slice Analysis

Performance is reported sliced by:

- **Region**: LCK, LPL, LEC, LCS, international
- **Tournament tier**: Major (Worlds, MSI), regional playoffs, regular season
- **Series format**: BO1, BO3, BO5
- **Probability bucket**: [0-0.2), [0.2-0.4), [0.4-0.6), [0.6-0.8), [0.8-1.0]
- **Time period**: by quarter
- **Patch**: grouped by patch, and by "first week of patch" vs "later weeks"

### 3.5 Market Comparison Protocol

1. Freeze model version and all parameters BEFORE accessing Kalshi data for that time period.
2. For each match in the test window, collect the nearest Kalshi snapshot BEFORE match start.
3. Extract executable prices.
4. Compute raw_edge = p_conservative - p_market_executable.
5. Report: mean raw_edge, fraction of matches with edge > threshold, and edge P&L on the subset that would have been traded.

### 3.6 Minimum Sample Size

- Calibration assessment: ≥ 100 predictions per probability bin.
- Slice analysis: ≥ 30 predictions per slice. Slices below this are reported with a "low sample" warning.
- Trading simulation: ≥ 200 resolved matches total, ≥ 30 traded matches.
- Statistical significance of edge: compute p-value for one-sided test that mean raw_edge ≤ 0 against mean raw_edge > 0.

---

## 4. Modeling Roadmap

### 4.1 Layered Progression

The modeling roadmap is deliberately ordered from simplest to most complex. Each layer must demonstrate improvement over the previous layer on walk-forward metrics BEFORE the next layer is built.

**Layer 0 — Naive Baseline**
- Always predict p = 0.50.
- Establishes the Brier/log-loss floor.
- If any model does worse than 0.50, something is broken.

**Layer 1 — Elo Baseline**
- Compute Elo ratings from historical match outcomes.
- Convert Elo difference to probability via sigmoid: p = 1 / (1 + 10^(-Δ/400)).
- Single hyperparameter: K-factor. Tune on earliest 20% of data only.
- This is the first "real" model. It must beat Layer 0.

**Layer 2 — Logistic Regression**
- Features from architecture.md §6.2.
- L2 regularization. Hyperparameters tuned via walk-forward CV on training portion.
- Platt scaling calibration on held-out calibration fold.
- This is the MVP model. It must beat Layer 1 in Brier and ECE.

**Layer 3 — Gradient Boosting (Gated)**
- Only built if Layer 2 demonstrates a positive edge vs. Kalshi after costs.
- LightGBM with monotonic constraints on Elo diff, form features.
- Requires additional calibration step (isotonic).
- Requires OOD detection infrastructure.
- **Why gated**: Adding model complexity without demonstrated need increases overfitting risk, reduces interpretability, and adds maintenance burden.

**Layer 4 — Ensemble (Gated)**
- Only if both L2 and L3 exist and disagree meaningfully.
- Disagreement as an uncertainty signal.
- Weighted or voting ensemble for prediction.
- **Why gated**: Ensemble adds complexity for a marginal calibration improvement. The primary value is uncertainty estimation, not raw prediction.

### 4.2 Why Simple First?

1. **Interpretability**: Logistic regression coefficients can be read and debated. Stakeholders can validate that the model's reasoning aligns with domain knowledge.
2. **Debugging**: When a logistic regression misbehaves, the cause is traceable to specific features. Gradient boosting and neural networks obscure this.
3. **Overfitting risk**: Esports data is high-variance. Complex models can fit noise (e.g., patch-specific patterns that never repeat) while simple models with strong regularization are forced to learn robust signals.
4. **Calibration**: Linear models with Platt scaling are well-studied for calibration. Complex models often require post-hoc calibration that may not generalize.
5. **Cost of complexity**: Every additional model layer requires new tests, new monitoring, new failure modes. The burden must be justified by a measurable edge improvement.
6. **Prior art**: In sports prediction, Elo + logistic regression often achieves 90%+ of the predictive power of complex models. The remaining 10% may not translate to trading edge after costs.

### 4.3 Calibration Methods

| Method | When to Use | Notes |
|--------|-------------|-------|
| Platt scaling | Logistic regression output | Fits sigmoid to map scores to probabilities. Works well when scores are roughly normally distributed. |
| Isotonic regression | Any model output | Non-parametric. Better for poorly calibrated scores. Requires more calibration data. |
| No calibration | Elo sigmoid | The sigmoid transform IS the calibration. |

### 4.4 Uncertainty Estimation Methods

| Method | Complexity | When |
|--------|-----------|------|
| Bootstrap resampling | Medium | Train N models on N bootstrap samples. Variance of predictions = epistemic uncertainty. |
| Ensemble disagreement | Low (if ensemble exists) | Difference between L2 and L3 predictions. |
| Conformal prediction | Medium | Produce prediction intervals with guaranteed coverage. Optional future addition. |

---

## 5. Trading Logic

### 5.1 Definitions

- **Model probability (p_model)**: The calibrated probability output by the model. E.g., "Team A has a 62% chance to win."

- **Conservative probability (p_conservative)**: The model probability adjusted downward by uncertainty. Formally: p_conservative = max(0.05, min(0.95, p_model - λ·σ_bootstrap - δ·disagreement)). This is the probability we actually act on.

- **Executable market price (p_market)**: The price at which we can transact. For a "yes" position: best_ask. For a "no": 1 - best_bid.

- **Raw edge**: p_conservative - p_market. Positive means our conservative estimate exceeds what the market charges.

- **Net (adjusted) edge**: raw_edge - spread_cost. Spread cost = (ask - bid) / 2 expressed in probability terms for the relevant side.

- **Maximum acceptable entry price**: p_conservative - min_edge_threshold. The highest market price at which we would still enter.

### 5.2 Formulas

**Expected Value per contract (yes position):**
```
EV_yes = p_conservative × (1 - p_entry) + (1 - p_conservative) × (0 - p_entry)
       = p_conservative - p_entry
```
Where p_entry is the executable price.

**Uncertainty-Adjusted Probability:**
```
p_conservative = max(0.05, min(0.95, p_calibrated - λ × σ_bootstrap - δ × d_ensemble))
```
Default starting values: λ = 1.0, δ = 0.5. These are tuning parameters, not fixed laws.

**Trading Threshold:**
```
trade if: net_edge ≥ min_edge_threshold
default min_edge_threshold = 0.03 (3 percentage points)
```

**Fractional Kelly Sizing:**
```
b = (1 - p_market) / p_market   # net odds received
f* = (p_conservative × (b + 1) - 1) / b   # full Kelly fraction
f = f* × k_fraction              # fractional Kelly
position_notional = bankroll × max(0, f)
```
Default k_fraction = 0.25.

### 5.3 Exposure Caps (Repeated from Architecture)

| Cap Type | Default | Description |
|----------|---------|-------------|
| Per match | 5% of bankroll | Max notional on single match |
| Per team | 10% of bankroll | Max total exposure across all markets on one team |
| Per tournament | 20% of bankroll | Max total exposure within one tournament |
| Per day | 15% of bankroll | Max notional deployed in one calendar day |
| Max contracts | 500 | Absolute contract count cap |

### 5.4 Rejection Conditions (Complete List)

A trade is rejected if ANY of these is true:

1. Roster not confirmed at T_pred.
2. Event matching confidence < threshold.
3. Tournament not in supported list.
4. Spread > max_spread (default 0.05).
5. Bid or ask depth < min_depth (default $50 notional or 50 contracts).
6. Snapshot age > max_age (default 30 minutes).
7. Ensemble disagreement > max_disagreement (default 0.10).
8. Match flagged as out-of-distribution.
9. net_edge < min_edge_threshold (default 0.03).
10. Any exposure cap would be exceeded.
11. Stale data: any feature source older than its freshness threshold.
12. Match is within 5 minutes of scheduled start (no last-second entries — data may be stale).

---

## 6. Hermes Strategy-Agent Role

### 6.1 Agent Design

The Hermes agent acts as a **review and decision layer**. It does not generate predictions, compute features, or place orders. It:

1. Receives a structured `RecommendationRequest` from the strategy layer.
2. Independently re-checks all eligibility and risk conditions.
3. Validates position sizing against current exposure.
4. Produces a signed `Recommendation` with an APPROVE / REJECT / FLAG decision.
5. Provides a human-readable explanation of the reasoning.
6. After the match resolves, produces a postmortem comparing prediction to outcome.

### 6.2 Separation of Concerns

```
Prediction model ──→ Strategy layer ──→ Hermes review ──→ Paper execution
                                         │
                                    (gate: APPROVE?
                                     REJECT? FLAG?)
```

Hermes does NOT:
- Access model internals or retrain models.
- Access Kalshi API directly (reads from snapshot DB).
- Submit orders (even paper ones — the execution layer does that).
- Modify position sizes without flagging the change.

### 6.3 Input/Output Schemas

See architecture.md §10.2 and §10.3 for the Pydantic models.

### 6.4 Check Independence

Hermes performs checks independently from the strategy layer. This means:
- Hermes has its own copy of the eligibility rules.
- Hermes reads the same snapshot data but validates it itself.
- Hermes computes exposure from the paper trade ledger, not from the strategy layer's reported exposure.
- Any discrepancy between strategy-layer check and Hermes check is flagged.

### 6.5 Postmortem Structure

For each resolved match, Hermes produces:

```python
class Postmortem(BaseModel):
    trade_id: int
    match_id: str
    decision: str                # APPROVE / REJECT (what we did)
    p_model_entry: float
    p_market_entry: float
    net_edge_entry: float
    position_notional: float
    actual_outcome: str          # won, lost, void
    realized_pnl: float
    was_plus_ev_ex_post: bool    # p_model > p_market at entry
    calibration_error: float     # p_model - actual (0 or 1)
    notes: str
```

---

## 7. Data Sources

### 7.1 Primary Sources

| Source | Data Provided | Access | Notes |
|--------|--------------|--------|-------|
| **Oracle's Elixir** | Game-level stats for LCK, LPL, LEC, LCS | Free CSV/JSON download | Gold standard for LoL stats. Covers 2014-present. |
| **Leaguepedia (via API)** | Match schedules, results, rosters, tournaments | Free wiki API | Good for metadata, rosters, tournament structure. |
| **LoL Esports API** | Official match data, schedules, standings | Free (rate-limited) | Riot's official data. Best for upcoming matches. |
| **Kalshi API** | Market listings, order books, historical prices | Free (read-only) | Primary trading venue. |

### 7.2 Data Collection Cadence

| Data Type | Collection Frequency | Trigger |
|-----------|---------------------|---------|
| Historical matches | One-time bulk, then daily | Manual bulk load, then cron |
| Upcoming matches | Daily | Cron |
| Rosters | On match announcement, then on roster lock | Event-driven or daily poll |
| Patch notes | On patch release | Event-driven |
| Kalshi snapshots | Every 5 minutes during active markets | Cron |

### 7.3 Data Storage

All raw data stored immutably in `data/raw/`. Processed/canonical data in `data/processed/`. Feature snapshots in `data/features/`. All gitignored.

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Kalshi esports liquidity too low | Medium | High | Start with paper only. Measure liquidity before any real-money consideration. |
| Model calibration drifts after major patches | Medium | Medium | Monitor calibration per-patch. Implement recalibration trigger. |
| Roster data unreliable or late | High | Medium | Rejection condition for unconfirmed rosters. Track roster accuracy. |
| Event matching failures (wrong match paired) | Medium | High | Confidence scoring. Flag ambiguous matches for manual review. |
| Overfitting to a specific meta or patch cycle | High | Medium | Walk-forward validation. Regular retraining. Slice analysis. |
| Data pipeline breaks silently | Medium | High | Data quality checks at ingestion. Alerts on schema violations. |
| Hermes and strategy layer diverge | Low | Medium | Independent checks. Discrepancy logging. |
