"""Google OAuth for YouTube read-only subscriptions.

Server-only credentials and token exchange over official Google endpoints.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CALLBACK_URL = "https://osved.tima.biz/api/accounts/youtube/callback"
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"


class YoutubeOAuthError(RuntimeError):
    pass


def authorization_url(client_id: str, state: str) -> str:
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client_id,
        "redirect_uri": CALLBACK_URL,
        "response_type": "code",
        "scope": YOUTUBE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })


def exchange_code(client_id: str, client_secret: str, code: str) -> tuple[str, str | None]:
    body = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": CALLBACK_URL,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = Request("https://oauth2.googleapis.com/token", data=body, method="POST",
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=12) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise YoutubeOAuthError("google_token_exchange_failed") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise YoutubeOAuthError("google_token_exchange_failed")
    refresh = payload.get("refresh_token")
    return payload["access_token"], refresh if isinstance(refresh, str) else None


def own_channel_id(access_token: str) -> str:
    req = Request(
        "https://www.googleapis.com/youtube/v3/channels?part=id&mine=true",
        headers={"Authorization": "Bearer " + access_token, "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=12) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise YoutubeOAuthError("youtube_identity_failed") from exc
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0].get("id"), str):
        raise YoutubeOAuthError("youtube_channel_not_found")
    return items[0]["id"]


class YoutubeReconnectRequired(YoutubeOAuthError):
    """Google rejected the refresh token; the owner must authorize again."""


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Exchange a saved refresh token on Google's fixed token endpoint."""
    if not client_id or not client_secret or not refresh_token:
        raise YoutubeReconnectRequired("youtube_reconnect_required")
    body = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    request = Request(
        "https://oauth2.googleapis.com/token", data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code in {400, 401}:
            raise YoutubeReconnectRequired("youtube_reconnect_required") from exc
        raise YoutubeOAuthError("youtube_token_refresh_failed") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise YoutubeOAuthError("youtube_token_refresh_failed") from exc
    access = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(access, str) or not access:
        raise YoutubeOAuthError("youtube_token_refresh_failed")
    return access
