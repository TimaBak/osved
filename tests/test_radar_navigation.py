"""Routed radar candidates remain explicitly unverified."""

from app.ops.news_readiness import diagnose
from app.telegram_bot.navigation import LABELS, persistent_keyboard, radar_preview
from tests.test_schedule import insert_event, setup_schedule


def test_radar_button_shows_real_candidates_without_mislabeling(tmp_path):
    _, repository = setup_schedule(tmp_path)
    insert_event(repository)
    text, keyboard = radar_preview(repository)
    assert "не прошли проверку фактов" in text
    assert "Новости готовы" not in text
    assert keyboard is not None
    assert any(button.url for row in keyboard.inline_keyboard for button in row)


def test_radar_empty_state_and_site_keyboard(tmp_path):
    _, repository = setup_schedule(tmp_path)
    text, keyboard = radar_preview(repository)
    assert "Новых сигналов пока нет" in text
    assert keyboard is None
    labels = [btn.text for row in persistent_keyboard().keyboard for btn in row]
    assert LABELS["site"] in labels


def test_portal_health_is_diagnostic_not_a_public_https_claim(tmp_path):
    _, repository = setup_schedule(tmp_path)
    healthy = diagnose(
        repository.database_path, openrouter_configured=False, portal_reachable=True
    )
    assert healthy["portal"]["backend_reachable"] is True
    assert healthy["portal"]["public_https_verified"] is False
    assert "card_provider_unconfigured" in healthy["issues"]
    missing = diagnose(
        repository.database_path, openrouter_configured=False, portal_reachable=False
    )
    assert missing["portal"]["backend_reachable"] is False
