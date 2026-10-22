"""Only public GitHub repositories can appear in the owner preview."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.web.github_subscriptions import list_repositories
from app.web.oauth_vault import initialize_token_vault, save_tokens
from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN, signed_data
from tests.test_web_api import fixture


def test_github_repository_preview_owner_only(tmp_path):
    async def run():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        key = Fernet.generate_key().decode()
        settings.oauth_token_encryption_key = SecretStr(key)
        initialize_token_vault(repo)
        save_tokens(
            repo, encryption_key=key, provider="github", owner_id=123,
            account_id="9876", access_token="sample-token",
        )
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            assert (await client.get("/api/accounts/github/subscriptions")).status == 401
            login = await client.post(
                "/api/session", json={"init_data": signed_data(123, int(time.time()))}
            )
            cookie = login.cookies[COOKIE].value
            with patch(
                "app.web.github_subscriptions.list_repositories",
                return_value=[{"full_name": "example/project", "url":
                               "https://github.com/example/project", "description": "Sample"}],
            ) as listing:
                response = await client.get(
                    "/api/accounts/github/subscriptions?collection=starred",
                    headers={"Cookie": f"{COOKIE}={cookie}"},
                )
                assert response.status == 200
                body = await response.json()
                assert body["repositories"][0]["full_name"] == "example/project"
                assert "sample-token" not in str(body)
                listing.assert_called_once_with("sample-token", collection="starred", page=1)
                bad = await client.get(
                    "/api/accounts/github/subscriptions?collection=invalid",
                    headers={"Cookie": f"{COOKIE}={cookie}"},
                )
                assert bad.status == 400
        finally:
            await client.close()

    asyncio.run(run())


def test_github_collection_rejects_invalid_values_before_network():
    for collection in ("", "issues", "../admin"):
        try:
            list_repositories("secret", collection=collection)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid collection accepted")
