"""Telegram Bot API client — long-poll ``getUpdates`` only (no webhook server)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramApiError(RuntimeError):
    """Ops-visible Telegram Bot API failure (no secret values)."""

    def __init__(self, *, method: str, status: int | None, detail: str) -> None:
        self.method = method
        self.status = status
        self.detail = detail
        super().__init__(f"telegram_api_error method={method} status={status} detail={detail}")


def _api_url(token: str, method: str) -> str:
    return f"{TELEGRAM_API_BASE}/bot{token}/{method}"


def telegram_request(
    *,
    token: str,
    method: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """POST JSON to Bot API. Never logs the token."""
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        _api_url(token, method),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")[:300]
        logger.error(
            "ops_telegram_http_error method=%s status=%s body_prefix=%s",
            method,
            exc.code,
            err_body.replace("\n", " "),
        )
        raise TelegramApiError(method=method, status=exc.code, detail="http_error") from exc
    except urllib.error.URLError as exc:
        logger.error("ops_telegram_url_error method=%s reason=%s", method, type(exc.reason).__name__)
        raise TelegramApiError(method=method, status=None, detail="url_error") from exc
    except TimeoutError as exc:
        logger.error("ops_telegram_timeout method=%s", method)
        raise TelegramApiError(method=method, status=None, detail="timeout") from exc

    if not isinstance(data, dict) or data.get("ok") is not True:
        logger.error("ops_telegram_api_not_ok method=%s", method)
        raise TelegramApiError(method=method, status=None, detail="api_not_ok")
    result = data.get("result")
    if not isinstance(result, (dict, list)):
        raise TelegramApiError(method=method, status=None, detail="bad_result_type")
    return data


def get_updates(
    *,
    token: str,
    offset: int | None = None,
    timeout: int = 25,
    allowed_updates: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Long-poll getUpdates. Default allowed_updates = message only (STORY-02)."""
    payload: dict[str, Any] = {
        "timeout": timeout,
        "allowed_updates": allowed_updates if allowed_updates is not None else ["message"],
    }
    if offset is not None:
        payload["offset"] = offset
    # HTTP timeout must exceed Telegram long-poll timeout.
    data = telegram_request(
        token=token,
        method="getUpdates",
        payload=payload,
        timeout=float(timeout) + 10.0,
    )
    result = data["result"]
    assert isinstance(result, list)
    return [u for u in result if isinstance(u, dict)]


def send_message(
    *,
    token: str,
    chat_id: str,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Minimal Send Message for bridge reply_text (+ optional inline keyboard)."""
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    data = telegram_request(token=token, method="sendMessage", payload=payload, timeout=30.0)
    result = data["result"]
    assert isinstance(result, dict)
    return result
