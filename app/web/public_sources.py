"""Owner-managed public GitHub repositories and Reddit communities.

All external collector requests use platform-specific, fixed-host adapters.
This module makes no network requests, stores no platform credentials, and
retains the original source events on removal.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit

from app.config import Settings, runtime_source_registry
from app.db.repository import Repository

KINDS = {"github", "reddit"}
GITHUB_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
GITHUB_REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}")
REDDIT_COMMUNITY = re.compile(r"[A-Za-z0-9_]{2,21}")
MAX_SOURCES = 50


class SourceInputError(ValueError):
    pass


def normalize(kind: str, value: str) -> tuple[str, str, str]:
    """Canonical fixed-platform locator, display name and public URL."""
    if kind not in KINDS or not isinstance(value, str) or not 2 <= len(value) <= 300:
        raise SourceInputError("Неизвестная платформа или слишком длинная ссылка.")
    value = value.strip()
    if any(ord(ch) < 32 for ch in value):
        raise SourceInputError("Недопустимые символы ссылки.")
    if "://" in value:
        url = urlsplit(value)
        allowed = {"github": {"github.com", "www.github.com"},
                   "reddit": {"reddit.com", "www.reddit.com"}}[kind]
        if (url.scheme != "https" or url.hostname not in allowed
                or url.username or url.password or url.port
                or url.query or url.fragment):
            raise SourceInputError("Подключается только публичная HTTPS-ссылка платформы.")
        path = unquote(url.path).strip("/")
    else:
        path = value.strip("/")
    if kind == "github":
        if path.startswith("github.com/"):
            path = path.removeprefix("github.com/")
        if path.startswith("www.github.com/"):
            path = path.removeprefix("www.github.com/")
        bits = path.split("/")
        if (len(bits) != 2 or not GITHUB_OWNER.fullmatch(bits[0])
                or not GITHUB_REPO.fullmatch(bits[1]) or bits[1] in {".", ".."}):
            raise SourceInputError("Укажи репозиторий вида owner/repo.")
        owner, repo = bits
        return f"{owner}/{repo}", f"GitHub — {owner}/{repo}", f"https://github.com/{owner}/{repo}"
    if path.lower().startswith("r/"):
        path = path[2:]
    if not REDDIT_COMMUNITY.fullmatch(path):
        raise SourceInputError("Укажи сообщество вида r/Python.")
    return path.lower(), f"Reddit — r/{path}", f"https://www.reddit.com/r/{path.lower()}/"


def initialize(repository: Repository) -> None:
    with repository.connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS owner_public_sources (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, locator TEXT NOT NULL,
                title TEXT NOT NULL, topic TEXT NOT NULL DEFAULT '',
                added_at TEXT NOT NULL, removed_at TEXT,
                UNIQUE(kind, locator)
            )"""
        )


def add(repository: Repository, settings: Settings, kind: str, value: str) -> dict:
    locator, title, url = normalize(kind, value)
    identifier = "user_" + kind + "_" + hashlib.sha256(
        locator.casefold().encode("utf-8")
    ).hexdigest()[:20]
    now = datetime.now(UTC).isoformat()
    with repository.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT removed_at FROM owner_public_sources WHERE kind=? AND locator=?",
            (kind, locator),
        ).fetchone()
        if not existing or existing["removed_at"] is not None:
            count = db.execute(
                "SELECT COUNT(*) FROM owner_public_sources WHERE removed_at IS NULL"
            ).fetchone()[0]
            if count >= MAX_SOURCES:
                raise SourceInputError("Достигнут лимит 50 публичных источников.")
        db.execute(
            """INSERT INTO owner_public_sources
               (id,kind,locator,title,added_at,removed_at) VALUES(?,?,?,?,?,NULL)
               ON CONFLICT(id) DO UPDATE SET removed_at=NULL,title=excluded.title""",
            (identifier, kind, locator, title, now),
        )
        if not existing or existing["removed_at"] is not None:
            db.execute(
                """INSERT INTO runtime_settings(key,value,updated_at)
                   VALUES(?,'true',?) ON CONFLICT(key) DO UPDATE SET
                   value='true',updated_at=excluded.updated_at""",
                ("source_enabled:" + identifier, now),
            )
    repository.sync_sources(runtime_source_registry(settings))
    return {"id": identifier, "name": title, "url": url,
            "existing": bool(existing and existing["removed_at"] is None)}


def remove(repository: Repository, settings: Settings, source_id: str) -> None:
    if (not isinstance(source_id, str)
            or not re.fullmatch(r"user_(?:github|reddit)_[0-9a-f]{20}", source_id)):
        raise SourceInputError("Это не личный публичный источник.")
    now = datetime.now(UTC).isoformat()
    with repository.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        updated = db.execute(
            """UPDATE owner_public_sources SET removed_at=?
               WHERE id=? AND removed_at IS NULL""", (now, source_id)
        ).rowcount
        if not updated:
            raise SourceInputError("Подписка уже удалена или не найдена.")
        db.execute(
            """INSERT INTO runtime_settings(key,value,updated_at)
               VALUES(?,'false',?) ON CONFLICT(key) DO UPDATE SET
               value='false',updated_at=excluded.updated_at""",
            ("source_enabled:" + source_id, now),
        )
    repository.sync_sources(runtime_source_registry(settings))
