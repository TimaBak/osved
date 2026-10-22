"""Regression: importing a connected YouTube subscription must not need public RSS."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.web.oauth_vault import initialize_token_vault, save_tokens
from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN, signed_data
from tests.test_web_api import fixture

CHANNEL = "UC" + "a" * 22


def test_authenticated_subscription_import_without_public_feed(tmp_path):
    async def run():
        settings, repository, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        key = Fernet.generate_key().decode()
        settings.oauth_token_encryption_key = SecretStr(key)
        initialize_token_vault(repository)
        save_tokens(
            repository, encryption_key=key, provider="youtube", owner_id=123,
            account_id="UC" + "b" * 22, access_token="test-access",
        )
        client = TestClient(TestServer(create_portal(settings, repository)))
        await client.start_server()
        try:
            path = "/api/accounts/youtube/channels/import"
            assert (await client.post(path, json={"channel_id": CHANNEL})).status == 401
            login = await client.post(
                "/api/session", json={"init_data": signed_data(123, int(time.time()))},
            )
            csrf = (await login.json())["csrf"]
            headers = {"Cookie": f"{COOKIE}={login.cookies[COOKIE].value}"}
            assert (await client.post(
                path, headers=headers, json={"channel_id": CHANNEL},
            )).status == 403
            headers["X-CSRF-Token"] = csrf
            assert (await client.post(
                path, headers=headers, json={"channel_id": "../../not-a-channel"},
            )).status == 400
            with patch(
                "app.web.youtube_subscriptions.verify_owner_subscription",
                return_value=None,
            ):
                forbidden = await client.post(
                    path, headers=headers, json={"channel_id": CHANNEL},
                )
                assert forbidden.status == 409
                assert (await forbidden.json())["error"] == "youtube_not_in_subscriptions"
            with patch(
                "app.web.youtube_subscriptions.verify_owner_subscription",
                return_value="Достоверное имя канала",
            ) as verify:
                added = await client.post(
                    path, headers=headers, json={"channel_id": CHANNEL},
                )
                assert added.status == 200
                data = await added.json()
                assert data["title"] == "Достоверное имя канала"
                assert data["existing"] is False
                verify.assert_called_with("test-access", CHANNEL)
                repeated = await client.post(
                    path, headers=headers, json={"channel_id": CHANNEL},
                )
                assert (await repeated.json())["existing"] is True
            overview = await client.get("/api/overview", headers={
                "Cookie": headers["Cookie"],
            })
            sources = (await overview.json())["sources"]
            assert any(source["id"] == data["source_id"] for source in sources)
        finally:
            await client.close()

    asyncio.run(run())
