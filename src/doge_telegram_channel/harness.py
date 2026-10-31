"""Verify harness — same production poller classes + stub bridge (AC-04/05).

Packaging SSOT remains ``python -m doge_telegram_channel`` / ``runtime:main``.
This module is a verify surface that exercises ``LongPollTurnsLoop`` with synthetic
updates and ``BRIDGE_STUB`` peer — not a second packaging binary.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

from doge_telegram_channel.bridge_stub import RecordingStubBridge, bridge_stub_enabled
from doge_telegram_channel.config import Settings, load_settings
from doge_telegram_channel.poller import LongPollTurnsLoop
from doge_telegram_channel.store import SqliteStore

logger = logging.getLogger("doge_telegram_channel.harness")


def _synthetic_message(*, update_id: int) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "text": "harness-ping",
            "from": {"id": 100},
            "chat": {"id": 200},
        },
    }


def run_duplicate_turn_proof(*, sqlite_path: Path) -> RecordingStubBridge:
    """Process the same synthetic update twice; stub must see a single turns call."""
    os.environ["BRIDGE_STUB"] = "1"
    settings = Settings(
        telegram_bot_token="harness-token",
        bridge_base_url="http://stub.invalid",
        channel_bearer="harness-bearer",
        sqlite_path=sqlite_path,
    )
    stub = RecordingStubBridge()
    updates = [_synthetic_message(update_id=42)]

    def get_updates(**_kwargs: object) -> list[dict]:
        # First call returns the update; subsequent polls empty (offset advanced).
        batch = list(updates)
        updates.clear()
        return batch

    store = SqliteStore(sqlite_path)
    loop = LongPollTurnsLoop(
        settings=settings,
        poll_timeout=0,
        bridge_client=stub,
        get_updates_fn=get_updates,
        apply_fn=lambda **_k: None,
        store=store,
        drain_fn=lambda **_k: 0,
    )
    assert loop.process_updates_once() == 1
    # Re-inject duplicate update_id (Telegram redelivery).
    updates.append(_synthetic_message(update_id=42))
    assert loop.process_updates_once() == 0
    assert stub.turns_count == 1
    # Persist across reopen.
    store.close()
    store2 = SqliteStore(sqlite_path)
    store2.open()
    assert store2.has_seen(update_id=42, kind="message")
    store2.close()
    return stub


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
    parser = argparse.ArgumentParser(
        description="STORY-04 harness: idempotency proof against stub bridge (no live models)."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=None,
        help="Override SQLITE_PATH for isolated proof run",
    )
    parser.add_argument(
        "--with-production-entry",
        action="store_true",
        help="Also start runtime.main briefly with BRIDGE_STUB=1 (packaging honesty)",
    )
    args = parser.parse_args(argv)

    os.environ.setdefault("BRIDGE_STUB", "1")
    if not bridge_stub_enabled():
        logger.error("BRIDGE_STUB must be enabled for harness")
        return 2

    path = args.sqlite_path
    if path is None:
        try:
            settings = load_settings()
            path = settings.sqlite_path
        except Exception:
            path = Path.cwd() / ".harness-seen.sqlite"

    stub = run_duplicate_turn_proof(sqlite_path=path)
    logger.info(
        "harness_ac04_pass turns_count=%s (duplicate suppressed)",
        stub.turns_count,
    )

    if args.with_production_entry:
        from doge_telegram_channel.runtime import main as runtime_main

        # Fail-closed env may already be loaded; ensure stub + short run.
        os.environ.setdefault("TELEGRAM_BOT_TOKEN", "harness-token")
        os.environ.setdefault("BRIDGE_BASE_URL", "http://stub.invalid")
        os.environ.setdefault("CHANNEL_BEARER", "harness-bearer")
        os.environ["SQLITE_PATH"] = str(path)
        os.environ["BRIDGE_STUB"] = "1"
        rc = runtime_main(stop_after_seconds=0.2)
        if rc != 0:
            return rc
        logger.info("harness_production_entry_ok entry=runtime.main")

    logger.info(
        "defense_in_depth_note peer_tests=doge-ai-bridge/tests/integration/"
        "test_idempotency_concurrency.py (second belt; not sole AC-04)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
