"""Russian-first reading and private research notebook regression tests."""

from __future__ import annotations

import asyncio
import time

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.login_codes import issue_login_code
from app.web.portal import COOKIE, create_portal
from app.web.reader_notes import content_language, get_note, save_note
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture


def test_language_disclosure_does_not_invent_translation():
    assert content_language("Крупное исследование науки и технологий") == "ru"
    assert content_language("New scientific findings from original sources") == "original"
    assert content_language("AI") == "unknown"


def test_reading_notes_are_persistent_and_validated(tmp_path):
    _, repository, delivery = fixture(tmp_path)
    from app.web.reader_notes import initialize

    initialize(repository)
    item_id = delivery["card_id"]
    note = save_note(repository, "news", item_id, "Проверить контекст и тезис.", True)
    assert note["note"] == "Проверить контекст и тезис."
    assert note["is_read"] is True
    assert get_note(repository, "news", item_id)["note"] == note["note"]
    try:
        save_note(repository, "news", item_id, "x" * 4001, False)
    except ValueError:
        pass
    else:
        raise AssertionError("Oversized note accepted")
    assert get_note(repository, "news", item_id)["note"] == note["note"]


def test_research_notes_require_owner_csrf_and_real_item(tmp_path):
    async def exercise():
        settings, repository, delivery = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        client = TestClient(TestServer(create_portal(settings, repository)))
        await client.start_server()
        item_path = f"/api/reader/news/{delivery['card_id']}"
        payload = {"note": "Заметка для проверки источников.", "is_read": True}
        try:
            assert (await client.get(item_path)).status == 401
            assert (await client.post(item_path, json=payload)).status == 401
            code = issue_login_code(
                repository, token=BOT_TOKEN, owner_id=123, now=int(time.time())
            )
            auth = await client.post("/api/code-login", json={"code": code})
            assert auth.status == 200
            csrf = (await auth.json())["csrf"]
            cookie = {"Cookie": f"{COOKIE}={auth.cookies[COOKIE].value}"}
            assert (await client.get(item_path, headers=cookie)).status == 200
            assert (await client.post(item_path, headers=cookie, json=payload)).status == 403
            saved = await client.post(
                item_path, headers={**cookie, "X-CSRF-Token": csrf}, json=payload
            )
            assert saved.status == 200
            assert (await saved.json())["is_read"] is True
            overview = await (await client.get("/api/overview", headers=cookie)).json()
            assert overview["locale"] == "ru-RU"
            assert any(row["note"] == payload["note"] for row in overview["reading"])
            assert all(item["language"] in {"ru", "original", "unknown"}
                       for item in overview["feed"] + overview["radar"])
            assert (await client.get("/api/reader/news/999999", headers=cookie)).status == 404
            assert (await client.post(
                item_path, headers={**cookie, "X-CSRF-Token": csrf},
                json={"note": "too long" * 600, "is_read": True}
            )).status == 400
            assert (await client.post(
                item_path, headers={**cookie, "X-CSRF-Token": csrf},
                json={"note": "ok", "is_read": "true"}
            )).status == 400
            assert (await client.get(
                "/api/reader/forbidden/1", headers=cookie
            )).status == 400
        finally:
            await client.close()

    asyncio.run(exercise())
