"""Manual source checks are owner-only and restricted to zero-price sensors."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.login_codes import issue_login_code
from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture


def test_manual_check_only_permits_a_single_owner_approved_public_source(tmp_path):
    async def scenario():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            endpoint = "/api/source/check"
            payload = {"id": "github_qwen_code"}
            assert (await client.post(endpoint, json=payload)).status == 401
            code = issue_login_code(
                repo, token=BOT_TOKEN, owner_id=123, now=int(time.time())
            )
            login = await client.post("/api/code-login", json={"code": code})
            assert login.status == 200
            csrf = (await login.json())["csrf"]
            headers = {"Cookie": f"{COOKIE}={login.cookies[COOKIE].value}"}
            assert (await client.post(
                endpoint, json=payload, headers=headers,
            )).status == 403
            headers["X-CSRF-Token"] = csrf
            denied = await client.post(
                endpoint, json={"id": "rss_openai_news"}, headers=headers,
            )
            assert denied.status == 400
            assert (await denied.json())["error"] == "source_manual_check_unsupported"
            missing = await client.post(
                endpoint, json={"id": "not-a-source"}, headers=headers,
            )
            assert missing.status == 404
            result = {
                "sources_attempted": 1,
                "cost_usd": 0.0,
                "sources": [{
                    "source_id": "github_qwen_code", "status": "ok",
                    "seen": 3, "inserted": 2,
                }],
            }
            with patch(
                "app.collectors.orchestrator.collect_due_sources",
                return_value=result,
            ) as collect:
                accepted = await client.post(
                    endpoint, json=payload, headers=headers,
                )
                assert accepted.status == 200
                data = await accepted.json()
                assert data["attempted"] is True
                assert data["results"][0]["inserted"] == 2
                assert data["paid_cost_usd"] == 0
                collect.assert_called_once()
                args, kwargs = collect.call_args
                assert kwargs["source_ids"] == ["github_qwen_code"]
                assert kwargs["force"] is False
                assert kwargs["dry_run"] is False
                assert kwargs["limit_per_source"] == 10
                assert args[0] is settings and args[1] is repo
            repo.set_runtime_setting("source_enabled:github_qwen_code", "false")
            paused = await client.post(endpoint, json=payload, headers=headers)
            assert paused.status == 409
            assert (await paused.json())["error"] == "source_paused"
        finally:
            await client.close()

    asyncio.run(scenario())
