# CI/CD: Kalshi prediction bot to DigitalOcean

## Scope and current safety boundary

This repository controls components that can submit **real Kalshi trades**. The
CI/CD design intentionally separates uncredentialed offline validation from
deployment and **never changes a running trading process**.

- `Python CI` runs on pushes/PRs with trading disabled and no Kalshi credentials.
- `Deploy to DigitalOcean (staging)` is manually triggered from the **main**
  branch, repeats tests, then waits for the `digitalocean-staging` environment
  approval (configure a required reviewer in GitHub).
- The approved workflow authenticates by SSH with a dedicated unprivileged user,
  uses a pinned host public key, transfers only source code and configuration
  templates, creates a versioned Python virtual environment, and atomically
  changes the `~/prediction_bot_staging/current` symlink.
- **No `systemctl restart`, cron modifications, order submissions, automatic
  activation, or live service file changes are performed.** The production
  `lol-match-bot.service` mentioned in README is not touched.
- Live data, SQLite ledgers, model artifacts, API credentials, and `.env` are
  excluded from releases and remain where the operator already stores them.

**Why staging only?** The repository's October 2026 README references
`src/prediction_bot/trading/match_winner_bot.py`, but that entry point and the
referenced `models/recency_model/` artifacts are not present in the current
GitHub `main` tree. Automatically restarting the live service using this
incomplete checkout would be unsafe. Before automating production promotion,
reconcile the actual Droplet service's `ExecStart`, code path, artifacts, and
runtime dependencies with the versioned repository.

## Setup (one-time, by the repository owner)

1. On the Droplet, create a **non-root deployment user** with SSH key access and
   Python 3.11 (including `venv`) installed. This user must not be in sudoers
   and must have **no access to Kalshi credentials or the active service path**.
   GitHub Actions will create `~/prediction_bot_staging` automatically.
2. Generate a dedicated SSH key for GitHub Actions. Put **only the public key**
   in the deployment user's `~/.ssh/authorized_keys`. Store the **private key**
   as `DO_SSH_PRIVATE_KEY` in the GitHub environment, never in source code.
3. In repository **Settings → Environments**, create
   `digitalocean-staging`. Restrict deployments to `main` and configure
   **Required reviewers**, so someone must approve before SSH secrets can be
   accessed. Merely naming an environment in YAML does not enable approval.
4. Add the following **environment secrets**:
   - `DO_SSH_HOST`: Droplet's public DNS hostname or IP.
   - `DO_SSH_USER`: unprivileged deploy username.
   - `DO_SSH_PRIVATE_KEY`: entire dedicated private SSH key.
   - `DO_SSH_KNOWN_HOSTS`: verified `known_hosts` line for the host's SSH
     public key. Verify its fingerprint independently using the Droplet's
     console; do not blindly trust a host key fetched over the same network.
5. Check **Actions → Python CI** after merging. The tests must pass before any
   staging attempt. From **Actions → Deploy to DigitalOcean (staging) → Run
   workflow**, select `main`, then approve the gated deployment.
6. Confirm `~/prediction_bot_staging/current` points to the correct commit and
   imports successfully. The running live bot remains unchanged.

## Validate the staged release (safe)

```bash
ssh DEPLOY_USER@DROPLET_HOST
readlink -f ~/prediction_bot_staging/current
cat ~/prediction_bot_staging/current_sha
~/prediction_bot_staging/current/.venv/bin/python -c 'import prediction_bot'
```

Do **not** manually activate production trading as part of this staging check.

## Future production promotion (not implemented)

After reconciling the actual service and model artifacts, add a separately
protected promotion workflow with a pre-deploy backup, startup self-check,
minimal-downtime restart, persistent data isolation, rollback, order-idempotency
checks, and a smoke test that cannot place an order.

A staging deploy alone is continuous **delivery** of versioned artifacts to a
cloud Linux VM; it is **not yet automatic production deployment of a live bot**.
