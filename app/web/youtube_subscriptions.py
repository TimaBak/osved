"""Read owner's YouTube subscriptions without exposing OAuth credentials."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class YoutubeSubscriptionsError(RuntimeError):
    pass


def list_subscriptions(token: str, *, page_token: str = "") -> dict:
    if not isinstance(page_token, str) or len(page_token) > 256 or not page_token.isascii() or not all(ch.isalnum() or ch in "-_" for ch in page_token):
        raise ValueError("Invalid page token")
    query = {"part": "snippet", "mine": "true", "maxResults": "50"}
    if page_token:
        query["pageToken"] = page_token
    url = "https://www.googleapis.com/youtube/v3/subscriptions?" + urlencode(query)
    request = Request(url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/json",
        "User-Agent": "OSVED",
    })
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise YoutubeSubscriptionsError("youtube_subscriptions_fetch_failed") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise YoutubeSubscriptionsError("youtube_subscriptions_invalid_payload")
    channels = []
    for item in payload["items"][:50]:
        snippet = item.get("snippet") if isinstance(item, dict) else None
        resource = snippet.get("resourceId") if isinstance(snippet, dict) else None
        channel_id = resource.get("channelId") if isinstance(resource, dict) else None
        if not isinstance(channel_id, str) or not channel_id.startswith("UC") or len(channel_id) != 24:
            continue
        channels.append({
            "channel_id": channel_id,
            "title": str(snippet.get("title") or channel_id)[:180],
            "url": "https://www.youtube.com/channel/" + channel_id,
        })
    next_token = payload.get("nextPageToken")
    return {"channels": channels, "next_page_token": next_token if isinstance(next_token, str) else None}
