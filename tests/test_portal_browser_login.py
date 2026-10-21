"""Owner-only web login and private/dashboard UI regression tests."""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.login_codes import issue_login_code, redeem_login_code
from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture

STATIC = Path(__file__).resolve().parents[1] / "app/web/portal_static"


def test_single_use_login_codes_expire_and_lock_after_guessing(tmp_path):
    settings, repo, _ = fixture(tmp_path)
    code = issue_login_code(repo, token=BOT_TOKEN, owner_id=123, now=1000)
    assert len(code) == 12 and code.isascii() and code.isdecimal()
    assert not redeem_login_code(
        repo, token=BOT_TOKEN, owner_id=456, code=code, now=1001
    )
    assert redeem_login_code(
        repo, token=BOT_TOKEN, owner_id=123, code=code, now=1001
    )
    assert not redeem_login_code(
        repo, token=BOT_TOKEN, owner_id=123, code=code, now=1001
    )
    expired = issue_login_code(repo, token=BOT_TOKEN, owner_id=123, now=1000)
    assert not redeem_login_code(
        repo, token=BOT_TOKEN, owner_id=123, code=expired, now=1301
    )
    another = issue_login_code(repo, token=BOT_TOKEN, owner_id=123, now=1000)
    wrong = "000000000000" if another != "000000000000" else "111111111111"
    for _ in range(5):
        assert not redeem_login_code(
            repo, token=BOT_TOKEN, owner_id=123, code=wrong, now=1001
        )
    assert not redeem_login_code(
        repo, token=BOT_TOKEN, owner_id=123, code=another, now=1001
    )


def test_desktop_login_requires_owner_code_and_private_session(tmp_path):
    async def exercise():
        settings, repo, _ = fixture(tmp_path)
        settings.telegram_bot_token = SecretStr(BOT_TOKEN)
        client = TestClient(TestServer(create_portal(settings, repo)))
        await client.start_server()
        try:
            pre = await client.get("/api/overview")
            assert pre.status == 401
            bogus = await client.post("/api/code-login", json={"code": "000000000000"})
            assert bogus.status == 401
            code = issue_login_code(
                repo, token=BOT_TOKEN, owner_id=123, now=int(time.time())
            )
            login = await client.post("/api/code-login", json={"code": code})
            assert login.status == 200
            assert login.cookies[COOKIE]["secure"]
            csrf = (await login.json())["csrf"]
            cookie = {"Cookie": f"{COOKIE}={login.cookies[COOKIE].value}"}
            resumed = await client.get("/api/session", headers=cookie)
            assert resumed.status == 200
            assert (await resumed.json())["csrf"] == csrf
            loaded = await client.get("/api/overview", headers=cookie)
            assert loaded.status == 200
            assert "radar" in await loaded.json()
            replay = await client.post("/api/code-login", json={"code": code})
            assert replay.status == 401
            done = await client.post(
                "/api/logout", json={}, headers={**cookie, "X-CSRF-Token": csrf}
            )
            assert done.status == 200
            blocked = await client.get("/api/overview", headers=cookie)
            assert blocked.status == 401
        finally:
            await client.close()

    asyncio.run(exercise())


def test_hidden_shell_and_browser_login_have_functional_assets():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    markup = (STATIC / "index.html").read_text(encoding="utf-8")
    javascript = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "[hidden]{display:none!important}" in css
    assert 'id="shell" class="shell" hidden' in markup
    assert 'id="code-login-form"' in markup
    assert 'id="code-login-submit"' in markup
    assert 'id="logout"' in markup
    assert '"/api/code-login"' in javascript
    assert '"/api/overview"' in javascript
    assert 'await loadDashboard();' in javascript
    assert 'showShell();' in javascript
    assert "state.data=data;" in javascript
    if shutil.which("node"):
        subprocess.run(["node", "--check", str(STATIC / "app.js")], check=True)
