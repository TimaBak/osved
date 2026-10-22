"""Single-use OAuth handshake state in the existing OSVED SQLite database.

The OAuth authorization code itself is never stored in this table.
"""
from __future__ import annotations

import hashlib
import secrets
import time

from app.db.repository import Repository

STATE_TTL_SECONDS = 600
PROVIDERS = frozenset({"github", "youtube"})


def initialize_oauth_states(repository: Repository) -> None:
    with repository.connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS oauth_pending_states (
                state_digest TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                owner_id INTEGER NOT NULL,
                browser_digest TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )"""
        )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_oauth_state(
    repository: Repository, *, provider: str, owner_id: int, browser_session: str,
    now: int | None = None,
) -> str:
    if provider not in PROVIDERS or not browser_session or owner_id <= 0:
        raise ValueError("Invalid OAuth state parameters")
    moment = int(time.time()) if now is None else now
    token = secrets.token_urlsafe(32)
    with repository.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM oauth_pending_states WHERE expires_at <= ?", (moment,))
        db.execute(
            """INSERT INTO oauth_pending_states
                (state_digest,provider,owner_id,browser_digest,expires_at)
                VALUES (?,?,?,?,?)""",
            (_digest(token), provider, owner_id, _digest(browser_session),
             moment + STATE_TTL_SECONDS),
        )
    return token


def consume_oauth_state(
    repository: Repository, *, provider: str, state: str, owner_id: int,
    browser_session: str, now: int | None = None,
) -> bool:
    if provider not in PROVIDERS or not isinstance(state, str) or len(state) > 256:
        return False
    if not browser_session or owner_id <= 0:
        return False
    moment = int(time.time()) if now is None else now
    with repository.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            """SELECT provider,owner_id,browser_digest,expires_at
               FROM oauth_pending_states WHERE state_digest=?""",
            (_digest(state),),
        ).fetchone()
        if row:
            db.execute(
                "DELETE FROM oauth_pending_states WHERE state_digest=?", (_digest(state),)
            )
        return bool(
            row and row["provider"] == provider and row["owner_id"] == owner_id
            and secrets.compare_digest(row["browser_digest"], _digest(browser_session))
            and row["expires_at"] > moment
        )
