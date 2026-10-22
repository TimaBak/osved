"""Google OAuth flow uses one-use state and a real browser session."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from aiohttp.test_utils import TestClient, TestServer
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN, signed_data
from tests.test_web_api import fixture


def test_youtube_callback_single_use_and_encrypted_storage(tmp_path):
    async def run():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        settings.oauth_google_client_id = "sample-id.apps.googleusercontent.com"
        settings.oauth_google_client_secret = SecretStr("secret-test")
        settings.oauth_token_encryption_key = SecretStr(Fernet.generate_key().decode())
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            assert (await client.post("/api/accounts/youtube/start", json={})).status == 401
            login = await client.post("/api/session", json={
                "init_data": signed_data(123, int(time.time()))
            })
            cookie = login.cookies[COOKIE].value
            csrf = (await login.json())["csrf"]
            headers = {"Cookie": f"{COOKIE}={cookie}", "X-CSRF-Token": csrf}
            start = await client.post("/api/accounts/youtube/start", json={}, headers=headers)
            assert start.status == 200
            url = (await start.json())["authorization_url"]
            assert urlsplit(url).hostname == "accounts.google.com"
            args = parse_qs(urlsplit(url).query)
            assert args["scope"] == ["https://www.googleapis.com/auth/youtube.readonly"]
            token_state = args["state"][0]
            with (
                patch("app.web.youtube_oauth.exchange_code",
                      return_value=("test-token", "test-refresh")),
                patch("app.web.youtube_oauth.own_channel_id", return_value="UCtestchannel"),
            ):
                response = await client.get(
                    "/api/accounts/youtube/callback?code=googlecode&state=" + token_state,
                    headers={"Cookie": f"{COOKIE}={cookie}"}, allow_redirects=False,
                )
            assert response.status == 302
            status = await client.get(
                "/api/accounts/status", headers={"Cookie": f"{COOKIE}={cookie}"},
            )
            assert (await status.json())["accounts"]["youtube"]["connected"] is True
            replay = await client.get(
                "/api/accounts/youtube/callback?code=googlecode&state=" + token_state,
                headers={"Cookie": f"{COOKIE}={cookie}"}, allow_redirects=False,
            )
            assert replay.status == 403
            from app.web.oauth_vault import read_tokens

            stored = read_tokens(
                repo,
                encryption_key=settings.oauth_token_encryption_key.get_secret_value(),
                provider="youtube", owner_id=123, account_id="UCtestchannel",
            )
            assert stored == ("test-token", "test-refresh")
        finally:
            await client.close()
    asyncio.run(run())
