"""Long-poll loop placeholder — real getUpdates→bridge mapping is STORY-02."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class PollerPlaceholder:
    """Runs until stop. Does not call Telegram Bot API or bridge (STORY-02)."""

    def __init__(self, *, tick_seconds: float = 1.0) -> None:
        self._tick_seconds = tick_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="poller-placeholder", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        logger.info("poller_placeholder_started")
        while not self._stop.wait(self._tick_seconds):
            # Intentionally idle: STORY-02 owns getUpdates → /v1/channel/turns mapping.
            time.sleep(0)
        logger.info("poller_placeholder_stopped")
