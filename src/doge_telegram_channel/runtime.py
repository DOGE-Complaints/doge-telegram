"""Canonical production entry: poller placeholder + minimal health HTTP.

Packaging SSOT: `python -m doge_telegram_channel` or console script
`doge-telegram-channel` → :func:`main`.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

from doge_telegram_channel.config import ConfigError, Settings, load_settings, readiness_reasons
from doge_telegram_channel.health import start_health_server
from doge_telegram_channel.poller import PollerPlaceholder

logger = logging.getLogger("doge_telegram_channel")


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doge-telegram-channel",
        description="Telegram transport channel (poller + health). Peer: doge-ai-bridge /v1/channel/* only.",
    )
    parser.add_argument(
        "--health-host",
        default=os.environ.get("HEALTH_HOST", "127.0.0.1"),
        help="Health HTTP bind host",
    )
    parser.add_argument(
        "--health-port",
        type=int,
        default=int(os.environ.get("HEALTH_PORT", "8080")),
        help="Health HTTP bind port",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Optional path to .env (default: ./.env if present)",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit non-zero before serving if readiness fails (strict fail-closed start)",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    stop_after_seconds: float | None = None,
) -> int:
    """Production entry. Starts health + poller; never logs secret values.

    ``stop_after_seconds`` is for tests/harness only — production uses signals.
    """
    _configure_logging()
    args = build_parser().parse_args(argv)

    settings: Settings | None
    try:
        settings = load_settings(env_file=args.env_file)
    except ConfigError as exc:
        logger.error("config_fail_closed: %s", exc)
        settings = None
        if args.require_ready:
            return 2

    if settings is not None:
        reasons = readiness_reasons(settings)
        if reasons:
            logger.error("not_ready: %s", ",".join(reasons))
            if args.require_ready:
                return 3
        else:
            logger.info(
                "config_loaded bridge_base_url=%s sqlite_path=%s",
                settings.bridge_base_url,
                settings.sqlite_path,
            )

    held: list[Settings | None] = [settings]

    def provider() -> Settings | None:
        return held[0]

    server, _thread = start_health_server(
        host=args.health_host,
        port=args.health_port,
        settings_provider=provider,
    )
    poller = PollerPlaceholder()
    poller.start()
    logger.info(
        "production_entry_started health=http://%s:%s/healthz poller=placeholder",
        args.health_host,
        args.health_port,
    )

    stop = False
    deadline = (
        time.monotonic() + stop_after_seconds if stop_after_seconds is not None else None
    )

    def _handle_signal(signum: int, _frame: object) -> None:
        nonlocal stop
        logger.info("signal_received signum=%s", signum)
        stop = True

    # Signals only work in the main thread (harness / production).
    if stop_after_seconds is None:
        try:
            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
        except ValueError:
            logger.warning("signal_handlers_unavailable_non_main_thread")

    try:
        while not stop:
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(0.05)
    finally:
        poller.stop()
        server.shutdown()
        logger.info("production_entry_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
