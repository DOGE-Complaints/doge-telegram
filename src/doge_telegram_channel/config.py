"""Fail-closed settings from environment / optional `.env` file.

Locked / class keys per `docs/architecture/telegram-channel/01-runtime-and-packaging.md` §3
and committed template `example.env`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REQUIRED_KEYS: tuple[str, ...] = (
    "TELEGRAM_BOT_TOKEN",
    "BRIDGE_BASE_URL",
    "CHANNEL_BEARER",
    "SQLITE_PATH",
)

# Forbidden in this service (AC-TG-01-02) — model / gateway domains belong to peers.
FORBIDDEN_ENV_KEY_FRAGMENTS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "GATEWAY_SUBMIT",
    "GATEWAY_ADMIN",
    "AIBRIDGE_OPENAI",
)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def load_env_file(path: Path | None = None) -> None:
    """Load `.env` into process env without overriding already-set keys."""
    env_path = path or Path.cwd() / ".env"
    for key, value in _parse_dotenv(env_path).items():
        os.environ.setdefault(key, value)


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings. Token is never included in ``repr`` / logs helpers."""

    telegram_bot_token: str
    bridge_base_url: str
    channel_bearer: str
    sqlite_path: Path

    def __repr__(self) -> str:
        return (
            "Settings("
            f"telegram_bot_token=***, "
            f"bridge_base_url={self.bridge_base_url!r}, "
            f"channel_bearer=***, "
            f"sqlite_path={str(self.sqlite_path)!r})"
        )


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"missing required env: {name}")
    return value


def load_settings(*, env_file: Path | None = None) -> Settings:
    """Load settings fail-closed. Does not log secret values."""
    load_env_file(env_file)
    return Settings(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        bridge_base_url=_require("BRIDGE_BASE_URL").rstrip("/"),
        channel_bearer=_require("CHANNEL_BEARER"),
        sqlite_path=Path(_require("SQLITE_PATH")).expanduser(),
    )


def missing_required_keys() -> list[str]:
    """Return names of required keys that are unset/blank (after optional `.env`)."""
    load_env_file()
    return [k for k in REQUIRED_KEYS if not os.environ.get(k, "").strip()]


def sqlite_open_ok(path: Path) -> bool:
    """If SQLite file exists, require it to open; if absent, path readiness only."""
    import sqlite3

    if not path.exists():
        parent = path.parent
        return parent.exists() and parent.is_dir() and os.access(parent, os.W_OK | os.X_OK)
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.close()
        return True
    except sqlite3.Error:
        return False


def readiness_reasons(settings: Settings | None = None) -> list[str]:
    """Empty list ⇒ ready. Reasons never include secret values.

    ``settings is None`` means config failed / not loaded → not ready
    (do not re-parse cwd ``.env`` here; that would mask fail-closed).
    """
    if settings is None:
        missing = [
            k for k in REQUIRED_KEYS if not os.environ.get(k, "").strip()
        ]
        if missing:
            return ["missing_required_env:" + ",".join(missing)]
        return ["settings_unavailable"]
    reasons: list[str] = []
    if not sqlite_open_ok(settings.sqlite_path):
        reasons.append("sqlite_not_ready")
    return reasons
