from app.llm.model_registry import set_model
from app.telegram_bot.model_menu import (
    overview_keyboard,
    overview_text,
    provider_keyboard,
    selection_keyboard,
    selection_text,
)


class MemoryStore:
    def __init__(self):
        self.values = {}

    def get_runtime_setting(self, key):
        return self.values.get(key)

    def set_runtime_setting(self, key, value):
        self.values[key] = value


def test_model_menu_shows_tasks_and_selected_models():
    store = MemoryStore()
    keyboard = overview_keyboard(store)
    assert len(keyboard.inline_keyboard) == 6
    assert "gpt-6-luna" in overview_text(store)
    assert keyboard.inline_keyboard[0][0].callback_data == "osved_models:task:news"


def test_model_change_updates_same_menu_state():
    store = MemoryStore()
    set_model(store, "news", "gpt-5.6-terra")
    assert "gpt-5.6-terra" in selection_text(store, "news")
    assert "gpt-5.6-terra" in overview_text(store)
    catalog = [{"id": "gpt-5.6-terra"}, {"id": "gpt-6-luna"}]
    keyboard = selection_keyboard(store, "news", catalog=catalog)
    assert any(row[0].text == "✅ gpt-5.6-terra" for row in keyboard.inline_keyboard)
    assert keyboard.inline_keyboard[-1][0].callback_data == "osved_models:task:news"
    providers = provider_keyboard(catalog, "news")
    assert providers.inline_keyboard[0][0].text.startswith("OpenAI / Codex")
