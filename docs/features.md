# Feature Documentation — Esports Prediction

## Architecture

All features are computed by `src/prediction_bot/esports/features/engine.py`.

The `FeatureStore` class maintains rolling per-team statistics and updates
chronologically after each match. Features for match N are computed from
matches 0..N-1 only — **zero data leakage**.

## Feature Catalog

### 1. Elo Rating (`elo`, `elo_diff`)
- **Definition**: Rolling Elo rating, K=32, initial=1500, blue side +30 home advantage
- **Calculation**: Updated after each match: `new = old + K * (actual - expected)`
- **Leakage risk**: None — computed before the match
- **Intuition**: Higher Elo → stronger team. Blue side gets a small boost.

### 2. Win Rate (`win_rate`, `win_rate_diff`)
- **Definition**: Win rate over last 20 games
- **Calculation**: `wins_in_window / total_games_in_window`
- **Leakage risk**: None
- **Intuition**: Recent results should predict future results
- **Status**: Collinear with Elo (r≈0.85), adds no unique value

### 3. Win/Loss Streaks (`win_streak`, `loss_streak`)
- **Definition**: Consecutive wins or losses in most recent games
- **Calculation**: Count from most recent game backward until streak breaks
- **Leakage risk**: None
- **Intuition**: Momentum effects
- **Status**: Negligible coefficient, no improvement

### 4. Weighted Win Rate (`weighted_win_rate`)
- **Definition**: Exponentially weighted win rate (recent games matter more)
- **Calculation**: Σ(w_i × result_i) where w_i = exp(i/max_games)
- **Leakage risk**: None
- **Status**: Collinear with raw win rate, no unique value

### 5. Kill Metrics (`avg_kills`, `avg_deaths`, `kda_ratio`, `kill_diff`)
- **Definition**: Rolling averages of team kills, deaths, and ratios
- **Calculation**: Mean over last 20 games
- **Leakage risk**: None
- **Intuition**: Teams with higher kill differentials should be stronger
- **Status**: Collinear with Elo, no improvement

### 6. Game Pace (`avg_duration`)
- **Definition**: Average game duration over last 20 games
- **Calculation**: Mean of `gamelength` column
- **Leakage risk**: None
- **Intuition**: Fast-paced teams may have different matchup dynamics
- **Status**: Near-zero coefficient

### 7. Early Game Stats (`avg_golddiff15`, `avg_xpdiff15`, `avg_csdiff15`)
- **Definition**: Average gold/XP/CS difference at 15 minutes
- **Calculation**: Mean of per-game differences (67% coverage, NaN→0)
- **Leakage risk**: None — these are from PAST games only
- **Intuition**: Strong early-game teams convert leads to wins
- **Status**: No improvement; 67% coverage limits signal

### 8. Objective Control (`first_dragon_rate`, `first_herald_rate`, etc.)
- **Definition**: Rate at which team secures first objectives
- **Calculation**: Count of first-objective events / total games
- **Leakage risk**: None
- **Intuition**: Objective-focused teams are more disciplined
- **Status**: Marginal improvement (+0.34% acc); only group that helps

### 9. Dragon/Baron Control (`dragon_control`, `baron_control`)
- **Definition**: Fraction of total dragons/barons secured
- **Calculation**: `team_dragons / (team_dragons + opp_dragons)`
- **Leakage risk**: None
- **Intuition**: Better objective control → stronger macro play
- **Status**: Small positive coefficient but no unique improvement

### 10. Tower Differential (`avg_tower_diff`)
- **Definition**: Average tower advantage per game
- **Calculation**: Mean of `towers - opp_towers`
- **Leakage risk**: None
- **Intuition**: Tower leads correlate with winning
- **Status**: Second most important feature after Elo (coef=0.27)

### 11. Roster Stability (`roster_stability`, `roster_size`)
- **Definition**: Fraction of consecutive games with same 5 players
- **Calculation**: Based on player IDs from Oracle's Elixir
- **Leakage risk**: None
- **Intuition**: Stable rosters perform more consistently
- **Status**: No improvement; Tier 1 rosters are mostly stable

### 12. Champion Pool (`champ_pool_size`, `champ_diversity`)
- **Definition**: Number of unique champions and entropy of pick distribution
- **Calculation**: From per-player champion picks in past games
- **Leakage risk**: None
- **Intuition**: Teams with wider champion pools are harder to draft against
- **Status**: Not implemented (needs player-level data join)

### 13. Tournament Context (`playoffs`, `is_international`, `patch_num`)
- **Definition**: Binary flags for playoff matches and international tournaments
- **Calculation**: From match metadata
- **Leakage risk**: None (known before match)
- **Intuition**: Different stakes and meta contexts matter
- **Status**: Playoff flag already in baseline; others add no value

## Feature Selection Summary

**Keep (baseline):**
- `elo_diff` — dominates all other features
- `playoffs` — small but consistent benefit

**Consider (marginal):**
- `first_dragon_rate_diff`, `first_tower_rate_diff`, `dragon_control_diff`, `baron_control_diff`, `avg_tower_diff_diff` — objectives group

**Drop:**
- All form features (collinear with Elo)
- All kill features (collinear with Elo)
- Early game features (low coverage, no signal)
- Roster features (too stable in Tier 1)
- Pace features (no signal)
- Champion pool (not implemented)
