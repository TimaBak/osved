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
    """Try up to three new verified events once; never retry after restart."""
    if settings.app_env != "production" or settings.codex_sale_api_key is None:
        return {"status": "not_configured"}
    from app.telegram_bot.bot import configured_owner_id
    from app.db.card_predicates import finished_card_sql

    owner = configured_owner_id(settings, repository)
    if owner is None:
        return {"status": "owner_not_configured"}
    with repository.connection() as connection:
        if connection.execute(
            f"SELECT 1 FROM cards WHERE {finished_card_sql()} LIMIT 1"
        ).fetchone():
            return {"status": "existing_card"}
    candidates = fresh_research_events(repository, now=datetime.now(UTC), limit=10)
    if not candidates:
        return {"status": "no_recent_evidence"}
    key = "first_news_pilot_v2"
    if not claim_runtime_window(repository, key, now=datetime.now(UTC)):
        return {"status": "already_attempted"}
    start_cost = repository.current_month_cost()
    outcomes = []
    try:
        executor = ScheduledJobExecutor(settings, repository)
        for event in candidates[:3]:
            if repository.current_month_cost() - start_cost >= 0.03:
                break
            result = executor.research_event(event)
            outcomes.append({
                "event_id": int(event["id"]),
                "cards_created": result.get("cards_created", 0),
                "fact_sheet": result.get("fact_sheet", {}).get("status"),
                "errors": result.get("errors", 0),
                "research": result.get("research", {}).get("status"),
            })
            if result.get("cards_created"):
                from app.ops.schedule import fresh_delivery_card_ids
                from app.telegram_bot.bot import send_cards_by_ids

                card_ids = fresh_delivery_card_ids(
                    repository, owner_id=owner, now=datetime.now(UTC), limit=1
                )
                if card_ids:
                    sent = asyncio.run(
                        send_cards_by_ids(settings, repository, card_ids)
                    )
                    outcomes[-1]["delivery_sent"] = sent.get("sent", 0)
                break
        result = {
            "attempts": outcomes,
            "cards_created": sum(item["cards_created"] for item in outcomes),
            "cost_usd_observed": max(0.0, repository.current_month_cost() - start_cost),
        }
        repository.set_runtime_setting(
            "first_news_pilot_result_v2",
            json.dumps(result, ensure_ascii=False)[:5000],
        )
        return result
    except Exception as exc:
        repository.set_runtime_setting(
            "first_news_pilot_result_v2",
            json.dumps({"attempts": outcomes, "status": "failed",
                        "error": redact_text(str(exc))[:300]}),
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
