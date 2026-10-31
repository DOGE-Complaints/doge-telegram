"""Long-poll getUpdates → POST /v1/channel/turns → minimal outbound apply."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Protocol

from doge_telegram_channel.bridge_client import BridgeClientError, BridgeTurnsClient
from doge_telegram_channel.config import Settings
from doge_telegram_channel.mapper import MappingSkip, map_message_update_to_turn
from doge_telegram_channel.outbound import apply_bridge_success
from doge_telegram_channel.telegram_api import TelegramApiError, get_updates

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
    """v1 ingress: Telegram long-poll only (no webhook server)."""

    def __init__(
        self,
        *,
        settings: Settings,
        poll_timeout: int = 25,
        bridge_client: BridgeTurnsClient | None = None,
        get_updates_fn: Callable[..., list] | None = None,
        apply_fn: Callable[..., None] | None = None,
    ) -> None:
        self._settings = settings
        self._poll_timeout = poll_timeout
        self._bridge = bridge_client or BridgeTurnsClient(
            base_url=settings.bridge_base_url,
            channel_bearer=settings.channel_bearer,
        )
        self._get_updates = get_updates_fn or get_updates
        self._apply = apply_fn or apply_bridge_success
        self._offset: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="longpoll-turns", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=float(self._poll_timeout) + 15.0)

    def process_updates_once(self) -> int:
        """Fetch and process one getUpdates batch. Returns processed message count."""
        updates = self._get_updates(
            token=self._settings.telegram_bot_token,
            offset=self._offset,
            timeout=self._poll_timeout,
        )
        processed = 0
        for update in updates:
            update_id = update.get("update_id")

            def _advance_offset() -> None:
                if isinstance(update_id, int):
                    self._offset = update_id + 1

            try:
                envelope = map_message_update_to_turn(update)
            except MappingSkip as skip:
                # Non-message / out-of-scope updates: acknowledge offset so they are not redelivered forever.
                logger.debug(
                    "ops_update_skipped reason=%s",
                    skip.args[0] if skip.args else "skip",
                )
                _advance_offset()
                continue
            try:
                response = self._bridge.post_turns(envelope)
            except BridgeClientError as exc:
                logger.error(
                    "ops_bridge_turn_failed event_id=%s status=%s detail=%s",
                    envelope.get("event_id"),
                    exc.status,
                    exc.detail,
                )
                # Do not advance offset — Telegram can redeliver this update_id.
                continue
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
                # Do not advance offset — turn may have succeeded but outbound failed; retry update.
                continue
            _advance_offset()
            processed += 1
            logger.info(
                "ops_turn_ok event_id=%s chat_id=%s",
                envelope.get("event_id"),
                chat_id,
            )
        return processed

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
