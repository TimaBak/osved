from app.pipeline.telegram_style import clean_news_html
from app.telegram_bot.emoji_style import FALLBACK, PACKS, emoji_html, headline_role, load_custom_emoji_ids


def test_registered_packs_and_balanced_fallback() -> None:
    assert len(PACKS) == 15
    assert emoji_html("security") == FALLBACK["security"]
    assert headline_role("Continuous accountability for Verified bots") == "security"


def test_custom_emoji_html_is_preserved() -> None:
    markup = emoji_html("news", {"news": "1234567890123456789"})
    assert '<tg-emoji emoji-id="1234567890123456789">' in markup
    assert clean_news_html(markup + " <b>Новость</b>") == markup + " <b>Новость</b>"


def test_untrusted_emoji_ids_are_rejected(tmp_path) -> None:
    data = tmp_path / "emoji_ids.json"
    data.write_text('{"news":"1\" onload=\"x","security":"1234567890"}', encoding="utf-8")
    assert load_custom_emoji_ids(data) == {}
    data.write_text('{"news":"not-an-id","security":"1234567890"}', encoding="utf-8")
    assert load_custom_emoji_ids(data) == {"security": "1234567890"}
    assert emoji_html("news", {"news": "bad"}) == "📰"
