from __future__ import annotations

import os
from pathlib import Path

import pytest

from doge_telegram_channel.config import (
    ConfigError,
    load_settings,
    missing_required_keys,
    readiness_reasons,
    sqlite_open_ok,
)


def test_missing_required_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in ("TELEGRAM_BOT_TOKEN", "BRIDGE_BASE_URL", "CHANNEL_BEARER", "SQLITE_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here → do not revive keys via setdefault
    assert "TELEGRAM_BOT_TOKEN" in missing_required_keys()
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        load_settings(env_file=tmp_path / "missing.env")


def test_load_settings_and_repr_hides_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "data"
    db.mkdir()
    sqlite_path = db / "channel.sqlite"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token-value")
    monkeypatch.setenv("BRIDGE_BASE_URL", "http://bridge.example")
    monkeypatch.setenv("CHANNEL_BEARER", "secret-bearer")
    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    settings = load_settings(env_file=tmp_path / "nope.env")
    rendered = repr(settings)
    assert "secret-token-value" not in rendered
    assert "secret-bearer" not in rendered
    assert settings.bridge_base_url == "http://bridge.example"


def test_ready_when_env_ok_and_parent_writable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_dir = tmp_path / "vol"
    db_dir.mkdir()
    sqlite_path = db_dir / "idempotency.sqlite"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("BRIDGE_BASE_URL", "http://bridge")
    monkeypatch.setenv("CHANNEL_BEARER", "b")
    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    settings = load_settings(env_file=tmp_path / "x.env")
    assert sqlite_open_ok(settings.sqlite_path) is True
    assert readiness_reasons(settings) == []


def test_dotenv_load(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in ("TELEGRAM_BOT_TOKEN", "BRIDGE_BASE_URL", "CHANNEL_BEARER", "SQLITE_PATH"):
        monkeypatch.delenv(key, raising=False)
    vol = tmp_path / "v"
    vol.mkdir()
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "TELEGRAM_BOT_TOKEN=from-file",
                "BRIDGE_BASE_URL=http://bridge",
                "CHANNEL_BEARER=bearer",
                f"SQLITE_PATH={vol / 'db.sqlite'}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    settings = load_settings()
    assert settings.telegram_bot_token == "from-file"
    assert os.environ.get("TELEGRAM_BOT_TOKEN") == "from-file"
