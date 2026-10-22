"""Disconnect OAuth credentials only for an authenticated owner, never all accounts."""
from __future__ import annotations

import asyncio
import time

from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.web.oauth_vault import initialize_token_vault, read_tokens, save_tokens
from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN, signed_data
from tests.test_web_api import fixture


def test_github_disconnect_requires_session_csrf_and_owner(tmp_path):
    async def exercise():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        key = Fernet.generate_key().decode()
        settings.oauth_token_encryption_key = SecretStr(key)
        initialize_token_vault(repo)
        for owner in (123, 456):
            save_tokens(
                repo, encryption_key=key, provider="github", owner_id=owner,
                account_id=str(owner), access_token=f"test-{owner}",
            )
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            route = "/api/accounts/github/disconnect"
            assert (await client.post(route, json={"account_id": "123"})).status == 401
            login = await client.post(
                "/api/session",
                json={"init_data": signed_data(123, int(time.time()))},
            )
            csrf = (await login.json())["csrf"]
            headers = {"Cookie": f"{COOKIE}={login.cookies[COOKIE].value}"}
            assert (await client.post(
                route, json={"account_id": "123"}, headers=headers
            )).status == 403
            result = await client.post(
                route, json={"account_id": "123"},
                headers={**headers, "X-CSRF-Token": csrf},
            )
            assert result.status == 200
            data = await result.json()
            assert data["removed"] is True
            assert data["remote_authorization_revoked"] is False
            assert read_tokens(
                repo, encryption_key=key, provider="github", owner_id=123, account_id="123"
            ) is None
            assert read_tokens(
                repo, encryption_key=key, provider="github", owner_id=456, account_id="456"
            ) is not None
        finally:
            await client.close()

    asyncio.run(exercise())
