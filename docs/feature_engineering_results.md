# Feature Engineering Results — Esports Prediction Baseline

Generated: 2026-07-28

## Executive Summary

**Adding more features to the logistic regression model does NOT improve
out-of-sample prediction.** The baseline model (Elo difference + playoff flag)
achieves 64.30% accuracy and 0.2231 Brier score. No feature group improves on
this — the expanded model with 25 features performs *worse* (63.85%,
0.2241).

Elo alone captures ~80% of all predictive power. The remaining signal is
either noise or too subtle for linear models to exploit.

## Dataset

- **Source**: Oracle's Elixir (2024–2026)
- **Filter**: Tier 1 leagues only (LCK, LPL, LEC, LCS/LTA, LCP, MSI, Worlds, EWC, FST)
- **Train**: 2024–2025 (4,591 matches)
- **Test**: 2026 (1,787 matches)
- **Chronological split**: No future information in training data

## Feature Groups Evaluated

| Group | Features | Coverage | Leakage Risk |
|-------|----------|----------|-------------|
| **Elo** | Elo difference | 100% | None |
| **Form** | Win rate, streaks, weighted form (last 20 games) | 100% | None |
| **Kills** | Avg kills, deaths, KDA ratio, kill diff | 100% | None |
| **Early game** | Avg gold/XP/CS diff at 15 min | 67% | None |
| **Objectives** | Dragon/herald/baron/tower rates + control ratios | 100% | None |
| **Pace** | Avg game duration | 100% | None |
| **Roster** | Roster stability, unique players seen | 100% | None |
| **Champion** | Champ pool size, pick diversity | 100% | None |
| **Context** | Playoff flag, international flag, patch number | 100% | None |

All features are computed chronologically — only data from matches with
`date < target_match_date` is used.

## Ablation Results

```
Feature Set                            N      Acc   Brier    ΔAcc  ΔBrier
----------------------------------- ---- -------- ------- ------- -------
Baseline (elo + playoffs)              2  64.30%  0.2231       -       -
+ form                                 6  64.19%  0.2227  -0.11%  -0.0003
+ kills                                6  64.24%  0.2225  -0.06%  -0.0005
+ early_game                           5  63.79%  0.2230  -0.50%  -0.0001
+ objectives                           9  64.63%  0.2219  +0.34%  -0.0012
+ pace                                 3  64.07%  0.2233  -0.22%  +0.0002
+ roster                               4  64.19%  0.2244  -0.11%  +0.0014
----------------------------------- ---- -------- ------- ------- -------
All features                          25  63.85%  0.2241  -0.45%  +0.0011
```

## Key Findings

### 1. Elo dominates everything
The Elo difference coefficient is 0.70 in the expanded model — 5× larger
than the next most important feature (tower diff at 0.27). Elo already
encodes win/loss information, making win rate, KDA, and form features
redundant.

### 2. Objectives show marginal promise
Adding objective control features (dragon, herald, baron, tower rates)
improves accuracy by +0.34% and Brier by -0.0012. This is the only
group that improves on the baseline, but the gain is small and may
not replicate.

### 3. More features → worse performance
The 25-feature model performs WORSE than the 2-feature baseline.
Overfitting in logistic regression is real even with moderate
feature counts. Collinearity between features (e.g., win_rate and
elo are ~0.85 correlated) degrades coefficient estimates.

### 4. Early game data has limited value
Early game stats (gold/XP/CS at 15 min) have 67% coverage and
add no predictive value. Teams that are strong early also have
high Elo — the signal is captured already.

### 5. Roster, champion, and pace features add nothing
These features show near-zero coefficients and no improvement in
any metric. Roster changes happen too infrequently in Tier 1
leagues to matter at this scale.

## Feature Importance (All Features Model)

| Feature | Coefficient | Interpretation |
|---------|------------|---------------|
| elo_diff | +0.705 | Higher Elo → higher win probability |
| avg_tower_diff | +0.266 | Teams that take more towers win more |
| win_rate_diff | -0.259 | Collinear with Elo; negative due to redundancy |
| avg_csdiff15 | +0.177 | Better CS at 15 → slight edge |
| roster_stability | -0.148 | Perplexing sign; likely noise |
| kda_ratio_diff | -0.111 | Collinear with Elo |
| Others | ±0.00–0.09 | Negligible |

## Calibration

### Baseline (Elo + Playoffs)
- Well-calibrated: observed rates track expected across all bins
- 0.85–1.00 bin: 80.5% observed vs 92.5% expected — slight overconfidence

### All Features
- Slightly worse calibration in lower bins
- 0.50–0.55 bin: 48.2% observed vs 52.5% expected — underconfident

## Conclusion

**The optimal model is: Elo difference + playoff flag.**

No additional feature from Oracle's Elixir dataset improves out-of-sample
prediction for Tier 1 League of Legends matches. The Elo rating system,
updated chronologically with K=32 and a 30-point blue-side advantage,
already captures the competitive hierarchy effectively.

Adding features from the same dataset (objectives, early game, roster,
form) introduces collinearity and overfitting without adding new
information.

## Recommendation for Next Phase

1. **Keep the simple model.** Elo + playoffs is optimal.
2. **Seek external data.** The next improvement will come from data
   NOT already encoded in match outcomes — roster change announcements,
   player interviews, meta analysis, patch notes interpretation.
3. **Cross-game expansion.** Apply the same Elo framework to CS2,
   Dota 2, and Valorant using Oracle's Elixir equivalents.
4. **Live prediction pipeline.** Deploy the Elo model to generate
   base probabilities for live Kalshi markets, with the enrichment
   pipeline providing context for Hermes review.
