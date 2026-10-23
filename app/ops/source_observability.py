"""Read-only source collection history from the authoritative SQLite ledger.

Importing a source is not evidence of a successful polling cycle. This module
never calls upstream providers, changes source settings, or triggers collection.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import UTC, datetime

from app.collectors.ingest import redact_text

SUCCESS = frozenset({"ok", "partial", "empty", "filtered", "pending"})


def snapshots(db: sqlite3.Connection) -> dict[str, dict]:
    rows = db.execute(
        """SELECT s.id, s.kind, s.enabled, s.role, s.admission_mode,
            override.value AS enabled_override,
            h.consecutive_errors, h.cooldown_until, h.last_attempt_at,
            h.last_productive_at,
            r.status AS run_status, r.started_at, r.finished_at,
            r.items_seen, r.items_inserted, r.items_rejected,
            r.latency_ms, r.error,
            (SELECT COUNT(*) FROM source_items i WHERE i.source_id=s.id) AS total_items,
            (SELECT MAX(i.published_at) FROM source_items i WHERE i.source_id=s.id)
                AS latest_item_published_at
        FROM sources s
        LEFT JOIN runtime_settings override ON override.key='source_enabled:'||s.id
        LEFT JOIN source_health h ON h.source_id=s.id
        LEFT JOIN source_runs r ON r.rowid=(
            SELECT last_run.rowid FROM source_runs last_run
            WHERE last_run.source_id=s.id AND last_run.strategy!='snapshot_replay'
            ORDER BY last_run.started_at DESC, last_run.rowid DESC LIMIT 1
        )
        ORDER BY s.kind,s.id"""
    ).fetchall()
    output = {}
    for item in rows:
        row = dict(item)
        enabled = (
            row["enabled_override"] == "true"
            if row["enabled_override"] is not None
            else bool(row["enabled"])
        )
        last = row["run_status"]
        if not enabled:
            status = "paused"
        elif row["role"] == "own_history" or row["admission_mode"] == "history":
            status = "history_only"
        elif last is None:
            status = "never_checked"
        elif last == "running":
            status = "running"
        elif last not in SUCCESS:
            status = "error"
        elif int(row["items_inserted"] or 0) > 0:
            status = "collected"
        elif int(row["items_seen"] or 0) > 0:
            status = "no_new_items"
        else:
            status = "empty"
        output[row["id"]] = {
            "source_id": row["id"],
            "kind": row["kind"],
            "enabled": enabled,
            "status": status,
            "last_run_status": last,
            "last_attempt_at": row["started_at"] or row["last_attempt_at"],
            "last_finished_at": row["finished_at"],
            "last_productive_at": row["last_productive_at"],
            "last_run_seen": int(row["items_seen"] or 0),
            "last_run_inserted": int(row["items_inserted"] or 0),
            "last_run_rejected": int(row["items_rejected"] or 0),
            "total_items": int(row["total_items"]),
            "latest_item_published_at": row["latest_item_published_at"],
            "consecutive_errors": int(row["consecutive_errors"] or 0),
            "cooldown_until": row["cooldown_until"],
            "last_error": redact_text(str(row["error"] or ""))[:180] or None,
        }
    return output


def summarize(values: dict[str, dict], *, now: datetime | None = None) -> dict:
    """Bounded operational summary, suitable for an automated read-only log."""
    now = now or datetime.now(UTC)
    counts = Counter()
    platform = {}
    latest_errors = []
    for row in values.values():
        kind = row["kind"]
        if kind not in platform:
            platform[kind] = {"active": 0, "collected": 0, "never_checked": 0, "errors": 0}
        if not row["enabled"]:
            continue
        status = row["status"]
        counts[status] += 1
        platform[kind]["active"] += 1
        if status == "collected":
            platform[kind]["collected"] += 1
        if status == "never_checked":
            platform[kind]["never_checked"] += 1
        if status == "error":
            platform[kind]["errors"] += 1
            if len(latest_errors) < 10:
                latest_errors.append({
                    "source_id": row["source_id"],
                    "kind": kind, "run_status": row["last_run_status"],
                    "last_attempt_at": row["last_attempt_at"],
                    "error": row["last_error"],
                })
    return {
        "active_status_counts": dict(sorted(counts.items())),
        "by_platform": dict(sorted(platform.items())),
        "recent_failed_sources": latest_errors,
        "observed_at": now.isoformat(),
        "read_only": True,
    }
