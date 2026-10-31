from __future__ import annotations

from pathlib import Path

import pytest

from doge_telegram_channel.bridge_client import BridgeTurnsClient
from doge_telegram_channel.config import Settings
from doge_telegram_channel.poller import LongPollTurnsLoop
from doge_telegram_channel.webhook_guard import assert_no_webhook_ingress, scan_webhook_ingress


def test_process_message_calls_turns_and_outbound(tmp_path: Path) -> None:
    settings = Settings(
        telegram_bot_token="tok",
        bridge_base_url="http://bridge.test",
        channel_bearer="bear",
        sqlite_path=tmp_path / "db.sqlite",
    )
    captured: dict[str, object] = {}

    def fake_get_updates(**kwargs: object) -> list[dict]:
        return [
            {
                "update_id": 9,
                "message": {
                    "message_id": 3,
                    "text": "hi",
                    "from": {"id": 11},
                    "chat": {"id": 22},
                },
            }
        ]

    class FakeBridge(BridgeTurnsClient):
        def __init__(self) -> None:  # noqa: D107
            pass

        def post_turns(self, envelope: dict) -> dict:
            captured["envelope"] = envelope
            return {
                "request_id": "r1",
                "session_id": "s1",
                "state": "ask",
                "reply_text": "pong",
                "actions": [{"label": "OK", "token": "t1", "style": "default"}],
                "outcome": None,
                "draft_id": None,
                "continuation_url": None,
            }

    def fake_apply(*, token: str, chat_id: str, response: dict) -> None:
        captured["apply"] = {"token": token, "chat_id": chat_id, "text": response["reply_text"]}

    loop = LongPollTurnsLoop(
        settings=settings,
        poll_timeout=0,
        bridge_client=FakeBridge(),  # type: ignore[arg-type]
        get_updates_fn=fake_get_updates,
        apply_fn=fake_apply,
        drain_fn=lambda **kwargs: 0,
    )
    assert loop.process_updates_once() == 1
    assert captured["envelope"]["event_id"] == "9"
    assert captured["envelope"]["channel"] == "telegram"
    assert captured["apply"] == {"token": "tok", "chat_id": "22", "text": "pong"}
    assert loop._offset == 10  # noqa: SLF001 — success advances after turn+outbound


def test_offset_not_advanced_on_bridge_failure(tmp_path: Path) -> None:
    from doge_telegram_channel.bridge_client import BridgeClientError

    settings = Settings(
        telegram_bot_token="tok",
        bridge_base_url="http://bridge.test",
        channel_bearer="bear",
        sqlite_path=tmp_path / "db.sqlite",
    )

    def fake_get_updates(**kwargs: object) -> list[dict]:
        return [
            {
                "update_id": 5,
                "message": {
                    "message_id": 1,
                    "text": "hi",
                    "from": {"id": 1},
                    "chat": {"id": 2},
                },
            }
        ]

    class FailingBridge(BridgeTurnsClient):
        def __init__(self) -> None:  # noqa: D107
            pass

        def post_turns(self, envelope: dict) -> dict:
            raise BridgeClientError(path="/v1/channel/turns", status=503, detail="http_error")

    loop = LongPollTurnsLoop(
        settings=settings,
        poll_timeout=0,
        bridge_client=FailingBridge(),  # type: ignore[arg-type]
        get_updates_fn=fake_get_updates,
        apply_fn=lambda **kwargs: None,
        drain_fn=lambda **kwargs: 0,
    )
    assert loop.process_updates_once() == 0
    assert loop._offset is None  # noqa: SLF001 — failure keeps update retryable


def test_offset_advanced_on_mapping_skip(tmp_path: Path) -> None:
    settings = Settings(
        telegram_bot_token="tok",
        bridge_base_url="http://bridge.test",
        channel_bearer="bear",
        sqlite_path=tmp_path / "db.sqlite",
    )

    def fake_get_updates(**kwargs: object) -> list[dict]:
        return [{"update_id": 3, "edited_message": {"text": "x"}}]

    loop = LongPollTurnsLoop(
        settings=settings,
        poll_timeout=0,
        get_updates_fn=fake_get_updates,
        apply_fn=lambda **kwargs: None,
        drain_fn=lambda **kwargs: 0,
    )
    assert loop.process_updates_once() == 0
    assert loop._offset == 4  # noqa: SLF001 — MappingSkip still advances


