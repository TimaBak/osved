"""GitHub login remains owner-only and never exchanges tokens without state."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN, signed_data
from tests.test_web_api import fixture


def test_github_oauth_button_backend_and_callback(tmp_path):
    async def run():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        settings.oauth_github_client_id = "github-test-id"
        settings.oauth_github_client_secret = SecretStr("github-test-secret")
        settings.oauth_token_encryption_key = SecretStr(Fernet.generate_key().decode())
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            assert (await client.post("/api/accounts/github/start", json={})).status == 401
            login = await client.post(
                "/api/session", json={"init_data": signed_data(123, int(time.time()))}
            )
            assert login.status == 200
            cookie = login.cookies[COOKIE].value
            csrf = (await login.json())["csrf"]
            headers = {"Cookie": f"{COOKIE}={cookie}", "X-CSRF-Token": csrf}
            start = await client.post("/api/accounts/github/start", json={}, headers=headers)
            assert start.status == 200
            from urllib.parse import parse_qs, urlsplit

            url = (await start.json())["authorization_url"]
            assert urlsplit(url).hostname == "github.com"
            state = parse_qs(urlsplit(url).query)["state"][0]
            with (
                patch("app.web.github_oauth.exchange_code", return_value="sample-token"),
                patch("app.web.github_oauth.github_identity", return_value="9898"),
            ):
                callback = await client.get(
                    f"/api/accounts/github/callback?code=sample-code&state={state}",
                    headers={"Cookie": f"{COOKIE}={cookie}"}, allow_redirects=False,
                )
            assert callback.status == 302
            assert callback.headers["Location"] == "/?github_connected=1"
            listing = await client.get(
                "/api/accounts/status", headers={"Cookie": f"{COOKIE}={cookie}"}
            )
            assert (await listing.json())["accounts"]["github"]["connected"] is True
            replay = await client.get(
                f"/api/accounts/github/callback?code=sample-code&state={state}",
                headers={"Cookie": f"{COOKIE}={cookie}"}, allow_redirects=False,
            )
            assert replay.status == 403
        finally:
            await client.close()

    asyncio.run(run())
