"""Stable per-task model selection for the personal OSVED instance."""
from __future__ import annotations

from typing import Protocol

# Initial allowlist based on advertised Codex Sale text models.
# Live availability and IDs must be validated with the account's /v1/models.
TEXT_MODELS = (
    "gpt-6-luna", "gpt-6.1-sol", "gpt-6-sol", "gpt-6-astra",
    "gpt-5.6-sol", "gpt-5.5", "gpt-5.6-terra", "gpt-5.6-luna",
    "glm-5.3-flash", "glm-5.3", "glm-5.2",
)
TASK_DEFAULTS = {
    "news": "gpt-6-luna",
    "research": "gpt-6.1-sol",
    "search": "gpt-6-luna",
    "video": "gpt-5.6-terra",
}
KEY_PREFIX = "codexsale.model."


class SettingsStore(Protocol):
    def get_runtime_setting(self, key: str) -> str | None: ...
    def set_runtime_setting(self, key: str, value: str) -> object: ...


def selected_model(store: SettingsStore, task: str) -> str:
    if task not in TASK_DEFAULTS:
        raise ValueError("Unknown model task")
    stored = store.get_runtime_setting(KEY_PREFIX + task)
    return stored if stored in TEXT_MODELS else TASK_DEFAULTS[task]


def set_model(store: SettingsStore, task: str, model: str) -> None:
    if task not in TASK_DEFAULTS:
        raise ValueError("Unknown model task")
    if model not in TEXT_MODELS:
        raise ValueError("Unsupported text model")
    store.set_runtime_setting(KEY_PREFIX + task, model)
