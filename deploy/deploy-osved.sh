#!/usr/bin/env bash
set -Eeuo pipefail

# This is a manually approved, one-time staging bootstrap. Never invoke from
# a self-hosted runner job or grant osved-runner permissions to execute it.
[[ $(id -u) -eq 0 ]] || { echo "Run as root" >&2; exit 1; }
[[ ${1:-} == /opt/osved/staging-source ]] || { echo "Expected source: /opt/osved/staging-source" >&2; exit 1; }
SOURCE=/opt/osved/staging-source
DEST=/opt/osved/app
[[ -f "$SOURCE/compose.yaml" && -f "$SOURCE/Dockerfile" ]] || { echo "Missing project sources" >&2; exit 1; }
[[ -f "$DEST/.env" ]] || { echo "Missing protected application environment" >&2; exit 1; }
command -v rsync >/dev/null
docker compose version >/dev/null
# Do not delete secrets, persistent data, or arbitrary files in target.
rsync -a --exclude='.git/' --exclude='.env' --exclude='secrets/' --exclude='data/' --exclude='exports/' "$SOURCE/" "$DEST/"
cd "$DEST"
docker compose config --quiet
docker compose build newsfeed
docker compose run --rm --no-deps newsfeed osved doctor
docker compose up -d --no-deps newsfeed
docker compose ps newsfeed
