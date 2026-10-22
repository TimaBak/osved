from app.web.oauth_state import (
    consume_oauth_state,
    initialize_oauth_states,
    new_oauth_state,
)
from tests.test_web_api import fixture


def test_oauth_state_single_use_and_bound_to_session(tmp_path):
    _, repo, _ = fixture(tmp_path)
    initialize_oauth_states(repo)
    token = new_oauth_state(
        repo, provider="github", owner_id=123, browser_session="session-A", now=1000
    )
    assert not consume_oauth_state(
        repo, provider="github", state=token, owner_id=123,
        browser_session="session-B", now=1001,
    )
    assert not consume_oauth_state(
        repo, provider="github", state=token, owner_id=123,
        browser_session="session-A", now=1002,
    )
    token = new_oauth_state(
        repo, provider="youtube", owner_id=123, browser_session="session-A", now=1000
    )
    assert consume_oauth_state(
        repo, provider="youtube", state=token, owner_id=123,
        browser_session="session-A", now=1001,
    )
    assert not consume_oauth_state(
        repo, provider="youtube", state=token, owner_id=123,
        browser_session="session-A", now=1002,
    )


def test_oauth_state_expires_and_provider_is_bound(tmp_path):
    _, repo, _ = fixture(tmp_path)
    initialize_oauth_states(repo)
    token = new_oauth_state(
        repo, provider="github", owner_id=123, browser_session="session-A", now=1000
    )
    assert not consume_oauth_state(
        repo, provider="youtube", state=token, owner_id=123,
        browser_session="session-A", now=1001,
    )
    token = new_oauth_state(
        repo, provider="github", owner_id=123, browser_session="session-A", now=1000
    )
    assert not consume_oauth_state(
        repo, provider="github", state=token, owner_id=123,
        browser_session="session-A", now=1600,
    )
