# Feature Leakage Rules for Esports Prediction

## Core Principle

For a prediction target match at time **T**:

> **All features must be computable using only data available BEFORE time T.**

Information from time ≥ T is FORBIDDEN in any feature used to predict the
outcome of the match at time T.

## Forbidden Data (ALWAYS exclude)

These columns or derived values must NEVER appear in pre-match features:

### From the Target Match Itself
| Column / Value | Reason |
|----------------|--------|
| `result` | The prediction target — including it would be 100% leakage |
| `gamelength` | Only known after the game ends |
| `kills`, `deaths`, `assists` | Post-game player stats |
| `teamkills`, `teamdeaths` | Post-game team stats |
| `damagetochampions`, `dpm`, `damageshare` | Post-game damage stats |
| `totalgold`, `earnedgold`, `earned gpm` | Post-game economy |
| `total cs`, `cspm`, `minionkills`, `monsterkills` | Post-game farming |
| `dragons`, `barons`, `heralds`, `towers`, `inhibitors` | Post-game objectives |
| `wardsplaced`, `visionscore`, `vspm` | Post-game vision |
| `firstblood`, `firstdragon`, `firstbaron`, `firsttower` | In-game events |
| `goldat{10,15,20,25}` and all derivatives | In-game snapshots |
| `pick1`–`pick5` (from target match) | Draft occurs at match start |
| `ban1`–`ban5` (from target match) | Draft occurs at match start |
| Any `opp_*` column | Opponent data from this specific match |

### From Matches AFTER Time T
| Data | Reason |
|------|--------|
| Any row where `date` > T | Future information |
| Tournament results | May not be known yet |
| Roster changes after T | Future team composition |
| Patch changes after T | Meta not yet known |
| Player transfers after T | Future roster information |

## Allowed Data (can use with proper temporal filtering)

### Pre-Match Context (known at time T)
| Data Source | What's Allowed | Temporal Constraint |
|-------------|---------------|---------------------|
| Past match results | Win/loss records | `date < T` |
| Past team performance | Aggregated stats from prior games | `date < T` |
| Past player performance | Individual stats from prior games | `date < T` |
| Head-to-head history | Prior meetings between same teams | `date < T` |
| Current roster | Players active on team at time T | Last seen `date < T` |
| Champion pool (past) | Champions played by each player | `date < T` |
| Draft patterns (past) | Historical ban/pick preferences | `date < T` |
| Side win rates (past) | Blue/red side win rate | `date < T` |
| Patch meta (past) | Win rates on current patch | `date < T` but `patch == current_patch` |
| League tier | Always known | N/A |
| Playoff context | Known from tournament structure | N/A |

### Specific Allowed Features
1. **Recent form (last N games before T):**
   - Win rate
   - Average gold difference at 15
   - Average first tower rate
   - Average dragon control rate
   - Average team KDA ratio

2. **Roster stability:**
   - Number of games played together by current 5
   - Days since last roster change

3. **Head-to-head (all meetings before T):**
   - Historical win rate vs opponent
   - Average gold difference vs opponent
   - Most recent meeting date

4. **League context:**
   - Team's current split win rate
   - Team's playoff qualification status
   - Tournament stage (groups, quarters, etc.)

5. **Side advantage:**
   - Team's blue side win rate (all past games)
   - Team's red side win rate (all past games)

## Temporal Weighting

League of Legends meta evolves rapidly. Not all historical data is equally
predictive.

| Time Window | Weight | Rationale |
|-------------|--------|-----------|
| Same patch | 1.0× | Most predictive — same game version |
| Same split, different patch | 0.7× | Same teams/strats, meta shift |
| Same year, earlier split | 0.5× | Roster may differ, meta different |
| Previous year | 0.3× | Significant roster/meta changes |
| 2+ years ago | 0.1× | Mostly irrelevant except H2H context |

## Implementation Rules

### Rule 1: Timestamp Filter
```python
def get_pre_match_data(df, target_date, team_a, team_b):
    """Return only rows from before target_date."""
    return df[
        (df['date'] < target_date) &
        (df['teamname'].isin([team_a, team_b]))
    ]
```

### Rule 2: Column Blacklist
```python
POST_GAME_COLUMNS = {
    'result', 'gamelength', 'kills', 'deaths', 'assists',
    'teamkills', 'teamdeaths', 'totalgold', 'earnedgold',
    'damagetochampions', 'dpm', 'damageshare',
    'dragons', 'barons', 'heralds', 'towers', 'inhibitors',
    'wardsplaced', 'visionscore', 'vspm',
    'firstblood', 'firstdragon', 'firstbaron', 'firsttower',
    'goldat10', 'goldat15', 'goldat20', 'goldat25',
    'xpat10', 'xpat15', 'xpat20', 'xpat25',
    'csat10', 'csat15', 'csat20', 'csat25',
}
```

### Rule 3: Aggregation Must Use Only Past Data
When computing "last 5 games" or "season-to-date" stats, the cutoff is
strictly `date < T`. The target match itself is NOT included in any
aggregation.

### Rule 4: Verification
Every feature pipeline must include a leakage test:
1. Select a random past match
2. Generate features using only data before that match
3. Assert that no column from the target match appears in feature values
4. Assert that no row with `date >= T` was used in aggregation
