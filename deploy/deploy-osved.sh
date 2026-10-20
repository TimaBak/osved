#!/usr/bin/env bash
set -Eeuo pipefail

# Intended for an isolated VPS and a dedicated self-hosted runner labeled osved-deploy.
# One-time provision: install Docker/Compose, runner, and /opt/osved/.env (chmod 600).
DEST="${OSVED_DEPLOY_DIR:-/opt/osved}"
if [[ "$DEST" != "/opt/osved" ]]; then
  echo "Unexpected deploy destination" >&2
  exit 1
fi
if [[ ! -f "$DEST/.env" ]]; then
  echo "Missing $DEST/.env. Provision secrets directly on VPS first." >&2
  exit 1
fi
command -v rsync >/dev/null || { echo "rsync required" >&2; exit 1; }
docker compose version >/dev/null
mkdir -p "$DEST"
# Preserve deployment secrets and data; SQLite lives in a named Docker volume.
rsync -a --delete --exclude='.git/' --exclude='.env' --exclude='data/' --exclude='exports/' ./ "$DEST/"
cd "$DEST"
docker compose config --quiet
docker compose build newsfeed
docker compose run --rm --no-deps newsfeed osved doctor
docker compose up -d --no-deps newsfeed
docker compose ps newsfeed
