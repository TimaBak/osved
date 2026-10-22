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
from app.web.hidden_items import hidden_snapshot, set_hidden
from app.web.hidden_items import initialize as initialize_hidden_items
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




async def github_disconnect(request: web.Request) -> web.Response:
    """Remove only the authenticated owner's chosen local GitHub credentials.

    This does not revoke authorization on github.com; the owner can revoke
    there under Settings -> Applications -> Authorized OAuth Apps.
    """
    from app.telegram_bot.bot import configured_owner_id
    from app.web.oauth_vault import revoke_stored_tokens

    state: PortalState = request.app[STATE]
    owner_id = configured_owner_id(state.settings, state.repository)
    if not owner_id:
        return error("unauthorized", 401)
    try:
        payload = await request.json()
        account_id = payload["account_id"]
        if not isinstance(account_id, str) or not account_id.isdecimal() or len(account_id) > 24:
            return error("invalid_account_id")
    except (ValueError, TypeError, KeyError):
        return error("invalid_account_id")
    removed = await asyncio.to_thread(
        revoke_stored_tokens, state.repository,
        provider="github", owner_id=owner_id, account_id=account_id,
    )
    return web.json_response({
        "ok": True, "removed": removed, "remote_authorization_revoked": False,
        "remote_revoke_url": "https://github.com/settings/applications",
    })


async def github_subscriptions_preview(request: web.Request) -> web.Response:
    """Owner-only private preview, excluding private repositories and tokens."""
    from app.telegram_bot.bot import configured_owner_id
    from app.web.github_subscriptions import GithubSubscriptionsError, list_repositories
    from app.web.oauth_vault import connected_accounts, read_tokens

    state: PortalState = request.app[STATE]
    owner_id = configured_owner_id(state.settings, state.repository)
    secret = state.settings.oauth_token_encryption_key
    if not owner_id or secret is None:
        return error("github_not_connected", 409)
    collection = request.query.get("collection", "starred")
    try:
        page = int(request.query.get("page", "1"))
        if collection not in {"starred", "watching"} or not 1 <= page <= 10:
            return error("invalid_github_collection")
        accounts = await asyncio.to_thread(
            connected_accounts, state.repository, provider="github", owner_id=owner_id
        )
        if len(accounts) != 1:
            return error("github_account_selection_required", 409)
        tokens = await asyncio.to_thread(
            read_tokens, state.repository, encryption_key=secret.get_secret_value(),
            provider="github", owner_id=owner_id, account_id=accounts[0],
        )
        if not tokens:
            return error("github_not_connected", 409)
        items = await asyncio.to_thread(
            list_repositories, tokens[0], collection=collection, page=page
        )
    except (ValueError, GithubSubscriptionsError):
        return error("github_subscription_fetch_failed", 502)
    return web.json_response({
        "collection": collection, "page": page,
        "repositories": items, "next_page": page + 1 if len(items) == 30 else None,
        "read_only": True,
    })


