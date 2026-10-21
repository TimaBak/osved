# OSVED staging SSH — one-time owner bootstrap

The workflow `.github/workflows/staging-ssh.yml` runs **only after a successful `Checks` run on `main`**, from the repository `TimaBak/osved`. It has read-only GitHub permissions and uses the protected `staging` environment. The deployment key is deliberately **not** a root SSH key and grants no interactive shell.

**Do not send private keys, bot tokens, passwords, .env, or session files to chat or commits.** The runner in the existing `ci.yml` remains unprivileged. These SSH jobs run on GitHub-hosted runners instead.

## 1. Server bootstrap (one time, by server owner)

* Review and audit `deploy/osved-ssh-release.sh` and `deploy/deploy-osved.sh` first.
* The Git checkout must be at `/opt/osved/staging-source` with clean tracked files and `origin` set to exactly `https://github.com/TimaBak/osved.git` (script refuses any other remote). The private repository requires configured read-only Git authentication **on the server**; never paste its token into Actions logs.
* Create a dedicated locked-password account `osved-release`, with a home directory and no Docker group membership. Keep the existing application `.env` root-protected.
* Install **reviewed versions** of `deploy/deploy-osved.sh` as `/usr/local/sbin/osved-root-deploy` and `deploy/osved-ssh-release.sh` as `/usr/local/sbin/osved-ssh-release`. Set ownership `root:root`, mode `0755`; the SSH user must not be able to modify these.
* Create a dedicated SSH keypair outside the repository. Put **only its public half** into `~osved-release/.ssh/authorized_keys`, with the key prefixed by:
  `restrict,command="sudo -n /usr/local/sbin/osved-ssh-release"`
  The key must not permit port forwarding, agent forwarding, pty, or arbitrary commands.
* Use `visudo -f /etc/sudoers.d/osved-release` to add exactly:
  `osved-release ALL=(root) NOPASSWD: /usr/local/sbin/osved-ssh-release`
  Never grant `docker`, unrestricted `sudo`, `bash` or write access to deployment scripts.
* Review SSH daemon user/account restrictions and ownership. Verify the fingerprint of Hermes' SSH **host key through a trusted channel**. Do not blindly trust an unverified `ssh-keyscan` response.

The privileged deploy entrypoint expects **one exact SHA over standard input**; it verifies it equals the current remote `main`, serializes runs with a lock, deploys, waits for Docker health, and rolls back the previous commit on deployment/health failure. It refuses remote shell commands.

## 2. GitHub repository settings

Configure the existing environment `staging` with branch restrictions allowing `main` only and required approval where available.

Under `Settings → Environments → staging`, set:

| Key | Type | Value |
| --- | --- | --- |
| `OSVED_DEPLOY_HOST` | Environment variable | Verified hostname or IP of Hermes |
| `OSVED_DEPLOY_USER` | Environment variable | `osved-release` |
| `OSVED_DEPLOY_KEY` | Environment secret | Entire private half of dedicated deploy key |
| `OSVED_KNOWN_HOSTS` | Environment secret | Verified known_hosts line containing Hermes SSH host public key |

No `OPENROUTER_API_KEY`, Telegram secrets or root credentials are required in GitHub.

## 3. Activation and tests

1. Land the reviewed workflows and server scripts on the protected default branch `main`. `workflow_run` only fires for workflow files available on the default branch.
2. Set the four environment entries above. Bootstrap and verify the restricted SSH principal on Hermes **before** allowing successful-main push deployments.
3. Merge one reviewed commit into `main`. Passing `Checks` triggers the SSH workflow. Check logs and on-server Docker health. Run `osved doctor` and the free stored-fact revalidation separately when authorized.
4. Keep `staging` approval required during initial rollout; switch to automatic approval only after multiple stable deployments. Never enable a deploy from an untrusted PR branch.
5. On failed release, inspect Actions and protected server logs. Rollback is best-effort; a schema/data migration may require an explicit recovery plan because code rollback alone cannot restore a database.

## Safety limitations

The root-installed script is part of the trusted computing base. Reviewing the GitHub code alone does not install or activate it. GitHub CI succeeding does not demonstrate Hermes deployment; verify the separate `Staging SSH deployment` run. Only staging is supported by this flow. The currently existing `ci.yml` self-hosted request job remains separate and unprivileged.
