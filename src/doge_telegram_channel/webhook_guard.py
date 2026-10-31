"""v1 ingress must not require a Telegram webhook server."""

from __future__ import annotations

import ast
from pathlib import Path

# Health HTTP is an ops probe (arch), not Telegram webhook ingress.
_FORBIDDEN_WEBHOOK_SYMBOLS = frozenset(
    {
        "setWebhook",
        "deleteWebhook",
        "WebhookInfo",
        "process_webhook",
        "telegram_webhook",
    }
)


def package_root() -> Path:
    return Path(__file__).resolve().parent


def scan_webhook_ingress(root: Path | None = None) -> list[str]:
    """Return findings if webhook ingress symbols/paths appear in package code."""
    findings: list[str] = []
    base = root or package_root()
    for path in sorted(base.rglob("*.py")):
        if path.name == "webhook_guard.py":
            continue
        text = path.read_text(encoding="utf-8")
        for sym in _FORBIDDEN_WEBHOOK_SYMBOLS:
            if sym in text:
                findings.append(f"{path}: literal {sym}")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings.append(f"{path}: syntax_error:{exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in _FORBIDDEN_WEBHOOK_SYMBOLS:
                findings.append(f"{path}: name {node.id}")
            if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_WEBHOOK_SYMBOLS:
                findings.append(f"{path}: attr {node.attr}")
    return findings


def assert_no_webhook_ingress(root: Path | None = None) -> None:
    findings = scan_webhook_ingress(root)
    if findings:
        raise AssertionError("v1 webhook ingress forbidden:\n" + "\n".join(findings))