async def youtube_import_subscription(request: web.Request) -> web.Response:
    """Import only a channel the OAuth owner is actually subscribed to.

    Official subscriptions.list verifies membership and title; public Atom
    availability is deliberately not required for OAuth-sourced metadata.
    """
    from app.telegram_bot.bot import configured_owner_id
    from app.video.channels import CHANNEL_ID
    from app.web.oauth_vault import connected_accounts, read_tokens
    from app.web.youtube_subscriptions import (
        YoutubeSubscriptionsError,
        verify_owner_subscription,
    )

    state: PortalState = request.app[STATE]
    owner_id = configured_owner_id(state.settings, state.repository)
    key = state.settings.oauth_token_encryption_key
    if not owner_id or key is None:
        return error("youtube_not_connected", 409)
    try:
        data = await request.json()
        channel = data.get("channel_id") if isinstance(data, dict) else None
        if not isinstance(channel, str) or not CHANNEL_ID.fullmatch(channel):
            return error("invalid_youtube_channel")
        accounts = await asyncio.to_thread(
            connected_accounts, state.repository, provider="youtube", owner_id=owner_id,
        )
        if len(accounts) != 1:
            return error("youtube_account_selection_required", 409)
        tokens = await asyncio.to_thread(
            read_tokens, state.repository, encryption_key=key.get_secret_value(),
            provider="youtube", owner_id=owner_id, account_id=accounts[0],
        )
        if not tokens:
            return error("youtube_not_connected", 409)
        title = await asyncio.to_thread(verify_owner_subscription, tokens[0], channel)
        if not title:
            return error("youtube_not_in_subscriptions", 409)
        result = await asyncio.to_thread(
            ChannelService(state.settings, state.repository).add_verified,
            channel, title, owner_id,
        )
    except (ValueError, TypeError, KeyError):
        return error("invalid_youtube_channel")
    except YoutubeSubscriptionsError:
        return error("youtube_subscription_verify_failed", 502)
    except ChannelError as exc:
        return web.json_response({
            "error": "youtube_channel_unavailable", "detail": str(exc)[:180],
        }, status=422)
    return web.json_response({
        "ok": True, "source_id": result["source_id"],
        "title": result["title"], "existing": bool(result["existing"]),
    })


async def youtube_subscriptions_preview(request: web.Request) -> web.Response:
    from app.telegram_bot.bot import configured_owner_id
    from app.web.oauth_vault import connected_accounts, read_tokens
    from app.web.youtube_subscriptions import (
        YoutubeSubscriptionsError,
        list_subscriptions,
    )

    state: PortalState = request.app[STATE]
    owner_id = configured_owner_id(state.settings, state.repository)
    key = state.settings.oauth_token_encryption_key
    if not owner_id or key is None:
        return error("youtube_not_connected", 409)
    try:
        accounts = await asyncio.to_thread(
            connected_accounts, state.repository, provider="youtube", owner_id=owner_id,
        )
        if len(accounts) != 1:
            return error("youtube_account_selection_required", 409)
        token_pair = await asyncio.to_thread(
            read_tokens, state.repository, encryption_key=key.get_secret_value(),
            provider="youtube", owner_id=owner_id, account_id=accounts[0],
        )
        if not token_pair:
            return error("youtube_not_connected", 409)
        result = await asyncio.to_thread(
            list_subscriptions, token_pair[0], page_token=request.query.get("page", ""),
        )
    except ValueError:
        return error("invalid_youtube_page")
    except YoutubeSubscriptionsError:
        return error("youtube_subscriptions_fetch_failed", 502)
    # Annotate subscribed channels with their current OSVED source status.
    # No tokens or unrelated source metadata are returned to the browser.
    with state.repository.connection() as db:
        active = {
            row["channel_id"]: row["source_id"]
            for row in db.execute(
                "SELECT channel_id,source_id FROM youtube_channels "
                "WHERE removed_at IS NULL"
            )
        }
    for channel in result["channels"]:
        source_id = active.get(channel["channel_id"])
        channel["tracked"] = bool(source_id)
        channel["removable_source_id"] = (
            source_id if source_id and source_id.startswith("youtube_user_") else None
        )
    return web.json_response(result)


async def youtube_login_start(request: web.Request) -> web.Response:
    from app.telegram_bot.bot import configured_owner_id
    from app.web.oauth_state import new_oauth_state
    from app.web.youtube_oauth import authorization_url

    state: PortalState = request.app[STATE]
    owner_id = configured_owner_id(state.settings, state.repository)
    settings = state.settings
    if not owner_id or state.session(request) is None:
        return error("unauthorized", 401)
    if not (settings.oauth_google_client_id and settings.oauth_google_client_secret
            and settings.oauth_token_encryption_key):
        return error("youtube_oauth_unconfigured", 503)
    nonce = await asyncio.to_thread(
        new_oauth_state, state.repository, provider="youtube",
        owner_id=owner_id, browser_session=request.cookies.get(COOKIE, ""),
    )
    return web.json_response({
        "authorization_url": authorization_url(settings.oauth_google_client_id, nonce)
    })


