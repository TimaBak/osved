"""Validate read-only YouTube subscription parsing without contacting Google."""
from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from app.web.youtube_subscriptions import list_subscriptions


def test_youtube_subscriptions_filters_invalid_channels_and_returns_page():
    valid_id = "UC" + "a" * 22
    payload = {
        "items": [
            {"snippet": {"title": "Demo", "resourceId": {"channelId": valid_id}}},
            {"snippet": {"title": "Bad", "resourceId": {"channelId": "invalid"}}},
        ],
        "nextPageToken": "PAGE_2",
    }

    class FakeResponse:
        def __enter__(self):
            return io.BytesIO(json.dumps(payload).encode())

        def __exit__(self, *args):
            return False

    with patch("app.web.youtube_subscriptions.urlopen", return_value=FakeResponse()):
        result = list_subscriptions("secret")
    assert result == {
        "channels": [{"channel_id": valid_id, "title": "Demo",
                      "url": "https://www.youtube.com/channel/" + valid_id}],
        "next_page_token": "PAGE_2",
    }


@pytest.mark.parametrize("page", ["..", "bad&x=1", "a" * 257])
def test_bad_page_token_rejected_without_network(page):
    with pytest.raises(ValueError):
        list_subscriptions("secret", page_token=page)
