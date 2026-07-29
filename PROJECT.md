# PROJECT.md

> prediction_bot — independent esports probability-modeling and value-trading research system
> Last updated: 2026-07-28

---

## What This Is

An end-to-end research pipeline that:

1. Builds its own pre-match probability model for esports match outcomes.
2. Compares calibrated model probabilities with executable Kalshi contract prices.
3. Identifies positive expected-value opportunities.
4. Sizes positions conservatively using uncertainty-adjusted fractional Kelly.
5. Holds selected positions to settlement.
6. Does all of the above on paper only.

The primary objective is **calibrated probabilities**, not classification accuracy. The downstream objective is to empirically test whether a simple, disciplined quantitative approach can identify mispricing in esports prediction markets.

---

## What This Is Not

- A production trading system.
- A real-time in-play betting model.
- A general "sports betting" framework.
- An automated execution system.
- A claim of guaranteed edge.

---

## Quick Links

| Document | Purpose |
|----------|---------|
| [docs/architecture.md](docs/architecture.md) | System design, package structure, data schema, integration points |
| [docs/research_plan.md](docs/research_plan.md) | Hypothesis, MVP definition, modeling roadmap, validation framework, trading logic |
| [docs/task_plan.md](docs/task_plan.md) | 12-milestone implementation plan with acceptance criteria and dependencies |

---

## Scope

**Initial scope:**
- Platform: Kalshi
- Esport: League of Legends
- Market type: match/series winner
- Timing: pre-match only
- Holding: hold to settlement
- Execution: paper only
- Validation: chronological (walk-forward), leakage-safe

---

## Five Most Important Architecture Decisions

1. **Leakage safety is the first constraint.** Every feature is timestamp-gated. Every train-test split is temporal. Every test verifies that no future information contaminates the model. This is not negotiable — a model with look-ahead bias produces results that look great in backtesting and fail catastrophically live.

2. **Kalshi prices are a comparison target, never a model input.** The independent model is built and evaluated before any market data is seen. This prevents the model from learning to mimic market prices and ensures that any identified edge is genuine rather than an artifact of overfitting to price data.

3. **Probability calibration is the primary metric.** We optimize for Brier score and ECE, not accuracy. A model that correctly estimates 70% probability on 70% of outcomes is more useful for trading than a model with 75% accuracy that is poorly calibrated. The downstream trading logic depends on well-calibrated probabilities to correctly compute expected value.

4. **Hermes is a separate review layer, not an integrated executor.** The Hermes agent receives structured recommendations from the strategy layer and independently validates eligibility, risk, and sizing before producing a signed decision. This separation ensures that execution decisions are auditable, that checks are performed redundantly, and that the model never directly triggers trades.

5. **Simplicity is a design goal, not a starting point to be overcome.** The modeling roadmap starts with a naive baseline and an Elo baseline before any machine learning. Logistic regression is the target MVP model. Gradient boosting is gated behind demonstrated need. Every complexity increase must be justified by measurable improvement in calibration or edge identification.

---

## Five Biggest Unresolved Questions

1. **Does the Kalshi esports market have sufficient liquidity for executable edges?** Spreads may be wide (>10%) and depth may be thin (<$50 notional). If so, even a well-calibrated model may find edges that cannot be captured. This is the most important empirical question and will be answered in Milestone 9 (snapshot collection).

2. **What is the right K-factor for League of Legends Elo, and does a single value work across regions and formats?** The K-factor controls how quickly ratings update. LoL has rapid meta changes (patches every 2 weeks) and roster volatility. A single K-factor may not be optimal for all contexts.

3. **Are pre-match probabilities stationary across patch cycles?** Major patches can fundamentally change team strength (e.g., a patch that nerfs a team's signature champion). If model calibration degrades sharply after patches, we may need patch-aware retraining or shorter training windows.

4. **How much does roster data improve predictions beyond Elo alone?** Roster features (continuity, substitutions, days together) are theoretically important but practically challenging — roster data may be unreliable, late, or unavailable pre-match. If roster features add noise rather than signal, they degrade rather than improve the model.

5. **What is the right conservatism parameter (λ, δ) for uncertainty-adjusted probabilities?** The formula p_conservative = p_model - λ·σ - δ·disagreement is a proposal. The values of λ and δ will significantly affect whether we trade at all and how large positions are. These need empirical calibration using walk-forward simulation, not a priori choice.

---

## First Implementation Task

**Recommended first task to delegate to Codex:**

Build Milestone 1: Project skeleton and configuration.

Concrete deliverable:
- Create `pyproject.toml` with project metadata, Python ≥3.10, and dependencies: pydantic-settings, scikit-learn, pandas, numpy, SQLAlchemy, pytest, ruff, mypy.
- Create `src/prediction_bot/` package with `__init__.py`.
- Create `src/prediction_bot/config/settings.py` with pydantic-settings `Settings` class reading from environment variables (data paths, logging level).
- Create `src/prediction_bot/config/paths.py` with path resolution utilities.
- Create `tests/` directory with `conftest.py` and a placeholder test.
- Create `.env.example` documenting required environment variables (no real values).
- Ensure `pip install -e .` works, `pytest` runs, `ruff check src/` passes.

Context for the subagent:
- The project is called `prediction_bot`.
- The package name is `prediction_bot`.
- Minimum Python version is 3.10.
- Use `pyproject.toml` (not setup.py or setup.cfg).
- Settings should follow pydantic-settings patterns: class with fields, loaded from env, with `.env` file support.
- Paths: `DATA_DIR` (default `./data`), `RAW_DIR`, `PROCESSED_DIR`, `FEATURES_DIR`, `MODELS_DIR`, `SNAPSHOTS_DIR`, `RESULTS_DIR`.
- Test with `pytest`, lint with `ruff`, type-check with `mypy`.

---

## Constraints (Non-Negotiable)

- Do not place real trades. Ever.
- Do not create or request production API credentials.
- Do not commit secrets. `.env` is gitignored. Use `.env.example` for documentation.
- Do not claim an edge before it is empirically demonstrated.
- Do not use random train-test splitting. Temporal splits only.
- Do not use future match, roster, patch, or market information in features or training.
- Prefer simple and auditable designs.
- Mark uncertain assumptions explicitly.
- This document is the source of truth for project-level constraints.

---

## Repository

```
prediction_bot/
├── PROJECT.md              ← this file
├── README.md
├── pyproject.toml          ← to be created (Milestone 1)
├── .gitignore
├── .env.example            ← to be created (Milestone 1)
├── docs/
│   ├── architecture.md
│   ├── research_plan.md
│   └── task_plan.md
├── src/
│   └── prediction_bot/     ← to be built (Milestones 1-12)
│       ├── config/
│       ├── data/
│       ├── features/
│       ├── models/
│       ├── calibration/
│       ├── kalshi/
│       ├── strategy/
│       ├── hermes/
│       ├── evaluation/
│       └── scripts/
├── tests/                  ← to be built (Milestones 1-12)
└── data/                   ← gitignored
```

---

## Status

| Milestone | Status | Date |
|-----------|--------|------|
| 1. Project skeleton | not started | — |
| 2. Data ingestion | not started | — |
| 3. Teams & rosters | not started | — |
| 4. Elo baseline | not started | — |
| 5. Walk-forward eval | not started | — |
| 6. Logistic regression | not started | — |
| 7. Kalshi client | not started | — |
| 8. Event matching | not started | — |
| 9. Snapshot collection | not started | — |
| 10. Paper trading | not started | — |
| 11. Hermes layer | not started | — |
| 12. Attribution reports | not started | — |
