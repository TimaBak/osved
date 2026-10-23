"""Single process supervising Telegram and the bounded scheduled pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from app.collectors.ingest import redact_text
from app.config import Settings
from app.db.repository import Repository
from app.ops.feed_health import feed_health
from app.ops.schedule import (
    ScheduledJobExecutor,
    claim_runtime_window,
    fresh_research_events,
    run_schedule_tick,
)
from app.telegram_bot.bot import run_bot

logger = logging.getLogger(__name__)


async def resume_waiting_reader(settings: Settings, repository: Repository) -> None:
    """A replenished queue resumes after the reader's rating, not hours later."""
    from app.telegram_bot.bot import configured_owner_id
    from app.telegram_bot.news_queue import current_news, queue_enabled, send_next_news

    if (
        not queue_enabled(repository)
        or repository.get_runtime_setting("schedule_enabled") != "true"
        or repository.get_runtime_setting("schedule_dry_run") != "false"
    ):
        return
    owner = configured_owner_id(settings, repository)
    current = current_news(repository, owner) if owner is not None else None
    if current and repository.current_reaction(current["id"]):
        await send_next_news(
            settings,
            repository,
            after_delivery_id=current["id"],
            limit=settings.news_extra_batch_size,
        )



def run_first_news_pilot(settings: Settings, repository: Repository) -> dict:
    """Try one actual, sourced news event once; never auto-repeat paid operations."""
    if settings.app_env != "production" or settings.codex_sale_api_key is None:
        return {"status": "not_configured"}
    from app.telegram_bot.bot import configured_owner_id

    if configured_owner_id(settings, repository) is None:
        return {"status": "owner_not_configured"}
    from app.db.card_predicates import finished_card_sql

    with repository.connection() as connection:
        if connection.execute(
            f"SELECT 1 FROM cards WHERE {finished_card_sql()} LIMIT 1"
        ).fetchone():
            return {"status": "existing_card"}
    candidates = fresh_research_events(repository, now=datetime.now(UTC), limit=1)
    if not candidates:
        return {"status": "no_recent_evidence"}
    if not claim_runtime_window(repository, "first_news_pilot_v1", now=datetime.now(UTC)):
        return {"status": "already_attempted"}
    event_id = int(candidates[0]["id"])
    try:
        executor = ScheduledJobExecutor(settings, repository)
        outcome = executor.research_event(candidates[0])
        if outcome.get("cards_created"):
            sent = executor.delivery(limit=1)
            outcome["pilot_delivery"] = {
                "sent": sent.get("news_sent", 0), "status": sent.get("status")
            }
        repository.set_runtime_setting(
            "first_news_pilot_result_v1",
            json.dumps(outcome, ensure_ascii=False, default=str)[:6000],
        )
        return {"status": "attempted", "event_id": event_id,
                "cards_created": outcome.get("cards_created", 0)}
    except Exception as exc:
        repository.set_runtime_setting(
            "first_news_pilot_result_v1",
            json.dumps({"status": "failed", "error": redact_text(str(exc))[:300]}),
        )
        raise


async def schedule_worker(settings: Settings, repository: Repository) -> None:
    try:
        outcome = await asyncio.to_thread(run_first_news_pilot, settings, repository)
        logger.info("First news pilot: %s", outcome)
    except Exception as exc:
        logger.error("First news pilot failed: %s", redact_text(str(exc))[:300])
    while True:
        try:
            await asyncio.to_thread(run_schedule_tick, settings, repository)
            await resume_waiting_reader(settings, repository)
            repository.set_runtime_setting(
                "service_last_tick",
                datetime.now(UTC).isoformat(),
            )
            snapshot = feed_health(repository)
            previous = repository.get_runtime_setting("feed_health_status")
            if previous != snapshot["status"]:
                logger.warning("News feed product health changed: %s", snapshot)
                repository.set_runtime_setting("feed_health_status", snapshot["status"])
            repository.set_runtime_setting("feed_health", json.dumps(snapshot))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Schedule tick failed: %s", redact_text(str(exc))[:500])
        await asyncio.sleep(30)


async def portal_worker(settings: Settings, repository: Repository) -> None:
    """Expose the private dashboard only on the Docker-local port.

    This is one supervised backend: Telegram, scheduler and HTTPS-proxied
    portal all share the authoritative repository and deployment lifecycle.
    """
    from aiohttp import web

    from app.web.portal import create_portal

    runner = web.AppRunner(create_portal(settings, repository))
    await runner.setup()
    try:
        site = web.TCPSite(runner, host="0.0.0.0", port=8080)
        await site.start()
        logger.info("OSVED private portal is listening inside the service container")
        await asyncio.Future()
    finally:
        await runner.cleanup()


async def serve(settings: Settings, repository: Repository) -> None:
    # Initial liveness marker: the first bounded radar may take several minutes.
    # Only successful ticks refresh it afterward; a stuck/erroring scheduler
    # therefore becomes unhealthy after the existing fifteen-minute threshold.
    # This marker is not a claim that a scheduled job completed successfully.
    repository.set_runtime_setting("service_last_tick", datetime.now(UTC).isoformat())
    tasks = [
        asyncio.create_task(schedule_worker(settings, repository), name="schedule"),
        asyncio.create_task(run_bot(settings, repository), name="telegram"),
    ]
    if settings.app_env == "production":
        tasks.append(asyncio.create_task(portal_worker(settings, repository), name="portal"))
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
