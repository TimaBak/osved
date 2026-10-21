"""Owner-only, persistent Telegram navigation with honest Unicode icon fallbacks.

Telegram custom emoji are not used until the exact emoji IDs are verified.
All callback names stay below Telegram's 64-byte limit.
"""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

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
