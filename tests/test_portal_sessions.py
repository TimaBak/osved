"""Owner sessions survive page reloads and Docker restarts without plain tokens on disk."""
from __future__ import annotations

import asyncio
import time

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.login_codes import issue_login_code
from app.web.portal import COOKIE, create_portal
from app.web.sessions import (
    SESSION_SECONDS,
    initialize_sessions,
    issue_session,
    lookup_session,
    revoke_session,
)
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture


def test_hashed_cookie_expiry_owner_binding_and_logout(tmp_path):
    settings, repository, _ = fixture(tmp_path)
    initialize_sessions(repository)
    token, csrf = issue_session(repository, 123, now=100)
    assert lookup_session(repository, token, 123, now=101) == csrf
    assert lookup_session(repository, token, 456, now=101) is None
    assert lookup_session(repository, token, 123, now=100 + SESSION_SECONDS) is None
    with repository.connection() as db:
        row = db.execute(
            "SELECT token_digest,csrf_token,expires_at FROM portal_sessions"
        ).fetchone()
    assert row is not None
    assert token != row["token_digest"]
    assert csrf == row["csrf_token"]
    assert row["expires_at"] == 100 + SESSION_SECONDS
    revoke_session(repository, token)
    assert lookup_session(repository, token, 123, now=101) is None


def test_owner_cookie_survives_backend_restart_and_can_be_revoked(tmp_path):
    async def exercise():
        settings, repository, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        browser = TestClient(TestServer(create_portal(settings, repository)))
        await browser.start_server()
        try:
            issued = issue_login_code(
                repository, token=BOT_TOKEN, owner_id=123, now=int(time.time())
            )
            response = await browser.post(
                "/api/code-login", json={"code": issued}
            )
            assert response.status == 200
            cookie = response.cookies[COOKIE]
            assert cookie["secure"] and cookie["httponly"]
            assert cookie["max-age"] == str(SESSION_SECONDS)
            raw_cookie = {"Cookie": f"{COOKIE}={cookie.value}"}
            csrf = (await response.json())["csrf"]
            before = await browser.get("/api/session", headers=raw_cookie)
            assert before.status == 200
        finally:
            await browser.close()

        # A brand-new aiohttp app / PortalState, with the SAME persistent
        # SQLite file, models a full Docker restart.
        restarted = TestClient(TestServer(create_portal(settings, repository)))
        await restarted.start_server()
        try:
            resumed = await restarted.get("/api/session", headers=raw_cookie)
            assert resumed.status == 200
            assert (await resumed.json())["csrf"] == csrf
            dashboard = await restarted.get("/api/overview", headers=raw_cookie)
            assert dashboard.status == 200
            logged_out = await restarted.post(
                "/api/logout", headers={
                    **raw_cookie, "X-CSRF-Token": csrf,
                }, json={},
            )
            assert logged_out.status == 200
            assert (await restarted.get(
                "/api/session", headers=raw_cookie
            )).status == 401
            assert (await restarted.get(
                "/api/overview", headers=raw_cookie
            )).status == 401
        finally:
            await restarted.close()

    asyncio.run(exercise())


def test_owner_change_invalidates_old_browser_session(tmp_path):
    async def exercise():
        settings, repository, _ = fixture(tmp_path)
        client = TestClient(TestServer(create_portal(settings, repository)))
        await client.start_server()
        try:
            token, _ = issue_session(repository, 123)
            headers = {"Cookie": f"{COOKIE}={token}"}
            assert (await client.get("/api/session", headers=headers)).status == 200
            settings.allowed_user_id = 456
            assert (await client.get("/api/session", headers=headers)).status == 401
        finally:
            await client.close()

    asyncio.run(exercise())
