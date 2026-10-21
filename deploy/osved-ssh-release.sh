#!/usr/bin/env bash
set -Eeuo pipefail
# Install this as root-owned /usr/local/sbin/osved-ssh-release, never run from
# a checkout writable by CI or by the SSH deployment user.
[[ $(id -u) -eq 0 ]] || exit 1
[[ -z "${SSH_ORIGINAL_COMMAND:-}" ]] || { echo "Remote commands forbidden" >&2; exit 1; }
IFS= read -r release_sha
[[ "$release_sha" =~ ^[a-f0-9]{40}$ ]] || { echo "Invalid commit" >&2; exit 1; }
# A forced-command account must not accept arbitrary commands or shell input.
[[ ! -t 0 ]] || exit 1
exec 9>/run/lock/osved-ssh-release.lock
flock -n 9 || { echo "Another deployment is already running" >&2; exit 1; }
source_dir=/opt/osved/staging-source
app_dir=/opt/osved/app
[[ -d "$source_dir/.git" && -f "$app_dir/.env" ]] || exit 1
# Prevent a CI-controlled tree or unknown remote from selecting executable scripts.
[[ "$(git -C "$source_dir" remote get-url origin)" == "https://github.com/TimaBak/osved.git" ]] || {
  echo "Unexpected origin" >&2; exit 1;
}
[[ -z "$(git -C "$source_dir" status --porcelain --untracked-files=no)" ]] || {
  echo "Source checkout has local edits" >&2; exit 1;
}
previous_sha=$(git -C "$source_dir" rev-parse HEAD)
git -C "$source_dir" fetch --no-tags origin main
[[ "$(git -C "$source_dir" rev-parse refs/remotes/origin/main)" == "$release_sha" ]] || {
  echo "Refusing anything except exact current main" >&2; exit 1;
}
git -C "$source_dir" checkout --detach "$release_sha"
# The deploy script is root-owned outside the checkout so repository changes
# alone cannot rewrite the privileged deployment entrypoint.
verify_health() {
  cd "$app_dir"
  local container_id status
  container_id=$(docker compose ps -q newsfeed)
  [[ -n "$container_id" ]] || return 1
  for attempt in $(seq 1 18); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$container_id")
    [[ "$status" == healthy ]] && return 0
    [[ "$status" == unhealthy ]] && return 1
    sleep 10
  done
  return 1
}
if ! (/usr/local/sbin/osved-root-deploy "$source_dir" && verify_health); then
  echo "Deploy or healthcheck failed. Reverting to $previous_sha" >&2
  git -C "$source_dir" checkout --detach "$previous_sha"
  if ! (/usr/local/sbin/osved-root-deploy "$source_dir" && verify_health); then
    echo "Rollback failed; manual recovery required" >&2
    exit 1
  fi
  exit 1
fi
cd "$app_dir"
docker compose ps newsfeed
echo "OSVED staging deployed commit $release_sha"
