"""OAuth expiry recovery and GitHub source import regressions."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest
from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.web.oauth_vault import initialize_token_vault, read_tokens, save_tokens
from app.web.portal import COOKIE, create_portal
from app.web.youtube_access import with_youtube_access
from app.web.youtube_oauth import YoutubeReconnectRequired
from app.web.youtube_subscriptions import YoutubeSubscriptionsAuthError
from tests.test_portal import BOT_TOKEN, signed_data
from tests.test_web_api import fixture


def test_youtube_expired_access_refreshed_once_and_keeps_refresh_token(tmp_path):
    settings, repo, _ = fixture(tmp_path)
    key = Fernet.generate_key().decode()
    settings.oauth_token_encryption_key = SecretStr(key)
    settings.oauth_google_client_id = "test-id.apps.googleusercontent.com"
    settings.oauth_google_client_secret = SecretStr("secret")
    initialize_token_vault(repo)
    account = "UC" + "a" * 22
    save_tokens(
        repo, encryption_key=key, provider="youtube", owner_id=123,
        account_id=account, access_token="expired", refresh_token="stored-refresh",
    )
    seen = []

    def operation(access):
        seen.append(access)
        if access == "expired":
            raise YoutubeSubscriptionsAuthError("youtube_token_expired")
        return {"channels": []}

    with patch(
        "app.web.youtube_access.refresh_access_token", return_value="new-access",
    ) as refresh:
        assert with_youtube_access(settings, repo, 123, account, operation) == {
            "channels": [],
        }
        refresh.assert_called_once_with(
            "test-id.apps.googleusercontent.com", "secret", "stored-refresh",
        )
    assert seen == ["expired", "new-access"]
    assert read_tokens(
        repo, encryption_key=key, provider="youtube", owner_id=123,
        account_id=account,
    ) == ("new-access", "stored-refresh")


def test_youtube_requires_reconnect_when_refresh_token_unavailable(tmp_path):
    settings, repo, _ = fixture(tmp_path)
    key = Fernet.generate_key().decode()
    settings.oauth_token_encryption_key = SecretStr(key)
    initialize_token_vault(repo)
    account = "UC" + "a" * 22
    save_tokens(
        repo, encryption_key=key, provider="youtube", owner_id=123,
        account_id=account, access_token="expired",
    )

    def operation(_):
        raise YoutubeSubscriptionsAuthError("youtube_token_expired")

    with pytest.raises(YoutubeReconnectRequired):
        with_youtube_access(settings, repo, 123, account, operation)


def test_github_import_accepts_locator_and_csrf(tmp_path):
    async def scenario():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            path = "/api/public-sources/add"
            assert (await client.post(path, json={
                "kind": "github", "locator": "Example/Repo",
            })).status == 401
            login = await client.post(
                "/api/session",
                json={"init_data": signed_data(123, int(time.time()))},
            )
            csrf = (await login.json())["csrf"]
            headers = {"Cookie": f"{COOKIE}={login.cookies[COOKIE].value}"}
            assert (await client.post(path, headers=headers, json={
                "kind": "github", "locator": "Example/Repo",
            })).status == 403
            headers["X-CSRF-Token"] = csrf
            result = await client.post(path, headers=headers, json={
                "kind": "github", "locator": "Example/Repo", "topic": "",
            })
            assert result.status == 200
            body = await result.json()
            assert body["id"].startswith("user_github_")
            assert not body["existing"]
            repeated = await client.post(path, headers=headers, json={
                "kind": "github", "locator": "Example/Repo",
            })
            assert repeated.status == 200
            assert (await repeated.json())["existing"] is True
            removed = await client.post(
                "/api/public-sources/remove", headers=headers,
                json={"id": body["id"]},
            )
            assert removed.status == 200
        finally:
            await client.close()

    asyncio.run(scenario())
