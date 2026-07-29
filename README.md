# prediction_bot

Independent esports probability-modeling and value-trading research system for Kalshi.

**Paper trading only. No real money is ever committed. No orders are ever placed.**

## What This Does

1. Downloads and classifies currently open Kalshi esports markets.
2. Extracts executable prices (bid/ask) from order book snapshots.
3. Builds calibrated pre-match probability models for esports match outcomes (coming in later milestones).
4. Identifies positive expected-value opportunities (coming in later milestones).
5. Records paper-trading decisions with full post-settlement attribution (coming in later milestones).

## Status

- [x] Milestone 1: Project skeleton and configuration
- [ ] Milestone 2: Historical data ingestion
- [ ] Milestones 3–12: See [docs/task_plan.md](docs/task_plan.md)

## Setup

### Prerequisites

- Python 3.10 or later
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install

```bash
# Clone the repository
git clone <repo-url>
cd prediction_bot

# Create a virtual environment and install
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Or with plain pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Environment Variables

Copy `.env.example` to `.env` and fill in any values:

```bash
cp .env.example .env
```

For the esports market audit (public data only), no Kalshi API key is required. The client will attempt unauthenticated access first. For authenticated access, set `KALSHI_API_KEY` in `.env`.

**Do not commit `.env` to version control.** It is already in `.gitignore`.

### Running Tests

```bash
pytest
```

### Linting and Type Checking

```bash
ruff check src/ tests/
mypy src/
```

## Running the Esports Market Audit

The audit script downloads currently open Kalshi markets, identifies esports-related ones, classifies them by game, and produces CSV/JSON/Markdown reports.

```bash
# After installing:
prediction-bot

# Or directly:
python -m prediction_bot.scripts.audit
```

### Expected Outputs

Files are written to the `artifacts/` directory:

| File | Description |
|------|-------------|
| `artifacts/esports_markets.csv` | All identified esports markets with ticker, game, spread, volume, etc. |
| `artifacts/esports_markets.json` | Full audit including summary statistics and raw entries. |
| `artifacts/feasibility_report.md` | Human-readable summary with counts, spread/volume statistics, and liquidity assessment. |

### What the Audit Measures

- Number of esports markets vs. total markets
- Markets by game (League of Legends, CS2, VALORANT, Dota 2, etc.)
- Markets by type (match winner, series winner, tournament winner, etc.)
- Spread distribution (median, percentiles)
- Volume and open interest distribution
- Markets with missing or ambiguous metadata tags
- Markets whose titles could not be classified to a specific game

## Current Limitations

- This project does NOT place trades — real or paper.
- No Elo rating system has been implemented yet.
- No Kelly sizing or position management has been implemented.
- No model training infrastructure has been built.
- Esports detection uses keyword matching and may miss markets with non-standard naming.
- Game classification may misclassify ambiguous titles (e.g., a generic "Team A vs Team B" with no game context).
- Order book depth retrieval is available but not yet integrated into the automated audit.
- Historical data ingestion (Oracle's Elixir, Leaguepedia) is not yet implemented.

## Project Documentation

| Document | Purpose |
|----------|---------|
| [PROJECT.md](PROJECT.md) | Project overview, architecture decisions, constraints |
| [docs/architecture.md](docs/architecture.md) | System design, package structure, data schema |
| [docs/research_plan.md](docs/research_plan.md) | Hypothesis, MVP, modeling roadmap, validation framework |
| [docs/task_plan.md](docs/task_plan.md) | 12-milestone implementation plan |

## Constraints (Non-Negotiable)

- Do not place real trades. Ever.
- Do not commit secrets (`.env` is gitignored).
- Do not claim an edge before it is empirically demonstrated.
- Do not use random train-test splitting (temporal walk-forward only).
- Do not use future match, roster, patch, or market information in features or training.
- Prefer simple and auditable designs.

## License

MIT
