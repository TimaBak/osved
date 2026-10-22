"""Encrypted at-rest OAuth token storage, using the existing SQLite database.

The encryption key must be a separately configured Fernet key. Never persist
plaintext provider access/refresh tokens or emit them to the portal response.
"""
from __future__ import annotations

import time

from cryptography.fernet import Fernet, InvalidToken

from app.db.repository import Repository


def _cipher(key: str) -> Fernet:
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid OAuth encryption key") from exc


def initialize_token_vault(repository: Repository) -> None:
    with repository.connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS oauth_account_tokens (
                provider TEXT NOT NULL,
                owner_id INTEGER NOT NULL,
                account_id TEXT NOT NULL,
                access_cipher BLOB NOT NULL,
                refresh_cipher BLOB,
                granted_scopes TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (provider, owner_id, account_id)
            )"""
        )


def save_tokens(
    repository: Repository, *, encryption_key: str, provider: str,
    owner_id: int, account_id: str, access_token: str,
    refresh_token: str | None = None, scopes: str = "",
) -> None:
    if provider not in {"github", "youtube"} or owner_id <= 0:
        raise ValueError("Invalid OAuth account")
    if not account_id or len(account_id) > 200 or not access_token:
        raise ValueError("Invalid OAuth token data")
    cipher = _cipher(encryption_key)
    with repository.connection() as db:
        db.execute(
            """INSERT INTO oauth_account_tokens
                 (provider,owner_id,account_id,access_cipher,refresh_cipher,
                  granted_scopes,updated_at) VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(provider,owner_id,account_id) DO UPDATE SET
                 access_cipher=excluded.access_cipher,
                 refresh_cipher=COALESCE(excluded.refresh_cipher,oauth_account_tokens.refresh_cipher),
                 granted_scopes=excluded.granted_scopes,
                 updated_at=excluded.updated_at""",
            (provider, owner_id, account_id,
             cipher.encrypt(access_token.encode("utf-8")),
             cipher.encrypt(refresh_token.encode("utf-8")) if refresh_token else None,
             scopes, int(time.time())),
        )


def read_tokens(
    repository: Repository, *, encryption_key: str, provider: str,
    owner_id: int, account_id: str,
) -> tuple[str, str | None] | None:
    cipher = _cipher(encryption_key)
    with repository.connection() as db:
        row = db.execute(
            """SELECT access_cipher,refresh_cipher FROM oauth_account_tokens
               WHERE provider=? AND owner_id=? AND account_id=?""",
            (provider, owner_id, account_id),
        ).fetchone()
    if not row:
        return None
    try:
        access = cipher.decrypt(row["access_cipher"]).decode("utf-8")
        refresh = (
            cipher.decrypt(row["refresh_cipher"]).decode("utf-8")
            if row["refresh_cipher"] else None
        )
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise ValueError("OAuth token cannot be decrypted") from exc
    return access, refresh


def connected_accounts(repository: Repository, *, provider: str, owner_id: int) -> list[str]:
    if provider not in {"github", "youtube"} or owner_id <= 0:
        raise ValueError("Invalid OAuth account")
    with repository.connection() as db:
        rows = db.execute(
            """SELECT account_id FROM oauth_account_tokens
               WHERE provider=? AND owner_id=? ORDER BY account_id""",
            (provider, owner_id),
        ).fetchall()
    return [row["account_id"] for row in rows]


def revoke_stored_tokens(
    repository: Repository, *, provider: str, owner_id: int, account_id: str
) -> bool:
    with repository.connection() as db:
        result = db.execute(
            """DELETE FROM oauth_account_tokens
               WHERE provider=? AND owner_id=? AND account_id=?""",
            (provider, owner_id, account_id),
        )
        return result.rowcount > 0
