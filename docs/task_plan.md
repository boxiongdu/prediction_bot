# Task Plan

> Last updated: 2026-07-28
> Author: prediction_bot team
> Companion documents: architecture.md, research_plan.md, PROJECT.md

---

## Overview

This document divides the project into 12 milestones. Each milestone is small, testable, and has clear acceptance criteria. Milestones are ordered by dependency. No milestone begins until its dependencies are satisfied.

**Rule**: Every milestone that produces code must include tests. Leakage tests are non-negotiable for any feature that touches match data.

---

## Milestone 1: Project Skeleton and Configuration

**Objective**: Create the Python package structure, configuration system, and testing infrastructure.

**Files / Modules**:
- `pyproject.toml` — project metadata, dependencies, tool config (pytest, ruff, mypy)
- `src/prediction_bot/__init__.py`
- `src/prediction_bot/config/__init__.py`
- `src/prediction_bot/config/settings.py` — pydantic-settings, env-driven
- `src/prediction_bot/config/paths.py` — data/cache/output path resolution
- `tests/__init__.py`
- `tests/conftest.py` — shared fixtures
- `.env.example` — documents required env vars (no real values)

**Acceptance Criteria**:
- `pip install -e .` succeeds in a clean virtualenv.
- `pytest` runs and discovers 0 tests (infrastructure only for this milestone).
- `python -c "from prediction_bot.config.settings import Settings; print(Settings())"` works.
- `ruff check src/` passes with zero errors.
- `.env` is gitignored. `.env.example` is committed.

**Tests Required**:
- Settings load from environment variables.
- Settings raise on missing required values.
- Paths resolve correctly.

**Dependencies**: None (first milestone).

**Major Risks**: None.

---

## Milestone 2: Historical Data Ingestion

**Objective**: Ingest League of Legends historical match data from Oracle's Elixir into the canonical schema.

**Files / Modules**:
- `src/prediction_bot/data/__init__.py`
- `src/prediction_bot/data/schema.py` — SQLAlchemy or dataclass models for matches, games, teams, tournaments, patches
- `src/prediction_bot/data/ingestion.py` — raw CSV/JSON → canonical transforms
- `src/prediction_bot/data/quality.py` — validation checks
- `src/prediction_bot/data/sources/__init__.py`
- `src/prediction_bot/data/sources/oracleelixir.py` — Oracle's Elixir parser
- `tests/data/test_ingestion.py`
- `tests/data/test_quality.py`
- `tests/data/test_schema.py`
- `tests/data/fixtures/` — small sample CSVs for testing

**Acceptance Criteria**:
- Ingestion script loads Oracle's Elixir data for 2023-2025 without errors.
- All quality checks pass on the ingested data.
- Schema constraints are enforced (no null winners for completed matches, valid tournament tiers, etc.).
- Canonical team IDs are generated and deduplicated.
- At least 500 matches are successfully ingested.

**Tests Required**:
- Known sample CSV → correct match records.
- Missing fields handled gracefully.
- Duplicate match detection.
- Quality check functions reject known-bad data.
- Tournament tier validation.

**Dependencies**: Milestone 1.

**Major Risks**:
- Oracle's Elixir schema may change. Mitigation: pin to a known-good snapshot.
- Team name normalization is fuzzy. Mitigation: start with exact matches, build alias table incrementally.

---

## Milestone 3: Canonical Team and Roster Schema

**Objective**: Build canonical team and player tables from Leaguepedia and ingestion data, with roster timeline tracking.

**Files / Modules**:
- `src/prediction_bot/data/sources/leaguepedia.py` — Leaguepedia API client
- Extend `schema.py` with player and roster tables
- Extend `ingestion.py` with roster ingestion
- `tests/data/test_rosters.py`

**Acceptance Criteria**:
- At least 50 teams have canonical team_ids with aliases.
- At least 200 players are tracked with role assignments.
- Roster entries include effective_from and effective_to timestamps.
- Roster continuity features can be computed (see Milestone 4).

