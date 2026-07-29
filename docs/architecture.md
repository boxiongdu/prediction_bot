# Architecture

> Last updated: 2026-07-28
> Author: prediction_bot team

---

## 1. Overview

This document describes the system architecture of the prediction_bot research system — an independent, paper-only esports probability-modeling and value-trading research pipeline. The system generates calibrated pre-match outcome probabilities for esports matches, compares them with executable Kalshi contract prices, identifies positive expected-value opportunities, and records paper-trading decisions for post-hoc evaluation. No real money is ever committed.

---

## 2. Design Principles

1. **Chronological safety above all else.** No future information may leak into feature computation, model training, or evaluation. Every pipeline split is timestamp-gated.
2. **Simple before complex.** A naive baseline is built first. Elo follows. Logistic regression after that. Gradient boosting only if residual edge is demonstrated. Every complexity increase must be justified by a measurable improvement in calibration or profitability.
3. **Probability calibration is the primary signal.** Classification accuracy is a secondary diagnostic. A model that wins 60% of bets on 50% contracts is worse than one that correctly estimates the 50%.
4. **Kalshi prices are a comparison target, never a model input.** The initial independent model must be built without seeing Kalshi data. Only after the model is frozen do prices enter the pipeline as a decision signal.
5. **Hermes is a review layer, not an executor.** Hermes reads model output, applies risk checks, and produces a signed recommendation. A separate, trivial script maps recommendations to paper orders. The two layers are deliberately decoupled.

---

## 3. System Boundary

