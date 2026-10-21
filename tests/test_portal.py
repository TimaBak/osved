"""The public-facing OSVED portal never trusts unverified Telegram user data."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.portal import COOKIE, create_portal, telegram_owner
from tests.test_web_api import fixture

BOT_TOKEN = "123456:secret-test-token"


def signed_data(user_id: int, now: int, token: str = BOT_TOKEN) -> str:
    fields = {
        "auth_date": str(now),
        "user": json.dumps({"id": user_id}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_telegram_login_checks_hmac_owner_and_expiry():
    now = int(time.time())
    good = signed_data(123, now)
    assert telegram_owner(good, BOT_TOKEN, 123, now)
    assert not telegram_owner(good, BOT_TOKEN, 456, now)
    assert not telegram_owner(good, BOT_TOKEN, 123, now + 601)
    assert not telegram_owner(signed_data(123, now, "wrong-token"), BOT_TOKEN, 123, now)
    assert not telegram_owner(good + "&auth_date=99", BOT_TOKEN, 123, now)


def test_portal_api_requires_owner_session_and_csrf(tmp_path):
    async def exercise():
        settings, repo, delivery = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            response = await client.get("/api/overview")
            assert response.status == 401
            wrong = await client.post(
                "/api/session",
                json={"init_data": signed_data(456, int(time.time()))},
            )
            assert wrong.status == 401
            auth = await client.post(
                "/api/session",
                json={"init_data": signed_data(123, int(time.time()))},
            )
            assert auth.status == 200
            csrf = (await auth.json())["csrf"]
            assert auth.cookies[COOKIE]["httponly"]
            assert auth.cookies[COOKIE]["secure"]
            token = auth.cookies[COOKIE].value
            headers = {"Cookie": f"{COOKIE}={token}"}
            accepted = await client.get("/api/overview", headers=headers)
            assert accepted.status == 200
            payload = await accepted.json()
            assert "feed" in payload and "radar" in payload and "sources" in payload
            denied = await client.post(
                "/api/bookmark",
                headers=headers,
                json={"kind": "news", "id": delivery["card_id"], "saved": True},
            )
            assert denied.status == 403
            saved = await client.post(
                "/api/bookmark",
                headers={**headers, "X-CSRF-Token": csrf},
                json={"kind": "news", "id": delivery["card_id"], "saved": True},
            )
            assert saved.status == 200
            fresh = await client.get("/api/overview", headers=headers)
            updated = await fresh.json()
            assert any(x["saved"] for x in updated["feed"] if x["kind"] == "news")
        finally:
            await client.close()

    asyncio.run(exercise())


def test_portal_host_restrictions(tmp_path):
    async def exercise():
        settings, repo, _ = fixture(tmp_path)
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            denied = await client.get("/healthz", headers={"Host": "evil.example"})
            assert denied.status == 403
            success = await client.get("/healthz")
            assert success.status == 200
        finally:
            await client.close()

    asyncio.run(exercise())



def test_portal_accepts_only_persisted_telegram_owner_without_env_allowlist(tmp_path):
    async def exercise():
        settings, repo, _ = fixture(tmp_path)
        settings.allowed_user_id = None
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        repo.set_runtime_setting("allowed_user_id", "123")
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            outsider = await client.post(
                "/api/session",
                json={"init_data": signed_data(456, int(time.time()))},
            )
            assert outsider.status == 401

            rightful_owner = await client.post(
                "/api/session",
                json={"init_data": signed_data(123, int(time.time()))},
            )
            assert rightful_owner.status == 200
        finally:
            await client.close()

    asyncio.run(exercise())


def test_portal_does_not_claim_owner_from_unconfigured_web_login(tmp_path):
    async def exercise():
        settings, repo, _ = fixture(tmp_path)
        settings.allowed_user_id = None
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            response = await client.post(
                "/api/session",
                json={"init_data": signed_data(123, int(time.time()))},
            )
            assert response.status == 503
            assert repo.get_runtime_setting("allowed_user_id") is None
        finally:
            await client.close()

    asyncio.run(exercise())
