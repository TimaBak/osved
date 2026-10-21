"""Owner-scoped reading notes and progress on the shared OSVED SQLite database.

No external services, no LLM requests and no change to the editorial pipeline.
All operations are authenticated by the portal middleware before reaching here.
"""
from __future__ import annotations

import re

from app.db.repository import Repository, utc_now

KINDS = {"news", "video", "radar"}
MAX_NOTE_LENGTH = 4000
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
LATIN = re.compile(r"[A-Za-z]")


def content_language(value: str) -> str:
    """Conservative label, NOT automatic translation."""
    value = value[:4000]
    ru = len(CYRILLIC.findall(value))
    other = len(LATIN.findall(value))
    if ru >= 6 and ru >= other * 0.6:
        return "ru"
    if other >= 6 and other >= ru * 2:
        return "original"
    return "unknown"


def initialize(repository: Repository) -> None:
    with repository.connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS portal_reading_notes (
               kind TEXT NOT NULL CHECK(kind IN ('news','video','radar')),
               item_id INTEGER NOT NULL,
               note TEXT NOT NULL DEFAULT '',
               is_read INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0,1)),
               updated_at TEXT NOT NULL,
               PRIMARY KEY(kind,item_id)
            )"""
        )


def list_notes(repository: Repository) -> list[dict]:
    with repository.connection() as db:
        rows = db.execute(
            """SELECT kind,item_id,note,is_read,updated_at
            FROM portal_reading_notes
            ORDER BY updated_at DESC LIMIT 200"""
        ).fetchall()
    return [
        {
            "kind": row["kind"],
            "id": row["item_id"],
            "note": row["note"],
            "is_read": bool(row["is_read"]),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def get_note(repository: Repository, kind: str, item_id: int) -> dict:
    if kind not in KINDS or type(item_id) is not int or item_id < 1:
        raise ValueError("Unknown reading item")
    with repository.connection() as db:
        row = db.execute(
            """SELECT note,is_read,updated_at FROM portal_reading_notes
            WHERE kind=? AND item_id=?""", (kind, item_id),
        ).fetchone()
    return {
        "kind": kind, "id": item_id,
        "note": row["note"] if row else "",
        "is_read": bool(row["is_read"]) if row else False,
        "updated_at": row["updated_at"] if row else None,
    }


def save_note(
    repository: Repository, kind: str, item_id: int, note: str, is_read: bool
) -> dict:
    if kind not in KINDS or type(item_id) is not int or item_id < 1:
        raise ValueError("Unknown reading item")
    if not isinstance(note, str) or len(note) > MAX_NOTE_LENGTH or type(is_read) is not bool:
        raise ValueError("Invalid note")
    stamp = utc_now()
    with repository.connection() as db:
        db.execute(
            """INSERT INTO portal_reading_notes(kind,item_id,note,is_read,updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(kind,item_id) DO UPDATE SET
            note=excluded.note,is_read=excluded.is_read,
            updated_at=excluded.updated_at""",
            (kind, item_id, note, int(is_read), stamp),
        )
    return get_note(repository, kind, item_id)
