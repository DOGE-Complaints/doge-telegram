"""Long-poll getUpdates → turns | callbacks→actions + SQLite outbox delivery."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Protocol

from doge_telegram_channel.bridge_client import BridgeClientError, BridgeTurnsClient
from doge_telegram_channel.bridge_stub import make_bridge_client
from doge_telegram_channel.config import Settings
from doge_telegram_channel.delivery import drain_outbox, payload_from_bridge_response
from doge_telegram_channel.mapper import (
    MappingSkip,
    map_callback_update_to_action,
    map_message_update_to_turn,
)
from doge_telegram_channel.outbound import apply_bridge_success
from doge_telegram_channel.store import SqliteStore
from doge_telegram_channel.telegram_api import (
    TelegramApiError,
    answer_callback_query,
    get_updates,
)

KIND_MESSAGE = "message"
KIND_CALLBACK = "callback"

logger = logging.getLogger(__name__)


class Poller(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class IdlePoller:
    """No-op when settings fail-closed — health may still run."""

    def __init__(self) -> None:
        self._started = False

    def start(self) -> None:
        self._started = True
        logger.warning("ops_poller_idle_no_settings")

    def stop(self) -> None:
        self._started = False


class LongPollTurnsLoop:
    """v1 ingress: Telegram long-poll only (no webhook server).

    Messages → turns + minimal outbound.
    Callbacks → answerCallbackQuery → actions → outbox → Send/Edit (+ drain/retry).
    """

    def __init__(
        self,
        *,
        settings: Settings,
        poll_timeout: int = 25,
        bridge_client: BridgeTurnsClient | None = None,
        get_updates_fn: Callable[..., list] | None = None,
        apply_fn: Callable[..., None] | None = None,
        store: SqliteStore | None = None,
        answer_callback_fn: Callable[..., object] | None = None,
        drain_fn: Callable[..., int] | None = None,
    ) -> None:
        self._settings = settings
        self._poll_timeout = poll_timeout
        self._bridge = bridge_client or make_bridge_client(
            base_url=settings.bridge_base_url,
            channel_bearer=settings.channel_bearer,
        )
        self._get_updates = get_updates_fn or get_updates
        self._apply = apply_fn or apply_bridge_success
        self._store = store or SqliteStore(settings.sqlite_path)
        self._store_owned = store is None
        self._answer_callback = answer_callback_fn or answer_callback_query
        self._drain = drain_fn or drain_outbox
        self._offset: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._store.open()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="longpoll-turns", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=float(self._poll_timeout) + 15.0)
        if self._store_owned:
            self._store.close()

    def ensure_store(self) -> SqliteStore:
        """Open Volume SQLite if not yet open (tests may call process without start)."""
        if self._store._conn is None:  # noqa: SLF001
            self._store.open()
        return self._store

    def process_updates_once(self) -> int:
        """Fetch and process one getUpdates batch. Returns processed update count."""
        self.ensure_store()
        # Recover undelivered outbox before/after each poll batch.
        try:
            self._drain(store=self._store, token=self._settings.telegram_bot_token)
        except Exception:
            logger.exception("ops_outbox_drain_unexpected")

        updates = self._get_updates(
            token=self._settings.telegram_bot_token,
            offset=self._offset,
            timeout=self._poll_timeout,
        )
        processed = 0
        for update in updates:
            if self._process_one(update):
                processed += 1
        return processed

    def _process_one(self, update: dict) -> bool:
        update_id = update.get("update_id")

        def _advance_offset() -> None:
            if isinstance(update_id, int):
                self._offset = update_id + 1

        if "callback_query" in update:
            return self._process_callback(update, _advance_offset)

        if isinstance(update_id, int) and self._store.has_seen(
            update_id=update_id, kind=KIND_MESSAGE
        ):
            logger.info("ops_dedup_skip update_id=%s kind=%s", update_id, KIND_MESSAGE)
            _advance_offset()
            return False

        try:
            envelope = map_message_update_to_turn(update)
        except MappingSkip as skip:
            logger.debug(
                "ops_update_skipped reason=%s",
                skip.args[0] if skip.args else "skip",
            )
            _advance_offset()
            return False
        try:
            response = self._bridge.post_turns(envelope)
        except BridgeClientError as exc:
            logger.error(
                "ops_bridge_turn_failed event_id=%s status=%s detail=%s",
                envelope.get("event_id"),
                exc.status,
                exc.detail,
            )
            return False
        # Mark seen after successful turns so outbound failure cannot double-apply turns.
        if isinstance(update_id, int):
            self._store.mark_seen(update_id=update_id, kind=KIND_MESSAGE)
        chat_id = envelope["principal"]["chat_id"]
        try:
            self._apply(
                token=self._settings.telegram_bot_token,
                chat_id=chat_id,
                response=response,
            )
        except TelegramApiError as exc:
            logger.error(
                "ops_outbound_failed chat_id=%s method=%s detail=%s",
                chat_id,
                exc.method,
                exc.detail,
            )
            # Seen already — advance so Telegram does not re-POST turns.
            _advance_offset()
            return False
        _advance_offset()
        logger.info(
            "ops_turn_ok event_id=%s chat_id=%s",
            envelope.get("event_id"),
            chat_id,
        )
        return True

    def _process_callback(self, update: dict, advance: Callable[[], None]) -> bool:
        """Ack promptly → POST /v1/channel/actions → persist outbox → drain."""
        update_id = update.get("update_id")
        if isinstance(update_id, int) and self._store.has_seen(
            update_id=update_id, kind=KIND_CALLBACK
        ):
            logger.info("ops_dedup_skip update_id=%s kind=%s", update_id, KIND_CALLBACK)
            advance()
            return False

        try:
            envelope, edit_message_id = map_callback_update_to_action(update)
        except MappingSkip as skip:
            logger.debug(
                "ops_callback_skipped reason=%s",
                skip.args[0] if skip.args else "skip",
            )
            advance()
            return False

        cq_id = envelope["callback_query_id"]
        try:
            self._answer_callback(
                token=self._settings.telegram_bot_token,
                callback_query_id=cq_id,
            )
        except TelegramApiError as exc:
            logger.error(
                "ops_callback_ack_failed method=%s detail=%s",
                exc.method,
                exc.detail,
            )
            # Do not advance — retry full callback path.
            return False

        try:
            response = self._bridge.post_actions(envelope)
        except BridgeClientError as exc:
            logger.error(
                "ops_bridge_action_failed event_id=%s status=%s detail=%s",
                envelope.get("event_id"),
                exc.status,
                exc.detail,
            )
            return False

        chat_id = envelope["principal"]["chat_id"]
        payload = payload_from_bridge_response(
            response=response,
            chat_id=chat_id,
            edit_message_id=edit_message_id,
        )
        if payload is None:
            if isinstance(update_id, int):
                self._store.mark_seen(update_id=update_id, kind=KIND_CALLBACK)
            advance()
            return True

        job_id = self._store.enqueue(chat_id=chat_id, payload=payload)
        try:
            self._drain(store=self._store, token=self._settings.telegram_bot_token)
        except Exception:
            logger.exception("ops_outbox_drain_after_enqueue id=%s", job_id)
        if isinstance(update_id, int):
            self._store.mark_seen(update_id=update_id, kind=KIND_CALLBACK)
        advance()
        logger.info(
            "ops_action_ok event_id=%s chat_id=%s outbox_id=%s",
            envelope.get("event_id"),
            chat_id,
            job_id,
        )
        return True

    def _run(self) -> None:
        logger.info("longpoll_turns_started poll_timeout=%s", self._poll_timeout)
        while not self._stop.is_set():
            try:
                self.process_updates_once()
            except TelegramApiError as exc:
                logger.error(
                    "ops_telegram_poll_failed method=%s status=%s detail=%s",
                    exc.method,
                    exc.status,
                    exc.detail,
                )
                if self._stop.wait(2.0):
                    break
            except Exception:
                logger.exception("ops_poll_loop_unexpected")
                if self._stop.wait(2.0):
                    break
        logger.info("longpoll_turns_stopped")
