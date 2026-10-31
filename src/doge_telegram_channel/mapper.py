"""Map Telegram updates → ChannelTurnRequest / ChannelActionRequest (OpenAPI only).

SSOT: ``doge-ai-bridge/docs/openapi/aibridge-channel-v1.openapi.yaml``
"""

from __future__ import annotations

from typing import Any


class MappingSkip(Exception):
    """Update is out of scope for turns/actions mapping."""


# OpenAPI ChannelTurnRequest / ChannelActionRequest — do not invent keys.
_TURN_KEYS = frozenset({"channel", "event_id", "principal", "message"})
_ACTION_KEYS = frozenset(
    {"channel", "event_id", "callback_query_id", "principal", "action_token"}
)
_PRINCIPAL_KEYS = frozenset({"user_id", "chat_id"})
_MESSAGE_KEYS = frozenset({"message_id", "text", "language_code"})


def map_message_update_to_turn(update: dict[str, Any]) -> dict[str, Any]:
    """Build ChannelTurnRequest from a Telegram ``message`` update."""
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
    _assert_turn_shape(envelope)
    return envelope


def map_callback_update_to_action(update: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Build ChannelActionRequest from ``callback_query``.

    Returns ``(envelope, edit_message_id)`` where edit_message_id comes from the
    callback's message (Bot API) for Edit path — not an OpenAPI request field.
    """
    cq = update.get("callback_query")
    if not isinstance(cq, dict):
        raise MappingSkip("no_callback_query")
    update_id = update.get("update_id")
    if update_id is None:
        raise MappingSkip("no_update_id")
    cq_id = cq.get("id")
    if cq_id is None:
        raise MappingSkip("no_callback_query_id")
    data = cq.get("data")
    if not isinstance(data, str) or not data:
        raise MappingSkip("no_action_token")
    from_user = cq.get("from")
    if not isinstance(from_user, dict) or from_user.get("id") is None:
        raise MappingSkip("no_user_id")
    message = cq.get("message")
    chat_id: str | None = None
    edit_message_id: str | None = None
    if isinstance(message, dict):
        chat = message.get("chat")
        if isinstance(chat, dict) and chat.get("id") is not None:
            chat_id = str(chat["id"])
        if message.get("message_id") is not None:
            edit_message_id = str(message["message_id"])
    if chat_id is None:
        raise MappingSkip("no_chat_id")

    envelope: dict[str, Any] = {
        "channel": "telegram",
        "event_id": str(update_id),
        "callback_query_id": str(cq_id),
        "principal": {
            "user_id": str(from_user["id"]),
            "chat_id": chat_id,
        },
        "action_token": data[:64],
    }
    _assert_action_shape(envelope)
    return envelope, edit_message_id


def _assert_turn_shape(envelope: dict[str, Any]) -> None:
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


def _assert_action_shape(envelope: dict[str, Any]) -> None:
    extra = set(envelope) - _ACTION_KEYS
    if extra:
        raise ValueError(f"invented_action_fields:{sorted(extra)}")
    if set(envelope["principal"]) - _PRINCIPAL_KEYS:
        raise ValueError("invented_principal_fields")
    if envelope["channel"] != "telegram":
        raise ValueError("channel_must_be_telegram")
