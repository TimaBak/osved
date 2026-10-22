"""Model catalog endpoints remain authenticated, CSRF-protected and non-generating."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.llm.codexsale import CodexSaleClient
from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN, signed_data
from tests.test_web_api import fixture


def test_model_catalog_owner_session_and_csrf(tmp_path):
    async def exercise():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        settings.codex_sale_api_key = SecretStr("test-only-secret")
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            assert (await client.get("/api/ai/catalog")).status == 401
            signed = signed_data(123, int(time.time()))
            auth = await client.post("/api/session", json={"init_data": signed})
            assert auth.status == 200
            token = auth.cookies[COOKIE].value
            headers = {"Cookie": f"{COOKIE}={token}"}
            with patch.object(
                CodexSaleClient, "models", return_value=[{"id": "test-model"}]
            ):
                listing = await client.get("/api/ai/catalog", headers=headers)
                assert (await listing.json())["models"] == ["test-model"]
                unsafe = await client.post(
                    "/api/ai/models", headers=headers,
                    json={"task": "news", "model": "test-model"},
                )
                assert unsafe.status == 403
                valid = await client.post(
                    "/api/ai/models",
                    headers={**headers, "X-CSRF-Token": (await auth.json())["csrf"]},
                    json={"task": "news", "model": "test-model"},
                )
                assert valid.status == 200
                assert repo.get_runtime_setting("ai.routing.task.news") == "test-model"
                rejected = await client.post(
                    "/api/ai/models",
                    headers={**headers, "X-CSRF-Token": (await auth.json())["csrf"]},
                    json={"task": "news", "model": "invented-model"},
                )
                assert rejected.status == 400
        finally:
            await client.close()

    asyncio.run(exercise())