async def youtube_login_callback(request: web.Request) -> web.Response:
    from app.telegram_bot.bot import configured_owner_id
    from app.web.oauth_state import consume_oauth_state
    from app.web.oauth_vault import save_tokens
    from app.web.youtube_oauth import (
        YOUTUBE_SCOPE,
        YoutubeOAuthError,
        exchange_code,
        own_channel_id,
    )

    state: PortalState = request.app[STATE]
    owner_id = configured_owner_id(state.settings, state.repository)
    if not owner_id or state.session(request) is None:
        return error("unauthorized", 401)
    code = request.query.get("code", "")
    if not 1 <= len(code) <= 2048:
        return error("invalid_oauth_callback")
    valid = await asyncio.to_thread(
        consume_oauth_state, state.repository, provider="youtube",
        state=request.query.get("state", ""), owner_id=owner_id,
        browser_session=request.cookies.get(COOKIE, ""),
    )
    if not valid:
        return error("invalid_oauth_state", 403)
    settings = state.settings
    if not (settings.oauth_google_client_id and settings.oauth_google_client_secret
            and settings.oauth_token_encryption_key):
        return error("youtube_oauth_unconfigured", 503)
    try:
        access, refresh = await asyncio.to_thread(
            exchange_code, settings.oauth_google_client_id,
            settings.oauth_google_client_secret.get_secret_value(), code,
        )
        channel_id = await asyncio.to_thread(own_channel_id, access)
        await asyncio.to_thread(
            save_tokens, state.repository,
            encryption_key=settings.oauth_token_encryption_key.get_secret_value(),
            provider="youtube", owner_id=owner_id, account_id=channel_id,
            access_token=access, refresh_token=refresh, scopes=YOUTUBE_SCOPE,
        )
    except (YoutubeOAuthError, ValueError):
        return error("youtube_oauth_failed", 502)
    raise web.HTTPFound("/?youtube_connected=1")


async def github_login_start(request: web.Request) -> web.Response:
    """Issue state bound to existing owner session; never silently connect."""
    from app.telegram_bot.bot import configured_owner_id
    from app.web.github_oauth import authorization_url
    from app.web.oauth_state import new_oauth_state

    state: PortalState = request.app[STATE]
    owner_id = configured_owner_id(state.settings, state.repository)
    session_cookie = request.cookies.get(COOKIE, "")
    if not owner_id or state.session(request) is None:
        return error("unauthorized", 401)
    if not (state.settings.oauth_github_client_id
            and state.settings.oauth_github_client_secret
            and state.settings.oauth_token_encryption_key):
        return error("github_oauth_unconfigured", 503)
    nonce = await asyncio.to_thread(
        new_oauth_state, state.repository, provider="github",
        owner_id=owner_id, browser_session=session_cookie,
    )
    return web.json_response({
        "authorization_url": authorization_url(state.settings.oauth_github_client_id, nonce)
    })


async def github_login_callback(request: web.Request) -> web.Response:
    """Consume one-use state before code exchange; persist encrypted token."""
    from app.telegram_bot.bot import configured_owner_id
    from app.web.github_oauth import GithubOAuthError, exchange_code, github_identity
    from app.web.oauth_state import consume_oauth_state
    from app.web.oauth_vault import save_tokens

    state: PortalState = request.app[STATE]
    owner_id = configured_owner_id(state.settings, state.repository)
    if not owner_id or state.session(request) is None:
        return error("unauthorized", 401)
    token_state = request.query.get("state", "")
    code = request.query.get("code", "")
    if not 1 <= len(code) <= 512:
        return error("invalid_oauth_callback")
    valid = await asyncio.to_thread(
        consume_oauth_state, state.repository, provider="github",
        state=token_state, owner_id=owner_id,
        browser_session=request.cookies.get(COOKIE, ""),
    )
    if not valid:
        return error("invalid_oauth_state", 403)
    credentials = state.settings
    if not (credentials.oauth_github_client_id and credentials.oauth_github_client_secret
            and credentials.oauth_token_encryption_key):
        return error("github_oauth_unconfigured", 503)
    try:
        token = await asyncio.to_thread(
            exchange_code, credentials.oauth_github_client_id,
            credentials.oauth_github_client_secret.get_secret_value(), code,
        )
        github_id = await asyncio.to_thread(github_identity, token)
        await asyncio.to_thread(
            save_tokens, state.repository,
            encryption_key=credentials.oauth_token_encryption_key.get_secret_value(),
            provider="github", owner_id=owner_id, account_id=github_id,
            access_token=token, scopes="read:user",
        )
    except (GithubOAuthError, ValueError):
        return error("github_oauth_failed", 502)
    raise web.HTTPFound("/?github_connected=1")


