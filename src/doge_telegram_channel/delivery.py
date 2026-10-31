"""Outbox drain / retry — Send/Edit from persisted bridge envelope fields."""

from __future__ import annotations

import logging
from typing import Any

from doge_telegram_channel.outbound import inline_keyboard_from_actions
from doge_telegram_channel.store import SqliteStore
from doge_telegram_channel.telegram_api import (
    TelegramApiError,
    edit_message_text,
    send_message,
)

logger = logging.getLogger(__name__)


def payload_from_bridge_response(
    *,
    response: dict[str, Any],
    chat_id: str,
    edit_message_id: str | None = None,
) -> dict[str, Any] | None:
    """Build outbox payload from OpenAPI ChannelSuccessResponse (+ optional edit target)."""
    reply_text = response.get("reply_text")
    if not isinstance(reply_text, str) or not reply_text:
        logger.warning("ops_bridge_response_missing_reply_text chat_id=%s", chat_id)
        return None
    actions = response.get("actions")
    markup = None
    if isinstance(actions, list) and actions:
        markup = inline_keyboard_from_actions(actions)
    method = "editMessageText" if edit_message_id else "sendMessage"
    payload: dict[str, Any] = {
        "method": method,
        "chat_id": chat_id,
        "text": reply_text,
    }
    if markup is not None:
        payload["reply_markup"] = markup
    if edit_message_id is not None:
        payload["message_id"] = edit_message_id
    return payload


def apply_outbox_payload(*, token: str, payload: dict[str, Any]) -> None:
    """Apply one outbox job to Telegram Bot API (fields from OpenAPI + Bot API)."""
    method = payload.get("method")
    chat_id = payload.get("chat_id")
    text = payload.get("text")
    if not isinstance(chat_id, str) or not isinstance(text, str):
        raise TelegramApiError(method=str(method), status=None, detail="bad_payload")
    reply_markup = payload.get("reply_markup")
    if method == "editMessageText":
        message_id = payload.get("message_id")
        if not isinstance(message_id, str):
            raise TelegramApiError(method="editMessageText", status=None, detail="missing_message_id")
        edit_message_text(
            token=token,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup if isinstance(reply_markup, dict) else None,
        )
        return
    send_message(
        token=token,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup if isinstance(reply_markup, dict) else None,
    )


def drain_outbox(*, store: SqliteStore, token: str, limit: int = 50) -> int:
    """Claim pending/failed jobs, deliver, mark sent|failed. Returns success count."""
    jobs = store.claim_retryable(limit=limit)
    ok = 0
    for job in jobs:
        try:
            apply_outbox_payload(token=token, payload=job.payload)
            store.mark_sent(job.id)
            ok += 1
        except TelegramApiError as exc:
            store.mark_failed(job.id, f"{exc.method}:{exc.detail}")
            logger.error(
                "ops_delivery_failed id=%s method=%s detail=%s",
                job.id,
                exc.method,
                exc.detail,
            )
    return ok
