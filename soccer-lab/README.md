# Soccer research agents — V1

EPL pre-match probability research, with Championship histories for promoted teams.
Forecasts target regulation plus stoppage time: home win, draw, away win.
Forecast cutoff is two hours before kickoff. No odds inputs or odds benchmarks.
No trading, news overrides, exits, or portfolio exists in this phase.

## Three roles

| Role | Deterministic work | Astra responsibility |
|---|---|---|
| Data engineer | Download source CSVs; validate results, names, dates and statistics; preserve hashes | Review coverage, anomalies and availability assumptions |
| Model engineer | Replay team states; train goal-based features; compare a fixed candidate set | Explain experiments and propose improvements |
| Supervisor | Independent checks; frozen experiment files; measured report | Audit both memos and report evidence, limitations and proposed process changes |

Only the supervisor's report is intended for routine review. Supporting memos remain inspectable.
The first implementation uses bounded role calls around tested Python functions. It does **not**
let an LLM write and execute arbitrary new modeling code unattended. Candidate selection is automatic;
new feature designs and code changes are reported proposals, not silently applied changes.
No agent can change a match probability or place an order. The older kalshi-astra prototype is separate.

## Run locally

Python 3.11+ (tested on Python 3.12).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python data.py download --data-dir data/raw --seasons 2223 2324 2425
python lab.py run --out runs/my-first-run
```

This Git checkout excludes raw data and working run directories. Download the CSVs with the command above. The earlier ZIP includes source snapshots; reports/ preserves the initial measured result for reference, not as a portable run directory.
The run command refuses to overwrite a directory. It reads only development seasons and writes
data audit, metrics, calibration bins, per-match predictions, source/package provenance, selection,
test-check output, change log, and an offline `SUPERVISOR.md`.

To invoke the three actual Astra roles:

```bash
export OPENAI_API_KEY='set-your-key-locally'
python lab.py run --out runs/astra-review-1 --astra
```

Read `runs/astra-review-1/reviews/SUPERVISOR.md`. Model identifier is `gpt-6-astra`.
The roles receive aggregate experiment evidence, not credentials. Each run makes at most three
API requests, with no automatic retries, 48,000-character input limits and 3,500 output-token caps.
Usage is logged. The $100 monthly ceiling is **not** enforced by this code; configure provider
spending controls and monitor usage before scheduling repeated runs. API account/model access
and authenticated responses have not been tested in this environment. No key is bundled.

## Model experiment

- 2022–23: initialize team states (EPL and Championship).
- 2023–24: fit logistic coefficients on EPL outcomes; other results update team states.
- 2024–25: choose among eight predeclared configurations using EPL log loss.
- 2025–26: separate one-time test command, not accessed for model selection.
- 2026–27: available completed results update strengths for future forecasts.

Candidates: draw-aware Elo control; four smoothed attack/defense features with multinomial logistic
regression. A fixed home/draw/away-frequency benchmark is also reported. Brier uses the sum across
three classes (range 0–2), log loss uses natural logs; accuracy is secondary. Calibration bins are
diagnostics, not a fitted recalibration layer. No statistical significance claim is made.

Team states update as eligible results arrive. Logistic coefficients are frozen during each evaluated
season and refit on earlier seasons for the next one. This distinction means current-season results
influence ratings/features without unrestricted live model redesign.

Championship strength translation is an explicit provisional assumption, not a learned truth.
See MODEL_CARD.md for exact equations and parameters. The ScienceDirect method has not been
verified in full, so neither candidate is labeled a paper replication.

## Open the held-out test deliberately

After inspecting and freezing the development run:

```bash
python data.py download --data-dir data/raw --seasons 2526
python lab.py test --run runs/my-first-run
```

The command requires unchanged source/runtime and development data, uses the existing selected
configuration, and records that the test was opened. It refuses a second opening in that run.
This is an accidental-leakage guard, not an access-control system: anyone editing files could bypass
it. After seeing test performance, changes must be judged against a new future evaluation period.

## Forecast fixtures

Supply a CSV with `season,division,home_team,away_team,kickoff_utc`, using exact source team names,
`division=E0`, season such as `2627`, and ISO UTC kickoff times. No outcome columns needed.
Download current completed history before running:

```bash
python data.py download --data-dir data/raw --seasons 2526 2627
python lab.py forecast --run runs/my-first-run --fixtures fixtures.csv --out forecasts.csv
```

Run at the two-hour cutoff (five-minute tolerance). Earlier requests are rejected; late requests
require `--retrospective` and are labeled simulations. Output includes the cutoff, actual generation
timestamp, last used result availability and H/D/A probabilities. Missing source files fail closed.
Unseen names require an explicit data/mapping review. No fixture scheduler or live feed is installed.

## Data limitations

Historical CSVs can contain later corrections and do not provide historical publication timestamps.
We assume English kickoff times are Europe/London and proxy result availability as kickoff +24h.
These are disclosed conservative backtest assumptions, **not verified point-in-time availability**.
One development shot anomaly is quarantined; goals remain usable. Odds remain in original source
bytes for provenance but are removed from the modeling interface. Cup/European games, transfers,
lineups and injuries are absent. Stored raw downloads are source data, not synthetic fixtures.

## Checks and deployment

```bash
python -m unittest discover -s tests -v
docker build -t soccer-lab .
docker run --rm -v "$PWD/data:/app/data" -v "$PWD/runs:/app/runs" soccer-lab run --out runs/container-run
```

The Docker recipe is supplied but not built here. No cloud service or continuous process is deployed.
Run locally first, then provision a host and schedule data refreshes/forecast jobs with persistent
volumes and secret injection. Autonomous code editing and trading are not connected.

## Sources

- https://www.football-data.co.uk/englandm.php
- https://www.football-data.co.uk/notes.txt
- https://arxiv.org/abs/2403.07669 (survey, not a single reproducible model)
- https://www.sciencedirect.com/science/article/pii/S2772662224001413 (full methods pending)
- https://developers.openai.com/api/docs/models/gpt-6-astra
- https://developers.openai.com/api/docs/guides/structured-outputs

Inspect DATA_AUDIT.md, MODEL_CARD.md and VALIDATION.md for detailed evidence and remaining work.

## Hermes deployment

See [HERMES_DEPLOY.md](HERMES_DEPLOY.md) before deploying this research component on the shared Droplet.