```
┌─────────────────────────────────────────────────────────────────┐
│                        EXTERNAL DATA                            │
│  (match results, rosters, patches, tournament schedules,        │
│   Kalshi API — read-only, no credentials committed)             │
└───────────────┬──────────────────────────────────┬──────────────┘
                │                                  │
                ▼                                  ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│      DATA LAYER              │    │    KALSHI LAYER              │
│  - ingestion                 │    │  - market discovery          │
│  - canonical IDs             │    │  - event matching            │
│  - quality checks            │    │  - snapshot collection       │
│  - schema enforcement        │    │  - bid/ask reconstruction    │
└───────────────┬──────────────┘    └───────────────┬──────────────┘
                │                                   │
                ▼                                   │
┌──────────────────────────────┐                    │
│      FEATURE LAYER            │                   │
│  - leakage-safe timestamps   │                   │
│  - Elo / rating features     │                   │
│  - roster / form features    │                   │
│  - patch / format features   │                   │
└───────────────┬──────────────┘                   │
                │                                  │
                ▼                                  │
┌──────────────────────────────┐                   │
│      MODEL LAYER              │                   │
│  - naive baseline            │                   │
│  - Elo baseline              │                   │
│  - logistic regression       │                   │
│  - calibration               │                   │
│  - uncertainty estimation    │                   │
└───────────────┬──────────────┘                   │
                │                                  │
                ▼                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      STRATEGY LAYER                             │
│  - edge computation              - position sizing              │
│  - eligibility checks            - exposure limits              │
│  - rejection conditions          - threshold calibration        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     HERMES REVIEW LAYER                         │
│  - input schema ingestion       - eligibility & risk re-checks  │
│  - position-sizing review       - human-readable explanation    │
│  - signed recommendation        - post-trade / settlement review│
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   PAPER EXECUTION LAYER                         │
│  - maps Hermes recs → paper orders                              │
│  - records fills at executable prices                           │
│  - tracks P&L → resolution                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Package Structure

```
prediction_bot/
├── pyproject.toml
├── PROJECT.md
├── README.md
├── docs/
│   ├── architecture.md          # this file
│   ├── research_plan.md         # analytical foundations
│   └── task_plan.md             # implementation roadmap
├── src/
│   └── prediction_bot/
│       ├── __init__.py
│       ├── config/
│       │   ├── __init__.py
│       │   ├── settings.py      # pydantic-settings, env-driven
│       │   └── paths.py         # data/cache/output paths
│       ├── data/
│       │   ├── __init__.py
│       │   ├── schema.py        # SQLAlchemy / dataclass models
│       │   ├── ingestion.py     # raw → canonical transforms
│       │   ├── quality.py       # validation and checks
│       │   └── sources/         # one file per data source
│       │       ├── __init__.py
│       │       ├── lolesports.py
│       │       ├── oracleelixir.py
│       │       └── leaguepedia.py
│       ├── features/
│       │   ├── __init__.py
│       │   ├── base.py          # feature registry, timestamps
│       │   ├── elo.py           # Elo rating system
│       │   ├── form.py          # recent performance
│       │   ├── roster.py        # continuity, substitutions
│       │   ├── patch.py         # patch/version features
│       │   └── leak_test.py     # leakage detection tests
│       ├── models/
│       │   ├── __init__.py
│       │   ├── baseline.py      # naive, Elo baselines
│       │   ├── logistic.py      # logistic regression
│       │   ├── gbm.py           # gradient boosting (optional)
│       │   └── ensemble.py      # disagreement, OOD detection
│       ├── calibration/
│       │   ├── __init__.py
│       │   ├── isotonic.py      # isotonic regression
│       │   ├── platt.py         # Platt scaling
│       │   └── metrics.py       # Brier, log loss, ECE
│       ├── kalshi/
│       │   ├── __init__.py
│       │   ├── client.py        # read-only API client
│       │   ├── discovery.py     # esports market discovery
│       │   ├── matching.py      # event/team matching
│       │   ├── snapshots.py     # order-book snapshots
│       │   └── prices.py        # executable price extraction
│       ├── strategy/
│       │   ├── __init__.py
│       │   ├── edge.py          # edge / EV computation
│       │   ├── sizing.py        # fractional Kelly, exposure
│       │   ├── eligibility.py   # rejection conditions
│       │   └── thresholds.py    # configurable thresholds
│       ├── hermes/
│       │   ├── __init__.py
│       │   ├── schema.py        # input/output Pydantic models
│       │   ├── review.py        # eligibility + risk re-checks
│       │   ├── explain.py       # human-readable rec text
│       │   └── postmortem.py    # post-trade/settlement analysis
│       ├── evaluation/
│       │   ├── __init__.py
│       │   ├── walkforward.py   # expanding-window splitter
│       │   ├── metrics.py       # Brier, log loss, calibration
│       │   ├── slices.py        # by region, tier, format
│       │   └── reports.py       # HTML / markdown reports
│       └── scripts/
│           ├── ingest.py        # CLI: ingest historical data
│           ├── train.py         # CLI: train models
│           ├── evaluate.py      # CLI: walk-forward eval
│           ├── snapshot.py      # CLI: collect Kalshi snapshots
│           ├── recommend.py     # CLI: generate Hermes recs
│           └── postmortem.py    # CLI: post-settlement analysis
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── data/
│   │   ├── test_ingestion.py
│   │   ├── test_quality.py
│   │   └── test_schema.py
│   ├── features/
│   │   ├── test_elo.py
│   │   ├── test_form.py
│   │   ├── test_roster.py
│   │   ├── test_patch.py
│   │   └── test_leak.py
│   ├── models/
│   │   ├── test_baseline.py
│   │   ├── test_logistic.py
│   │   └── test_ensemble.py
│   ├── calibration/
│   │   └── test_calibration.py
│   ├── kalshi/
│   │   ├── test_client.py
│   │   ├── test_matching.py
│   │   └── test_prices.py
│   ├── strategy/
│   │   ├── test_edge.py
│   │   ├── test_sizing.py
│   │   └── test_eligibility.py
│   ├── hermes/
│   │   ├── test_schema.py
│   │   ├── test_review.py
│   │   └── test_postmortem.py
│   └── evaluation/
│       ├── test_walkforward.py
│       └── test_slices.py
└── data/                          # gitignored
    ├── raw/                       # immutable source data
    ├── processed/                 # canonical, cleaned
    ├── features/                  # feature snapshots by time
    ├── models/                    # serialized model artifacts
    ├── snapshots/                 # Kalshi order-book snapshots
    └── results/                   # evaluation reports
```

---

## 5. Data Architecture

### 5.1 Entity-Relationship Summary

```
Team  1──* Roster  *──1 Player
  │
  │
  ▼
Match *──1 Tournament
  │
  ├──* Game (game-level stats)
  │
  ▼
MatchOutcome
  │
  ▼
FeatureSnapshot (timestamp-gated)
  │
  ▼
ModelPrediction
  │
  ▼
KalshiMarket  1──* KalshiSnapshot
  │
  ▼
