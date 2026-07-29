"""
Paper trading pipeline v2.

Modules:
  scanner    — full pagination, discovery ledger
  filter     — market classification with rejection reasons
  strategy   — prediction, Elo lookup, Hermes review
  risk       — position limits, edge thresholds, dedup
  executor   — dry-run order simulation
  order_client — Kalshi API (disabled by default)
  pipeline   — end-to-end orchestration
"""