def test_callback_ack_then_actions_then_outbox(tmp_path: Path) -> None:
    settings = Settings(
        telegram_bot_token="tok",
        bridge_base_url="http://bridge.test",
        channel_bearer="bear",
        sqlite_path=tmp_path / "db.sqlite",
    )
    order: list[str] = []

    def fake_get_updates(**kwargs: object) -> list[dict]:
        return [
            {
                "update_id": 8,
                "callback_query": {
                    "id": "cq-1",
                    "data": "btn-a",
                    "from": {"id": 3},
                    "message": {"message_id": 50, "chat": {"id": 99}},
                },
            }
        ]

    class FakeBridge(BridgeTurnsClient):
        def __init__(self) -> None:  # noqa: D107
            pass

        def post_turns(self, envelope: dict) -> dict:
            raise AssertionError("turns must not run for callback")

        def post_actions(self, envelope: dict) -> dict:
            order.append("actions")
            assert envelope["action_token"] == "btn-a"
            assert envelope["callback_query_id"] == "cq-1"
            return {
                "request_id": "r",
                "session_id": "s",
                "state": "x",
                "reply_text": "edited",
                "actions": [],
                "outcome": None,
                "draft_id": None,
                "continuation_url": None,
            }

    def fake_ack(**kwargs: object) -> dict:
        order.append("ack")
        assert kwargs["callback_query_id"] == "cq-1"
        return {"ok": True}

    def fake_drain(**kwargs: object) -> int:
        order.append("drain")
        return 0

    loop = LongPollTurnsLoop(
        settings=settings,
        poll_timeout=0,
        bridge_client=FakeBridge(),  # type: ignore[arg-type]
        get_updates_fn=fake_get_updates,
        answer_callback_fn=fake_ack,
        drain_fn=fake_drain,
    )
    assert loop.process_updates_once() == 1
    # process_updates_once drains once at start, then ack → actions → enqueue → drain
    assert order[0] == "drain"
    assert order[1:] == ["ack", "actions", "drain"]
    assert loop._offset == 9  # noqa: SLF001
    job = loop.ensure_store().get_job(1)
    assert job is not None
    assert job.payload["method"] == "editMessageText"
    assert job.payload["message_id"] == "50"


def test_no_webhook_ingress() -> None:
    assert scan_webhook_ingress() == []
    assert_no_webhook_ingress()


def test_bridge_client_posts_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import json
    from urllib.request import Request

    seen: dict[str, object] = {}

    class FakeResp:
        status = 200

        def read(self) -> bytes:
            return json.dumps(
                {
                    "request_id": "r",
                    "session_id": "s",
                    "state": "x",
                    "reply_text": "y",
                    "actions": [],
                    "outcome": None,
                    "draft_id": None,
                    "continuation_url": None,
                }
            ).encode()

        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(req: Request, timeout: float = 0) -> FakeResp:
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization")
        seen["body"] = json.loads(req.data.decode())  # type: ignore[union-attr]
        return FakeResp()

    monkeypatch.setattr("doge_telegram_channel.bridge_client.urllib.request.urlopen", fake_urlopen)
    client = BridgeTurnsClient(base_url="http://bridge", channel_bearer="secret-bearer")
    client.post_turns(
        {
            "channel": "telegram",
            "event_id": "1",
            "principal": {"user_id": "1", "chat_id": "1"},
            "message": {"message_id": "1", "text": "x"},
        }
    )
    assert seen["url"] == "http://bridge/v1/channel/turns"
    assert seen["auth"] == "Bearer secret-bearer"
    assert seen["body"]["channel"] == "telegram"
    client.post_actions(
        {
            "channel": "telegram",
            "event_id": "2",
            "callback_query_id": "cq",
            "principal": {"user_id": "1", "chat_id": "1"},
            "action_token": "tok",
        }
    )
    assert seen["url"] == "http://bridge/v1/channel/actions"
