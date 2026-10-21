"""Bookmarked news shared between Telegram and the existing web_saved projection."""
from __future__ import annotations

from urllib.parse import urlsplit

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.card_predicates import finished_card_sql
from app.db.repository import Repository, utc_now


def ensure_bookmarks(repository: Repository) -> None:
    # This is the same schema as DashboardStore.initialize: one SQLite source of truth.
    with repository.connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS web_saved (
                kind TEXT NOT NULL, item_id INTEGER NOT NULL, saved INTEGER NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY(kind,item_id))"""
        )


def is_bookmarked(repository: Repository, card_id: int) -> bool:
    ensure_bookmarks(repository)
    with repository.connection() as db:
        row = db.execute(
            "SELECT saved FROM web_saved WHERE kind='news' AND item_id=?",
            (card_id,),
        ).fetchone()
    return bool(row and row["saved"])


def toggle_delivery(repository: Repository, *, delivery_id: int, owner_id: int) -> bool | None:
    ensure_bookmarks(repository)
    with repository.connection() as db:
        # Never let an arbitrary callback bookmark another owner's delivery.
        delivery = db.execute(
            "SELECT card_id FROM deliveries WHERE id=? AND chat_id=? "
            "AND delivery_status='sent'",
            (delivery_id, owner_id),
        ).fetchone()
        if delivery is None:
            return None
        card_id = int(delivery["card_id"])
        old = db.execute(
            "SELECT saved FROM web_saved WHERE kind='news' AND item_id=?", (card_id,)
        ).fetchone()
        selected = not bool(old and old["saved"])
        db.execute(
            "INSERT INTO web_saved(kind,item_id,saved,updated_at) VALUES('news',?,?,?) "
            "ON CONFLICT(kind,item_id) DO UPDATE SET saved=excluded.saved,"
            "updated_at=excluded.updated_at",
            (card_id, int(selected), utc_now()),
        )
    return selected


def saved_news(repository: Repository, limit: int = 10) -> list[dict]:
    ensure_bookmarks(repository)
    with repository.connection() as db:
        rows = db.execute(
            f"""SELECT c.id AS card_id, e.headline, c.primary_preview_url
            FROM web_saved b
            JOIN cards c ON c.id=b.item_id
            JOIN events e ON e.id=c.event_id
            WHERE b.kind='news' AND b.saved=1
              AND {finished_card_sql("c")}
            ORDER BY b.updated_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def bookmark_markup(
    keyboard: InlineKeyboardMarkup,
    delivery_id: int,
    *,
    saved: bool = False,
) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            text="✅ В избранном" if saved else "⭐ Сохранить",
            callback_data=f"osved_save:{delivery_id}",
        )
    ]
    # Keep «Подробнее» in the last row for existing navigation and reactions.
    last_row = keyboard.inline_keyboard[-1] if keyboard.inline_keyboard else []
    has_detail = any(
        (button.callback_data or "").startswith(("nd:", "dt:"))
        for button in last_row
    )
    at = len(keyboard.inline_keyboard) - (1 if has_detail else 0)
    keyboard.inline_keyboard.insert(at, row)
    return keyboard


def saved_links(rows: list[dict]) -> InlineKeyboardMarkup | None:
    buttons = []
    for row in rows:
        url = str(row.get("primary_preview_url") or "")
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            continue
        buttons.append(
            [InlineKeyboardButton(text=str(row["headline"])[:55], url=url)]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
