"""Trust-boundary inventory helpers (AC-TG-01-02).

This service must not hold model API keys or a gateway submit client.
"""

from __future__ import annotations

import ast
from pathlib import Path

from doge_telegram_channel.config import FORBIDDEN_ENV_KEY_FRAGMENTS

# Import / symbol patterns that would indicate gateway submit or model SDK wiring.
FORBIDDEN_IMPORT_ROOTS: tuple[str, ...] = (
    "openai",
    "anthropic",
    "litellm",
)
FORBIDDEN_NAME_FRAGMENTS: tuple[str, ...] = (
    "gateway_submit",
    "GatewaySubmit",
    "submit_complaint",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def package_root() -> Path:
    return Path(__file__).resolve().parent


def iter_package_py_files(root: Path | None = None) -> list[Path]:
    base = root or package_root()
    return sorted(p for p in base.rglob("*.py") if p.is_file())


_DENYLIST_MODULES = frozenset({"config.py", "boundary.py"})


def scan_source_for_forbidden(root: Path | None = None) -> list[str]:
    """Return human-readable findings; empty list means inventory clean."""
    findings: list[str] = []
    for path in iter_package_py_files(root):
        text = path.read_text(encoding="utf-8")
        rel = str(path)
        allow_deny_literals = path.name in _DENYLIST_MODULES
        if not allow_deny_literals:
            for frag in FORBIDDEN_ENV_KEY_FRAGMENTS:
                if frag in text:
                    findings.append(f"{rel}: literal {frag}")
            for frag in FORBIDDEN_NAME_FRAGMENTS:
                if frag in text:
                    findings.append(f"{rel}: literal {frag}")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings.append(f"{rel}: syntax_error:{exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".", 1)[0]
                    if root_name in FORBIDDEN_IMPORT_ROOTS:
                        findings.append(f"{rel}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_name = node.module.split(".", 1)[0]
                if root_name in FORBIDDEN_IMPORT_ROOTS:
                    findings.append(f"{rel}: from {node.module}")
            elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAME_FRAGMENTS:
                if not allow_deny_literals:
                    findings.append(f"{rel}: name {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAME_FRAGMENTS:
                if not allow_deny_literals:
                    findings.append(f"{rel}: attr {node.attr}")
    return findings


def assert_boundary_clean(root: Path | None = None) -> None:
    findings = scan_source_for_forbidden(root)
    if findings:
        raise AssertionError("AC-TG-01-02 boundary violations:\n" + "\n".join(findings))
