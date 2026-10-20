"""Inline model-selection menu for the owner's private Telegram bot."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.llm.model_registry import TASK_DEFAULTS, TEXT_MODELS, selected_model

LABELS = {
    "news": "📰 Новости",
    "research": "🔬 Исследования",
    "search": "🔎 Поиск",
    "video": "🎬 Видео",
}
PREFIX = "osved_models:"


def overview_text(store) -> str:
    lines = ["<b>⚙️ Codex Sale · Модели</b>", "", "Выбери задачу, чтобы изменить модель:"]
    for task in TASK_DEFAULTS:
        lines.append(f"{LABELS[task]} — <code>{selected_model(store, task)}</code>")
    return "\n".join(lines)


def overview_keyboard(store) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{LABELS[task]} · {selected_model(store, task)}",
            callback_data=f"{PREFIX}task:{task}",
        )] for task in TASK_DEFAULTS
    ])


def selection_text(store, task: str) -> str:
    return (
        f"<b>{LABELS[task]} · выбор модели</b>\n\n"
        f"Сейчас: <code>{selected_model(store, task)}</code>\n"
        "Нажми модель ниже. Выбор сохранится."
    )


def selection_keyboard(store, task: str) -> InlineKeyboardMarkup:
    current = selected_model(store, task)
    rows = [
        [InlineKeyboardButton(
            text=("✅ " if model == current else "") + model,
            callback_data=f"{PREFIX}set:{task}:{model}",
        )] for model in TEXT_MODELS
    ]
    rows.append([InlineKeyboardButton(text="← К задачам", callback_data=f"{PREFIX}home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
