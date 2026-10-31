from __future__ import annotations

import pytest

from doge_telegram_channel.mapper import (
    MappingSkip,
    map_callback_update_to_action,
    map_message_update_to_turn,
)


def test_map_message_update_to_turn() -> None:
    env = map_message_update_to_turn(
        {
            "update_id": 1,
            "message": {
                "message_id": 7,
                "text": "hello",
                "from": {"id": 10, "language_code": "et"},
                "chat": {"id": 20},
            },
        }
    )
    assert env["channel"] == "telegram"
    assert env["event_id"] == "1"
    assert env["principal"] == {"user_id": "10", "chat_id": "20"}
    assert env["message"]["text"] == "hello"
    assert env["message"]["language_code"] == "et"


def test_map_message_skips_callback() -> None:
    with pytest.raises(MappingSkip, match="callback_query"):
        map_message_update_to_turn({"update_id": 1, "callback_query": {"id": "x"}})


def test_map_callback_update_to_action() -> None:
    env, edit_id = map_callback_update_to_action(
        {
            "update_id": 42,
            "callback_query": {
                "id": "cq-9",
                "data": "tok-abc",
                "from": {"id": 5},
                "message": {"message_id": 99, "chat": {"id": 77}},
            },
        }
    )
    assert env == {
        "channel": "telegram",
        "event_id": "42",
        "callback_query_id": "cq-9",
        "principal": {"user_id": "5", "chat_id": "77"},
        "action_token": "tok-abc",
    }
    assert edit_id == "99"
