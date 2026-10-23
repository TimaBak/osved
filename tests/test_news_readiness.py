"""News publication readiness is honest and never invokes a provider."""

from app.ops.news_readiness import diagnose
from app.ops.schedule import configure_schedule
from tests.test_schedule import setup_schedule


def test_readiness_reports_disabled_schedule_and_missing_card_provider(tmp_path):
    _, repository = setup_schedule(tmp_path)
    report = diagnose(repository.database_path, openrouter_configured=False)

    assert report["card_provider"] == {"name": "openrouter", "configured": False}
    assert report["live_publication_ready"] is False
    assert "schedule_disabled" in report["issues"]
    assert "card_provider_unconfigured" in report["issues"]
    assert report["counts"]["valid_cards"] == 0
    assert report["counts"]["sent_deliveries"] == 0


def test_readiness_distinguishes_live_mode_from_observed_news(tmp_path):
    _, repository = setup_schedule(tmp_path)
    configure_schedule(repository, enabled=True, dry_run=True)
    dry = diagnose(repository.database_path, openrouter_configured=True, openrouter_opt_in=True)
    assert dry["live_publication_ready"] is False
    assert "schedule_dry_run" in dry["issues"]
    assert "card_provider_unconfigured" not in dry["issues"]

    configure_schedule(repository, enabled=True, dry_run=False)
    live = diagnose(repository.database_path, openrouter_configured=True, openrouter_opt_in=True)
    assert live["live_publication_ready"] is True
    assert "no_valid_cards" in live["issues"]
    assert "no_sent_deliveries" in live["issues"]

def test_codexsale_is_ready_without_openrouter(tmp_path):
    _, repository = setup_schedule(tmp_path)
    configure_schedule(repository, enabled=True, dry_run=False)
    report = diagnose(
        repository.database_path, openrouter_configured=False, codexsale_configured=True
    )
    assert report["card_provider"] == {"name": "codexsale", "configured": True}
    assert report["live_publication_ready"] is True


def test_openrouter_requires_explicit_opt_in(tmp_path):
    _, repository = setup_schedule(tmp_path)
    report = diagnose(repository.database_path, openrouter_configured=True)
    assert report["card_provider"]["configured"] is False
    permitted = diagnose(
        repository.database_path, openrouter_configured=True, openrouter_opt_in=True
    )
    assert permitted["card_provider"]["configured"] is True
