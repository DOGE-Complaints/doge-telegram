from __future__ import annotations

import pytest

from doge_telegram_channel.mapper import MappingSkip, map_message_update_to_turn


def test_map_ordinary_message() -> None:
    update = {
        "update_id": 42,
        "message": {
            "message_id": 7,
            "text": "hello",
            "from": {"id": 100, "language_code": "et"},
            "chat": {"id": 200},
        },
    }
    env = map_message_update_to_turn(update)
    assert env == {
        "channel": "telegram",
        "event_id": "42",
        "principal": {"user_id": "100", "chat_id": "200"},
        "message": {"message_id": "7", "text": "hello", "language_code": "et"},
    }


def test_skip_callback() -> None:
    with pytest.raises(MappingSkip, match="callback_query"):
        map_message_update_to_turn({"update_id": 1, "callback_query": {}})


def test_skip_non_text() -> None:
    with pytest.raises(MappingSkip, match="no_text"):
        map_message_update_to_turn(
            {
                "update_id": 1,
                "message": {
                    "message_id": 1,
                    "from": {"id": 1},
                    "chat": {"id": 1},
                    "photo": [],
                },
            }
        )