async def account_connection_status(request: web.Request) -> web.Response:
    """Never claim OAuth is usable before state, token vault and revoke exist."""
    from app.telegram_bot.bot import configured_owner_id
    from app.web.oauth_vault import connected_accounts

    app_state: PortalState = request.app[STATE]
    settings = app_state.settings
    owner_id = configured_owner_id(settings, app_state.repository)
    youtube_accounts = connected_accounts(
        app_state.repository, provider="youtube", owner_id=owner_id
    ) if owner_id else []
    github_accounts = connected_accounts(
        app_state.repository, provider="github", owner_id=owner_id
    ) if owner_id else []
    github_configured = bool(
        settings.oauth_github_client_id and settings.oauth_github_client_secret
    )
    youtube_configured = bool(
        settings.oauth_google_client_id and settings.oauth_google_client_secret
    )
    vault_configured = settings.oauth_token_encryption_key is not None
    return web.json_response({
        "accounts": {
            "github": {
                "configuration_present": github_configured,
                "connected": bool(github_accounts),
                "account_ids": github_accounts,
                "login_available": github_configured and vault_configured,
                "missing": (["oauth_app"] if not github_configured else [])
                + (["token_vault"] if not vault_configured else [])
                + ([] if github_configured and vault_configured else ["callback_and_consent"]),
            },
            "youtube": {
                "configuration_present": youtube_configured,
                "connected": bool(youtube_accounts),
                "account_ids": youtube_accounts,
                "login_available": youtube_configured and vault_configured,
                "missing": (["oauth_app"] if not youtube_configured else [])
                + (["token_vault"] if not vault_configured else [])
                + ["callback_and_consent"],
            },
        },
        "token_vault_configured": vault_configured,
        "external_credentials_exposed": False,
    })


async def ai_model_settings(request: web.Request) -> web.Response:
    """Owner-only read of effective selections; never exposes provider secrets."""
    from app.llm.routing_policy import fallback_permitted, resolve_selection

    state: PortalState = request.app[STATE]
    tasks = ("news", "research", "search", "video")
    source_id = request.query.get("source_id")
    scenario_id = request.query.get("scenario_id")
    profile_id = request.query.get("profile_id")
    try:
        from app.llm.routing_policy import _key

        for scope, ident in (("source", source_id), ("scenario", scenario_id),
                             ("profile", profile_id)):
            if ident is not None:
                _key("news", scope, ident)
    except ValueError:
        return error("invalid_model_scope")
    selections = {
        task: {
            "provider": (route := resolve_selection(
                state.repository, task=task, source_id=source_id,
                scenario_id=scenario_id, profile_id=profile_id,
            )).provider,
            "model": route.model,
            "origin": route.origin,
            "verified": route.verified,
        }
        for task in tasks
    }
    return web.json_response({
        "provider": "codexsale",
        "provider_status": "not_verified",
        "settings_scope": "shared_runtime_settings",
        "openrouter_fallback_opt_in": fallback_permitted(state.repository),
        "model_execution_enabled": False,
        "scopes": {"source": source_id, "scenario": scenario_id, "profile": profile_id},
        "selections": selections,
    })