PaperTrade ─── Resolution
```

### 5.2 Proposed Tables

**teams**
| Column | Type | Notes |
|--------|------|-------|
| team_id | TEXT PK | canonical slug, e.g. `t1`, `g2-esports` |
| name | TEXT | display name |
| region | TEXT | LCK, LPL, LEC, LCS, etc. |
| aliases | JSON | known alternative names for matching |

**players**
| Column | Type | Notes |
|--------|------|-------|
| player_id | TEXT PK | canonical slug |
| name | TEXT | display name |
| role | TEXT | top, jungle, mid, adc, support |
| aliases | JSON | known alternative names |

**rosters**
| Column | Type | Notes |
|--------|------|-------|
| roster_id | INTEGER PK | |
| team_id | TEXT FK → teams | |
| players | JSON | list of player_ids |
| effective_from | TIMESTAMP | when this roster became active |
| effective_to | TIMESTAMP | NULL if current |

**tournaments**
| Column | Type | Notes |
|--------|------|-------|
| tournament_id | TEXT PK | |
| name | TEXT | |
| tier | TEXT | S, A, B, C or major/minor |
| region | TEXT | |
| start_date | DATE | |
| end_date | DATE | |

**matches**
| Column | Type | Notes |
|--------|------|-------|
| match_id | TEXT PK | |
| tournament_id | TEXT FK → tournaments | |
| team_a_id | TEXT FK → teams | |
| team_b_id | TEXT FK → teams | |
| format | TEXT | BO1, BO3, BO5 |
| patch | TEXT | e.g. `14.12` |
| scheduled_time | TIMESTAMP | UTC |
| actual_start_time | TIMESTAMP | UTC, nullable until known |
| winner | TEXT | team_id of winner, NULL if not played |
| cancelled | BOOL | |

**games**
| Column | Type | Notes |
|--------|------|-------|
| game_id | TEXT PK | |
| match_id | TEXT FK → matches | |
| game_number | INT | 1, 2, 3, ... |
| team_a_side | TEXT | blue or red |
| winner | TEXT | team_id |
| duration_seconds | INT | |
| objectives | JSON | dragons, barons, towers, inhibitors |
| economy | JSON | gold diffs at N minutes |

**patches**
| Column | Type | Notes |
|--------|------|-------|
| patch | TEXT PK | e.g. `14.12` |
| release_date | TIMESTAMP | when patch went live |
| notes_url | TEXT | optional link |

**feature_snapshots**
| Column | Type | Notes |
|--------|------|-------|
| snapshot_id | INTEGER PK | |
| match_id | TEXT FK → matches | |
| as_of_time | TIMESTAMP | point-in-time the features are valid |
| features | JSON | all feature values known at as_of_time |

**model_predictions**
| Column | Type | Notes |
|--------|------|-------|
| prediction_id | INTEGER PK | |
| match_id | TEXT FK → matches | |
| model_version | TEXT | hash or version tag |
| as_of_time | TIMESTAMP | when prediction was generated |
| prob_team_a | FLOAT | calibrated probability |
| prob_team_b | FLOAT | |
| uncertainty | FLOAT | model uncertainty estimate |
| is_ood | BOOL | out-of-distribution flag |

**kalshi_markets**
| Column | Type | Notes |
|--------|------|-------|
| market_ticker | TEXT PK | Kalshi ticker |
| event_ticker | TEXT | Kalshi event ID |
| title | TEXT | |
| rules | TEXT | contract rules |
| matched_match_id | TEXT FK → matches | NULL if unmatched |
| matched_team | TEXT | which team this side is on |

**kalshi_snapshots**
| Column | Type | Notes |
|--------|------|-------|
| snapshot_id | INTEGER PK | |
| market_ticker | TEXT FK → kalshi_markets | |
| captured_at | TIMESTAMP | |
| best_bid | FLOAT | |
| best_ask | FLOAT | |
| bid_depth | FLOAT | volume at best bid |
| ask_depth | FLOAT | volume at best ask |
| spread | FLOAT | ask - bid |
| midpoint | FLOAT | (bid + ask) / 2 |
| last_price | FLOAT | NULL if no trade |

**paper_trades**
| Column | Type | Notes |
|--------|------|-------|
| trade_id | INTEGER PK | |
| recommendation_id | TEXT | Hermes rec ID |
| match_id | TEXT FK → matches | |
| market_ticker | TEXT FK → kalshi_markets | |
| side | TEXT | yes or no |
| entry_price | FLOAT | executable price filled |
| quantity | INT | number of contracts |
| notional | FLOAT | quantity × entry_price |
| placed_at | TIMESTAMP | |
| status | TEXT | open, resolved, cancelled |

**resolutions**
| Column | Type | Notes |
|--------|------|-------|
| resolution_id | INTEGER PK | |
| trade_id | INTEGER FK → paper_trades | |
| resolved_at | TIMESTAMP | |
| outcome | TEXT | won, lost, void |
| payout | FLOAT | realized P&L |
| notes | TEXT | |

### 5.3 Data Quality Checks (enforced at ingestion)

- Each match must have a non-null scheduled_time.
- Winner must be one of the two participating teams (or NULL for unplayed).
- Roster effective_from must precede effective_to (if set).
- Feature snapshot as_of_time must be ≤ match scheduled_time.
- All timestamps in UTC.
- No duplicate primary keys.
- Tournament tier must be one of a closed set.

---

## 6. Leakage-Safe Feature Engineering

### 6.1 Timestamp Gating Rule

Every feature used to predict match M at time T_pred must be computable exclusively from information known at or before T_pred.

This rule is enforced by:

1. **Feature registry**: every feature function declares a `knowledge_deadline` parameter.
2. **Feature snapshot table**: features are materialized with an `as_of_time` column.
3. **Walk-forward splitter**: training data for match at time T only includes matches with scheduled_time < T.
4. **Leakage tests**: tests assert that for any match, features do not change when computed from a snapshot taken after the match.

### 6.2 Feature Inventory

| Feature | Knowledge Deadline | Description |
|---------|-------------------|-------------|
| elo_team_a, elo_team_b | match scheduled_time | Elo rating at deadline |
| elo_diff | match scheduled_time | elo_team_a - elo_team_b |
| form_win_rate_10 | match scheduled_time | win rate in last 10 matches |
| form_elo_change_10 | match scheduled_time | Elo change over last 10 matches |
| roster_continuity | match scheduled_time | fraction of roster unchanged from prior match |
| roster_days_together | match scheduled_time | days since last roster change |
| player_sub_flag | match scheduled_time | boolean: any substitution vs prior match |
| region_elo_mean | tournament start date | mean Elo of teams in the region |
| tournament_tier | always known | S/A/B/C tier |
| tournament_stage | always known | group, playoff, final |
| format_bo | always known | 1, 3, or 5 |
| patch_days_since_release | match scheduled_time | days since current patch went live |
| patch_is_new | match scheduled_time | boolean: patch < 7 days old |
| side_win_rate_team_a | match scheduled_time | team's historical win rate on side they'll play G1 |
| avg_game_duration_10 | match scheduled_time | average game duration last 10 |
| gold_diff_at_15_avg_10 | match scheduled_time | average gold diff at 15 min last 10 games |
| dragon_control_rate_10 | match scheduled_time | dragon first/stack rate last 10 |
| baron_control_rate_10 | match scheduled_time | baron rate last 10 |

### 6.3 Leakage Tests

Every feature function must pass:

1. **Snapshot immutability test**: given a match M, compute features at T_pred. Assert that computing the same features at any T > T_pred produces identical values for M.
2. **Training contamination test**: for every match in the training set, assert that no feature was computed using information from matches with scheduled_time ≥ the match's own scheduled_time.

---

## 7. Model Architecture

### 7.1 Layered Approach

```
Level 0: Naive Baseline
  Always predict 0.50 for every match. Establishes floor for Brier/log loss.

