"""Hidden cards do not train OSVED or change verified publication status."""
from __future__ import annotations

import asyncio
import time

import pytest
from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.hidden_items import hidden_snapshot, initialize, set_hidden
from app.web.login_codes import issue_login_code
from app.web.personalization import snapshot
from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture


def test_hidden_flags_are_idempotent_and_reversible(tmp_path):
    _, repository, _ = fixture(tmp_path)
    initialize(repository)
    set_hidden(repository, "radar", 8, True)
    set_hidden(repository, "radar", 8, True)
    assert len(hidden_snapshot(repository)) == 1
    set_hidden(repository, "radar", 8, False)
    assert hidden_snapshot(repository) == []
    for kind, item_id, enabled in [
        ("x", 8, True), ("news", -1, True),
        ("news", True, True), ("news", 1, "yes")
    ]:
        with pytest.raises(ValueError):
            set_hidden(repository, kind, item_id, enabled)


def test_owner_hide_endpoint_keeps_topic_feedback_unchanged(tmp_path):
    async def scenario():
        settings, repository, delivery = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        event_id = delivery["event_id"]
        with repository.connection() as db:
            db.execute("UPDATE events SET status='candidate' WHERE id=?", (event_id,))
        client = TestClient(TestServer(create_portal(settings, repository)))
        await client.start_server()
        try:
            payload = {"kind":"radar","id":event_id,"hidden":True}
            assert (await client.post("/api/hidden", json=payload)).status == 401
            code = issue_login_code(
                repository, token=BOT_TOKEN, owner_id=123, now=int(time.time())
            )
            login = await client.post("/api/code-login", json={"code":code})
            assert login.status == 200
            cookie = {"Cookie": f"{COOKIE}={login.cookies[COOKIE].value}"}
            assert (await client.post("/api/hidden", json=payload, headers=cookie)).status == 403
            headers = {**cookie, "X-CSRF-Token": (await login.json())["csrf"]}
            before = snapshot(repository)
            hidden = await client.post("/api/hidden", json=payload, headers=headers)
            assert hidden.status == 200
            assert (await hidden.json())["hidden"] is True
            overview = await (await client.get("/api/overview", headers=cookie)).json()
            assert {"kind":"radar","id":event_id}.items() <= overview["hidden"][0].items()
            assert snapshot(repository) == before
            assert (await client.post("/api/hidden", json={
                **payload,"id":9999999}, headers=headers)).status == 404
            assert (await client.post("/api/hidden", json={
                **payload,"hidden":"yes"}, headers=headers)).status == 400
            assert (await client.post("/api/hidden", json={
                **payload,"hidden":False}, headers=headers)).status == 200
            assert hidden_snapshot(repository) == []
        finally:
            await client.close()
    asyncio.run(scenario())
