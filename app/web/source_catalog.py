"""Display-only source taxonomy, built from the authoritative source registry.

No new subscriptions, no OAuth credentials, no network requests. Groups reflect
existing source kinds, not inferred account access or trusted verification.
"""
from __future__ import annotations

PLATFORMS: dict[str, tuple[str, str, str]] = {
    "telegram": ("Мессенджеры", "Telegram", "Каналы и публичные сообщения"),
    "x": ("Социальные сети", "X", "Авторы и публикации"),
    "reddit": ("Сообщества", "Reddit", "Сообщества и обсуждения"),
    "youtube": ("Видео", "YouTube", "Каналы и видео"),
    "github": ("Разработка", "GitHub", "Репозитории и релизы"),
    "rss": ("Сайты и RSS", "RSS / Atom", "Ленты сайтов и блогов"),
    "web": ("Сайты и RSS", "Веб-сайты", "Официальные и экспертные сайты"),
    "v2ex": ("Сообщества", "V2EX", "Технические сообщества"),
    "weibo": ("Социальные сети", "Weibo", "Социальные публикации"),
    "zhihu": ("Сообщества", "Zhihu", "Вопросы и экспертные ответы"),
}
PLATFORM_GROUPS = (
    "Мессенджеры", "Социальные сети", "Сообщества", "Видео",
    "Разработка", "Сайты и RSS", "Другие платформы",
)


def present_source(source: dict) -> dict:
    """Add explicit provider, platform family and topic categories."""
    result = dict(source)
    kind = str(result.get("kind") or "").lower()
    category, platform, description = PLATFORMS.get(
        kind, ("Другие платформы", kind or "Не определено", "Другой источник")
    )
    result["platform"] = platform
    result["category"] = category
    result["platform_description"] = description
    result["connection_mode"] = "public_source"
    # The source registry can attach multiple topics; do not hallucinate them.
    topics = result.get("topics")
    result["topics"] = [
        item for item in topics if isinstance(item, str) and item.strip()
    ][:30] if isinstance(topics, list) else []
    result["topic_status"] = "configured" if result["topics"] else "unclassified"
    result["account_connected"] = False
    return result


def public_capabilities(settings) -> dict:
    """Explain why a feature is disabled WITHOUT exposing any key or token."""
    ai = settings.openrouter_api_key is not None
    captions = settings.monid_api_key is not None
    enabled = bool(settings.video_reports_enabled)
    guarded = bool(settings.video_report_budget_enabled)
    reason = (
        "video_generation_disabled" if not enabled else
        "ai_provider_unconfigured" if not ai else
        "transcription_provider_unconfigured" if not captions else
        "video_budget_guard_disabled" if not guarded else
        None
    )
    return {
        "video": {
            "ready": reason is None,
            "reason": reason,
            "cached_available_without_provider": True,
            "requires": ["AI API", "субтитры", "лимит расходов"],
        },
        "translation": {
            "ready": False, "reason": "translation_engine_not_connected",
            "mode": "planned_on_demand", "target_language": "ru",
        },
        "image_ai": {
            "ready": False, "reason": "image_engine_not_connected",
            "vector_svg_available": True,
        },
        "accounts": {
            "oauth_ready": False,
            "mode": "public_sources_only",
        },
        "privacy": {"credentials_exposed": False},
    }
