# Kalshi Esports Backtest — Dataset Quality Report

Generated: 2026-07-28
Source: `/historical/markets?limit=1000&mve_filter=exclude` (10 pages)

---

## Summary

| Metric | Count |
|--------|-------|
| Total historical markets fetched | 10,000 |
| Esports markets (all types) | 64 |
| Match-winner contracts | 50 |
| Map-winner contracts | 12 |
| Total-maps contracts | 2 |
| Prediction-ready (match_winner) | 50 |
| Data quality issues | 0 |

## Contract Types

| Type | Count |
|------|-------|
| match_winner | 50 |
| map_winner | 12 |
| total_maps | 2 |

## By Game

| Game | Count |
|------|-------|
| league-of-legends | 34 |
| cs2 | 22 |
| valorant | 8 |

## By Game × Contract Type

| Game | match_winner | map_winner | total_maps |
|------|-------------|-----------|------------|
| league-of-legends | 28 | 6 | 2 |
| cs2 | 20 | 0 | 0 |
| valorant | 2 | 6 | 0 |

## Time Range

All 64 markets from May 2026. The `/markets?status=settled` endpoint
only returned markets from July 2026; `/historical/markets` with
`mve_filter=exclude` reaches further back.

## Settlement Leak Check

50 prediction packets generated. All passed:
- No `result` key in packets (0/50)
- No `settlement_value_dollars` in packets (0/50)
- No `settlement_ts` in packets (0/50)
- No `yes_sub_title` in packets (0/50) — stripped before generation
- No "settlement" in research prompts (0/50)

## Data Completeness (50 match_winner markets)

| Field | Coverage |
|-------|----------|
| contract_type | 50/50 (100%) |
| sport | 50/50 (100%) |
| game | 50/50 (100%) |
| participants | 50/50 (100%) |
| tournament | 50/50 (100%) |
| result (yes/no) | 50/50 (100%) |
| close_time | 50/50 (100%) |

## Non-Match-Winner Markets (excluded from prediction)

14 markets excluded from prediction packets (12 map_winner + 2 total_maps).
These are saved in `settled_esports.json` for future expansion but are not
part of the match_winner-only backtest.

## Differences from Previous Fetch

| Metric | v1 (/markets) | v2 (/historical) |
|--------|--------------|-------------------|
| Esports found | 23 | 64 |
| Match winner | 23 | 50 |
| Games | CS2+LOL+Valorant | CS2+LOL+Valorant |
| Time range | July 2026 | May 2026 |
| Quality issues | 3 (team names, parse) | 0 |
