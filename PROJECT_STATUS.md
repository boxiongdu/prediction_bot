# Prediction Bot Status

> Updated 2026-10-21. This file previously described the paper-trading research prototype.
> The live system is the LoL match-winner bot — see [README.md](README.md) and [docs/architecture.md](docs/architecture.md).

## Live (deployed)

- LoL match-winner trading bot (`src/prediction_bot/trading/match_winner_bot.py`) — trades Kalshi `KXLOLGAME`
- Random Forest + Platt-calibrated model (`models/recency_model`), shadow baseline (`models/baseline_model`)
- Kalshi Trade API v2 integration (RSA-PSS signing), market discovery, order execution, settlement from real fills
- Fractional-Kelly risk engine with drawdown tiers
- SQLite persistence + restart recovery
- Discord alerts + daily summary via Hermes gateway
- Deployed as `lol-match-bot.service` (systemd)

## Shadow / not live

- Map-winner "Model D" (48 features) and map bot (`research/map_winner_v2/`, `KXLOLMAP`) — not deployed
- "Unified Platform v2" (`lol-match-platform.service`) — disabled shadow mode
- Paper prediction tracker (`src/prediction_bot/tracking/`, `scripts/run_tracking.py`) — independent, non-live

## Superseded / not built (from the original 12-milestone plan)

- Logistic-regression model → replaced by Random Forest + Platt
- Hermes LLM decision layer → replaced by deterministic risk gates
- Snapshot-collection store → replaced by direct live market reads
- Formal post-settlement attribution reports → not built (partial)

## Out of scope here

- Polymarket→Kalshi copy-trading system and other strategies
