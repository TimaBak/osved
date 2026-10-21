# ОСВЕД — backend-first execution plan

**Source of truth:** current branch CI + actual Hermes doctor output. No UI or emoji enhancements until backend gates pass. No automatic paid API calls or Telegram delivery without a bounded, confirmed run.

## P0 — reliability and verified story (blocking)

- [x] Verify collection, ingestion, deduplication, and Codex Sale routing using pilot data.
- [x] Make `pipeline-once --generate-limit 1` mean at most one research candidate per iteration.
- [x] Fix CI regressions; maintain green Ruff, pytest and container checks.
- [x] Implement a no-network stored-fact revalidator with dry-run by default; preserve fact conflicts and existing evidence checks. CI verified.\n- [ ] **Gate P0-A:** Validate Cloudflare event 36 against Hermes SQLite using `osved revalidate-saved-facts 36` (dry-run); use `--apply` only if valid.
- [ ] **Gate P0-B:** Generate a *valid* grounded Telegram card and dossier from stored evidence. Verify no delivery and bounded cost.
- [ ] **Gate P0-C:** Run 3 consecutive controlled end-to-end cycles and inspect costs/errors/duplicate handling.

## P1 — source acquisition breadth

- [ ] Make default fresh-install sources empty; stage the Hermes pilot catalogue separately, retaining existing persistent DB subscriptions.
- [ ] Fix GitHub Blog RSS (DTD/ENTITY safety stays on); substitute a verified official endpoint if needed.
- [ ] Add source health reporting, metadata, credential modes, backoff, retries, freshness and per-adapter diagnostics.
- [ ] Validate official RSS/Atom sources (OpenAI, Anthropic, DeepMind, Hugging Face, GitHub, Cloudflare, NVIDIA, CNCF, Kubernetes) before activation.
- [ ] Test GitHub releases and repos, Telegram, YouTube, X, Reddit, Hacker News; mark unavailable providers as such.
- [ ] Catalog optional sources even when paid, geo-limited, or requiring user authentication. Never equate a catalog entry with an active, functional integration.

## P2 — continuous processing and operations

- [ ] Safely enable scheduler only after P0 and P1 evidence. Keep hard USD stops and rate limits.
- [ ] Add bounded queues, idempotency, cooldowns, failure classifications, operational metrics and backup/restore checks.
- [ ] Separate staging deployment, production config and public base install. Protect credentials and existing SQLite data.
- [ ] Establish explicit authorized deployment/rollback path; GitHub Actions CI alone is not VPS shell access.

## P3 — interests and intelligence

- [ ] Add topics/subtopics, organizations, authors, user-driven priorities and exclusions.
- [ ] Score source provenance separately from publisher trust, relevance and objective event quality.
- [ ] Use feedback for transparent personalization; avoid silently changing user preferences.
- [ ] Validate research summaries, saved bookmarks, weekly reviews and bounded PDF/video outputs.

## P4 — interface (deferred)

- [ ] Telegram news, navigation, detailed articles and delivery reliability.
- [ ] Shared API + Telegram authentication for `osved.tima.biz`.
- [ ] Dark, information-dense Intelligence Dashboard with mobile-friendly layout.
- [ ] Expandable, balanced Telegram custom emoji library only after backend quality.

## Release discipline

Offline recovery: `osved revalidate-saved-facts 36` is read-only and has no external API calls; if valid, `osved revalidate-saved-facts 36 --apply` stores a new validated fact sheet and dossier without repeat LLM charges. It never overrides failing evidence checks.\n\nEvery chunk: read live branch → implement → add regression tests → observe CI → fix to green → mark status with exact commit → next chunk. Report separately: **committed**, **CI-tested**, **verified on Hermes**. Do not publish, send messages or repeat paid research as a test of unrelated code.