Level 1: Elo Baseline
  Elo difference → sigmoid transform → probability.
  Single hyperparameter: K-factor. Tuned on earliest 20% of data only.

Level 2: Logistic Regression
  Features from §6.2, L2 regularization. Calibrated via Platt scaling or isotonic regression on held-out calibration set.

Level 3: Gradient Boosting (optional, gated)
  Only if Level 2 shows residual edge vs Kalshi. LightGBM with monotonic constraints.
  Requires extra calibration step and careful OOD detection.

Level 4: Ensemble (optional, gated)
  Disagreement between L2 and L3 as uncertainty signal.
  Only if Level 3 is justified.
```

### 7.2 Calibration Pipeline

Every model output must be calibrated:

1. Train model on training fold.
2. Fit calibrator (Platt or isotonic) on a held-out calibration fold.
3. Evaluate calibration on test fold using reliability diagrams, ECE, and Brier.

### 7.3 Uncertainty Estimation

Three sources of uncertainty:

1. **Aleatoric**: inherent randomness in match outcomes (captured by probability itself).
2. **Epistemic model uncertainty**: bootstrapped variance across N models trained on slightly different folds.
3. **Ensemble disagreement**: when multiple model types disagree beyond a threshold.

Conservative probability formula (proposed, to be validated):

```
p_conservative = max(0.05, min(0.95, p_calibrated - λ * σ_bootstrap - δ * disagreement))
```

Where λ and δ are tunable conservatism parameters.

### 7.4 Out-of-Distribution Detection

Flag a match as OOD if any of:

- Elo difference outside the range seen in training.
- Tournament tier not seen in training.
- Region not seen in training.
- Feature vector Mahalanobis distance from training centroid exceeds threshold.
- Patch newer than any patch in training.

OOD matches are not traded. They are tracked for research.

---

## 8. Kalshi Integration

### 8.1 Read-Only Client

The Kalshi client is read-only. It never submits orders, even paper ones.

Authentication: API key stored in environment variable `KALSHI_API_KEY`. Never committed. Accessible only via `.env` (gitignored). Paper trading does not require a real Kalshi account; the paper execution layer simulates fills against historical snapshots.

### 8.2 Market Discovery

1. Query Kalshi `/markets` endpoint with `event_ticker` filter for esports-related events.
2. Filter by category tags ("esports", "league of legends", "LoL").
3. For each market, extract contract rules text to determine payout condition.

### 8.3 Event Matching

Match Kalshi markets to internal matches:

1. Normalize team names from Kalshi title using alias table.
2. Match by date proximity (±1 day tolerance) and team pair.
3. Validate contract rules: "Who will win" → match winner. Other contract types (e.g., "map handicap") are excluded for MVP.
4. Flag ambiguous matches for manual review.

### 8.4 Executable Price

The trading signal uses the **executable price**, not the midpoint:

- For a "yes" position on team A: executable price = best_offer (ask).
- For a "no" position on team A: executable price = 1 - best_bid.

### 8.5 Liquidity Filters

Reject a market if:

- `spread > max_spread` (configurable, default 0.05).
- `ask_depth < min_depth` (configurable, default $50 notional or 50 contracts).
- `bid_depth < min_depth`.
- Last snapshot is older than `max_snapshot_age` (configurable, default 30 minutes).

### 8.6 Snapshot Collection

Snapshots are collected on a cron schedule (e.g., every 5 minutes) and stored immutably. The paper execution layer replays trades against the snapshot nearest to the decision timestamp.

---

## 9. Strategy Layer

### 9.1 Edge Computation

```
p_model         = calibrated model probability for outcome
p_conservative  = uncertainty-adjusted probability (see §7.3)
p_market        = executable Kalshi price for the same outcome

