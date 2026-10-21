"""Owner-only, persistent Telegram navigation with honest Unicode icon fallbacks.

Telegram custom emoji are not used until the exact emoji IDs are verified.
All callback names stay below Telegram's 64-byte limit.
"""
from __future__ import annotations

import html

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.web.content import public_url

LABELS = {
    "home": "🏠 Главная",
    "feed": "📰 Моя лента",
    "radar": "📡 Радар",
    "sources": "🗂 Источники",
    "topics": "🎯 Интересы",
    "favorites": "⭐ Избранное",
    "media": "🎬 Медиалаб",
    "settings": "⚙️ Настройки",
    "telegram": "✈️ Telegram-каналы",
    "youtube": "📺 YouTube-каналы",
    "videos": "🎥 Новые видео",
    "preferences": "🧠 Мои реакции",
    "week": "📊 Аналитика",
    "site": "🌐 Веб-кабинет",
}
TEXT_TO_SECTION = {label: key for key, label in LABELS.items()}
PRIMARY = (
    ("feed", "radar"),
    ("sources", "topics"),
    ("favorites", "media"),
    ("settings", "home"),
    ("site",),
)
HOME_INLINE = (
    ("feed", "radar"),
    ("sources", "topics"),
    ("favorites", "media"),
    ("settings", "week"),
)
SECTION_INLINE = {
    "media": (
        ("videos", "youtube"),
        ("telegram", "site"),
        ("home",),
    ),
    "settings": (
        ("topics", "preferences"),
        ("sources", "telegram"),
        ("youtube", "site"),
        ("home",),
    ),
    "favorites": (("feed", "site"), ("home",)),
    "topics": (("sources", "preferences"), ("home",)),
    "radar": (("sources", "topics"), ("home",)),
}


def persistent_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=LABELS[name]) for name in row] for row in PRIMARY
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери раздел ОСВЕД",
    )


def inline_menu(section: str = "home") -> InlineKeyboardMarkup:
    rows = HOME_INLINE if section == "home" else SECTION_INLINE.get(section, (("home",),))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=LABELS[name],
                    callback_data=f"osved_menu:{name}",
                )
                for name in row
            ]
            for row in rows
        ]
    )


def parse_section(value: str | None) -> str | None:
    if not value:
        return None
    section = value.removeprefix("osved_menu:")
    return section if section in LABELS else None

def radar_preview(repository, limit: int = 6) -> tuple[str, InlineKeyboardMarkup | None]:
    """Expose actual *unverified* candidates without fabricating news."""
    with repository.connection() as db:
        rows = db.execute(
            """SELECT e.headline, si.source_url, s.name AS source_name
            FROM events e
            JOIN source_items si ON si.id=e.primary_source_item_id
            JOIN sources s ON s.id=si.source_id
            WHERE e.status='candidate'
            ORDER BY e.latest_source_at DESC, e.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    if not rows:
        return ("📡 Новых сигналов пока нет. Проверенные новости появятся в ленте.", None)
    lines = [
        "<b>📡 Последние сигналы</b>",
        "<i>Ещё не прошли проверку фактов. Это не готовые новости.</i>",
    ]
    actions = []
    for i, row in enumerate(rows, 1):
        lines.append(
            f"\n{i}. <b>{html.escape(str(row['headline'])[:170])}</b>"
            f"\n   {html.escape(str(row['source_name'])[:70])}"
        )
        url = public_url(row["source_url"])
        if url:
            actions.append([InlineKeyboardButton(text=f"Источник {i} ↗", url=url)])
    actions.append(
        [InlineKeyboardButton(text="🏠 Главная", callback_data="osved_menu:home")]
    )
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=actions)
