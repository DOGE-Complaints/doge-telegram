from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from doge_telegram_channel.config import Settings, load_settings
from doge_telegram_channel.health import start_health_server


def _get(url: str) -> tuple[int, dict[str, object]]:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body)


def test_healthz_and_readyz(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vol = tmp_path / "vol"
    vol.mkdir()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("BRIDGE_BASE_URL", "http://bridge")
    monkeypatch.setenv("CHANNEL_BEARER", "bear")
    monkeypatch.setenv("SQLITE_PATH", str(vol / "x.sqlite"))
    settings = load_settings(env_file=tmp_path / "none.env")

    server, _ = start_health_server(
        host="127.0.0.1",
        port=0,
        settings_provider=lambda: settings,
    )
    port = server.server_address[1]
    try:
        code, payload = _get(f"http://127.0.0.1:{port}/healthz")
        assert code == 200
        assert payload == {"status": "ok"}
        assert "tok" not in json.dumps(payload)

        code, payload = _get(f"http://127.0.0.1:{port}/readyz")
        assert code == 200
        assert payload == {"status": "ready"}
        assert "bear" not in json.dumps(payload)
    finally:
        server.shutdown()


def test_readyz_fail_closed_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("TELEGRAM_BOT_TOKEN", "BRIDGE_BASE_URL", "CHANNEL_BEARER", "SQLITE_PATH"):
        monkeypatch.delenv(key, raising=False)

    server, _ = start_health_server(
        host="127.0.0.1",
        port=0,
        settings_provider=lambda: None,
    )
    port = server.server_address[1]
    try:
        code, payload = _get(f"http://127.0.0.1:{port}/readyz")
        assert code == 503
        assert payload["status"] == "not_ready"
        reasons = payload["reasons"]
        assert isinstance(reasons, list)
        assert reasons
        blob = json.dumps(payload)
        # reasons name keys / statuses only — never secret values
        assert "tok" not in blob
        assert "token_value" not in blob
    finally:
        server.shutdown()


def test_settings_type_for_mypy_smoke() -> None:
    # Keep Settings import exercised for packaging honesty.
    assert Settings.__dataclass_fields__
