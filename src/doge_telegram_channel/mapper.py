"""Map Telegram message updates → ChannelTurnRequest (OpenAPI fields only).

SSOT: ``doge-ai-bridge/docs/openapi/aibridge-channel-v1.openapi.yaml``
schemas ChannelTurnRequest / ChannelPrincipal / ChannelMessage.
"""

from __future__ import annotations

from typing import Any


class MappingSkip(Exception):
    """Update is not an ordinary text message for the turns path."""


# OpenAPI ChannelTurnRequest.properties — do not invent keys beyond these.
_TURN_KEYS = frozenset({"channel", "event_id", "principal", "message"})
_PRINCIPAL_KEYS = frozenset({"user_id", "chat_id"})
_MESSAGE_KEYS = frozenset({"message_id", "text", "language_code"})


def map_message_update_to_turn(update: dict[str, Any]) -> dict[str, Any]:
    """Build ChannelTurnRequest from a Telegram ``message`` update.

    Skips callback_query and non-text messages (STORY-03 owns callbacks).
    """
    if "callback_query" in update:
        raise MappingSkip("callback_query")
    message = update.get("message")
    if not isinstance(message, dict):
        raise MappingSkip("no_message")
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        raise MappingSkip("no_text")

    update_id = update.get("update_id")
    if update_id is None:
        raise MappingSkip("no_update_id")

    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        raise MappingSkip("no_chat_id")
    from_user = message.get("from")
    if not isinstance(from_user, dict) or from_user.get("id") is None:
        raise MappingSkip("no_user_id")
    message_id = message.get("message_id")
    if message_id is None:
        raise MappingSkip("no_message_id")

    principal: dict[str, str] = {
        "user_id": str(from_user["id"]),
        "chat_id": str(chat["id"]),
    }
    msg: dict[str, str] = {
        "message_id": str(message_id),
        "text": text,
    }
    language_code = from_user.get("language_code")
    if isinstance(language_code, str) and language_code:
        msg["language_code"] = language_code

    envelope: dict[str, Any] = {
        "channel": "telegram",
        "event_id": str(update_id),
        "principal": principal,
        "message": msg,
    }
    _assert_openapi_shape(envelope)
    return envelope


def _assert_openapi_shape(envelope: dict[str, Any]) -> None:
    extra = set(envelope) - _TURN_KEYS
    if extra:
        raise ValueError(f"invented_turn_fields:{sorted(extra)}")
    principal = envelope["principal"]
    message = envelope["message"]
    if set(principal) - _PRINCIPAL_KEYS:
        raise ValueError("invented_principal_fields")
    if set(message) - _MESSAGE_KEYS:
        raise ValueError("invented_message_fields")
    if envelope["channel"] != "telegram":
        raise ValueError("channel_must_be_telegram")