async def ai_model_catalog(request: web.Request) -> web.Response:
    """Read account model IDs on explicit owner request (no completion calls)."""
    from app.llm.codexsale import CodexSaleClient, CodexSaleError

    state: PortalState = request.app[STATE]
    secret = state.settings.codex_sale_api_key
    if secret is None:
        return error("codexsale_unconfigured", 503)
    try:
        client = CodexSaleClient(secret.get_secret_value(), timeout=10)
        models = await asyncio.to_thread(client.models)
    except CodexSaleError:
        return error("codexsale_catalog_unavailable", 503)
    ids = sorted({
        item["id"] for item in models
        if isinstance(item.get("id"), str)
        and 0 < len(item["id"]) <= 128
    })
    return web.json_response({
        "provider": "codexsale", "models": ids,
        "capabilities_verified": False,
        "note": "Catalog membership does not verify task capability or billing.",
    })


async def ai_model_select(request: web.Request) -> web.Response:
    """Persist a chosen text-model ID only after live catalog membership check.

    This endpoint does not make billable completion requests.
    """
    from app.llm.codexsale import CodexSaleClient, CodexSaleError
    from app.llm.routing_policy import set_selection

    state: PortalState = request.app[STATE]
    secret = state.settings.codex_sale_api_key
    if secret is None:
        return error("codexsale_unconfigured", 503)
    try:
        payload = await request.json()
        if not isinstance(payload, dict) or not {"task", "model"} <= set(payload):
            return error("invalid_model_selection")
        if set(payload) - {"task", "model", "scope", "scope_id"}:
            return error("invalid_model_selection")
        task, model = payload["task"], payload["model"]
        scope, scope_id = payload.get("scope"), payload.get("scope_id")
        if not isinstance(task, str) or not isinstance(model, str):
            return error("invalid_model_selection")
        if len(model) > 128:
            return error("invalid_model_selection")
        client = CodexSaleClient(secret.get_secret_value(), timeout=10)
        catalog = await asyncio.to_thread(client.models)
        verified_ids = {item["id"] for item in catalog if isinstance(item.get("id"), str)}
        # /models confirms membership only; execution remains separately disabled.
        await asyncio.to_thread(
            set_selection, state.repository,
            task=task, model=model, scope=scope, scope_id=scope_id,
            verified_models=verified_ids,
        )
    except (ValueError, TypeError, KeyError):
        return error("invalid_model_selection")
    except CodexSaleError:
        return error("codexsale_catalog_unavailable", 503)
    return web.json_response({
        "ok": True, "task": task, "model": model,
        "scope": scope, "scope_id": scope_id,
        "execution_enabled": False,
        "capability_verified": False,
    })


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
    from app.web.oauth_state import initialize_oauth_states

    await asyncio.to_thread(initialize_oauth_states, state.repository)
    from app.web.oauth_vault import initialize_token_vault

    await asyncio.to_thread(initialize_token_vault, state.repository)
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
    app.router.add_get("/api/accounts/status", account_connection_status)
    app.router.add_get("/api/accounts/github/subscriptions", github_subscriptions_preview)
    app.router.add_post("/api/accounts/github/disconnect", github_disconnect)
    app.router.add_get("/api/accounts/youtube/subscriptions", youtube_subscriptions_preview)
    app.router.add_post("/api/accounts/youtube/channels/import", youtube_import_subscription)
    app.router.add_post("/api/accounts/youtube/start", youtube_login_start)
    app.router.add_get("/api/accounts/youtube/callback", youtube_login_callback)
    app.router.add_post("/api/accounts/github/start", github_login_start)
    app.router.add_get("/api/accounts/github/callback", github_login_callback)
    app.router.add_get("/api/ai/models", ai_model_settings)
    app.router.add_get("/api/ai/catalog", ai_model_catalog)
    app.router.add_post("/api/ai/models", ai_model_select)
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
