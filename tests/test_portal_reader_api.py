"""Owner-authenticated portal reading and YouTube preflight tests."""

import asyncio
import time

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.login_codes import issue_login_code
from app.web.portal import COOKIE, STATE, create_portal
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture


def test_article_radar_and_cached_video_summary(tmp_path):
    async def exercise():
        settings, repository, delivery = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        with repository.connection() as db:
            db.execute(
                "UPDATE events SET status='candidate' WHERE id=?",
                (delivery["event_id"],),
            )
        client = TestClient(TestServer(create_portal(settings, repository)))
        await client.start_server()
        try:
            url = f"/api/article/news/{delivery['card_id']}"
            radar = f"/api/radar/{delivery['event_id']}"
            assert (await client.get(url)).status == 401
            assert (await client.get(radar)).status == 401
            code = issue_login_code(
                repository, token=BOT_TOKEN, owner_id=123, now=int(time.time())
            )
            login = await client.post("/api/code-login", json={"code": code})
            assert login.status == 200
            cookie = {"Cookie": f"{COOKIE}={login.cookies[COOKIE].value}"}
            csrf = (await login.json())["csrf"]
            response = await client.get(url, headers=cookie)
            assert response.status == 200
            article = (await response.json())["item"]
            assert article["kind"] == "news"
            assert article["content"]["brief"]
            assert article["sources"]
            signal = await client.get(radar, headers=cookie)
            assert signal.status == 200
            data = (await signal.json())["item"]
            assert data["verified"] is False
            assert data["source_name"]
            video = "https://www.youtube.com/watch?v=ABCDEFGHIjk"
            denied = await client.post("/api/video/summary", json={"url": video}, headers=cookie)
            assert denied.status == 403
            blocked = await client.post(
                "/api/video/summary",
                json={"url": video},
                headers={**cookie, "X-CSRF-Token": csrf},
            )
            assert blocked.status == 409
            assert (await blocked.json())["error"] == "ai_provider_unconfigured"
            client.server.app[STATE].store.reports.cached_tldr = lambda _: "Кэшированная выжимка"
            cached = await client.post(
                "/api/video/summary",
                json={"url": video},
                headers={**cookie, "X-CSRF-Token": csrf},
            )
            assert cached.status == 200
            assert (await cached.json())["cached"] is True
        finally:
            await client.close()

    asyncio.run(exercise())
