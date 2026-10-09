# Data engineering decision memo

## Decision and scope

Use Football-Data's English Premier League (`E0`) and Championship (`E1`) season CSVs. Forecast EPL only; Championship history supports a tested promotion adjustment, not an assumption that the leagues are equally strong. No bookmaker odds or public opinion enter features or model evaluation.

| Season | Role |
|---|---|
| 2022/23 | Warm-up; initialize historical ratings |
| 2023/24 | Initial model fitting |
| 2024/25 | Development and model-selection validation |
| 2025/26 | Sealed chronological test, accessed only after selection freezes |
| 2026/27 | Current-season sequential updates and prospective forecasts |

Raw downloading does not authorize examining held-out performance or tuning from held-out outcomes. Default development commands should load only 2223/2324/2425.

## Sources checked

- Dataset index: https://www.football-data.co.uk/englandm.php (retrieved 2026-10-09). EPL and Championship links exist for all requested seasons; descriptions cover full-time/half-time results, statistics and odds.
- Field definitions: https://www.football-data.co.uk/notes.txt (retrieved 2026-10-09). Defines Div, Date, Time, HomeTeam/AwayTeam, FTHG/FTAG/FTR, HS/AS and HST/AST. Statistics can be unavailable.
- CSV pattern: `https://www.football-data.co.uk/mmz4281/{season}/{division}.csv`.

Actual download success, counts, missing statistics, fetch timestamps, URLs and SHA-256 hashes are in `data/raw/manifest.json`. Failed downloads are explicitly recorded and return a nonzero command status. Successful downloads retain immutable content-addressed raw snapshots. A newer fetch creates a new manifest snapshot and replaces the convenience latest CSV only after validation. Downloaded originals contain bookmaker columns because those are part of the original source; normalized model-facing data excludes them through an explicit column whitelist.

## Validation and normalization

`normalize_matches` requires fixture identifiers, date, time and result fields. It rejects missing kickoff fields, bad dates, inconsistent result/goal labels, negative or fractional goal/stat counts, duplicate home-away pairings in one league-season, division mismatches, teams playing themselves, and division errors. Contradictory optional shot statistics are quarantined rather than blocking otherwise valid goals. Missing optional shot statistics remain missing, never implicit zeros. Fully unplayed rows are excluded from historical training; partially populated results fail validation. Team names are whitespace-normalized but not fuzzy-matched. That avoids silently merging distinct clubs. External market name aliases remain a future explicit mapping.

`load_matches(data_dir, seasons)` requires both E0 and E1 for every requested season. Its normalized columns are `season`, `division`, `home_team`, `away_team`, `kickoff_utc`, `forecast_utc`, `available_utc`, `home_goals`, `away_goals`, `result`, `home_shots`, `away_shots`, `home_sot`, `away_sot`, `home_shots_invalid`, `away_shots_invalid`. Results are H/D/A. Dataframe provenance records raw file hashes.

## Two-hour cutoff and point-in-time limitations

Forecast cutoff is two hours before kickoff. Historical result/stat availability is approximated by kickoff plus **24 hours**, not the final whistle. Feature code must enforce `available_utc <= forecast_utc` before using previous match results, so simultaneous matches cannot influence one another. The 24-hour delay is deliberately conservative but cannot certify original publication timing.

The source notes define kickoff time but do **not document its timezone**. This implementation explicitly assumes `Europe/London` for English fixtures, converts to UTC with daylight-saving rules, and rejects ambiguous/nonexistent local times. The assumption must be independently verified before production operation. Dates are parsed explicitly in day/month order.

These present-day season files are retrospectively revised records. They do not provide original publication timestamps, past file vintages, or kickoff rescheduling histories. Historical evaluations are therefore **retrospective simulations under stated timing assumptions**, not proven point-in-time live replays. Adding an availability delay cannot eliminate revision bias. Prospective operation must archive observed-at timestamps and fixture schedule snapshots and distinguish source match time from actual ingestion time. The downloader is not yet a reliable live fixture scheduler or two-hour forecasting service.

## Promotion and feature limitations

2022/23 Championship data supplies prior records for many later promoted clubs; promoted clubs at the very start of warm-up may still lack previous-season history. Use a declared fallback prior, not fabricated history. Championship goals and points need a league-strength adjustment, tested on development seasons. Relegated clubs and clubs entering the Championship from League One also require fallback policies. League-only histories omit cup/European workload; derived rest-day fields would not represent actual rest.

Final goals and shots are permissible only as prior-match observations. Using a match's own final totals to forecast its result is leakage. Raw shots may be missing or source definitions may drift. The proposed first model can use goals-based attack/defence summaries while future shot additions demonstrate improvement independently.

## Open questions

1. Verify source timezone and operational publication delay.
2. Validate promotion adjustment rather than treating it as an established fact.
3. Acquire the inaccessible paper's complete method before claiming replication.
4. Establish a live fixture source and prospective snapshot store before scheduled current-season forecasts.

## Observed development-data anomaly

2024/25 Championship: Burnley–Swansea, 10 November 2024, lists home shots=2 and home shots on target=7. Both home shot fields are set missing and `home_shots_invalid=True`; original bytes remain preserved for inspection. Goal results are retained. Initial models do not consume shot fields. We do not silently invert, impute or repair these figures.
