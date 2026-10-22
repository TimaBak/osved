"""Official GitHub OAuth code exchange and account identity lookup.

Credentials never leave the server. No GitHub access token is returned to web UI.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
CALLBACK_URL = "https://osved.tima.biz/api/accounts/github/callback"


class GithubOAuthError(RuntimeError):
    pass


def authorization_url(client_id: str, state: str) -> str:
    return GITHUB_AUTHORIZE + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": CALLBACK_URL,
        "state": state,
        "scope": "read:user",
    })


def exchange_code(client_id: str, client_secret: str, code: str) -> str:
    payload = json.dumps({
        "client_id": client_id, "client_secret": client_secret,
        "code": code, "redirect_uri": CALLBACK_URL,
    }).encode("utf-8")
    req = Request(
        "https://github.com/login/oauth/access_token", data=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=12) as response:
            data = json.load(response)
    except (HTTPError, URLError, ValueError, TimeoutError) as exc:
        raise GithubOAuthError("github_token_exchange_failed") from exc
    if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
        raise GithubOAuthError("github_token_exchange_failed")
    return data["access_token"]


def github_identity(token: str) -> str:
    req = Request(
        "https://api.github.com/user",
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "User-Agent": "OSVED"},
    )
    try:
        with urlopen(req, timeout=12) as response:
            data = json.load(response)
    except (HTTPError, URLError, ValueError, TimeoutError) as exc:
        raise GithubOAuthError("github_identity_failed") from exc
    if not isinstance(data, dict) or not isinstance(data.get("id"), int):
        raise GithubOAuthError("github_identity_failed")
    return str(data["id"])