**Tests Required**:
- Roster timeline: for a known match date, the correct roster is returned.
- Roster continuity: when a team makes a substitution, continuity < 1.0.
- Player aliases resolve correctly.

**Dependencies**: Milestone 2.

**Major Risks**:
- Leaguepedia API may be unreliable or slow. Mitigation: cache responses. Fall back to static dumps.
- Roster data may have gaps (especially for minor regions). Mitigation: flag matches with incomplete roster data.

---

## Milestone 4: Leakage-Safe Elo Baseline

**Objective**: Implement an Elo rating system and a simple Elo-difference → probability model with full leakage safety.

**Files / Modules**:
- `src/prediction_bot/features/__init__.py`
- `src/prediction_bot/features/base.py` — feature registry with knowledge deadlines
- `src/prediction_bot/features/elo.py` — Elo computation with timestamp gating
- `src/prediction_bot/features/leak_test.py` — leakage detection utilities
- `src/prediction_bot/models/__init__.py`
- `src/prediction_bot/models/baseline.py` — naive baseline, Elo baseline
- `src/prediction_bot/evaluation/__init__.py`
- `src/prediction_bot/evaluation/walkforward.py` — expanding-window splitter
- `src/prediction_bot/evaluation/metrics.py` — Brier, log loss, accuracy
- `tests/features/test_elo.py`
- `tests/features/test_leak.py`
- `tests/models/test_baseline.py`
- `tests/evaluation/test_walkforward.py`

**Acceptance Criteria**:
- Elo ratings can be computed for any point in time using only matches before that time.
- Elo K-factor is configurable and tuned on the earliest 20% of data.
- Elo baseline Brier score is computed via walk-forward validation on 2023-2025 data.
- Elo baseline Brier score < naive baseline Brier score.
- Leakage tests pass: for any match at time T, computing Elo at T and at T+1 day produces the same prediction for T.

**Tests Required**:
- Elo updates correctly after a win/loss.
- Elo at time T does not use matches with scheduled_time > T.
- Feature snapshot immutability (leakage test).
- Walk-forward split: training windows never contain test matches.
- Naive baseline returns 0.50 for all matches.

**Dependencies**: Milestones 2, 3.

**Major Risks**:
- Choosing the wrong K-factor. Mitigation: grid search on earliest 20% of data.
- Home/away or blue/red side advantage not captured by Elo alone. Mitigation: tracked as a separate feature in Milestone 6.

---

## Milestone 5: Walk-Forward Evaluation Framework

**Objective**: Build a reusable evaluation framework that works for any model following a standard interface.

**Files / Modules**:
- Refactor `evaluation/walkforward.py` into a generic framework
- `src/prediction_bot/evaluation/slices.py` — performance by region, tier, format, bucket
- `src/prediction_bot/evaluation/reports.py` — markdown/HTML reports
- `tests/evaluation/test_slices.py`

**Acceptance Criteria**:
- Walk-forward evaluation produces Brier, log loss, accuracy, and ECE for any model implementing the standard interface.
- Slice analysis produces per-region, per-tier, per-format, and per-probability-bucket metrics.
- Reports include calibration curves (reliability diagrams).
- Minimum sample-size warnings are emitted for slices with < 30 predictions.

**Tests Required**:
- Walk-forward with a mock model returns expected metrics.
- Slice analysis correctly partitions matches.
- Calibration curve matches manual calculation on a small known dataset.

**Dependencies**: Milestone 4.

**Major Risks**: None. This is a framework milestone with low external dependencies.

---

## Milestone 6: Logistic Regression Model and Calibration

**Objective**: Build the calibrated logistic regression model with the feature set from architecture.md §6.2.

**Files / Modules**:
- `src/prediction_bot/features/form.py` — win rate, Elo change features
- `src/prediction_bot/features/roster.py` — continuity, substitution features
- `src/prediction_bot/features/patch.py` — patch age, newness features
- `src/prediction_bot/models/logistic.py` — logistic regression with L2
- `src/prediction_bot/calibration/__init__.py`
- `src/prediction_bot/calibration/platt.py` — Platt scaling
- `src/prediction_bot/calibration/isotonic.py` — isotonic regression
- `src/prediction_bot/calibration/metrics.py` — ECE, reliability table
- `tests/features/test_form.py`
- `tests/features/test_roster.py`
- `tests/features/test_patch.py`
- `tests/models/test_logistic.py`
- `tests/calibration/test_calibration.py`

