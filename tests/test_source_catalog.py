"""Read-only source taxonomy and owner-only provider readiness checks."""
from __future__ import annotations

import asyncio
import time

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.login_codes import issue_login_code
from app.web.portal import COOKIE, create_portal
from app.web.source_catalog import present_source, public_capabilities
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture


def test_source_catalog_uses_real_metadata_not_account_assumptions():
    telegram = present_source({
        "id": "public_channel", "name": "Технологии", "kind": "telegram",
        "topics": ["tech", "ai"], "enabled": True, "status": "ready",
    })
    assert telegram["category"] == "Мессенджеры"
    assert telegram["platform"] == "Telegram"
    assert telegram["topics"] == ["tech", "ai"]
    assert telegram["account_connected"] is False
    assert telegram["connection_mode"] == "public_source"
    reddit = present_source({"kind": "reddit", "topics": None})
    assert reddit["category"] == "Сообщества"
    assert reddit["topics"] == []
    assert reddit["topic_status"] == "unclassified"
    assert present_source({"kind": "youtube", "topics": []})["category"] == "Видео"
    assert present_source({"kind": "rss", "topics": []})["category"] == "Сайты и RSS"


def test_paid_capabilities_fail_closed_without_configured_provider(tmp_path):
    settings, repo, _ = fixture(tmp_path)
    result = public_capabilities(settings)
    assert result["video"]["ready"] is False
    assert result["video"]["reason"] == "ai_provider_unconfigured"
    assert result["translation"]["ready"] is False
    assert result["image_ai"]["ready"] is False
    assert result["accounts"]["oauth_ready"] is False
    settings.video_reports_enabled = False
    assert public_capabilities(settings)["video"]["reason"] == "video_generation_disabled"
    assert "api_key" not in str(result)
    assert "token" not in str(result).lower()


def test_catalog_and_capabilities_require_owner_auth(tmp_path):
    async def scenario():
        settings, repository, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        client = TestClient(TestServer(create_portal(settings, repository)))
        await client.start_server()
        try:
            assert (await client.get("/api/capabilities")).status == 401
            code = issue_login_code(
                repository, token=BOT_TOKEN, owner_id=123, now=int(time.time())
            )
            response = await client.post("/api/code-login", json={"code": code})
            assert response.status == 200
            cookie = {"Cookie": f"{COOKIE}={response.cookies[COOKIE].value}"}
            capabilities = await client.get("/api/capabilities", headers=cookie)
            assert capabilities.status == 200
            result = await capabilities.json()
            assert result["video"]["reason"] == "ai_provider_unconfigured"
            assert result["translation"]["mode"] == "planned_on_demand"
            overview = await client.get("/api/overview", headers=cookie)
            assert overview.status == 200
            catalog = (await overview.json())["sources"]
            assert catalog
            for entry in catalog:
                assert "platform" in entry and "category" in entry
                assert "topics" in entry and "account_connected" in entry
                assert entry["account_connected"] is False
        finally:
            await client.close()

    asyncio.run(scenario())
