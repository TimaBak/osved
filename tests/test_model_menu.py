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
    assert any(row[0].text.startswith("✅ gpt-5.6-terra · ×1.5") for row in keyboard.inline_keyboard)
    assert keyboard.inline_keyboard[-1][0].callback_data == "osved_models:task:news"
    providers = provider_keyboard(catalog, "news")
    assert providers.inline_keyboard[0][0].text.startswith("OpenAI / Codex")


def test_claude_and_image_audio_coefficients():
    from app.telegram_bot.model_menu import available_models, provider_for

    catalog = [
        {"id": "claude-opus-5-5"},
        {"id": "gpt-image-2.5-flare"},
        {"id": "gpt-4o-transcribe"},
    ]
    store = MemoryStore()
    assert provider_for("claude-opus-5-5") == "anthropic"
    assert len(available_models(catalog, "news", "anthropic")) == 1
    image_button = selection_keyboard(store, "image", "gpt", 0, catalog)
    assert "×200" in image_button.inline_keyboard[0][0].text
    audio_button = selection_keyboard(store, "audio", "gpt", 0, catalog)
    assert "×1" in audio_button.inline_keyboard[0][0].text
