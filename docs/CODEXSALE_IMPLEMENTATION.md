# ОСВЕД — Codex Sale migration (work in progress)

Branch: `feature/codexsale-foundation`. This is a foundation, **not a completed provider cutover**.

## Included
- Typed, self-contained Codex Sale HTTP client for `GET /v1/models`, `POST /v1/chat/completions`, and `POST /v1/responses`.
- Stable per-task model settings in the existing runtime settings repository.
- Telegram `/models` and `/model <task> <model-id>` settings UI.
- Unit tests for basic model selection and client input checks.

## Still required before deployment
1. Route all existing calls to `app/llm/openrouter.py` and separate YouTube requests through the new client.
2. Verify actual model IDs, structured-output compatibility, usage payloads and provider-side limits with a real account; never commit API keys.
3. Replace OpenRouter-specific cost accounting; Codex Sale multipliers are **not USD prices**.
4. Integrate selected per-task models into all worker and report execution paths.
5. Add responsive private web interface and authenticated Telegram Mini App entry.
6. Add bookmarks and collection filtering to the existing SQLite schema.
7. Probe image and transcription endpoints, then add opt-in features.
8. Run all unit tests, integration smoke tests and GitHub CI before merge.

## Configuration (planned)
`CODEX_SALE_API_KEY` (secret); `CODEX_SALE_BASE_URL=https://codex.sale/v1`.
Do not expose secrets in frontend HTML, API responses or GitHub.
