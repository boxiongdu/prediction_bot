#!/usr/bin/env bash
# Called via SSH by the manually approved DigitalOcean staging workflow.
# DO NOT restart systemd services, touch live trading settings or modify live state.
set -euo pipefail

sha="${1:-}"
if [[ ! "$sha" =~ ^[a-f0-9]{40}$ ]]; then
  echo "Expected a 40-character git commit SHA." >&2
  exit 2
fi

base="$HOME/prediction_bot_staging"
archive="$base/incoming/$sha.tar.gz"
release="$base/releases/$sha"
current="$base/current"

test -f "$archive" || { echo "Missing uploaded release archive." >&2; exit 2; }
mkdir -p "$base/releases"

if [[ -e "$release" ]]; then
  echo "Release directory already exists; refusing to overwrite: $sha" >&2
  exit 2
fi

mkdir "$release"
tar -xzf "$archive" -C "$release" --no-same-owner --no-same-permissions
test -f "$release/pyproject.toml"
test -f "$release/src/prediction_bot/__init__.py"

# Requirements: pre-installed Python 3 with venv support, network access for pip.
python3 -m venv "$release/.venv"
"$release/.venv/bin/python" -m pip install --disable-pip-version-check -e "$release"
(
  cd "$release"
  ENABLE_LIVE_TRADING=false AUTO_TRADING_ENABLED=false LIVE_TRADING_MODE=PAPER \
    "$release/.venv/bin/python" -c 'import prediction_bot; print("Staging package import OK")'
)

# Atomic pointer update. This is NOT the live bot service path.
ln -s "$release" "$base/.current-next"
mv -Tf "$base/.current-next" "$current"
printf '%s\n' "$sha" > "$base/current_sha"
rm -f "$archive"
echo "Staged release $sha at $current. Live systemd services were not modified."
