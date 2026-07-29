# Oracle's Elixir League of Legends Dataset Report

Generated: 2026-07-28

## Source

Oracle's Elixir (oracleselixir.com) — the definitive public dataset for
professional League of Legends esports statistics. Downloaded as CSV exports
covering 2024–2026 (partial).

## Files

| File | Rows | Unique Games | Date Range |
|------|------|-------------|------------|
| `2024_LoL_esports_match_data_from_OraclesElixir.csv` | 122,340 | 10,195 | 2024-01-01 → 2024-12-08 |
| `2025_LoL_esports_match_data_from_OraclesElixir.csv` | 120,492 | 10,041 | 2025-01-11 → 2025-12-29 |
| `2026_LoL_esports_match_data_from_OraclesElixir.csv` | 78,720 | 6,560 | 2026-01-08 → 2026-07-28 |

**Total: 321,552 rows across 26,796 unique games.**

## Format

Each row represents **one player's performance in one game**. A standard game
produces 10 rows (5 players per team). Best-of-3 and best-of-5 series produce
30–50 rows.

All three files share identical schema: **165 columns**.

## Column Categories

### 1. Identifiers & Metadata
| Column | Type | Description |
|--------|------|-------------|
| `gameid` | str | Unique game identifier (e.g., `LOLTMNT05_171038`) |
| `datacompleteness` | str | `complete` or `partial` |
| `url` | str | Source URL on Oracle's Elixir |
| `league` | str | League abbreviation (LCK, LPL, LEC, etc.) |
| `year` | int | Calendar year |
| `split` | str | Split name (Spring, Summer, Split 1, etc.) |
| `playoffs` | int | 1 = playoff game, 0 = regular season |
| `date` | datetime | Match timestamp (UTC) |
| `game` | int | Game number in series (1, 2, 3, ...) |
| `patch` | str | Game patch version (e.g., `16.10`) |

### 2. Team & Player
| Column | Type | Description |
|--------|------|-------------|
| `teamname` | str | Team name (e.g., `T1`, `Gen.G`) |
| `teamid` | str | Team ID |
| `playername` | str | Player handle |
| `playerid` | str | Player unique ID |
| `position` | str | Role: top, jng, mid, bot, sup |
| `side` | str | Blue or Red |
| `participantid` | int | In-game participant number (1–10) |

### 3. Draft (Champion Select)
| Column | Type | Description |
|--------|------|-------------|
| `champion` | str | Champion picked by this player |
| `ban1`–`ban5` | str | Team's 5 bans |
| `pick1`–`pick5` | str | Team's 5 picks (ordered) |
| `firstPick` | int | 1 = team had first pick |

### 4. Match Result
| Column | Type | Description |
|--------|------|-------------|
| `result` | int | 1 = win, 0 = loss |
| `gamelength` | int | Game duration in seconds |

### 5. Player Performance (per-game)
| Column | Type | Description |
|--------|------|-------------|
| `kills`, `deaths`, `assists` | int | K/D/A |
| `teamkills`, `teamdeaths` | int | Team total kills/deaths |
| `doublekills`–`pentakills` | int | Multikill counts |
| `firstblood`, `firstbloodkill`, `firstbloodassist`, `firstbloodvictim` | int | First blood flags |
| `damagetochampions` | int | Total damage to champions |
| `dpm` | float | Damage per minute |
| `damageshare` | float | Share of team's damage |
| `damagetakenperminute` | float | Damage taken per minute |
| `damagemitigatedperminute` | float | Damage mitigated per minute |
| `damagetotowers` | int | Damage to towers |
| `totalgold` | int | Gold at game end |
| `earnedgold` | int | Gold earned |
| `earned gpm` | float | Gold per minute |
| `earnedgoldshare` | float | Share of team's gold |
| `goldspent` | int | Gold spent on items |
| `total cs` | int | Total creep score |
| `minionkills` | int | Lane minions killed |
| `monsterkills` | int | Jungle monsters killed |
| `monsterkillsownjungle` | int | Own-jungle monsters |
| `monsterkillsenemyjungle` | int | Enemy-jungle monsters |
| `cspm` | float | CS per minute |

### 6. Vision
| Column | Type | Description |
|--------|------|-------------|
| `wardsplaced` | int | Wards placed |
| `wpm` | float | Wards per minute |
| `wardskilled` | int | Enemy wards killed |
| `wcpm` | float | Ward clears per minute |
| `controlwardsbought` | int | Control wards purchased |
| `visionscore` | int | Vision score |
| `vspm` | float | Vision score per minute |

### 7. Objectives
| Column | Type | Description |
|--------|------|-------------|
| `firstdragon`, `firstherald`, `firstbaron`, `firsttower`, `firstmidtower`, `firsttothreetowers` | int | First-to-achieve flags |
| `dragons`, `opp_dragons` | int | Dragons slain / opponent dragons |
| `elementaldrakes`, `opp_elementaldrakes` | int | Elemental drakes |
| `infernals`, `mountains`, `clouds`, `oceans`, `chemtechs`, `hextechs` | int | Drake types |
| `elders`, `opp_elders` | int | Elder dragons |
| `heralds`, `opp_heralds` | int | Rift Heralds |
| `void_grubs`, `opp_void_grubs` | int | Void Grubs |
| `barons`, `opp_barons` | int | Baron Nashors |
| `atakhans`, `opp_atakhans` | int | Atakhans |
| `towers`, `opp_towers` | int | Towers destroyed |
| `turretplates`, `opp_turretplates` | int | Turret plates taken |
| `inhibitors`, `opp_inhibitors` | int | Inhibitors destroyed |

