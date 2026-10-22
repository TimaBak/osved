"""Owner-managed GitHub/Reddit source onboarding and security regression tests."""
from __future__ import annotations

import asyncio
import time

import pytest
from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.config import runtime_source_registry
from app.web.login_codes import issue_login_code
from app.web.portal import COOKIE, create_portal
from app.web.public_sources import (
    SourceInputError,
    add,
    initialize,
    normalize,
    remove,
)
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("github", "https://github.com/example/example-repo/tree/main"),
        ("github", "https://github.com.evil.test/example/repo"),
        ("github", "https://github.com/a/repo?token=abc"),
        ("github", "https://127.0.0.1/repo/name"),
        ("github", "../../private"),
        ("reddit", "https://reddit.com.evil.test/r/python"),
        ("reddit", "https://reddit.com:123/r/python"),
        ("reddit", "https://www.reddit.com/r/python/comments/example"),
        ("reddit", "http://www.reddit.com/r/python"),
        ("reddit", "r/../../../etc"),
        ("telegram", "https://t.me/official"),
    ],
)
def test_platform_locators_reject_ssrf_and_unexpected_routes(kind, value):
    with pytest.raises(SourceInputError):
        normalize(kind, value)


def test_canonical_platform_urls():
    assert normalize("github", "https://github.com/Example/Repo")[:2] == (
        "Example/Repo", "GitHub — Example/Repo"
    )
    assert normalize("github", "Example/Repo")[0] == "Example/Repo"
    assert normalize("reddit", "https://www.reddit.com/r/Python/")[0] == "python"
    assert normalize("reddit", "r/Python")[0] == "python"


def test_add_restart_pause_remove_and_restore(tmp_path):
    settings, repo, _ = fixture(tmp_path)
    initialize(repo)
    item = add(repo, settings, "github", "Example/Repository", "ai_software")
    assert item["existing"] is False
    source_id = item["id"]
    assert add(repo, settings, "github", "Example/Repository")["existing"]
    registry = runtime_source_registry(settings)
    source = next(src for src in registry.sources if src.id == source_id)
    assert source.locator == "Example/Repository"
    assert source.kind.value == "github"
    assert source.topics == ["ai_software"]
    assert source.strategy == "releases"
    assert source.admission_mode == "event_candidate"
    assert source.daily_call_cap <= 6
    from app.collectors.orchestrator import collect_due_sources

    plan = collect_due_sources(
        settings, repo, source_ids=[source_id], dry_run=True
    )
    assert plan["rows"][0]["status"] == "planned"
    assert plan["rows"][0]["estimated_cost_usd"] == 0
    repo.set_runtime_setting("source_enabled:" + source_id, "false")
    assert repo.get_runtime_setting("source_enabled:" + source_id) == "false"
    remove(repo, settings, source_id)
    assert next(src for src in runtime_source_registry(settings).sources
                if src.id == source_id).enabled is False
    assert repo.get_runtime_setting("source_enabled:" + source_id) == "false"
    restored = add(repo, settings, "github", "Example/Repository", "startups")
    assert restored["existing"] is False
    assert repo.get_runtime_setting("source_enabled:" + source_id) == "true"
    assert next(src for src in runtime_source_registry(settings).sources
                if src.id == source_id).topics == ["startups"]


def test_owner_source_api_requires_session_csrf_and_persists(tmp_path):
    async def scenario():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            path = "/api/public-sources/add"
            payload = {"kind": "reddit", "locator": "r/Python", "topic": "ai_software"}
            assert (await client.post(path, json=payload)).status == 401
            code = issue_login_code(
                repo, token=BOT_TOKEN, owner_id=123, now=int(time.time())
            )
            login = await client.post("/api/code-login", json={"code": code})
            assert login.status == 200
            cookie = {"Cookie": f"{COOKIE}={login.cookies[COOKIE].value}"}
            assert (await client.post(path, json=payload, headers=cookie)).status == 403
            headers = {**cookie, "X-CSRF-Token": (await login.json())["csrf"]}
            invalid = await client.post(path, json={
                "kind": "reddit", "locator": "https://127.0.0.1/", "topic": "ai_software"
            }, headers=headers)
            assert invalid.status == 400
            added = await client.post(path, json=payload, headers=headers)
            assert added.status == 200
            result = await added.json()
            overview = await (await client.get("/api/overview", headers=cookie)).json()
            entry = next(x for x in overview["sources"] if x["id"] == result["id"])
            assert entry["kind"] == "reddit"
            assert entry["platform"] == "Reddit"
            assert entry["category"] == "Сообщества"
            assert entry["topics"] == ["ai_software"]
            assert entry["url"] == "https://www.reddit.com/r/python/"
            assert entry["last_success_at"] is None  # No claim of first successful collection
            assert (await client.post("/api/public-sources/remove",
                headers=headers, json={"id": result["id"]})).status == 200
            after = await (await client.get("/api/overview", headers=cookie)).json()
            assert not any(x["id"] == result["id"] for x in after["sources"])
            assert (await client.post("/api/public-sources/remove",
                headers=headers, json={"id": "rss_primary"})).status == 400
        finally:
            await client.close()
    asyncio.run(scenario())
