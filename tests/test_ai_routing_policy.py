import pytest

from app.llm.routing_policy import (
    fallback_permitted, resolve_selection, set_fallback_opt_in, set_selection,
)


class MemoryStore:
    def __init__(self):
        self.entries = {}

    def get_runtime_setting(self, key):
        return self.entries.get(key)

    def set_runtime_setting(self, key, value):
        self.entries[key] = value


def test_routing_precedence_and_legacy_telegram():
    store = MemoryStore()
    store.set_runtime_setting("codexsale.model.news", "legacy-model")
    assert resolve_selection(store, task="news").model == "legacy-model"
    catalog = {"verified-model-a", "verified-model-b"}
    set_selection(store, task="news", model="verified-model-a", verified_models=catalog)
    set_selection(store, task="news", model="verified-model-b", scope="profile", scope_id="main", verified_models=catalog)
    set_selection(store, task="news", model="verified-model-a", scope="source", scope_id="hackernews", verified_models=catalog)
    assert resolve_selection(store, task="news", source_id="hackernews", profile_id="main").origin == "source:hackernews"
    assert resolve_selection(store, task="news", profile_id="main").model == "verified-model-b"
    assert resolve_selection(store, task="news").origin == "task"


def test_default_fallback_disabled_and_opt_in():
    store = MemoryStore()
    assert not fallback_permitted(store)
    set_fallback_opt_in(store, True)
    assert fallback_permitted(store)
    set_fallback_opt_in(store, False)
    assert not fallback_permitted(store)


@pytest.mark.parametrize("kwargs", [
    {"task": "news", "model": "not-in-catalog", "verified_models": {"allowed"}},
    {"task": "image", "model": "allowed", "verified_models": {"allowed"}},
    {"task": "news", "model": "allowed", "scope": "source", "scope_id": "../escape", "verified_models": {"allowed"}},
    {"task": "news", "model": "allowed", "scope": "source", "verified_models": {"allowed"}},
    {"task": "news", "model": "allowed"},
])
def test_invalid_route_rejected_without_write(kwargs):
    store = MemoryStore()
    with pytest.raises(ValueError):
        set_selection(store, **kwargs)
    assert not store.entries


def test_legacy_default_has_no_verified_capability_claim():
    value = resolve_selection(MemoryStore(), task="news")
    assert value.provider == "codexsale"
    assert not value.verified
    assert value.origin == "default"
