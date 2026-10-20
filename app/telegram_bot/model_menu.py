"""Owner-only provider/model navigation. Model IDs are loaded from the Codex Sale API."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.llm.model_registry import TASK_DEFAULTS, selected_model

PREFIX = "osved_models:"
PAGE_SIZE = 6
LABELS = {
    "news": "📰 Новости",
    "research": "🔬 Исследования",
    "search": "🔎 Поиск",
    "video": "🎬 Видео",
    "image": "🖼 Изображения",
    "audio": "🎙 Аудио / транскрипция",
}
COEFFICIENTS = {
    "gpt-6-astra": "11.25", "gpt-6.1-sol": "4", "gpt-6-sol": "3.8",
    "gpt-6-luna": "0.8", "gpt-5.6-sol": "4.5", "gpt-5.5": "4.5",
    "gpt-5.6-terra": "1.5", "gpt-5.6-luna": "0.9",
    "glm-5.3-flash": "1", "glm-5.3": "1.5", "glm-5.2": "1.5",
    "claude-opus-5-5": "20", "claude-fable-5-1": "20",
    "claude-opus-5": "12", "claude-opus-4-8": "12",
    "claude-opus-4-7": "10", "claude-opus-4-6": "10",
    "claude-sonnet-5-5": "11", "claude-haiku-4-5-20251001": "4",
    "claude-haiku-5-5": "9", "gpt-4o-transcribe": "1",
    "gpt-image-2.5-sunburst": "200", "gpt-image-2.5-flare": "200",
    "gpt-image-2": "200", "gpt-image-1.5": "200",
}
# DeepSeek V4.* is published on the website but not listed in this account's /models.
# Do not invent API identifiers or offer it as an executable choice.
PROVIDERS = {
    "gpt": "OpenAI / Codex",
    "glm": "GLM",
    "deepseek": "DeepSeek",
    "anthropic": "Anthropic / Claude",
    "other": "Другие",
}


def provider_for(model: str) -> str:
    name = model.lower()
    if name.startswith(("gpt-", "o1-", "o3-", "o4-", "chatgpt-")):
        return "gpt"
    if name.startswith("glm-"):
        return "glm"
    if name.startswith("deepseek-"):
        return "deepseek"
    if name.startswith(("claude-", "anthropic-")):
        return "anthropic"
    return "other"


def _type_for(model: str) -> str:
    name = model.lower()
    if "transcrib" in name or "whisper" in name or "speech-to-text" in name:
        return "audio"
    if "image" in name or "imagen" in name or "flux" in name:
        return "image"
    return "text"


def available_models(catalog: list[dict], task: str, provider: str | None = None) -> list[dict]:
    kind = "text" if task in {"news", "research", "search", "video"} else task
    result = []
    for item in catalog:
        model = str(item.get("id", ""))
        if not model or _type_for(model) != kind:
            continue
        if provider and provider_for(model) != provider:
            continue
        result.append(item)
    return sorted(result, key=lambda item: str(item["id"]))


def overview_text(store) -> str:
    rows = ["<b>⚙️ Codex Sale · Модели</b>", "", "Выбери задачу:"]
    for task in TASK_DEFAULTS:
        rows.append(f"{LABELS[task]} — <code>{selected_model(store, task)}</code>")
    return "\n".join(rows)


def overview_keyboard(store) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{LABELS[task]} · {selected_model(store, task)}",
            callback_data=f"{PREFIX}task:{task}",
        )] for task in TASK_DEFAULTS
    ])


def provider_text(store, task: str) -> str:
    return (
        f"<b>{LABELS[task]} · провайдер</b>\n\n"
        f"Выбрано: <code>{selected_model(store, task)}</code>\n"
        "Каталог моделей загружается из Codex Sale. Наличие модели в списке "
        "не гарантирует поддержку конкретного API-метода."
    )


def provider_keyboard(catalog: list[dict], task: str) -> InlineKeyboardMarkup:
    rows = []
    for key, label in PROVIDERS.items():
        count = len(available_models(catalog, task, key))
        if count:
            rows.append([InlineKeyboardButton(
                text=f"{label} · {count}",
                callback_data=f"{PREFIX}provider:{task}:{key}:0",
            )])
    rows.append([InlineKeyboardButton(text="← К задачам", callback_data=f"{PREFIX}home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def selection_text(store, task: str, provider: str = "gpt") -> str:
    return (
        f"<b>{LABELS[task]} · {PROVIDERS[provider]}</b>\n\n"
        f"Сейчас: <code>{selected_model(store, task)}</code>\n"
        "✅ — выбранная модель. Стоимость показывается только при наличии "
        "коэффициента из опубликованной таблицы тарифов."
    )


def selection_keyboard(
    store, task: str, provider: str = "gpt", page: int = 0,
    catalog: list[dict] | None = None,
) -> InlineKeyboardMarkup:
    rows = []
    options = available_models(catalog or [], task, provider)
    page = max(0, min(page, max(0, (len(options) - 1) // PAGE_SIZE)))
    current = selected_model(store, task)
    for item in options[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        model = str(item["id"])
        # Callback data is capped by Telegram at 64 bytes.
        if len(f"{PREFIX}set:{task}:{model}".encode()) > 64:
            continue
        rate = item.get("multiplier") or COEFFICIENTS.get(model)
        rate_label = f" · ×{rate}" if rate else ""
        rows.append([InlineKeyboardButton(
            text=("✅ " if model == current else "") + model + rate_label,
            callback_data=f"{PREFIX}set:{task}:{model}",
        )])
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(
            text="◀", callback_data=f"{PREFIX}provider:{task}:{provider}:{page - 1}",
        ))
    pages = max(1, (len(options) + PAGE_SIZE - 1) // PAGE_SIZE)
    navigation.append(InlineKeyboardButton(
        text=f"{page + 1}/{pages}", callback_data=f"{PREFIX}noop",
    ))
    if (page + 1) * PAGE_SIZE < len(options):
        navigation.append(InlineKeyboardButton(
            text="▶", callback_data=f"{PREFIX}provider:{task}:{provider}:{page + 1}",
        ))
    rows.append(navigation)
    rows.append([InlineKeyboardButton(
        text="← К провайдерам", callback_data=f"{PREFIX}task:{task}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)
