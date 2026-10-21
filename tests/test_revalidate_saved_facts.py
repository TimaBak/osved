"""Saved fact revalidation must fail closed without network or charges."""
from unittest.mock import Mock

import pytest

from app.research.revalidate import revalidate_saved_fact_sheet


def test_unknown_event_rejected() -> None:
    repo = Mock()
    repo.event_context.return_value = None
    with pytest.raises(ValueError, match="Unknown event"):
        revalidate_saved_fact_sheet(repo, 36)
    repo.connection.assert_not_called()


def test_empty_invalid_sheet_is_noop() -> None:
    from contextlib import contextmanager

    @contextmanager
    def connection():
        db = Mock()
        db.execute.return_value.fetchone.return_value = None
        yield db

    repo = Mock()
    repo.event_context.return_value = {"headline": "Verified bots"}
    repo.connection = connection
    result = revalidate_saved_fact_sheet(repo, 36, apply=True)
    assert result["status"] == "no_saved_invalid_sheet"
    assert result["cost_usd"] == 0
    repo.create_fact_sheet.assert_not_called()
