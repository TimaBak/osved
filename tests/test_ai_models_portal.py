"""AI settings are readable only by the authenticated owner."""
from __future__ import annotations

import asyncio
import time

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN, signed_data
from tests.test_web_api import fixture


def test_ai_models_requires_owner_and_reads_existing_settings(tmp_path):
    async def exercise():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        repo.set_runtime_setting("codexsale.model.news", "test-legacy-model")
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            no_auth = await client.get("/api/ai/models")
            assert no_auth.status == 401
            auth = await client.post(
                "/api/session", json={"init_data": signed_data(123, int(time.time()))}
            )
            assert auth.status == 200
            cookie = auth.cookies[COOKIE].value
            result = await client.get(
                "/api/ai/models", headers={"Cookie": f"{COOKIE}={cookie}"}
            )
            assert result.status == 200
            data = await result.json()
            assert data["selections"]["news"]["model"] == "test-legacy-model"
            assert data["selections"]["news"]["origin"] == "telegram-legacy"
            assert data["model_execution_enabled"] is False
            assert "api_key" not in str(data).lower()
        finally:
            await client.close()

    asyncio.run(exercise())
