"""Navigation and shared Telegram/web bookmark regression checks."""

from app.telegram_bot.bookmarks import (
    bookmark_markup,
    is_bookmarked,
    toggle_delivery,
)
from app.telegram_bot.keyboards import reaction_keyboard
from app.telegram_bot.navigation import (
    LABELS,
    TEXT_TO_SECTION,
    inline_menu,
    parse_section,
    persistent_keyboard,
)
from tests.test_schedule import setup_schedule


def test_persistent_keyboard_opens_real_sections():
    keyboard = persistent_keyboard()
    assert keyboard.is_persistent is True
    assert keyboard.resize_keyboard is True
    labels = {button.text for row in keyboard.keyboard for button in row}
    assert {LABELS["feed"], LABELS["sources"], LABELS["media"]} <= labels
    assert all(TEXT_TO_SECTION[label] in LABELS for label in labels)
    main = inline_menu()
    callback_data = {
        button.callback_data for row in main.inline_keyboard for button in row
    }
    assert "osved_menu:feed" in callback_data
    assert "osved_menu:sources" in callback_data
    assert "osved_menu:media" in callback_data
    assert all(len(value.encode("utf-8")) <= 64 for value in callback_data)
    assert parse_section("osved_menu:sources") == "sources"
    assert parse_section("osved_menu:unknown") is None


def test_delivery_bookmarks_are_durable_and_owner_restricted(tmp_path):
    _, repository = setup_schedule(tmp_path)
    delivered = repository.create_smoke_delivery(123, "https://example.org/source")
    delivery_id = delivered["delivery_id"]
    card_id = delivered["card_id"]
    repository.mark_delivery_sent(delivery_id, 99)
    assert toggle_delivery(repository, delivery_id=delivery_id, owner_id=456) is None
    assert not is_bookmarked(repository, card_id)
    assert toggle_delivery(repository, delivery_id=delivery_id, owner_id=123) is True
    assert is_bookmarked(repository, card_id)
    with repository.connection() as db:
        row = db.execute(
            "SELECT saved FROM web_saved WHERE kind='news' AND item_id=?",
            (card_id,),
        ).fetchone()
    assert row["saved"] == 1
    assert toggle_delivery(repository, delivery_id=delivery_id, owner_id=123) is False
    assert not is_bookmarked(repository, card_id)


def test_bookmark_button_uses_delivery_id():
    keyboard = bookmark_markup(reaction_keyboard(17), delivery_id=17, saved=True)
    bookmarks = [
        button for row in keyboard.inline_keyboard for button in row
        if button.callback_data == "osved_save:17"
    ]
    assert len(bookmarks) == 1
    assert "В избранном" in bookmarks[0].text
    assert keyboard.inline_keyboard[-1][0].text == "Подробнее"
