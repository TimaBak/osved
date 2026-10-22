"""Encrypted OAuth tokens are never stored as plaintext or returned publicly."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.web.oauth_vault import (
    connected_accounts,
    initialize_token_vault,
    read_tokens,
    revoke_stored_tokens,
    save_tokens,
)
from tests.test_web_api import fixture


def test_vault_encrypts_roundtrips_preserves_refresh_and_revokes(tmp_path):
    _, repo, _ = fixture(tmp_path)
    initialize_token_vault(repo)
    key = Fernet.generate_key().decode("ascii")
    save_tokens(
        repo, encryption_key=key, provider="github", owner_id=123,
        account_id="me", access_token="SECRET_ACCESS", refresh_token="SECRET_REFRESH",
    )
    with repo.connection() as db:
        row = db.execute("SELECT * FROM oauth_account_tokens").fetchone()
        assert b"SECRET_ACCESS" not in row["access_cipher"]
        assert b"SECRET_REFRESH" not in row["refresh_cipher"]
    assert read_tokens(
        repo, encryption_key=key, provider="github", owner_id=123, account_id="me"
    ) == ("SECRET_ACCESS", "SECRET_REFRESH")
    assert connected_accounts(repo, provider="github", owner_id=123) == ["me"]
    assert connected_accounts(repo, provider="github", owner_id=456) == []
    save_tokens(
        repo, encryption_key=key, provider="github", owner_id=123,
        account_id="me", access_token="SECOND_ACCESS",
    )
    assert read_tokens(
        repo, encryption_key=key, provider="github", owner_id=123, account_id="me"
    ) == ("SECOND_ACCESS", "SECRET_REFRESH")
    with pytest.raises(ValueError, match="cannot be decrypted"):
        read_tokens(
            repo, encryption_key=Fernet.generate_key().decode("ascii"),
            provider="github", owner_id=123, account_id="me",
        )
    assert revoke_stored_tokens(repo, provider="github", owner_id=123, account_id="me")
    assert not revoke_stored_tokens(repo, provider="github", owner_id=123, account_id="me")
    assert read_tokens(
        repo, encryption_key=key, provider="github", owner_id=123, account_id="me"
    ) is None
