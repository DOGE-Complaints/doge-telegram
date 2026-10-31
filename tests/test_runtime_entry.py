from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import pytest

from doge_telegram_channel.runtime import main


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_production_entry_starts_health(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vol = tmp_path / "vol"
    vol.mkdir()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("BRIDGE_BASE_URL", "http://bridge")
    monkeypatch.setenv("CHANNEL_BEARER", "bear")
    monkeypatch.setenv("SQLITE_PATH", str(vol / "db.sqlite"))
    port = _free_port()

    # Run entry briefly in-process; stop_after_seconds ends the loop cleanly.
    # Probe health from a nested check mid-run by starting with enough duration.
    # First ensure require-ready path works when env missing.
    for key in ("TELEGRAM_BOT_TOKEN", "BRIDGE_BASE_URL", "CHANNEL_BEARER", "SQLITE_PATH"):
        monkeypatch.delenv(key, raising=False)
    assert main(["--require-ready"], stop_after_seconds=0.01) == 2

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("BRIDGE_BASE_URL", "http://bridge")
    monkeypatch.setenv("CHANNEL_BEARER", "bear")
    monkeypatch.setenv("SQLITE_PATH", str(vol / "db.sqlite"))

    # Use a thread so we can HTTP-probe while main is running.
    import threading

    result: list[int] = []

    def runner() -> None:
        result.append(
            main(
                [
                    "--health-host",
                    "127.0.0.1",
                    "--health-port",
                    str(port),
                    "--env-file",
                    str(tmp_path / "none.env"),
                ],
                stop_after_seconds=1.5,
            )
        )

    thread = threading.Thread(target=runner)
    thread.start()
    import time

    deadline = time.time() + 2
    payload = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=0.3) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.05)
    thread.join(timeout=5)
    assert payload == {"status": "ok"}
    assert result == [0]


def test_module_entry_importable() -> None:
    import doge_telegram_channel.__main__ as mod

    assert callable(mod.main)
