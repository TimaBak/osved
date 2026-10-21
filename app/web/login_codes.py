"""Short-lived, owner-issued browser login codes for OSVED's private web portal.

Codes are revealed only by the owner-only Telegram bot, never logged by the
server. HMAC digests, global failed-attempt limits and single-use semantics
protect the web endpoint from guessing and replay.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from app.db.repository import Repository

TTL_SECONDS = 300
MAX_ATTEMPTS = 5


def ensure_login_schema(repository: Repository) -> None:
    with repository.connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS portal_login_code (
               singleton INTEGER PRIMARY KEY CHECK(singleton=1),
               owner_id INTEGER NOT NULL,
               code_digest TEXT NOT NULL,
               expires_at INTEGER NOT NULL,
               failed_attempts INTEGER NOT NULL DEFAULT 0)"""
        )


def _digest(token: str, owner_id: int, code: str) -> str:
    return hmac.new(
        token.encode("utf-8"),
        f"osved-portal-code:{owner_id}:{code}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def issue_login_code(
    repository: Repository, *, token: str, owner_id: int, now: int | None = None
) -> str:
    ensure_login_schema(repository)
    code = f"{secrets.randbelow(10**12):012d}"
    timestamp = int(time.time()) if now is None else now
    with repository.connection() as db:
        db.execute(
            """INSERT INTO portal_login_code (
               singleton, owner_id, code_digest, expires_at, failed_attempts
               ) VALUES (1, ?, ?, ?, 0)
               ON CONFLICT(singleton) DO UPDATE SET
               owner_id=excluded.owner_id,
               code_digest=excluded.code_digest,
               expires_at=excluded.expires_at,
               failed_attempts=0""",
            (owner_id, _digest(token, owner_id, code), timestamp + TTL_SECONDS),
        )
    return code


def redeem_login_code(
    repository: Repository, *, token: str, owner_id: int,
    code: str, now: int | None = None
) -> bool:
    if not isinstance(code, str) or len(code) != 12 or not code.isascii() or not code.isdecimal():
        return False
    timestamp = int(time.time()) if now is None else now
    with repository.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT owner_id,code_digest,expires_at,failed_attempts "
            "FROM portal_login_code WHERE singleton=1"
        ).fetchone()
        if row is None or row["owner_id"] != owner_id:
            return False
        if row["expires_at"] < timestamp or row["failed_attempts"] >= MAX_ATTEMPTS:
            db.execute("DELETE FROM portal_login_code WHERE singleton=1")
            return False
        expected = _digest(token, owner_id, code)
        if hmac.compare_digest(expected, row["code_digest"]):
            db.execute("DELETE FROM portal_login_code WHERE singleton=1")
            return True
        attempts = row["failed_attempts"] + 1
        if attempts >= MAX_ATTEMPTS:
            db.execute("DELETE FROM portal_login_code WHERE singleton=1")
        else:
            db.execute(
                "UPDATE portal_login_code SET failed_attempts=? WHERE singleton=1",
                (attempts,),
            )
        return False
