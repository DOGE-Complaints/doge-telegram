from __future__ import annotations

import os
from pathlib import Path

from doge_telegram_channel.bridge_stub import RecordingStubBridge, bridge_stub_enabled
from doge_telegram_channel.config import Settings
from doge_telegram_channel.harness import run_duplicate_turn_proof
from doge_telegram_channel.poller import LongPollTurnsLoop
from doge_telegram_channel.store import SqliteStore


def test_seen_event_persists_across_restart(tmp_path: Path) -> None:
    path = tmp_path / "seen.sqlite"
    store = SqliteStore(path)
    store.open()
    assert not store.has_seen(update_id=7, kind="message")
    store.mark_seen(update_id=7, kind="message")
    store.close()

    store2 = SqliteStore(path)
    store2.open()
    assert store2.has_seen(update_id=7, kind="message")
    assert not store2.has_seen(update_id=7, kind="callback")
    store2.close()


def test_dedup_gate_single_stub_side_effect(tmp_path: Path) -> None:
    settings = Settings(
        telegram_bot_token="tok",
        bridge_base_url="http://bridge.test",
        channel_bearer="bear",
        sqlite_path=tmp_path / "db.sqlite",
    )
    stub = RecordingStubBridge()
    queue: list[dict] = [
        {
            "update_id": 11,
            "message": {
                "message_id": 1,
                "text": "once",
                "from": {"id": 1},
                "chat": {"id": 2},
            },
        }
    ]

    def fake_get(**_k: object) -> list[dict]:
        batch = list(queue)
        queue.clear()
        return batch

    loop = LongPollTurnsLoop(
        settings=settings,
        poll_timeout=0,
        bridge_client=stub,
        get_updates_fn=fake_get,
        apply_fn=lambda **_k: None,
        drain_fn=lambda **_k: 0,
    )
    assert loop.process_updates_once() == 1
    queue.append(
        {
            "update_id": 11,
            "message": {
                "message_id": 1,
                "text": "once",
                "from": {"id": 1},
                "chat": {"id": 2},
            },
        }
    )
    assert loop.process_updates_once() == 0
    assert stub.turns_count == 1


def test_harness_duplicate_proof(tmp_path: Path) -> None:
    stub = run_duplicate_turn_proof(sqlite_path=tmp_path / "h.sqlite")
    assert stub.turns_count == 1


def test_bridge_stub_env(monkeypatch: object) -> None:
    monkeypatch.setenv("BRIDGE_STUB", "1")  # type: ignore[attr-defined]
    assert bridge_stub_enabled() is True
    monkeypatch.delenv("BRIDGE_STUB", raising=False)  # type: ignore[attr-defined]
    os.environ.pop("BRIDGE_STUB", None)
    assert bridge_stub_enabled() is False


def test_mark_seen_after_turns_outbound_fail_no_double_turns(tmp_path: Path) -> None:
    """M-01: outbound fail after turns must not re-POST turns on redelivery."""
    from doge_telegram_channel.telegram_api import TelegramApiError

    settings = Settings(
        telegram_bot_token="tok",
        bridge_base_url="http://bridge.test",
        channel_bearer="bear",
        sqlite_path=tmp_path / "db.sqlite",
    )
    stub = RecordingStubBridge()
    queue: list[dict] = [
        {
            "update_id": 55,
            "message": {
                "message_id": 1,
                "text": "x",
                "from": {"id": 1},
                "chat": {"id": 2},
            },
        }
    ]

    def fake_get(**_k: object) -> list[dict]:
        batch = list(queue)
        queue.clear()
        return batch

    def boom_apply(**_k: object) -> None:
        raise TelegramApiError(method="sendMessage", status=500, detail="http_error")

    loop = LongPollTurnsLoop(
        settings=settings,
        poll_timeout=0,
        bridge_client=stub,
        get_updates_fn=fake_get,
        apply_fn=boom_apply,
        drain_fn=lambda **_k: 0,
    )
    assert loop.process_updates_once() == 0
    assert stub.turns_count == 1
    assert loop._offset == 56  # noqa: SLF001 — advanced after seen despite outbound fail
    queue.append(
        {
            "update_id": 55,
            "message": {
                "message_id": 1,
                "text": "x",
                "from": {"id": 1},
                "chat": {"id": 2},
            },
        }
    )
    assert loop.process_updates_once() == 0
    assert stub.turns_count == 1


def test_callback_dedup_single_actions(tmp_path: Path) -> None:
    settings = Settings(
        telegram_bot_token="tok",
        bridge_base_url="http://bridge.test",
        channel_bearer="bear",
        sqlite_path=tmp_path / "cb.sqlite",
    )
    stub = RecordingStubBridge()
    cq = {
        "update_id": 77,
        "callback_query": {
            "id": "cq-1",
            "data": "tok-a",
            "from": {"id": 3},
            "message": {"message_id": 9, "chat": {"id": 8}},
        },
    }
    queue: list[dict] = [cq]

    def fake_get(**_k: object) -> list[dict]:
        batch = list(queue)
        queue.clear()
        return batch

    loop = LongPollTurnsLoop(
        settings=settings,
        poll_timeout=0,
        bridge_client=stub,
        get_updates_fn=fake_get,
        answer_callback_fn=lambda **_k: {"ok": True},
        drain_fn=lambda **_k: 0,
    )
    assert loop.process_updates_once() == 1
    assert stub.actions_count == 1
    queue.append(dict(cq))
    assert loop.process_updates_once() == 0
    assert stub.actions_count == 1
