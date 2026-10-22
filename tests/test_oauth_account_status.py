"""Personal OAuth account status requires the OSVED owner session."""
from __future__ import annotations

import asyncio
import time

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN, signed_data
from tests.test_web_api import fixture


def test_account_readiness_is_private_and_never_claims_login_ready(tmp_path):
    async def run():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        settings.oauth_github_client_id = "test-client"
        settings.oauth_github_client_secret = SecretStr("test-secret")
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            assert (await client.get("/api/accounts/status")).status == 401
            login = await client.post(
                "/api/session",
                json={"init_data": signed_data(123, int(time.time()))},
            )
            assert login.status == 200
            token = login.cookies[COOKIE].value
            response = await client.get(
                "/api/accounts/status", headers={"Cookie": f"{COOKIE}={token}"}
            )
            assert response.status == 200
            data = await response.json()
            assert data["accounts"]["github"]["configuration_present"]
            assert not data["accounts"]["github"]["login_available"]
            assert not data["accounts"]["youtube"]["connected"]
            assert "test-secret" not in str(data)
        finally:
            await client.close()

    asyncio.run(run())
