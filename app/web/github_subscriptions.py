"""Read-only GitHub starred and watched repositories through connected OAuth.

Only fetch from the fixed GitHub API host; never send bearer tokens to the browser.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GithubSubscriptionsError(RuntimeError):
    pass


def list_repositories(token: str, *, collection: str, page: int = 1) -> list[dict]:
    if collection not in {"starred", "watching"} or type(page) is not int or not 1 <= page <= 10:
        raise ValueError("Invalid GitHub collection or page")
    path = "/user/starred" if collection == "starred" else "/user/subscriptions"
    request = Request(
        f"https://api.github.com{path}?per_page=30&page={page}",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "OSVED",
        },
    )
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.load(response)
    except (HTTPError, URLError, ValueError, TimeoutError) as exc:
        raise GithubSubscriptionsError("github_subscription_fetch_failed") from exc
    if not isinstance(payload, list):
        raise GithubSubscriptionsError("github_subscription_invalid_payload")
    repositories = []
    for record in payload[:30]:
        if not isinstance(record, dict) or record.get("private") is not False:
            continue
        full_name = record.get("full_name")
        if not isinstance(full_name, str):
            continue
        from app.web.public_sources import SourceInputError, normalize

        try:
            canonical, _, url = normalize("github", full_name)
        except SourceInputError:
            continue
        repositories.append({
            "full_name": canonical,
            "url": url,
            "description": str(record.get("description") or "")[:240],
        })
    return repositories
