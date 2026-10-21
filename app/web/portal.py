"""Telegram Mini App dashboard over the SAME SQLite store as the OSVED bot.

The web service is not exposed on a public interface by Docker. nginx must
terminate HTTPS and reverse proxy to the loopback-bound host port.
Telegram initData must be verified server-side before exposing private data.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from aiohttp import web

from app.config import Settings
from app.db.repository import Repository
from app.ops.feed_health import feed_health
from app.web.content import public_url
from app.web.store import DashboardStore

COOKIE = "osved_portal_session"
STATIC = Path(__file__).resolve().parent / "portal_static"
MAX_INIT_AGE = 600


def telegram_owner(init_data: str, bot_token: str, owner_id: int, now: int) -> bool:
    """Verify Telegram WebApp initData (not the untrusted initDataUnsafe)."""
    if not isinstance(init_data, str) or not 20 < len(init_data) < 8192:
        return False
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            return False
        incoming = str(fields.pop("hash"))
        issued_at = int(fields["auth_date"])
        user = json.loads(fields["user"])
        if not isinstance(user, dict) or int(user["id"]) != owner_id:
            return False
        if not 0 <= now - issued_at <= MAX_INIT_AGE:
            return False
        if len(incoming) != 64:
            return False
        token_key = hmac.new(
            b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
        ).digest()
        # Telegram may include a separate Ed25519 'signature' field in
        # newer clients; it is not part of the HMAC payload.
        fields.pop("signature", None)
        check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        digest = hmac.new(token_key, check.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, incoming)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


class PortalState:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repository = repository
        self.store = DashboardStore(settings, repository)
        self.sessions: dict[str, tuple[str, float]] = {}

    def session(self, request: web.Request) -> tuple[str, float] | None:
        key = request.cookies.get(COOKIE, "")
        session = self.sessions.get(key)
        if session and session[1] > time.time():
            return session
        return None


STATE = web.AppKey("osved_portal_state", PortalState)


def error(code: str, status: int = 400) -> web.Response:
    return web.json_response({"error": code}, status=status)


@web.middleware
async def secure_headers(request: web.Request, handler):
    response = await handler(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://telegram.org; "
        "style-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"
    )
    return response


@web.middleware
async def protect(request: web.Request, handler):
    hostname = urlsplit("http://" + request.host).hostname
    allowed = {os.environ.get("OSVED_WEB_HOST", "osved.tima.biz"), "127.0.0.1", "localhost"}
    if hostname not in allowed:
        return error("invalid_host", 403)
    if request.path.startswith("/api/") and request.path != "/api/session":
        session = request.app[STATE].session(request)
        if session is None:
            return error("unauthorized", 401)
        if request.method not in {"GET", "HEAD"} and not hmac.compare_digest(
            request.headers.get("X-CSRF-Token", ""), session[0]
        ):
            return error("csrf", 403)
    if request.method not in {"GET", "HEAD"}:
        origin = request.headers.get("Origin")
        if origin and origin != f"https://{hostname}" and origin != f"http://{request.host}":
            return error("origin", 403)
        if request.content_type != "application/json":
            return error("content_type", 415)
    return await handler(request)


async def session_create(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    # The Telegram bot can establish an owner on first /start and persist it in
    # runtime_settings. Use that SAME owner resolution for the web login.
    # Never claim a new owner from an unauthenticated web request.
    from app.telegram_bot.bot import configured_owner_id

    owner_id = configured_owner_id(state.settings, state.repository)
    if state.settings.telegram_bot_token is None or owner_id is None:
        return error("authentication_unconfigured", 503)
    try:
        payload = await request.json()
        init_data = payload.get("init_data")
        if not telegram_owner(
            init_data,
            state.settings.telegram_bot_token.get_secret_value(),
            owner_id,
            int(time.time()),
        ):
            return error("invalid_telegram_session", 401)
    except (TypeError, AttributeError, ValueError, json.JSONDecodeError):
        return error("invalid_telegram_session", 401)
    now = time.time()
    state.sessions = {
        key: session for key, session in state.sessions.items() if session[1] > now
    }
    if len(state.sessions) >= 64:
        state.sessions.pop(next(iter(state.sessions)))
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    state.sessions[token] = (csrf, now + 8 * 3600)
    response = web.json_response({"ok": True, "csrf": csrf})
    response.set_cookie(
        COOKIE, token, httponly=True, secure=True, samesite="Lax",
        max_age=8 * 3600, path="/",
    )
    return response


async def logout(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    state.sessions.pop(request.cookies.get(COOKIE, ""), None)
    response = web.json_response({"ok": True})
    response.del_cookie(COOKIE, path="/")
    return response


def radar_rows(repository: Repository) -> list[dict]:
    with repository.connection() as db:
        rows = db.execute(
            """SELECT e.id,e.headline,e.event_at,e.status,s.name AS source,
            si.source_url,si.published_at
            FROM events e JOIN source_items si ON si.id=e.primary_source_item_id
            JOIN sources s ON s.id=si.source_id
            WHERE e.status='candidate'
            ORDER BY e.latest_source_at DESC, e.id DESC LIMIT 24"""
        ).fetchall()
    return [
        {
            "id": row["id"], "title": row["headline"], "source": row["source"],
            "url": public_url(row["source_url"]),
            "published_at": row["event_at"] or row["published_at"],
            "verified": False,
        }
        for row in rows
    ]


async def overview(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]

    def read():
        return {
            "feed": state.store.all_items()[:30],
            "radar": radar_rows(state.repository),
            "sources": state.store.sources(),
            "health": feed_health(state.repository),
        }

    return web.json_response(await asyncio.to_thread(read))


async def bookmark(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    try:
        data = await request.json()
        kind = data["kind"]
        item_id = data["id"]
        saved = data["saved"]
        if kind not in {"news", "video"} or type(item_id) is not int or item_id < 1:
            return error("invalid_item")
        if type(saved) is not bool:
            return error("invalid_saved_state")
    except (KeyError, ValueError, TypeError):
        return error("invalid_item")
    item = await asyncio.to_thread(state.store.item, kind, item_id)
    if item is None:
        return error("not_found", 404)
    await asyncio.to_thread(state.store.set_saved, kind, item_id, saved)
    return web.json_response({"ok": True, "saved": saved})


async def source_update(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    try:
        data = await request.json()
        source_id = data["id"]
        enabled = data["enabled"]
        if (
            not isinstance(source_id, str)
            or re.fullmatch(r"[a-z0-9_]{1,80}", source_id) is None
            or type(enabled) is not bool
        ):
            return error("invalid_source")
    except (KeyError, TypeError, ValueError):
        return error("invalid_source")
    sources = await asyncio.to_thread(state.store.sources)
    if source_id not in {row["id"] for row in sources}:
        return error("not_found", 404)

    def persist() -> None:
        state.repository.set_runtime_setting(
            f"source_enabled:{source_id}", str(enabled).lower()
        )
        if not enabled:
            from app.collectors.browser_queue import BrowserTaskQueue

            BrowserTaskQueue(state.repository.database_path).cancel_pending(source_id)

    await asyncio.to_thread(persist)
    return web.json_response({"id": source_id, "enabled": enabled})


async def healthz(request: web.Request) -> web.Response:
    return web.json_response({"status": "alive"})


async def static(request: web.Request) -> web.Response:
    filename = request.match_info.get("filename", "index.html") or "index.html"
    if filename not in {"index.html", "style.css", "app.js"}:
        return error("not_found", 404)
    return web.FileResponse(STATIC / filename)


async def startup(app: web.Application) -> None:
    state: PortalState = app[STATE]
    await asyncio.to_thread(state.store.initialize)


def create_portal(settings: Settings, repository: Repository) -> web.Application:
    app = web.Application(middlewares=[secure_headers, protect], client_max_size=12_000)
    app[STATE] = PortalState(settings, repository)
    app.router.add_get("/healthz", healthz)
    app.router.add_post("/api/session", session_create)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/api/overview", overview)
    app.router.add_post("/api/bookmark", bookmark)
    app.router.add_post("/api/source", source_update)
    app.router.add_get("/", static)
    app.router.add_get("/{filename}", static)
    app.on_startup.append(startup)
    return app


def main() -> None:
    settings = Settings()
    app = create_portal(settings, Repository(settings.database_path))
    web.run_app(app, host="0.0.0.0", port=8080, access_log=None)


if __name__ == "__main__":
    main()
