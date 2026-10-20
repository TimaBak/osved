# ОСВЕД — initial VPS CI/CD provisioning

Status: deployment foundation; do not merge until AI migration/tests and deployment review are complete.

## Recommended isolation

Use a dedicated VPS (Ubuntu) for the OSVED runner/deployment. Docker-group membership is effectively root-equivalent. Do **not** attach an unrestricted self-hosted runner to a VPS hosting VPN, mail, or other production services.

## One-time operator steps

1. Create/choose a dedicated VPS. Install Docker Engine + Compose plugin, git, rsync, and required OS security updates.
2. Create a non-root deployment account; arrange restricted permission to operate Docker **on this dedicated machine only**.
3. In GitHub repository `TimaBak/osved`, go to **Settings → Actions → Runners → New self-hosted runner**, choose Linux x64, and follow the **live GitHub instructions**. Register with custom label `osved-deploy`, install as a service. Registration credentials are short-lived; never commit them.
4. Create directory `/opt/osved` owned by the dedicated runner account. Put the eventual production secrets at `/opt/osved/.env`, private permissions `0600`. Provision using the project's `.env.example` as a template and set Telegram bot token, Telegram owner ID, Monid key, and Codex Sale key once full migration is ready. Do not publish secrets in workflow logs.
5. Create GitHub Environment `production`, restrict deployments to protected `main`, and configure required reviewers when available.
6. Keep CI GitHub-hosted: tests and Docker build run on `ubuntu-latest`. Only the deployment job uses the dedicated runner.
7. Do not merge until text inference paths are migrated to Codex Sale and validated. After merging, each `main` push runs tests → Docker build → dedicated runner deployment. Inspect Actions logs and `docker compose ps` on VPS.

## Deployment behavior

`deploy/deploy-osved.sh` copies the exact checked-out revision into `/opt/osved`, preserving `.env` and named Docker data/exports volumes, rebuilds `newsfeed`, runs `osved doctor`, then starts the Compose service. It does not touch other Compose projects. It does not configure domains, TLS, Telegram WebApp authentication, or rollback yet.

## Safety and release gates

- Never run unreviewed PR code on the runner (the deployment step runs only on main).
- Use branch protection and an approval gate before deploying to production.
- Check the backup state before updates; never use `docker compose down -v`.
- The simple deploy script is **not zero-downtime** and does not implement automated rollback.
- A passing static test suite does not verify paid provider endpoints or Telegram behavior. Staging smoke tests and provider verification are separate tasks.
- If runner labels do not match `self-hosted, Linux, X64, osved-deploy`, the deployment job will queue rather than run.
