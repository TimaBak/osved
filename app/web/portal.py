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
from app.video.channels import ChannelError, ChannelService, change_channel, channel_url
from app.video.reports import ReportError
from app.video.transcripts import youtube_video_id
from app.web.content import plain_text, public_url, safe_html
from app.web.hidden_items import (
    hidden_snapshot,
    initialize as initialize_hidden_items,
    set_hidden,
)
from app.web.login_codes import ensure_login_schema, redeem_login_code
from app.web.personalization import (
    clear_preferences,
    material_topic,
    personalize,
    set_feedback,
    set_priority,
    snapshot,
)
from app.web.personalization import (
    initialize as initialize_personalization,
)
from app.web.public_sources import SourceInputError
from app.web.public_sources import add as add_public_subscription
from app.web.public_sources import initialize as initialize_public_sources
from app.web.public_sources import remove as remove_public_subscription
from app.web.reader_notes import content_language, get_note, initialize, list_notes, save_note
from app.web.sessions import (
    SESSION_SECONDS,
    initialize_sessions,
    issue_session,
    lookup_session,
    revoke_session,
)
from app.web.source_catalog import public_capabilities
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
        self.video_jobs: dict[str, dict] = {}
        self.video_by_id: dict[str, str] = {}
        self.video_tasks: set[asyncio.Task] = set()

    def session(self, request: web.Request) -> tuple[str, float] | None:
        from app.telegram_bot.bot import configured_owner_id

        owner_id = configured_owner_id(self.settings, self.repository)
        csrf = lookup_session(
            self.repository, request.cookies.get(COOKIE, ""), owner_id
        )
        return (csrf, 0.0) if csrf else None


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
    if request.path.startswith("/api/") and request.path not in {"/api/session", "/api/code-login"}:
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


def new_session(state: PortalState, owner_id: int) -> web.Response:
    token, csrf = issue_session(state.repository, owner_id)
    response = web.json_response({"ok": True, "csrf": csrf})
    response.set_cookie(
        COOKIE, token, httponly=True, secure=True, samesite="Lax",
        max_age=SESSION_SECONDS, path="/",
    )
    return response


async def session_status(request: web.Request) -> web.Response:
    session = request.app[STATE].session(request)
    if session is None:
        return error("unauthorized", 401)
    return web.json_response({"ok": True, "csrf": session[0]})


