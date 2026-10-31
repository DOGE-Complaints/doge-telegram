"""Minimal outbound apply for message happy path (not full outbox — STORY-03).

Consumes ChannelSuccessResponse fields from OpenAPI: reply_text, actions.
"""

from __future__ import annotations

import logging
from typing import Any

from doge_telegram_channel.telegram_api import send_message

logger = logging.getLogger(__name__)

# OpenAPI ChannelSuccessResponse keys we may read (subset for minimal apply).
_RESPONSE_KEYS_USED = frozenset({"reply_text", "actions"})


def inline_keyboard_from_actions(actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Build Telegram reply_markup from OpenAPI ChannelAction list (token → callback_data)."""
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        label = action.get("label")
        token = action.get("token")
        if not isinstance(label, str) or not isinstance(token, str):
            continue
        # OpenAPI token maxLength 64; Telegram callback_data limit 64 bytes.
        row.append({"text": label, "callback_data": token[:64]})
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if not rows:
        return None
    return {"inline_keyboard": rows}


def apply_bridge_success(
    *,
    token: str,
    chat_id: str,
    response: dict[str, Any],
) -> None:
    """Send reply_text (+ optional inline buttons). Does not claim outbox DoD."""
    reply_text = response.get("reply_text")
    if not isinstance(reply_text, str) or not reply_text:
        logger.warning("ops_bridge_response_missing_reply_text chat_id=%s", chat_id)
        return
    actions = response.get("actions")
    markup = None
    if isinstance(actions, list) and actions:
        markup = inline_keyboard_from_actions(actions)
    send_message(token=token, chat_id=chat_id, text=reply_text, reply_markup=markup)
    logger.info(
        "ops_outbound_sent chat_id=%s has_actions=%s",
        chat_id,
        bool(markup),
    )
