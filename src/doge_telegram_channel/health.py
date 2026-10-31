"""Minimal health HTTP — ops probe only (not Telegram ingress)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from doge_telegram_channel.config import Settings, readiness_reasons

SettingsProvider = Callable[[], Settings | None]


def start_health_server(
    *,
    host: str,
    port: int,
    settings_provider: SettingsProvider,
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    """Start health HTTP in a daemon thread. Returns (server, thread)."""

    class HealthHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def _json(self, code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                self._json(200, {"status": "ok"})
                return
            if path == "/readyz":
                settings = settings_provider()
                reasons = readiness_reasons(settings)
                if reasons:
                    self._json(503, {"status": "not_ready", "reasons": reasons})
                else:
                    self._json(200, {"status": "ready"})
                return
            self._json(404, {"status": "not_found"})

    server = ThreadingHTTPServer((host, port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="health-http", daemon=True)
    thread.start()
    return server, thread
