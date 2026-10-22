"""Guard against JS parse errors and mismatched subscriptions route contracts."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

JAVASCRIPT = Path(__file__).parents[1] / "app/web/portal_static/app.js"


def test_account_frontend_matches_import_route_contract():
    source = JAVASCRIPT.read_text(encoding="utf-8")
    assert "locator:repository.full_name" in source
    assert "value:repository.full_name" not in source
    assert "youtube_reconnect_required" in source
    assert "oauth-subscriptions-panel" in source
    assert "/api/public-sources/remove" in source


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_portal_javascript_has_valid_syntax():
    subprocess.run(
        ["node", "--check", str(JAVASCRIPT)],
        check=True, capture_output=True, text=True,
    )


def test_feed_title_and_hide_button_contract():
    source = JAVASCRIPT.read_text(encoding="utf-8")
    assert 'el("button","tile-title-button",item.title||"Без заголовка")' in source
    assert 'titleButton.addEventListener("click",()=>openArticle(item,type))' in source
    assert 'el("p","tile-summary",previewText)' in source
    assert 'action(hidden?"Вернуть в ленту":"Скрыть",hidden?"refresh":"close"' in source
    assert '"✕ Скрыть","close"' not in source
