"""Presentation-only dismissals: closing a card never changes recommendations.

Unlike feedback, these flags are a reversible personal inbox action.
Stored per card identity; verification and original data remain untouched.
"""
from __future__ import annotations

from app.db.repository import Repository, utc_now

KINDS = {"news", "video", "radar"}


def initialize(repository: Repository) -> None:
    with repository.connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS portal_hidden_items (
                kind TEXT NOT NULL CHECK(kind IN ('news','video','radar')),
                item_id INTEGER NOT NULL CHECK(item_id > 0),
                hidden_at TEXT NOT NULL,
                PRIMARY KEY(kind,item_id)
            )"""
        )


def set_hidden(repository: Repository, kind: str, item_id: int, hidden: bool) -> None:
    if kind not in KINDS or type(item_id) is not int or item_id < 1 or type(hidden) is not bool:
        raise ValueError("invalid_hidden_item")
    with repository.connection() as db:
        if hidden:
            db.execute(
                """INSERT INTO portal_hidden_items(kind,item_id,hidden_at)
                VALUES(?,?,?) ON CONFLICT(kind,item_id)
                DO UPDATE SET hidden_at=excluded.hidden_at""",
                (kind, item_id, utc_now()),
            )
        else:
            db.execute(
                "DELETE FROM portal_hidden_items WHERE kind=? AND item_id=?",
                (kind, item_id),
            )


def hidden_snapshot(repository: Repository) -> list[dict]:
    with repository.connection() as db:
        rows = db.execute(
            "SELECT kind,item_id,hidden_at FROM portal_hidden_items "
            "ORDER BY hidden_at DESC LIMIT 500"
        ).fetchall()
    return [
        {"kind": row["kind"], "id": row["item_id"], "hidden_at": row["hidden_at"]}
        for row in rows
    ]
