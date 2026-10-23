# Independent validation review

Reviewed by a separate implementation agent. This review checks pipeline invariants; it does not establish an investment edge or prove predictive superiority.

## Reproducible checks

Run `python -m unittest discover -s tests -v` from this directory. Fixtures in `tests/test_pipeline.py` are deliberately synthetic. They are never reported as football evaluation results and use temporary directories for synthetic holdout tests.

All 12 independent tests passed on the implementation reviewed. The tests check:

- Changing a target match's goals, shots and outcome, and every later outcome, leaves its input features unchanged.
- Changing an already available earlier result changes later team strengths, demonstrating real causal use of history.
- Same-day scores that have not passed the availability proxy cannot enter the forecast.
- Every recorded source-availability timestamp is at or before the forecast cutoff.
- Elo probabilities are finite, nonnegative and sum to one, including large rating differences.
- Repeated feature construction yields identical frames.
- A promoted club retains sensitivity to Championship history; its state remains finite.
- Bookmaker columns never enter the normalized modeling data; kickoff and two-hour cutoff conversion are explicit.
- Incorrect result labels and duplicate fixtures are rejected. Contradictory optional shots are flagged and quarantined while valid goals remain usable.
- Forecasts enforce EPL scope, canonical known team names, distinct opponents, a two-hour cutoff, no duplicate fixtures and a matching frozen model-code hash.
- Synthetic test-season label changes do not change model selection or validation metrics; test evaluation requires a frozen selection, refuses a second opening and rejects changed development data.

## Important limits

1. Football-Data CSVs are retrospective snapshots. A kickoff-plus-24-hour availability proxy prevents direct same-match lookahead but cannot prove what was published at a historical forecast time, or recover past corrections and postponement announcements. Forecasts are retrospective as-of simulations until prospective snapshots are collected.
2. Europe/London is an explicit source-clock assumption, not verified publication metadata.
3. Promotion adjustments (0.85 goal-rate conversion and lower initial Championship Elo) are assumptions, not estimated causal league strength. The test proves history is retained; it does not validate these parameter values. Championship participants arriving from League One lack equivalent prior history.
4. Attack/defense features currently summarize goals, with shrinkage and exponential forgetting. Source shots are validated but are not currently modeled. There are no player/lineup, injury, cup-rest or transfer features.
5. Team ratings update as earlier results become available. Logistic coefficients remain frozen during each evaluated season. This is an explicitly limited adaptive policy, not continuous within-season coefficient retraining.
6. Calibration tables are descriptive validation diagnostics, not a guarantee of calibration or statistical superiority. The selected model is selected on the same validation season that reports its best result. Use the untouched test season once to assess the frozen procedure.
7. The file/hash gates reduce accidental holdout reuse. They do not prevent a user from deleting directories or creating a new experiment after seeing the test. Once examined, 2025–26 is not untouched for later research.
8. There are no odds comparisons, executable price checks, portfolio returns, Kalshi orders or live deployment in this phase. Model predictive performance cannot establish trading profitability alone.
9. Bounded Astra calls write role memos and proposals; they do not modify code, tune against test outcomes, change match probabilities, or execute orders. Authenticated API behavior requires a configured account and is separate from offline checks.

## Sizing addition

The suite now also includes 11 sizing tests, for 23 total tests.
These use synthetic quotes and outcomes. They cover fixed and quarter-Kelly
quantities, fee rounding and missing fee quotes, YES/NO mapping, depth/cash/risk
caps, concurrent reservation attempts, persistent restart state, no re-entry,
gross losses without profit offsets, Chicago midnight rollover and code-enforced
policy caps. This validates the paper ledger only; no exchange fills, live
account reconciliation or market fee retrieval have been tested.

## Paper-method replication status

The official arXiv abstract for [Machine Learning for Soccer Match Result Prediction](https://arxiv.org/abs/2403.07669) identifies it as an overview of datasets, models, features and evaluation. It is background for candidate selection, not one reproducible model specification.

The ScienceDirect article [A predictive analytics framework for forecasting soccer match outcomes using machine learning models](https://www.sciencedirect.com/science/article/pii/S2772662224001413), DOI `10.1016/j.dajour.2024.100537`, could not be read from the publisher during this build (403). No full-method replication has been verified. The implemented attack/defense model must not be described as a replication. An accessible full paper is needed to map its actual features, forecast timing, algorithms and validation to this task.
