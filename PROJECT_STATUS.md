# Prediction Bot Status

## Completed
- Kalshi API integration
- RSA authentication
- Market audit pipeline
- Esports discovery
- MVE exclusion

## Current architecture

Kalshi API
 -> Market normalization
 -> Event grouping
 -> Prediction agent
 -> EV calculator
 -> Paper trading

## Next milestone

Build DeepSeek prediction agent:
- structured JSON output
- probability estimate
- confidence
- abstain option

Build paper trading engine:
- store predictions
- track settlement
- calculate Brier score
- calculate P&L

## Current limitation

Need better event normalization:
- group participant contracts
- enrich event metadata
- distinguish game/map/series markets