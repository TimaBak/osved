"""Safe, extensible Telegram emoji presentation for news.

Custom emoji IDs must come from Telegram getStickerSet/getCustomEmojiStickers.
Never guess IDs from a sticker-set URL.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

PACKS = (
    "tgiosicons", "wbwrr_emoji", "CheekspinkShoutoEmoji", "picardiemoj",
    "Ordinary_Human", "Fric_TheFrog", "Animalspart2ShoutoEmoji",
    "PetsMemesEmoji", "berserkemojixoley", "AdaptivePixelEmoji",
    "RestrictedEmoji", "FlameEmoji", "cyberslav_by_TgEmodziBot",
    "adaptiveqp_by_emsetbot", "soyacorp_emojipack",
)
FALLBACK = {
    "news": "📰",
    "source": "🔗",
    "security": "🛡️",
    "ai": "🤖",
    "development": "💻",
    "business": "📈",
}
VALID_ID = re.compile(r"^[0-9]{6,30}$")


def load_custom_emoji_ids(path: str | Path | None = None) -> dict[str, str]:
    """Optional mapping of semantic roles to Telegram-verified numeric IDs."""
    if path is None:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        role: str(data[role])
        for role in FALLBACK
        if role in data and VALID_ID.fullmatch(str(data[role]))
    }


def emoji_html(role: str, ids: dict[str, str] | None = None) -> str:
    symbol = FALLBACK.get(role, FALLBACK["news"])
    custom_id = (ids or {}).get(role, "")
    if VALID_ID.fullmatch(str(custom_id)):
        return f'<tg-emoji emoji-id="{html.escape(str(custom_id))}">{symbol}</tg-emoji>'
    return symbol


def headline_role(headline: str) -> str:
    text = headline.casefold()
    if any(word in text for word in ("security", "vulnerab", "bot", "кибер", "уязв")):
        return "security"
    if any(word in text for word in ("ai", "model", "llm", "агент", "нейросет")):
        return "ai"
    if any(word in text for word in ("github", "code", "rust", "python", "разработ")):
        return "development"
    if any(word in text for word in ("business", "revenue", "startup", "бизнес")):
        return "business"
    return "news"
