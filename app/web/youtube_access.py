"""Server-only retry of YouTube reads when Google expires an access token."""
from __future__ import annotations

from collections.abc import Callable

from app.config import Settings
from app.db.repository import Repository
from app.web.oauth_vault import read_tokens, save_tokens
from app.web.youtube_oauth import (
    YOUTUBE_SCOPE,
    YoutubeReconnectRequired,
    refresh_access_token,
)
from app.web.youtube_subscriptions import YoutubeSubscriptionsAuthError


def with_youtube_access[T](
    settings: Settings, repository: Repository, owner_id: int,
    account_id: str, operation: Callable[[str], T],
) -> T:
    """Retry once with refreshed credentials; never return tokens to the browser."""
    key = settings.oauth_token_encryption_key
    if key is None:
        raise YoutubeReconnectRequired("youtube_reconnect_required")
    encrypted_key = key.get_secret_value()
    tokens = read_tokens(
        repository, encryption_key=encrypted_key, provider="youtube",
        owner_id=owner_id, account_id=account_id,
    )
    if tokens is None:
        raise YoutubeReconnectRequired("youtube_reconnect_required")
    access, refresh = tokens
    try:
        return operation(access)
    except YoutubeSubscriptionsAuthError:
        if (not refresh or not settings.oauth_google_client_id
                or not settings.oauth_google_client_secret):
            raise YoutubeReconnectRequired("youtube_reconnect_required") from None
        new_access = refresh_access_token(
            settings.oauth_google_client_id,
            settings.oauth_google_client_secret.get_secret_value(), refresh,
        )
        save_tokens(
            repository, encryption_key=encrypted_key, provider="youtube",
            owner_id=owner_id, account_id=account_id, access_token=new_access,
            scopes=YOUTUBE_SCOPE,
        )
        try:
            return operation(new_access)
        except YoutubeSubscriptionsAuthError as exc:
            raise YoutubeReconnectRequired("youtube_reconnect_required") from exc
