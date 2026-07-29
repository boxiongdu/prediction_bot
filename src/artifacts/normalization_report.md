# Kalshi Market Normalization Report

Generated: 2026-07-28T20:33:20.081933+08:00

## Summary

- Total markets fetched: 2500
- Sports markets: 87
- Esports markets: 87
- Markets with metadata gaps: 84
- Unclassified (ambiguous) markets: 0

### Metadata Gap Breakdown

- zero_volume: 84
- zero_open_interest: 84

## Markets by Contract Type

- map_winner: 52
- match_winner: 30
- total_maps: 5

## Markets by Sport

- esports: 87

## Markets by Game

- dota2: 36
- league-of-legends: 35
- valorant: 12
- cs2: 4

## Spread Statistics

- Count: 87.0
- Mean: 0.6028
- Median: 0.7300
- 25th percentile: 0.2600
- 75th percentile: 0.9300
- Min: 0.0300
- Max: 0.9300

## Limitations

- Uses normalize_contract() combining ticker prefix, rules_primary, and title.
- Non-sports markets (weather, commodities, politics) are filtered by is_esports_market().
- Contract type classification is driven by ticker prefix (100% coverage for known).