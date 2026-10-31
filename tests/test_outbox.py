from __future__ import annotations

from pathlib import Path

from doge_telegram_channel.delivery import drain_outbox, payload_from_bridge_response
from doge_telegram_channel.store import STATUS_FAILED, STATUS_SENT, SqliteStore


def _response(**overrides: object) -> dict:
    base = {
        "request_id": "r1",
        "session_id": "s1",
        "state": "ask",
        "reply_text": "updated",
        "actions": [{"label": "Next", "token": "n1", "style": "default"}],
        "outcome": None,
        "draft_id": None,
        "continuation_url": None,
    }
    base.update(overrides)
    return base


def test_sqlite_volume_open_and_outbox_persist(tmp_path: Path) -> None:
    path = tmp_path / "vol" / "channel.sqlite"
    store = SqliteStore(path)
    store.open()
    assert path.is_file()
    payload = payload_from_bridge_response(
        response=_response(),
        chat_id="22",
        edit_message_id="5",
    )
    assert payload is not None
    assert payload["method"] == "editMessageText"
    job_id = store.enqueue(chat_id="22", payload=payload)
    job = store.get_job(job_id)
    assert job is not None
    assert job.status == "pending"
    assert job.payload["text"] == "updated"
    store.close()


def test_delivery_retry_marks_failed_and_recovers(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    store.open()
    payload = {
        "method": "sendMessage",
        "chat_id": "1",
        "text": "hi",
    }
    job_id = store.enqueue(chat_id="1", payload=payload)

    calls: list[dict] = []

    def boom(*, token: str, payload: dict) -> None:
        calls.append(payload)
        from doge_telegram_channel.telegram_api import TelegramApiError

        raise TelegramApiError(method="sendMessage", status=500, detail="http_error")

    import doge_telegram_channel.delivery as delivery

    orig = delivery.apply_outbox_payload
    delivery.apply_outbox_payload = boom  # type: ignore[assignment]
    try:
        assert drain_outbox(store=store, token="tok") == 0
        failed = store.get_job(job_id)
        assert failed is not None
        assert failed.status == STATUS_FAILED
        assert failed.last_error is not None
        assert "sendMessage" in failed.last_error
    finally:
        delivery.apply_outbox_payload = orig  # type: ignore[assignment]

    def ok(*, token: str, payload: dict) -> None:
        calls.append(payload)

    delivery.apply_outbox_payload = ok  # type: ignore[assignment]
    try:
        assert drain_outbox(store=store, token="tok") == 1
        sent = store.get_job(job_id)
        assert sent is not None
        assert sent.status == STATUS_SENT
    finally:
        delivery.apply_outbox_payload = orig  # type: ignore[assignment]
    store.close()


def test_reclaim_stale_sending_after_crash(tmp_path: Path) -> None:
    """M-01: orphan ``sending`` must become retryable after reopen/drain."""
    path = tmp_path / "crash.sqlite"
    store = SqliteStore(path)
    store.open()
    job_id = store.enqueue(
        chat_id="7",
        payload={"method": "sendMessage", "chat_id": "7", "text": "orphan"},
    )
    # Simulate crash after claim: force status=sending without completing deliver.
    store.conn.execute(
        "UPDATE outbox SET status = ? WHERE id = ?",
        ("sending", job_id),
    )
    store.conn.commit()
    store.close()

    store2 = SqliteStore(path)
    store2.open()
    # open() already reclaimed; assert pending then drain succeeds
    job = store2.get_job(job_id)
    assert job is not None
    assert job.status == "pending"

    delivered: list[str] = []

    def capture(*, token: str, payload: dict) -> None:
        delivered.append(payload["text"])

    import doge_telegram_channel.delivery as delivery

    orig = delivery.apply_outbox_payload
    delivery.apply_outbox_payload = capture  # type: ignore[assignment]
    try:
        assert drain_outbox(store=store2, token="tok") == 1
        assert delivered == ["orphan"]
        assert store2.get_job(job_id).status == STATUS_SENT  # type: ignore[union-attr]
    finally:
        delivery.apply_outbox_payload = orig  # type: ignore[assignment]
    store2.close()


def test_restart_recovers_pending(tmp_path: Path) -> None:
    path = tmp_path / "persist.sqlite"
    store = SqliteStore(path)
    store.open()
    store.enqueue(
        chat_id="9",
        payload={"method": "sendMessage", "chat_id": "9", "text": "survive"},
    )
    store.close()

    store2 = SqliteStore(path)
    store2.open()
    delivered: list[str] = []

    def capture(*, token: str, payload: dict) -> None:
        delivered.append(payload["text"])

    import doge_telegram_channel.delivery as delivery

    orig = delivery.apply_outbox_payload
    delivery.apply_outbox_payload = capture  # type: ignore[assignment]
    try:
        assert drain_outbox(store=store2, token="tok") == 1
        assert delivered == ["survive"]
    finally:
        delivery.apply_outbox_payload = orig  # type: ignore[assignment]
    store2.close()
