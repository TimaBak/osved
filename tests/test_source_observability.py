"""Read-only collector diagnostics must not mistake enrollment for ingestion."""
from __future__ import annotations

import asyncio
import time

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.ops.news_readiness import diagnose
from app.ops.source_observability import snapshots, summarize
from app.web.login_codes import issue_login_code
from app.web.portal import COOKIE, create_portal
from app.web.store import DashboardStore
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture


def test_source_collection_uses_runs_not_registry_readiness(tmp_path):
    settings, repo, _ = fixture(tmp_path)
    with repo.connection() as db:
        active = db.execute(
            "SELECT id,kind FROM sources WHERE role!='own_history' "
            "AND admission_mode!='history' LIMIT 2"
        ).fetchall()
        assert len(active) == 2
        first, second = active[0]["id"], active[1]["id"]
        db.execute(
            "INSERT INTO source_runs"
            "(id,source_id,adapter_id,strategy,status,items_seen,items_inserted,"
            "items_rejected,started_at,finished_at,lease_until) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("test-run",first,"github","releases","ok",3,2,0,
             "2026-10-22T09:00:00+00:00","2026-10-22T09:01:00+00:00",
             "2026-10-22T09:10:00+00:00"),
        )
    with repo.connection() as db:
        current = snapshots(db)
    assert current[first]["status"] == "collected"
    assert current[first]["last_run_seen"] == 3
    assert current[first]["last_run_inserted"] == 2
    assert current[first]["latest_item_published_at"] is None
    assert current[second]["status"] == "never_checked"
    catalog = {entry["id"]: entry for entry in DashboardStore(settings, repo).sources()}
    assert catalog[first]["collection"]["status"] == "collected"
    assert "latest_item_published_at" in catalog[first]["collection"]
    assert catalog[second]["collection"]["status"] == "never_checked"
    diag = diagnose(settings.database_path, openrouter_configured=False)
    assert "source_collection" in diag
    assert diag["source_collection"]["read_only"] is True

    # A later failed attempt supersedes an earlier successful poll.
    with repo.connection() as db:
        db.execute(
            "INSERT INTO source_runs"
            "(id,source_id,adapter_id,strategy,status,error,started_at,"
            "finished_at,lease_until) VALUES(?,?,?,?,?,?,?,?,?)",
            ("test-run-failed",first,"github","releases","failed",
             "HTTP 429 rate limit", "2026-10-22T10:00:00+00:00",
             "2026-10-22T10:01:00+00:00", "2026-10-22T10:10:00+00:00"),
        )
        current = snapshots(db)
    assert current[first]["status"] == "error"
    assert "429" in current[first]["last_error"]
    assert summarize(current)["by_platform"][active[0]["kind"]]["errors"] >= 1
    repo.set_runtime_setting("source_enabled:"+first, "false")
    with repo.connection() as db:
        current = snapshots(db)
    assert current[first]["status"] == "paused"


def test_source_health_is_private_on_portal(tmp_path):
    async def scenario():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            assert (await client.get("/api/overview")).status == 401
            code = issue_login_code(
                repo, token=BOT_TOKEN, owner_id=123, now=int(time.time())
            )
            login = await client.post("/api/code-login", json={"code": code})
            assert login.status == 200
            cookie = {"Cookie": f"{COOKIE}={login.cookies[COOKIE].value}"}
            response = await client.get("/api/overview", headers=cookie)
            assert response.status == 200
            sources = (await response.json())["sources"]
            assert sources
            assert all("collection" in source for source in sources)
            assert all(
                "last_run_inserted" in source["collection"] for source in sources
            )
        finally:
            await client.close()

    asyncio.run(scenario())
