"""Offline revalidation of stored AI facts against stored source documents.

No model, search, scrape or Telegram call. Reuses normal fact safety gates.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.db.repository import Repository
from app.research.facts import (
    FACT_SHEET_SCHEMA_VERSION,
    FactCoverage,
    FactConflict,
    FactSheetDraft,
    ResearchFact,
    sanitize_fact_sheet,
    select_research_documents,
    validate_fact_sheet,
)
from app.research.policy import fact_policy_metadata


def revalidate_saved_fact_sheet(
    repository: Repository,
    event_id: int,
    *,
    apply: bool = False,
) -> dict:
    event = repository.event_context(event_id)
    if event is None:
        raise ValueError("Unknown event")
    with repository.connection() as connection:
        row = connection.execute(
            """SELECT id, facts_json, coverage_json FROM event_fact_sheets
            WHERE event_id=? AND validation_status='invalid'
            ORDER BY fact_sheet_version DESC LIMIT 1""",
            (event_id,),
        ).fetchone()
    if row is None:
        return {"event_id": event_id, "status": "no_saved_invalid_sheet", "cost_usd": 0}
    facts = json.loads(row["facts_json"])
    coverage = json.loads(row["coverage_json"])
    documents = select_research_documents(
        repository.event_research_documents(event_id),
        event_headline=str(event.get("headline") or ""),
    )
    if not documents or not any(d.get("source_class") == "primary" for d in documents):
        return {
            "event_id": event_id, "status": "invalid",
            "errors": ["Full-text primary evidence is required"], "cost_usd": 0,
        }
    draft = FactSheetDraft(
        event_type=coverage.get("event_type", "other"),
        facts=[ResearchFact.model_validate(f) for f in facts],
        coverage=FactCoverage(
            event_identity=False, capabilities=False, benchmarks=False,
            pricing=False, availability=False, limitations=False,
            independent_confirmation=False,
        ),
        conflicts=[
            FactConflict.model_validate(c) for c in coverage.get("conflicts", [])
        ],
        editorial_hook=None,
    )
    validated, warnings = sanitize_fact_sheet(
        draft, documents, event_headline=str(event.get("headline") or "")
    )
    errors = validate_fact_sheet(validated, documents)
    result = {
        "event_id": event_id,
        "status": "valid" if not errors else "invalid",
        "fact_count": len(validated.facts),
        "hook": validated.editorial_hook.model_dump() if validated.editorial_hook else None,
        "errors": errors,
        "warnings": warnings,
        "cost_usd": 0,
        "applied": False,
    }
    if errors or not apply:
        return result
    fact_id = repository.create_fact_sheet(
        event_id=event_id,
        schema_version=FACT_SHEET_SCHEMA_VERSION,
        facts=[fact.model_dump() for fact in validated.facts],
        coverage={
            **validated.coverage.model_dump(),
            **fact_policy_metadata(),
            "event_type": validated.event_type,
            "editorial_hook": validated.editorial_hook.model_dump(),
            "conflicts": [conflict.model_dump() for conflict in validated.conflicts],
            "conflict_count": len(validated.conflicts),
            "dropped_fact_count": len(facts) - len(validated.facts),
            "dropped_fact_errors": warnings,
        },
        validation_status="valid",
        validation_errors=[],
        research_cost_usd=0,
        expires_at=(datetime.now(UTC) + timedelta(days=30)).isoformat(),
    )
    repository.update_event_classification(event_id, event_type=validated.event_type)
    from app.research.dossier import build_event_dossier

    result["fact_sheet_id"] = fact_id
    result["dossier"] = build_event_dossier(repository, event_id)
    result["applied"] = True
    return result