### 8. Timeline Snapshots (at 10, 15, 20, 25 minutes)
For each timestamp:

| Column | Description |
|--------|-------------|
| `goldat{N}` | Gold at N minutes |
| `xpat{N}` | XP at N minutes |
| `csat{N}` | CS at N minutes |
| `opp_goldat{N}` | Opponent gold at N minutes |
| `opp_xpat{N}` | Opponent XP at N minutes |
| `opp_csat{N}` | Opponent CS at N minutes |
| `golddiffat{N}` | Gold difference |
| `xpdiffat{N}` | XP difference |
| `csdiffat{N}` | CS difference |
| `killsat{N}`, `assistsat{N}`, `deathsat{N}` | K/D/A at N minutes |

### 9. Team-Level Aggregates
| Column | Type | Description |
|--------|------|-------------|
| `team kpm` | float | Team kills per minute |
| `ckpm` | float | Combined kills per minute |
| `gspd` | float | Gold spent percentage difference |
| `gpr` | float | Gold percentage rating |

## Leagues Covered

### Tier 1 (Major) — Well Represented
| League | 2024 Games | 2025 Games | 2026 Games |
|--------|-----------|-----------|-----------|
| LCK (Korea) | 482 | 555 | 349 |
| LPL (China) | 717 | 805 | 453 |
| LEC (Europe) | 294 | 306 | 260 |
| LCS (NA, 2024/2026) | 192 | — | 166 |
| LTA / LTA N / LTA S (Americas, 2025) | — | 476 | — |
| LCP (Pacific, 2025-26) | — | 291 | 211 |
| MSI (Mid-Season) | 78 | 80 | 71 |
| WLDs (Worlds) | 132 | 96 | — |
| EWC (Esports World Cup) | 19 | 33 | 232 |
| FST (First Stand) | — | 35 | 45 |

### Tier 2/3 (Regional) — Also Available
CBLOL, VCS, PCS, LJL, LCO, TCL, LLA, NACL, EBL, LFL, PRM, NLC, and many
more regional/amateur leagues. Total distinct leagues: 53 (2024), 45 (2025),
39 (2026).

## Key Strengths

1. **Per-player granularity** — individual player performance, champion picks,
   role assignments, roster composition.
2. **Temporal precision** — exact match dates, enabling strict timestamp-based
   feature engineering and leakage prevention.
3. **Rich draft data** — full ban/pick order, first pick side, champion
   selections for each player.
4. **Timeline snapshots** — gold/XP/CS at 10/15/20/25 min, enabling early-game
   and mid-game analysis.
5. **Objective control** — dragons, barons, heralds, towers, inhibitors with
   first-to-achieve flags.
6. **Multi-year coverage** — 2024–2026 enables trend analysis and form tracking.
7. **Tier 1 coverage** — all major leagues (LCK, LPL, LEC, LCS/LTA, MSI,
   Worlds) are well-represented.

## Limitations

1. **Player IDs inconsistent across years** — `playerid` values may change
   between seasons, requiring name-based fuzzy matching for cross-year tracking.
2. **Partial data** — 2024: 13.6% partial, 2025: 8.2% partial, 2026: 6.9%
   partial. Partial rows may lack timeline snapshots or gold data.
3. **No item builds** — champion items purchased are not recorded.
4. **No rune/mastery data** — rune pages and summoner spells not included.
5. **Roster changes not explicit** — must infer roster changes from player
   appearance/disappearance in team's games.
6. **Only LoL** — dataset covers League of Legends only. No CS2, Dota 2, or
   Valorant data for cross-game predictions.
7. **No Kalshi integration** — team names from Oracle's Elixir may differ from
   Kalshi market names (e.g., `Gen.G` vs `Gen G`, `T1` vs `SK Telecom T1`).
8. **2026 is partial year** — data ends July 2026.

## Useful Columns for Prediction Features

**Must-use (pre-match context):**
- `date` — temporal anchor for leakage prevention
- `teamname` — team identification
- `playername` — player/roster identification
- `position` — role context
- `league` — league tier classification
- `playoffs` — match importance flag
- `patch` — meta context
- `side` — blue/red side advantage

**For form/performance features (from past games only):**
- `result` — win/loss (the target variable for past games)
- `kills`, `deaths`, `assists` — player performance
- `teamkills`, `teamdeaths` — team performance
- `goldat15`, `golddiffat15`, `csdiffat15` — early-game dominance
- `dragons`, `barons`, `heralds`, `firsttower` — objective control
- `damageshare`, `earnedgoldshare` — carry performance
- `champion` — champion pool and meta picks
- `ban1`–`ban5` — draft targeting patterns

**NOT useful for prediction (post-game only):**
- `gamelength` — not known before match
- `damagetochampions`, `visionscore` — post-game aggregates
- `result` — the target; must not leak into features