**Acceptance Criteria**:
- All features pass leakage tests.
- Logistic regression trained via walk-forward achieves Brier ≤ 0.22.
- Platt-scaled probabilities achieve ECE ≤ 0.05 on test folds.
- Calibration curves are within ±0.05 of the diagonal in all bins with ≥ 100 samples.
- Model outperforms Elo baseline on Brier and log loss.

**Tests Required**:
- Feature leakage tests for all new features.
- Logistic regression: coefficients are finite and interpretable.
- Platt scaling: calibrated probabilities are monotonic in raw scores.
- ECE computation matches manual binning.

**Dependencies**: Milestones 4, 5.

**Major Risks**:
- Features may not improve over Elo alone. Mitigation: feature ablation to identify which features contribute. If LR doesn't beat Elo, the hypothesis that public data has signal beyond Elo is challenged — a valuable finding either way.
- Multicollinearity among features. Mitigation: L2 regularization handles this. Check VIF as diagnostic.

---

## Milestone 7: Kalshi Read-Only Client

**Objective**: Build a read-only Kalshi API client that can discover esports markets and retrieve order books.

**Files / Modules**:
- `src/prediction_bot/kalshi/__init__.py`
- `src/prediction_bot/kalshi/client.py` — API client with auth, rate limiting
- `src/prediction_bot/kalshi/discovery.py` — esports market filtering
- `tests/kalshi/test_client.py`

