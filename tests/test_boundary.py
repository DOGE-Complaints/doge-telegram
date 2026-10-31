from __future__ import annotations

from doge_telegram_channel.boundary import assert_boundary_clean, scan_source_for_forbidden
from doge_telegram_channel.config import FORBIDDEN_ENV_KEY_FRAGMENTS


def test_ac_tg_01_02_inventory_clean() -> None:
    findings = scan_source_for_forbidden()
    assert findings == [], findings
    assert_boundary_clean()


def test_forbidden_fragments_documented() -> None:
    assert "OPENAI_API_KEY" in FORBIDDEN_ENV_KEY_FRAGMENTS
    assert any("GATEWAY" in f for f in FORBIDDEN_ENV_KEY_FRAGMENTS)
