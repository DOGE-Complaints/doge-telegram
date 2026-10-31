"""In-process stub bridge peer — AC-TG-01-05 (no live model provider).

Selected when ``BRIDGE_STUB=1`` (or truthy). Does not call HTTP; records side effects
for harness/idempotency proofs (AC-TG-01-04).
"""

from __future__ import annotations

import logging
from typing import Any

from doge_telegram_channel.bridge_client import BridgeTurnsClient

logger = logging.getLogger(__name__)


def bridge_stub_enabled() -> bool:
    import os

    return os.environ.get("BRIDGE_STUB", "").strip().lower() in {"1", "true", "yes", "on"}


class RecordingStubBridge(BridgeTurnsClient):
    """Scripted ChannelSuccessResponse; counts turns/actions for dedup proofs."""

    def __init__(self) -> None:
        # Do not call super — no HTTP base.
        self.turns_calls: list[dict[str, Any]] = []
        self.actions_calls: list[dict[str, Any]] = []

    @property
    def turns_count(self) -> int:
        return len(self.turns_calls)

    @property
    def actions_count(self) -> int:
        return len(self.actions_calls)

    def post_turns(self, envelope: dict[str, Any]) -> dict[str, Any]:
        self.turns_calls.append(envelope)
        logger.info(
            "ops_stub_turns event_id=%s count=%s",
            envelope.get("event_id"),
            self.turns_count,
        )
        return _success_response(f"stub-turn-{envelope.get('event_id')}")

    def post_actions(self, envelope: dict[str, Any]) -> dict[str, Any]:
        self.actions_calls.append(envelope)
        logger.info(
            "ops_stub_actions event_id=%s count=%s",
            envelope.get("event_id"),
            self.actions_count,
        )
        return _success_response(f"stub-action-{envelope.get('event_id')}")


def _success_response(reply_text: str) -> dict[str, Any]:
    return {
        "request_id": "stub-req",
        "session_id": "stub-sess",
        "state": "stub",
        "reply_text": reply_text,
        "actions": [],
        "outcome": None,
        "draft_id": None,
        "continuation_url": None,
    }


def make_bridge_client(*, base_url: str, channel_bearer: str) -> BridgeTurnsClient:
    """Factory used by production entry — stub or HTTP."""
    if bridge_stub_enabled():
        logger.warning("ops_bridge_stub_enabled")
        return RecordingStubBridge()
    return BridgeTurnsClient(base_url=base_url, channel_bearer=channel_bearer)