**Acceptance Criteria**:
- Client authenticates using `KALSHI_API_KEY` from environment.
- Client can list active markets.
- Client can filter markets to esports/League of Legends only.
- Client can retrieve order book for a given market ticker.
- Client handles rate limits gracefully (retry with backoff).
- Client handles API errors gracefully (log, don't crash).
- Tests use mocked HTTP responses (no real API calls in CI).

**Tests Required**:
- Auth header is set correctly.
- Market filtering logic.
- Order book parsing.
- Rate limit retry behavior.
- Error response handling.

**Dependencies**: Milestone 1 (for config).

**Major Risks**:
- Kalshi API may change. Mitigation: version the client against a specific API version. Tests catch breaking changes.
- API key management. Mitigation: `.env` only, never committed. `.env.example` documents required vars.

---

## Milestone 8: Event Matching System

**Objective**: Match Kalshi markets to internal match records with confidence scoring.

**Files / Modules**:
- `src/prediction_bot/kalshi/matching.py` — event matching logic
- `tests/kalshi/test_matching.py`

**Acceptance Criteria**:
- For a Kalshi market titled "T1 vs Gen.G — LCK Spring 2025", the matcher identifies the correct internal match record.
- Team name normalization resolves common aliases (e.g., "T1" ↔ "SK Telecom T1").
- Matching produces a confidence score: HIGH (exact team + date match), MEDIUM (team match, date within ±1 day), LOW (team match only), NONE.
- Only HIGH and MEDIUM confidence matches proceed automatically. LOW is flagged for review.
- Matcher handles Kalshi markets that don't correspond to any internal match (returns no match).

**Tests Required**:
- Exact team + date match → HIGH confidence.
- Alias resolution: "T1" vs "SKT T1" → same team.
- Date tolerance: ±1 day → MEDIUM.
- No matching internal match → NONE.
- Multiple Kalshi markets for same event → both matched to same internal match.

**Dependencies**: Milestones 3, 7.

**Major Risks**:
- Kalshi team naming is inconsistent. Mitigation: build alias table incrementally. Manual review of unmatched markets.
- Events may be listed under unexpected tickers. Mitigation: search by keyword as well as category filter.

---

## Milestone 9: Snapshot Collection

**Objective**: Build a system to collect and store Kalshi order-book snapshots on a schedule for active esports markets.

**Files / Modules**:
- `src/prediction_bot/kalshi/snapshots.py` — snapshot collection
- `src/prediction_bot/kalshi/prices.py` — executable price extraction
- `src/prediction_bot/scripts/snapshot.py` — CLI script for manual/cron collection
- `tests/kalshi/test_prices.py`

**Acceptance Criteria**:
- Snapshot collection stores best_bid, best_ask, bid_depth, ask_depth, spread, midpoint, last_price, and timestamp for each active esports market.
- Snapshots are stored immutably (append-only).
- Executable price extraction: "yes" side = ask, "no" side = 1 - bid.
- Spread and depth filters applied.
- Snapshot script can be run manually for testing and via cron for production.

**Tests Required**:
- Executable price for yes = ask, no = 1 - bid.
- Spread filter: market with spread > max_spread is rejected.
- Depth filter: market with depth < min_depth is rejected.
- Snapshot immutability: same market at same timestamp produces same record.

**Dependencies**: Milestones 7, 8.

**Major Risks**:
- Snapshot collection frequency vs. Kalshi rate limits. Mitigation: start with 5-minute intervals. Adjust based on rate limit headers.
- Snapshot storage size. Mitigation: SQLite is fine for MVP scale. Reassess if row count exceeds 1M.

---

## Milestone 10: Paper Trading Simulator

**Objective**: Build a paper-trading system that simulates fills at executable prices and tracks positions to resolution.

**Files / Modules**:
- `src/prediction_bot/strategy/__init__.py`
- `src/prediction_bot/strategy/edge.py` — edge computation
- `src/prediction_bot/strategy/sizing.py` — Kelly sizing, exposure caps
- `src/prediction_bot/strategy/eligibility.py` — rejection conditions
- `src/prediction_bot/strategy/thresholds.py` — configurable thresholds
- `tests/strategy/test_edge.py`
- `tests/strategy/test_sizing.py`
- `tests/strategy/test_eligibility.py`

**Acceptance Criteria**:
- Edge computation: raw_edge = p_conservative - p_market_executable.
- Net edge = raw_edge - spread_cost.
- Fractional Kelly sizing produces position sizes within exposure caps.
- Exposure caps are enforced at match, team, tournament, and day level.
- All 12 rejection conditions from research_plan.md §5.4 are implemented and tested.
- Paper trades are recorded with entry price, quantity, notional, and timestamp.
- Paper P&L is computed at resolution.

**Tests Required**:
- Edge positive when p_conservative > p_market.
- Kelly fraction with edge=0 → position=0.
- Kelly fraction with edge=0.10, odds=1.0 → positive position.
- Exposure cap: position truncated when cap is hit.
- Each rejection condition triggers correctly on bad input.
- Paper P&L: won trade → positive payout (1 - entry_price) × contracts.

**Dependencies**: Milestones 6, 9.

**Major Risks**:
- Kelly formula edge cases (negative edge, zero market price). Mitigation: floor at 0.
- Exposure tracking across multiple concurrent matches. Mitigation: maintain a positions ledger queried at decision time.

---

## Milestone 11: Hermes Decision Layer

**Objective**: Build the Hermes review agent that sits between strategy output and paper execution.

**Files / Modules**:
- `src/prediction_bot/hermes/__init__.py`
- `src/prediction_bot/hermes/schema.py` — Pydantic input/output models
- `src/prediction_bot/hermes/review.py` — independent eligibility & risk re-checks
- `src/prediction_bot/hermes/explain.py` — human-readable recommendation text
- `src/prediction_bot/hermes/postmortem.py` — post-settlement analysis
- `src/prediction_bot/scripts/recommend.py` — CLI to run Hermes on strategy output
- `tests/hermes/test_schema.py`
- `tests/hermes/test_review.py`
- `tests/hermes/test_postmortem.py`

**Acceptance Criteria**:
- Hermes accepts a `RecommendationRequest` and returns a `Recommendation`.
- Hermes independently validates all eligibility checks (doesn't trust the request's own checks).
- Hermes computes exposure from the paper trade ledger, not from the request.
- Decision is APPROVE when all checks pass, REJECT when any fails, FLAG when ambiguous.
- Human-readable explanation includes: teams, model probability, market price, edge, position size, and reasoning for the decision.
- Postmortem compares entry probability to actual outcome and computes calibration error.
- All code paths are tested (APPROVE, REJECT, FLAG scenarios).

**Tests Required**:
- Valid request with all checks passing → APPROVE.
- Request with OOD flag → REJECT.
- Request with edge below threshold → REJECT.
- Request with exposure cap exceeded → REJECT.
- Request with edge within 0.005 of threshold → FLAG.
- Postmortem: won trade → calibration error = p_model - 1.0 (negative = overconfident).
- Postmortem: lost trade → calibration error = p_model - 0.0 (positive = overconfident in winner).
- Schema validation: malformed request raises ValidationError.

**Dependencies**: Milestone 10.

**Major Risks**:
- Hermes implementation may drift from strategy layer checks. Mitigation: tests explicitly verify that Hermes and strategy checks agree on given inputs. If they diverge, the test fails and requires reconciliation.
- Postmortem analysis may reveal model miscalibration that wasn't caught in backtesting. This is expected — the postmortem IS the detection mechanism.

---

## Milestone 12: Performance Attribution and Postmortem Reports

**Objective**: Build comprehensive post-settlement attribution reports that decompose P&L into model edge, calibration error, and luck.

**Files / Modules**:
- `src/prediction_bot/scripts/postmortem.py` — CLI to generate reports
- Extend `evaluation/reports.py` with attribution breakdowns
- Extend `hermes/postmortem.py` with aggregate statistics
- `tests/hermes/test_postmortem.py` (extended)

**Acceptance Criteria**:
- Report shows: total trades, win rate, total P&L, Sharpe ratio, max drawdown.
- Report decomposes P&L into: edge component (p_model - p_market) × position and luck component (actual - p_model) × position.
- Report shows calibration error distribution across all trades.
- Report shows performance by region, tournament tier, format, and edge bucket.
- Report identifies worst and best trades with explanations.
- Report is generated as a markdown file saved to `data/results/`.

**Tests Required**:
- Attribution: sum of edge + luck components = total P&L within floating-point tolerance.
- Calibration error mean across many trades → 0 for a perfectly calibrated model (test with synthetic data).
- Report generation does not crash on empty trade history.

**Dependencies**: Milestone 11.

**Major Risks**:
- Attribution is noisy with small sample sizes. Mitigation: report sample size alongside each statistic. Warn when < 30 trades.

---

## Dependency Graph

```
M1 (skeleton)
 └─ M2 (data ingestion)
     └─ M3 (canonical teams/rosters)
         └─ M4 (Elo baseline)
             └─ M5 (walk-forward eval)
                 └─ M6 (logistic regression)
                     └─ M10 (paper trading)
 └─ M7 (Kalshi client)
     └─ M8 (event matching)
         └─ M9 (snapshot collection)
             └─ M10 (paper trading)
                 └─ M11 (Hermes layer)
                     └─ M12 (attribution reports)
```

---

## Milestone Summary Table

| # | Milestone | Est. Files | Est. Tests | Depends On |
|---|-----------|-----------|-----------|------------|
| 1 | Project skeleton | 6 | 3 | — |
| 2 | Historical data ingestion | 10 | 3 | M1 |
| 3 | Canonical teams & rosters | 5 | 3 | M2 |
| 4 | Elo baseline | 12 | 7 | M2, M3 |
| 5 | Walk-forward evaluation | 4 | 2 | M4 |
| 6 | Logistic regression | 14 | 9 | M4, M5 |
| 7 | Kalshi client | 3 | 5 | M1 |
| 8 | Event matching | 2 | 4 | M3, M7 |
| 9 | Snapshot collection | 3 | 3 | M7, M8 |
| 10 | Paper trading | 5 | 12 | M6, M9 |
| 11 | Hermes layer | 6 | 8 | M10 |
| 12 | Attribution reports | 4 | 3 | M11 |
