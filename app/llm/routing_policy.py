"""Shared, side-effect-free AI model routing policy for OSVED surfaces.

No paid call or fallback is performed by this module. Stored choices share the
existing runtime_settings table already used by Telegram and web.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.llm.model_registry import TASK_DEFAULTS, TEXT_MODELS

_SCOPE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
_PROVIDER = "codexsale"
_PREFIX = "ai.routing."
_TEXT_TASKS = frozenset({"news", "research", "search", "video"})


class Store(Protocol):
    def get_runtime_setting(self, key: str) -> str | None: ...
    def set_runtime_setting(self, key: str, value: str) -> object: ...


@dataclass(frozen=True)
class Selection:
    provider: str
    model: str
    origin: str
    verified: bool = False


def _key(task: str, scope: str | None, scope_id: str | None) -> str:
    if task not in _TEXT_TASKS:
        raise ValueError("Unsupported text task")
    if scope is None:
        if scope_id is not None:
            raise ValueError("Scope ID without scope")
        return _PREFIX + "task." + task
    if scope not in {"source", "profile", "scenario"}:
        raise ValueError("Invalid scope")
    if not isinstance(scope_id, str) or not _SCOPE_ID.fullmatch(scope_id):
        raise ValueError("Invalid scope ID")
    return f"{_PREFIX}{scope}.{scope_id}.{task}"


def set_selection(
    store: Store, *, task: str, model: str,
    scope: str | None = None, scope_id: str | None = None,
    verified_models: set[str] | None = None,
) -> None:
    """Persist only models confirmed by an operator-supplied live catalog."""
    key = _key(task, scope, scope_id)
    if not verified_models or model not in verified_models:
        raise ValueError("Model not verified for this account")
    if not isinstance(model, str) or not model or len(model) > 128:
        raise ValueError("Invalid model ID")
    store.set_runtime_setting(key, model)


def resolve_selection(
    store: Store, *, task: str,
    source_id: str | None = None, profile_id: str | None = None,
    scenario_id: str | None = None,
) -> Selection:
    """Priority: source > scenario > profile > task > old Telegram task > default.

    Historical Telegram keys stay readable so both clients share one database
    until the legacy selection screen is migrated.
    """
    _key(task, None, None)
    for scope, ident in (("source", source_id), ("scenario", scenario_id), ("profile", profile_id)):
        if ident is None:
            continue
        key = _key(task, scope, ident)
        model = store.get_runtime_setting(key)
        if model:
            return Selection(_PROVIDER, model, f"{scope}:{ident}")
    stored = store.get_runtime_setting(_key(task, None, None))
    if stored:
        return Selection(_PROVIDER, stored, "task")
    legacy = store.get_runtime_setting("codexsale.model." + task)
    if legacy:
        return Selection(_PROVIDER, legacy, "telegram-legacy")
    return Selection(_PROVIDER, TASK_DEFAULTS[task], "default")


def fallback_permitted(store: Store) -> bool:
    """OpenRouter cannot be used unless owner explicitly opts in."""
    return store.get_runtime_setting(_PREFIX + "openrouter.opt_in") == "true"


def set_fallback_opt_in(store: Store, enabled: bool) -> None:
    store.set_runtime_setting(_PREFIX + "openrouter.opt_in", "true" if enabled else "false")