raw_edge        = p_conservative - p_market

net_edge        = raw_edge - estimated_costs
# estimated_costs: spread cost + slippage estimate (for MVP, spread cost only)
```

### 9.2 Eligibility Conditions (ALL must pass)

| Condition | Check |
|-----------|-------|
| Match is in supported tournament list | tier check |
| Match has confirmed roster | roster available at T_pred |
| Event matched unambiguously | matching confidence score > threshold |
| Spread ≤ max_spread | liquidity filter |
| Depth ≥ min_depth | liquidity filter |
| Snapshot age ≤ max_age | data freshness |
| Model disagreement ≤ max_disagreement | ensemble delta check |
| Match not flagged OOD | OOD detector |
| net_edge ≥ min_edge | threshold check |

### 9.3 Position Sizing (Fractional Kelly)

```
bankroll     = configured paper bankroll
edge         = net_edge (decimal)
odds         = 1 / p_market - 1  (decimal odds)
f_kelly      = max(0, (edge * odds - (1 - edge)) / odds)  # full Kelly fraction
f_fractional = f_kelly * kelly_fraction  # configurable, default 0.25
position     = bankroll * f_fractional
contracts    = floor(position / entry_price)
```

### 9.4 Exposure Caps

| Cap Type | Default | Description |
|----------|---------|-------------|
| per_match | 5% of bankroll | maximum notional on a single match |
| per_team | 10% of bankroll | maximum total exposure to one team across markets |
| per_tournament | 20% of bankroll | maximum total exposure within one tournament |
| per_day | 15% of bankroll | maximum notional deployed in one calendar day |
| max_contracts | 500 | absolute contract cap per trade |

### 9.5 Rejection Conditions (OR — any triggers rejection)

- Unconfirmed roster
- Ambiguous event match
- Unsupported tournament
- Wide spread (> max_spread)
- Insufficient depth
- Snapshot stale (> max_snapshot_age)
- Model disagreement too high
- Match flagged OOD
- net_edge < min_edge
- Exposure cap would be exceeded

---

## 10. Hermes Review Layer

### 10.1 Role

Hermes is NOT the trading engine. Hermes is a review and decision layer that sits between the strategy output and the paper execution layer. It reads a structured recommendation request, applies eligibility and risk checks independently, and produces a signed recommendation. The execution layer maps that recommendation to a paper order.

### 10.2 Input Schema

```python
class RecommendationRequest(BaseModel):
    request_id: str
    match_id: str
    team_a: str
    team_b: str
    tournament: str
    format: str              # BO1, BO3, BO5
    scheduled_time: datetime
    p_model_team_a: float    # calibrated probability
    p_conservative_team_a: float  # uncertainty-adjusted
    model_version: str
    uncertainty: float
    ood_flag: bool
    ensemble_disagreement: float

    # Kalshi
    market_ticker: str
    executable_price: float  # for the side we'd take
    side: str                # "yes" on team_a, or "no" on team_a
    spread: float
    depth: float
    snapshot_age_minutes: int

    # Strategy
    raw_edge: float
    net_edge: float
    proposed_position_pct: float
    proposed_contracts: int
    proposed_notional: float
    exposure_current: dict   # current exposure by team/tournament/day
