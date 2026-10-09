# Hermes handoff: soccer research component

Branch: `codex/soccer-agents-v1`. Application directory: `soccer-lab/`.
This is a research deployment handoff, not evidence that a service is already running.

## Existing host

The user reports a DigitalOcean Droplet with 2 vCPU, 2 GB RAM, and 90 GB disk,
already running a trading system and Hermes v0.19.0 with one local commit.
Observed available RAM was about 631 MiB; a short sample showed no active swap I/O.
Those are point-in-time observations, not guaranteed spare capacity.

## Deployment procedure

1. Inspect available resources and preserve the existing Hermes customization.
2. Use a separate checkout and virtual environment for this project. Do not switch
   branches in a checkout used by the running trading system or install dependencies
   into its environment. A separate checkout can target this branch explicitly:

   ```bash
   git clone --depth 1 --single-branch --branch codex/soccer-agents-v1 \
     git@github.com:boxiongdu/prediction_bot.git prediction-bot-soccer
   cd prediction-bot-soccer/soccer-lab
   ```

3. Follow README setup, run offline tests, and execute a development-only run in a
   resource-limited job. Limit numerical libraries to one thread, prevent overlapping
   jobs, and measure peak memory before deciding whether this host can run training.
   The initial 512 MiB suggestion is a trial budget, not a measured requirement.
4. Download only 2223, 2324, 2425 for development. Preserve raw snapshots and reports
   on persistent disk. Do not open the 2526 test as a routine deployment check.
5. Start with `python lab.py run --out runs/first-host-run` without `--astra`.
   This validates the data/model pipeline without paid API calls. Inspect the exit
   status, validation tests and supervisor report.
6. If requested, configure OPENAI_API_KEY locally for this application's process;
   do not print, commit, or copy secrets into reports. Then use `--astra` for its
   three bounded role reviews. The $100 monthly API budget is not enforced in code.
7. Return a concise report to the user with the checked-out commit, commands run,
   resource usage, test result, model metrics and uncompleted steps.

## Authority and operating boundaries

Hermes manages deployment and reports; statistical code produces probabilities.
The three Astra roles currently review evidence and propose changes. They do not
autonomously execute generated modeling code. Run the existing application as a
subprocess; avoid duplicating all three reviews with additional Hermes agents.

Hermes's own selected model and the application's `gpt-6-astra` calls are separate
settings. Verify the installed Hermes provider options before changing its model.
Do not blindly upgrade its customized installation or restart existing services.

No production Kalshi credentials or order execution are needed. Do not modify the
existing trading system, enable trading, merge this branch, or open the held-out test
as a side effect of deployment. No continuous scheduler, kickoff feed, failure-alert
service or automatic recovery is installed by this branch; these require a separate
implementation and verification step after the bounded run works.