async def code_login(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    from app.telegram_bot.bot import configured_owner_id

    owner_id = configured_owner_id(state.settings, state.repository)
    if state.settings.telegram_bot_token is None or owner_id is None:
        return error("authentication_unconfigured", 503)
    try:
        payload = await request.json()
        code = payload["code"]
    except (ValueError, KeyError, TypeError):
        return error("invalid_login_code", 401)
    accepted = await asyncio.to_thread(
        redeem_login_code,
        state.repository,
        token=state.settings.telegram_bot_token.get_secret_value(),
        owner_id=owner_id,
        code=code,
    )
    if not accepted:
        return error("invalid_login_code", 401)
    return new_session(state, owner_id)


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
    return new_session(state, owner_id)


async def logout(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    revoke_session(state.repository, request.cookies.get(COOKIE, ""))
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
        prefs = snapshot(state.repository)
        feed = state.store.all_items()[:100]
        signals = radar_rows(state.repository)
        for item in [*feed, *signals]:
            item["language"] = content_language(
                str(item.get("title") or "") + " " + str(item.get("summary") or "")
            )
        for item in signals:
            item["kind"] = "radar"
        return {
            "feed": personalize(feed, prefs)[:30],
            "radar": personalize(signals, prefs),
            "sources": state.store.sources(),
            "health": feed_health(state.repository),
            "reading": list_notes(state.repository),
            "hidden": hidden_snapshot(state.repository),
            "personalization": {"topics": prefs["topics"], "feedback_count": len(prefs["feedback"]),
                                "algorithm": "heuristic_v1"},
            "locale": "ru-RU",
        }

    return web.json_response(await asyncio.to_thread(read))


async def set_topic_preference(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    try:
        payload = await request.json()
        topic, priority = payload["topic"], payload["priority"]
        if not isinstance(topic, str) or type(priority) is not int:
            return error("invalid_topic_priority")
        await asyncio.to_thread(set_priority, state.repository, topic, priority)
    except (KeyError, TypeError, ValueError):
        return error("invalid_topic_priority")
    return web.json_response({"ok": True, "topic": topic, "priority": priority})


async def set_content_feedback(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    try:
        payload = await request.json()
        kind, item_id, action = payload["kind"], payload["id"], payload["action"]
        if (kind not in {"news", "video", "radar"}
                or type(item_id) is not int or item_id <= 0
                or action not in {"more", "less", "not_interested",
                                  "already_known", "deeper", "follow", "clear"}):
            return error("invalid_feedback")
    except (KeyError, TypeError, ValueError):
        return error("invalid_feedback")

    def item_topic() -> str | None:
        if kind == "radar":
            with state.repository.connection() as db:
                row = db.execute(
                    """SELECT e.headline AS title,si.original_text AS summary
                    FROM events e JOIN source_items si
                    ON si.id=e.primary_source_item_id
                    WHERE e.id=? AND e.status='candidate'""", (item_id,)
                ).fetchone()
            item = dict(row) if row else None
        else:
            item = state.store.item(kind, item_id, detail=False)
        return material_topic(item) if item else None

    topic = await asyncio.to_thread(item_topic)
    if topic is None:
        return error("not_found", 404)
    await asyncio.to_thread(set_feedback, state.repository, kind, item_id, topic, action)
    return web.json_response({"ok": True, "kind": kind, "id": item_id,
                              "topic": topic, "action": action})


async def reset_personalization(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    try:
        payload = await request.json()
        if not isinstance(payload, dict) or payload.get("confirm") is not True:
            return error("confirmation_required")
    except (ValueError, TypeError):
        return error("confirmation_required")
    await asyncio.to_thread(clear_preferences, state.repository)
    return web.json_response({"ok": True})


async def capabilities(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    return web.json_response(public_capabilities(state.settings))


async def article_detail(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    kind = request.match_info["kind"]
    try:
        item_id = int(request.match_info["item_id"])
    except ValueError:
        return error("invalid_id")
    if kind not in {"news", "video"} or not 0 < item_id < 2**31:
        return error("invalid_id")
    item = await asyncio.to_thread(state.store.item, kind, item_id)
    return web.json_response({"item": item}) if item else error("not_found", 404)


async def signal_detail(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    try:
        event_id = int(request.match_info["item_id"])
    except ValueError:
        return error("invalid_id")
    if not 0 < event_id < 2**31:
        return error("invalid_id")

    def read() -> dict | None:
        with state.repository.connection() as db:
            row = db.execute(
                """SELECT e.id, e.headline, e.event_at, si.original_text,
                si.source_url, s.name AS source_name
                FROM events e JOIN source_items si ON si.id=e.primary_source_item_id
                JOIN sources s ON s.id=si.source_id
                WHERE e.id=? AND e.status='candidate'""", (event_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "kind": "radar", "id": row["id"], "title": row["headline"],
            "summary": plain_text(row["original_text"])[:2000],
            "content": {
                "brief": safe_html(str(row["original_text"] or "")[:12000]),
            },
            "source_name": row["source_name"],
            "sources": [
                {"title": row["source_name"], "url": public_url(row["source_url"])}
            ] if public_url(row["source_url"]) else [],
            "url": public_url(row["source_url"]),
            "published_at": row["event_at"], "verified": False,
        }

    item = await asyncio.to_thread(read)
    return web.json_response({"item": item}) if item else error("not_found", 404)


async def run_video_job(state: PortalState, job_id: str, video_id: str) -> None:
    job = state.video_jobs[job_id]
    job["status"] = "running"
    try:
        text = await asyncio.to_thread(state.store.reports.build_tldr, video_id)
        job.update({"status": "ready", "text": text[:24000]})
    except ReportError as exc:
        job.update({"status": "failed", "error": exc.status})
    except Exception:
        job.update({"status": "failed", "error": "generation_failed"})


async def video_summary(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    try:
        payload = await request.json()
        url = payload["url"]
        if not isinstance(url, str) or len(url) > 2048:
            return error("invalid_youtube_link")
        video_id = youtube_video_id(url)
    except (KeyError, TypeError, ValueError):
        return error("invalid_youtube_link")
    cached = await asyncio.to_thread(state.store.reports.cached_tldr, video_id)
    if cached:
        return web.json_response({
            "status": "ready", "text": cached[:24000], "cached": True,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })
    if not state.settings.video_reports_enabled:
        return error("video_generation_disabled", 409)
    if state.settings.openrouter_api_key is None:
        return error("ai_provider_unconfigured", 409)
    if state.settings.monid_api_key is None:
        return error("transcription_provider_unconfigured", 409)
    # Browser-side video generation requires explicit budget protection.
    if not state.settings.video_report_budget_enabled:
        return error("video_budget_guard_disabled", 409)
    if state.repository.current_month_cost() >= state.settings.budget_hard_stop_usd:
        return error("budget_blocked", 409)
    existing = state.video_by_id.get(video_id)
    if existing:
        return web.json_response(
            {"status": state.video_jobs[existing]["status"], "job_id": existing}
        )
    if any(job["status"] in {"queued", "running"} for job in state.video_jobs.values()):
        return error("video_busy", 429)
    if len(state.video_jobs) > 50:
        # Completed job results can be recovered from the durable report cache.
        state.video_jobs = {
            key: value for key, value in state.video_jobs.items()
            if value["status"] in {"queued", "running"}
        }
        state.video_by_id = {
            key: value for key, value in state.video_by_id.items()
            if value in state.video_jobs
        }
    job_id = secrets.token_urlsafe(18)
    state.video_jobs[job_id] = {"status": "queued", "error": None}
    state.video_by_id[video_id] = job_id
    task = asyncio.create_task(run_video_job(state, job_id, video_id))
    state.video_tasks.add(task)
    task.add_done_callback(state.video_tasks.discard)
    return web.json_response({"status": "queued", "job_id": job_id}, status=202)


async def video_job(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    job = state.video_jobs.get(request.match_info["job_id"])
    return web.json_response(job) if job else error("not_found", 404)


async def shutdown(app: web.Application) -> None:
    state: PortalState = app[STATE]
    if state.video_tasks:
        await asyncio.wait(state.video_tasks, timeout=5)


async def reader_item(request: web.Request) -> web.Response:
    """Read or save personal research notes only for real OSVED materials."""
    state: PortalState = request.app[STATE]
    kind = request.match_info["kind"]
    try:
        item_id = int(request.match_info["item_id"])
    except ValueError:
        return error("invalid_item")
    if kind not in {"news", "video", "radar"} or not 0 < item_id < 2**31:
        return error("invalid_item")

    def exists() -> bool:
        if kind == "radar":
            with state.repository.connection() as db:
                return db.execute(
                    "SELECT 1 FROM events WHERE id=? AND status='candidate'",
                    (item_id,),
                ).fetchone() is not None
        return state.store.item(kind, item_id, detail=False) is not None

    if not await asyncio.to_thread(exists):
        return error("not_found", 404)
    if request.method == "GET":
        result = await asyncio.to_thread(get_note, state.repository, kind, item_id)
        return web.json_response(result)
    try:
        body = await request.json()
        note = body["note"]
        is_read = body["is_read"]
        if not isinstance(note, str) or len(note) > 4000 or type(is_read) is not bool:
            return error("invalid_note")
    except (KeyError, ValueError, TypeError):
        return error("invalid_note")
    result = await asyncio.to_thread(
        save_note, state.repository, kind, item_id, note, is_read
    )
    return web.json_response(result)


async def hide_item(request: web.Request) -> web.Response:
    """Dismiss or restore one item or signal, without changing preferences."""
    state: PortalState = request.app[STATE]
    try:
        payload = await request.json()
        kind, item_id, hidden = payload["kind"], payload["id"], payload["hidden"]
        if (
            kind not in {"news", "video", "radar"}
            or type(item_id) is not int or not 0 < item_id < 2**31
            or type(hidden) is not bool
        ):
            return error("invalid_hidden_item")
    except (KeyError, TypeError, ValueError):
        return error("invalid_hidden_item")

    def exists() -> bool:
        if kind == "radar":
            with state.repository.connection() as db:
                return db.execute(
                    "SELECT 1 FROM events WHERE id=? AND status='candidate'",
                    (item_id,),
                ).fetchone() is not None
        return state.store.item(kind, item_id, detail=False) is not None

    if not await asyncio.to_thread(exists):
        return error("not_found", 404)
    await asyncio.to_thread(set_hidden, state.repository, kind, item_id, hidden)
    return web.json_response({"ok": True, "kind": kind, "id": item_id, "hidden": hidden})


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


async def add_youtube_source(request: web.Request) -> web.Response:
    """Owner adds a validated public channel, without authorizing paid resolution."""
    from app.telegram_bot.bot import configured_owner_id

    state: PortalState = request.app[STATE]
    try:
        data = await request.json()
        url = data["url"]
        if not isinstance(url, str) or len(url) > 2048:
            return error("invalid_youtube_channel")
        try:
            normalized = channel_url(
                "https://www.youtube.com/" + url if url.startswith("@") else url
            )
        except ChannelError:
            return error("invalid_youtube_channel")
        # Only direct UC links are guaranteed free. Resolve @handles via the
        # existing Monid guard only when the owner opts into THIS request.
        if "/channel/UC" not in normalized:
            if data.get("allow_paid_resolution") is not True:
                return error("youtube_resolution_consent_required")
            if state.settings.monid_api_key is None:
                return error("youtube_resolver_unconfigured", 503)
        owner_id = configured_owner_id(state.settings, state.repository)
        if not owner_id:
            return error("authentication_unconfigured", 503)
        result = await asyncio.to_thread(
            ChannelService(state.settings, state.repository).add,
            normalized, owner_id,
        )
    except ChannelError as exc:
        return web.json_response({
            "error": "youtube_channel_unavailable", "detail": str(exc)[:180],
        }, status=422)
    except (KeyError, TypeError, ValueError):
        return error("invalid_youtube_channel")
    return web.json_response({
        "ok": True, "source_id": result["source_id"],
        "title": result["title"], "existing": bool(result["existing"]),
    })


async def remove_youtube_source(request: web.Request) -> web.Response:
    """Soft-delete an owner-added channel without touching collected history."""
    from app.telegram_bot.bot import configured_owner_id

    state: PortalState = request.app[STATE]
    try:
        data = await request.json()
        source_id = data["id"]
        if not isinstance(source_id, str) or not source_id.startswith("youtube_user_"):
            return error("not_owner_added_source")
        owner_id = configured_owner_id(state.settings, state.repository)
        if not owner_id:
            return error("authentication_unconfigured", 503)
        with state.repository.connection() as db:
            found = db.execute(
                "SELECT 1 FROM youtube_channels WHERE source_id=? AND removed_at IS NULL",
                (source_id,),
            ).fetchone()
        if not found:
            return error("not_found", 404)
        await asyncio.to_thread(
            change_channel, state.settings, state.repository,
            source_id, "remove", owner_id,
        )
    except (KeyError, TypeError, ValueError):
        return error("invalid_source")
    except ChannelError:
        return error("not_found", 404)
    return web.json_response({"ok": True, "id": source_id, "removed": True})


async def add_public_source(request: web.Request) -> web.Response:
    """Add a fixed-platform public source to the live collector registry."""
    state: PortalState = request.app[STATE]
    try:
        data = await request.json()
        if not isinstance(data, dict):
            return error("invalid_source")
        kind = data["kind"]
        locator = data["locator"]
        topic = data.get("topic", "")
        if not isinstance(kind, str) or not isinstance(locator, str):
            return error("invalid_source")
        result = await asyncio.to_thread(
            add_public_subscription,
            state.repository, state.settings, kind, locator, topic,
        )
    except SourceInputError as exc:
        return web.json_response({"error": "invalid_public_source",
                                  "detail": str(exc)[:180]}, status=400)
    except (KeyError, TypeError, ValueError):
        return error("invalid_source")
    return web.json_response({"ok": True, **result})


async def remove_public_source(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    try:
        data = await request.json()
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            return error("invalid_source")
        source_id = data["id"]
        await asyncio.to_thread(
            remove_public_subscription, state.repository, state.settings, source_id
        )
    except (KeyError, TypeError, ValueError):
        return error("invalid_source")
    except SourceInputError as exc:
        return web.json_response({"error": "invalid_public_source",
                                  "detail": str(exc)[:180]}, status=400)
    return web.json_response({"ok": True, "id": source_id, "removed": True})


async def source_update(request: web.Request) -> web.Response:
    state: PortalState = request.app[STATE]
    try:
        data = await request.json()
        source_id = data["id"]
        enabled = data["enabled"]
        if (
            not isinstance(source_id, str)
            or not 1 <= len(source_id) <= 160
            or re.search(r"[\\x00-\\x1f]", source_id)
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
    await asyncio.to_thread(ensure_login_schema, state.repository)
    await asyncio.to_thread(initialize_sessions, state.repository)
    await asyncio.to_thread(initialize, state.repository)
    await asyncio.to_thread(initialize_personalization, state.repository)
    await asyncio.to_thread(initialize_hidden_items, state.repository)
    await asyncio.to_thread(initialize_public_sources, state.repository)


def create_portal(settings: Settings, repository: Repository) -> web.Application:
    app = web.Application(middlewares=[secure_headers, protect], client_max_size=12_000)
    app[STATE] = PortalState(settings, repository)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/session", session_status)
    app.router.add_post("/api/session", session_create)
    app.router.add_post("/api/code-login", code_login)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/api/overview", overview)
    app.router.add_get("/api/capabilities", capabilities)
    app.router.add_post("/api/personalization/topic", set_topic_preference)
    app.router.add_post("/api/personalization/feedback", set_content_feedback)
    app.router.add_post("/api/personalization/reset", reset_personalization)
    app.router.add_get("/api/article/{kind}/{item_id}", article_detail)
    app.router.add_get("/api/radar/{item_id}", signal_detail)
    app.router.add_post("/api/video/summary", video_summary)
    app.router.add_get("/api/video/jobs/{job_id}", video_job)
    app.router.add_post("/api/bookmark", bookmark)
    app.router.add_post("/api/hidden", hide_item)
    app.router.add_get("/api/reader/{kind}/{item_id}", reader_item)
    app.router.add_post("/api/reader/{kind}/{item_id}", reader_item)
    app.router.add_post("/api/source", source_update)
    app.router.add_post("/api/public-sources/add", add_public_source)
    app.router.add_post("/api/public-sources/remove", remove_public_source)
    app.router.add_post("/api/youtube/channels/add", add_youtube_source)
    app.router.add_post("/api/youtube/channels/remove", remove_youtube_source)
    app.router.add_get("/", static)
    app.router.add_get("/{filename}", static)
    app.on_startup.append(startup)
    app.on_shutdown.append(shutdown)
    return app


def main() -> None:
    settings = Settings()
    app = create_portal(settings, Repository(settings.database_path))
    web.run_app(app, host="0.0.0.0", port=8080, access_log=None)


if __name__ == "__main__":
    main()
