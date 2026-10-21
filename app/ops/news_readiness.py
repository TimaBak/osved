"""Read-only OSVED news pipeline diagnostic (no provider calls or secret output).

Usage inside the running container:
  python -m app.ops.news_readiness --db /app/data/newsfeed.sqlite3
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from app.collectors.ingest import redact_text


def diagnose(database: Path, *, openrouter_configured: bool | None = None) -> dict:
    # URI mode=ro prevents this command from modifying production data.
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        def scalar(query: str, params: tuple = ()) -> int:
            return int(connection.execute(query, params).fetchone()[0] or 0)

        settings = {
            row["key"]: row["value"]
            for row in connection.execute(
                "SELECT key, value FROM runtime_settings WHERE key IN "
                "('schedule_enabled','schedule_dry_run','service_last_tick')"
            )
        }
        counts = {
            "source_items": scalar("SELECT COUNT(*) FROM source_items"),
            "candidate_events": scalar(
                "SELECT COUNT(*) FROM events WHERE status='candidate'"
            ),
            "valid_fact_sheets": scalar(
                "SELECT COUNT(*) FROM event_fact_sheets WHERE validation_status='valid'"
            ),
            "ready_dossiers": scalar(
                "SELECT COUNT(*) FROM event_dossiers "
                "WHERE decision='ready' AND validation_status='valid'"
            ),
            "sent_deliveries": scalar(
                "SELECT COUNT(*) FROM deliveries WHERE delivery_status='sent'"
            ),
        }
        # Reflect existing repository's card predicate instead of treating any
        # historical or invalid card row as publishable.
        from app.db.card_predicates import finished_card_sql
        counts["valid_cards"] = scalar(
            f"SELECT COUNT(*) FROM cards WHERE {finished_card_sql()}"
        )
        recent_slots = [
            {
                "job_type": row["job_type"],
                "status": row["status"],
                "slot_at": row["slot_at"],
                "error": redact_text(str(row["error"] or ""))[:200],
            }
            for row in connection.execute(
                "SELECT job_type,status,slot_at,error FROM schedule_slots "
                "ORDER BY slot_at DESC LIMIT 12"
            )
        ]
        issues: list[str] = []
        if openrouter_configured is False:
            issues.append("card_provider_unconfigured")
        if settings.get("schedule_enabled") != "true":
            issues.append("schedule_disabled")
        elif settings.get("schedule_dry_run") != "false":
            issues.append("schedule_dry_run")
        if counts["candidate_events"] == 0:
            issues.append("no_candidate_events")
        if counts["valid_fact_sheets"] == 0:
            issues.append("no_valid_fact_sheets")
        if counts["ready_dossiers"] == 0:
            issues.append("no_ready_dossiers")
        if counts["valid_cards"] == 0:
            issues.append("no_valid_cards")
        if counts["sent_deliveries"] == 0:
            issues.append("no_sent_deliveries")
        return {
            "database": str(database),
            "schedule_enabled": settings.get("schedule_enabled"),
            "schedule_dry_run": settings.get("schedule_dry_run"),
            "service_last_tick": settings.get("service_last_tick"),
            "card_provider": {
                "name": "openrouter",
                "configured": openrouter_configured,
            },
            "live_publication_ready": (
                settings.get("schedule_enabled") == "true"
                and settings.get("schedule_dry_run") == "false"
                and openrouter_configured is True
            ),
            "counts": counts,
            "issues": issues,
            "recent_slots": recent_slots,
            "note": "Run osved doctor separately for redacted provider configuration; "
                    "this report does not attempt paid calls or deliveries.",
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error("database does not exist")
    # No credentials leave this process: only the boolean configuration state
    # of the provider actually used by the existing generation pipeline.
    from app.config import Settings

    configured = Settings().openrouter_api_key is not None
    print(
        json.dumps(
            diagnose(args.db, openrouter_configured=configured),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
