from unittest.mock import patch

import pytest

from app.llm.codexsale import CodexSaleClient, CodexSaleError
from app.llm.model_registry import selected_model, set_model


class Store:
    def __init__(self):
        self.data = {}

    def get_runtime_setting(self, key):
        return self.data.get(key)

    def set_runtime_setting(self, key, value):
        self.data[key] = value


def test_model_store_roundtrip():
    store = Store()
    assert selected_model(store, "news") == "gpt-6-luna"
    set_model(store, "news", "gpt-5.6-terra")
    assert selected_model(store, "news") == "gpt-5.6-terra"


def test_model_rejects_untrusted_name():
    with pytest.raises(ValueError):
        set_model(Store(), "news", "unknown-model")


def test_rejects_non_codex_origin():
    with pytest.raises(CodexSaleError):
        CodexSaleClient("test-secret", "https://attacker.invalid/v1")


def test_models_parse_response():
    client = CodexSaleClient("test-secret")
    mock_data = {"data": [{"id": "gpt-6-luna"}, {"oops": 1}]}
    with patch.object(CodexSaleClient, "_request", return_value=mock_data):
        assert client.models() == [{"id": "gpt-6-luna"}]


def test_image_requires_capability_allowlist():
    with pytest.raises(ValueError, match="capability"):
        set_model(Store(), "image", "gpt-6-luna")
