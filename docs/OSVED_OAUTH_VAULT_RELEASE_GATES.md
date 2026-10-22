# OAuth vault implementation gate

This branch introduces authenticated encryption (Fernet from cryptography) for provider
tokens in the existing SQLite volume. The cryptographic library is a new runtime
dependency.

**Do not merge/deploy yet:** the repository uses uv --frozen; `uv.lock` must be
regenerated with `uv lock` and the build/test jobs must pass on the same exact
commit before release. Without that step, the runtime package might be absent.

Vault API deliberately has no automatic OAuth flow or external connection; access
tokens and refresh tokens are encrypted and must never be printed or exposed to
frontend JSON. The configured key must remain stable through restarts; key rotation
and backup recovery need a separate procedure.

The first user-connected provider remains GitHub, followed by YouTube/Google.
Required future gates: callback validation, token exchange, scopes, revocation,
owner-only account listing, official OAuth app configuration, and integration tests.
