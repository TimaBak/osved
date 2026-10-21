# ОСВЕД — delivery plan/fact (2026-10-21)

Goal: an actually usable private news-intelligence service with continuous safe news intake, Telegram feed, `osved.tima.biz` web cabinet / Telegram Mini App, verified authentication and accessible settings.

**State vocabulary**: `implemented` = repository code exists; `CI` = tests passed; `Hermes verified` = observed working against the running deployment. Do not infer later states from an earlier one.

| Priority | Product outcome | Fact as of 2026-10-21 | Acceptance gate |
| --- | --- | --- | --- |
| P0 | Trusted, auto-updated staging deployment | SSH smoke succeeded on Hermes, deploy workflow landed in main; actual staging release **not yet verified** | Main Checks success → staging workflow success → healthy `newsfeed` on Hermes, actual SHA verified, rollback exercised |
| P0 | Useful grounded daily news | Collectors, research and Telegram bot implemented in stages; validated publishable card **not yet proven** | One sourced, validated card; three bounded consecutive cycles with no duplicates, cost guards observed |
| P0 | Safe delivery to owner | Telegram delivery code exists; actual delivery not verified | Owner identity, valid destination, deduplication, sent-item state and delivery logs verified |
| P0 | Model provider compatibility | Codex Sale client/settings foundation exists; OpenRouter generation paths remain | Every generation path uses selected working model; actual provider responses/cost guard tested with bounded live sample |
| P1 | Continuous scheduler and source monitoring | Components exist; not confirmed enabled | Enabled deliberately with rate/cost caps, backoff, source health and operator-visible errors |
| P1 | Functional web API | Not implemented | Versioned read API for news, dossiers, bookmarks, preferences, notifications; auth checks for every private path |
| P1 | Telegram login | Not implemented | Validate Telegram login or Mini App init data server-side; owner allowlist; secure HttpOnly session with CSRF/origin checks, logout |
| P1 | Usable responsive web cabinet | Not implemented | Feed, filters, item details, bookmarks, source status, model/settings, notification preferences; desktop/mobile tested |
| P1 | Public domain / TLS and ingress | Not verified | `osved.tima.biz` serves cabinet over HTTPS, correct routing and security headers |
| P2 | Polished Telegram interaction | Emoji-led depth/navigation labels committed in feature branch; release pending | Inline callbacks and edited messages pass tests; owner-facing copy reviewed |
| P2 | Expanded media/reports | Foundations exist; no evidence of ready features | Grounded exports, permission checks, costs and failure recovery |

## Execution order

1. Establish reproducible, healthy staging and source truth. Verify exact deployed SHA and no loss of `.env` / SQLite data.
2. Fix event→facts→dossier→card→delivery path, then perform three budget-bounded runs and measure results. Do not turn on background paid operations before this passes.
3. Complete Codex Sale compatibility and per-task model application. Multipliers are not dollar prices; budget must be mapped to measured provider usage.
4. Implement protected API + Telegram-authenticated sessions and bookmark/settings persistence.
5. Build the responsive intelligence cabinet and Telegram Mini App against the same API; deploy with HTTPS.
6. Polish Telegram buttons, navigation, notifications and operation reporting; keep smoke + regression gates.
7. Final release gate: healthy Hermes application, live delivery, live web login, mobile UX and no insecure secret exposure.

## Risks and operating rules

- Pull request #1 is a broad **draft** containing incomplete functional changes. Do not merge solely because tests are green; validate production readiness and isolate independent patches when necessary.
- No verified evidence yet that the user's supplied service keys are valid within deployed runtime. Never print secrets or expose them to browser bundles.
- Tests and git commits are not a working site or delivered news. Mark **Hermes verified** only after actual runtime observation.
- Persist backups before migrations; preserve existing owner credentials, source subscriptions and stored history.
- Telegram's regular inline buttons support Unicode emoji in text. Custom emoji require Telegram-verifiable sticker IDs and may not be rendered in every button client; use standard emoji as accessible fallback.

## Progress journal

- 2026-10-21: SSH smoke [GitHub Actions 39523707151](https://github.com/TimaBak/osved/actions/runs/39523707151) passed.
- 2026-10-21: deploy-only PR #2 passed CI and was merged, SHA `23cb100e373386c7ca8256e9b1d8d8d84560b46b`. Staging deploy is **unverified**.
- 2026-10-21: draft PR #1 remains open. Emoji-led news navigation and companion tests updated in the feature branch; CI must pass before claiming tested.