```

### 10.3 Output Schema

```python
class Recommendation(BaseModel):
    request_id: str
    decision: str            # APPROVE, REJECT, or FLAG
    reason: str              # human-readable explanation
    checks: dict             # each check name → PASS/FAIL/WARN
    approved_position_pct: float | None
    approved_contracts: int | None
    approved_notional: float | None
    reviewer_notes: str
    signed_at: datetime
    hermes_version: str
```

### 10.4 Decision Logic

Hermes re-checks all eligibility conditions independently (does not trust the strategy layer blindly). If any check fails, decision = REJECT with reason. If all pass, decision = APPROVE. If ambiguous (e.g., edge close to threshold), decision = FLAG for manual review.

### 10.5 Post-Trade Review

After each paper trade is placed, Hermes logs:

- What was recommended vs what was executed.
- Final fill price vs. snapshot price.
- Any discrepancies.

### 10.6 Post-Settlement Review

After each match resolves, Hermes produces a per-trade postmortem:

- Model probability vs. market price at entry.
- Actual outcome.
- Realized P&L.
- Calibration error contribution.
- Whether the trade was +EV ex-post (not the same as profitable — a +EV trade can lose).

---

## 11. Hold and Exit Policy

### 11.1 Default: Hold to Settlement

All positions are held until Kalshi contract settlement. Pre-match probabilities are point-in-time estimates and should not be used to justify in-play adjustments.

### 11.2 No Live Re-Entry

Pre-match model probabilities have no live-updating component. They cannot guide re-entry or averaging down after the match starts. Any in-play trading would require a fundamentally different model (not in scope).

### 11.3 Exceptional Exit Conditions

A position may be exited paper-only before settlement if:

1. **Roster change**: announced roster substitution after position entry but before match start.
2. **Contract mismatch**: Kalshi contract is resolved under a rule we did not anticipate (tracked for learning).
3. **Cancellation risk**: match is officially postponed or cancelled (void, not exited).
4. **Data error discovered**: we learn that our feature snapshot or model input was wrong at time of decision.

These exits are recorded with full rationale and reviewed in postmortems.

---

## 12. Key Architecture Decisions

See PROJECT.md §"Five Most Important Architecture Decisions" for the top-level summary.

---

## 13. Open Questions

See PROJECT.md §"Five Biggest Unresolved Questions" for the top-level summary.

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| Brier score | Mean squared error between predicted probability and binary outcome. Lower is better. Range [0, 1]. |
| Calibration | Property that when model says "60%", the outcome occurs ~60% of the time. |
| ECE | Expected Calibration Error. Binned comparison of predicted vs. actual frequency. |
| Elo | Rating system that updates after each match based on expected vs actual outcome. |
| EV | Expected value. edge × position size. |
| Fractional Kelly | Kelly criterion multiplied by a fraction (e.g., 0.25) to reduce volatility. |
| Leakage | Future information inadvertently used in training or feature computation. |
| OOD | Out-of-distribution. A match whose features lie outside the training distribution. |
| Paper trading | Simulated trading with no real money at risk. |
| Walk-forward | Temporal cross-validation where training always precedes testing. |
