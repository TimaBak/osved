"""Real YouTube channel onboarding through the authenticated OSVED website."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.video.channels import ChannelService
from app.web.login_codes import issue_login_code
from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture

CHANNEL_ID = "UC" + "a" * 22
CHANNEL_URL = f"https://www.youtube.com/channel/{CHANNEL_ID}"


def channel_xml() -> bytes:
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:yt="http://www.youtube.com/xml/schemas/2015">'
        f"<yt:channelId>{CHANNEL_ID}</yt:channelId>"
        "<title>Новый канал из кабинета</title></feed>"
    ).encode()


def test_website_add_and_remove_public_youtube_channel(tmp_path):
    async def scenario():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        settings.monid_api_key = None
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            add = "/api/youtube/channels/add"
            remove = "/api/youtube/channels/remove"
            assert (await client.post(add, json={"url": CHANNEL_URL})).status == 401
            code = issue_login_code(
                repo, token=BOT_TOKEN, owner_id=123, now=int(time.time())
            )
            login = await client.post("/api/code-login", json={"code": code})
            assert login.status == 200
            csrf = (await login.json())["csrf"]
            cookie = {"Cookie": f"{COOKIE}={login.cookies[COOKIE].value}"}
            assert (await client.post(add, headers=cookie,
                json={"url": CHANNEL_URL})).status == 403
            headers = {**cookie, "X-CSRF-Token": csrf}
            # Handles need potentially paid resolution; reject before any bill.
            indirect = await client.post(add, headers=headers,
                json={"url": "https://youtube.com/@creator"})
            assert indirect.status == 400
            assert (await indirect.json())["error"] == "youtube_resolution_consent_required"
            agreed = await client.post(add, headers=headers, json={
                "url":"@creator", "allow_paid_resolution":True
            })
            assert agreed.status == 503
            assert (await agreed.json())["error"] == "youtube_resolver_unconfigured"
            bad = await client.post(add, headers=headers,
                json={"url": "https://youtube.com.evil.com/channel/" + CHANNEL_ID})
            assert bad.status == 400
            with patch(
                "app.web.portal.ChannelService",
                side_effect=lambda s, r: ChannelService(
                    s, r, fetcher=lambda _: channel_xml()
                ),
            ):
                added = await client.post(add, headers=headers,
                    json={"url": CHANNEL_URL})
                assert added.status == 200
                result = await added.json()
                assert result["title"] == "Новый канал из кабинета"
                assert result["existing"] is False
                repeat = await client.post(add, headers=headers,
                    json={"url": CHANNEL_URL})
                assert repeat.status == 200
                assert (await repeat.json())["existing"] is True
            overview = await (await client.get(
                "/api/overview", headers=cookie
            )).json()
            source = next(row for row in overview["sources"]
                          if row["id"] == result["source_id"])
            assert source["category"] == "Видео"
            assert source["enabled"]
            assert source["platform"] == "YouTube"
            assert repo.current_month_cost() == 0
            removed = await client.post(remove, headers=headers,
                json={"id": result["source_id"]})
            assert removed.status == 200
            refreshed = await (await client.get(
                "/api/overview", headers=cookie
            )).json()
            assert not any(row["id"] == result["source_id"]
                           for row in refreshed["sources"])
            assert (await client.post(remove, headers=headers,
                json={"id": result["source_id"]})).status == 404
            assert (await client.post(remove, headers=headers,
                json={"id": "other_source"})).status == 400
        finally:
            await client.close()

    asyncio.run(scenario())
