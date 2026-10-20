"""Codex Sale OpenAI-compatible text gateway. No secrets or payloads are logged."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://codex.sale/v1"


class CodexSaleError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodexSaleClient:
    api_key: str
    base_url: str = BASE_URL
    timeout: int = 90

    def __post_init__(self) -> None:
        if not self.api_key:
            raise CodexSaleError("CODEX_SALE_API_KEY is missing")
        if self.base_url.rstrip("/") != BASE_URL:
            raise CodexSaleError("Only the approved Codex Sale API origin is allowed")

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        encoded = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None else None
        )
        request = Request(
            self.base_url.rstrip("/") + path,
            data=encoded,
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read(12_000_000).decode("utf-8"))
        except HTTPError as exc:
            # Error bodies may contain sensitive input. Only report the status.
            raise CodexSaleError(f"Codex Sale HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise CodexSaleError("Codex Sale connection failed") from exc
        except (UnicodeDecodeError, ValueError) as exc:
            raise CodexSaleError("Codex Sale returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise CodexSaleError("Codex Sale returned invalid response shape")
        return result

    def models(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/models").get("data")
        if not isinstance(data, list):
            raise CodexSaleError("Invalid /models response")
        return [item for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)]

    def chat(self, *, model: str, messages: list[dict[str, Any]], **options: Any) -> dict[str, Any]:
        if not model or not messages:
            raise ValueError("model and messages are required")
        return self._request(
            "POST", "/chat/completions",
            {"model": model, "messages": messages, **options},
        )

    def responses(self, *, model: str, input: Any, **options: Any) -> dict[str, Any]:
        if not model:
            raise ValueError("model is required")
        return self._request("POST", "/responses", {"model": model, "input": input, **options})
