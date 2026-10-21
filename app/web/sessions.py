"""Durable owner-only browser sessions backed by the shared OSVED SQLite volume.

The browser receives an opaque 256-bit random cookie. SQLite stores only its
SHA-256 digest, making stolen database rows insufficient to impersonate users.
Sessions survive application and container restarts; logout removes one session.
"""
from __future__ import annotations

import hashlib
import secrets
import time

from app.db.repository import Repository

SESSION_SECONDS = 30 * 24 * 60 * 60
MAX_ACTIVE_SESSIONS = 64


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def initialize_sessions(repository: Repository) -> None:
    with repository.connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS portal_sessions (
                token_digest TEXT PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                csrf_token TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )"""
        )
        db.execute(
            """CREATE INDEX IF NOT EXISTS idx_portal_sessions_expiry
            ON portal_sessions(expires_at)"""
        )


def issue_session(
    repository: Repository, owner_id: int, *, now: int | None = None
) -> tuple[str, str]:
    if type(owner_id) is not int or owner_id <= 0:
        raise ValueError("Owner must be a positive Telegram user ID")
    current = int(time.time()) if now is None else now
    raw = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    with repository.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "DELETE FROM portal_sessions WHERE expires_at <= ?", (current,)
        )
        db.execute(
            """INSERT INTO portal_sessions (
               token_digest,owner_id,csrf_token,created_at,expires_at)
               VALUES (?,?,?,?,?)""",
            (_digest(raw), owner_id, csrf, current, current + SESSION_SECONDS),
        )
        db.execute(
            """DELETE FROM portal_sessions
            WHERE token_digest IN (
                SELECT token_digest FROM portal_sessions
                ORDER BY created_at DESC, rowid DESC
                LIMIT -1 OFFSET ?
            )""",
            (MAX_ACTIVE_SESSIONS,),
        )
    return raw, csrf


def lookup_session(
    repository: Repository, token: str, owner_id: int | None,
    *, now: int | None = None
) -> str | None:
    if (
        not isinstance(token, str)
        or not 32 <= len(token) <= 256
        or type(owner_id) is not int
        or owner_id <= 0
    ):
        return None
    current = int(time.time()) if now is None else now
    with repository.connection() as db:
        row = db.execute(
            """SELECT csrf_token FROM portal_sessions
               WHERE token_digest=? AND owner_id=? AND expires_at>?""",
            (_digest(token), owner_id, current),
        ).fetchone()
    return str(row["csrf_token"]) if row else None


def revoke_session(repository: Repository, token: str) -> None:
    if not isinstance(token, str) or not 32 <= len(token) <= 256:
        return
    with repository.connection() as db:
        db.execute(
            "DELETE FROM portal_sessions WHERE token_digest=?", (_digest(token),)
        )
