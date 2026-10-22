# ОСВЕД — scoped AI model routing, phase 2

This small PR depends on PR #30. It adds a **pure policy layer**, not a paid
provider call or production routing switch.

- One existing SQLite `runtime_settings` store for the website and Telegram.
- Resolution order: source > scenario > profile > task > historical Telegram task > default.
- Writes require model IDs from an externally verified account catalog; defaults
  are not proof that models exist or that their endpoint capabilities work.
- OpenRouter fallback is off by default. The policy does not execute fallback.
- Requests for `image` and `audio` are intentionally excluded until dedicated
  endpoint capability verification and quotas are available.
- This phase does not change the website, Telegram handlers, schedules, secrets,
  DB schema, requests, or delivery mechanisms.

Next: integrate authenticated site settings with this same store; add server-side
catalog verification + budget/idempotency gates before provider execution.
