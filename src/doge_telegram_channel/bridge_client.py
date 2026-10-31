"""Outbound HTTP to doge-ai-bridge channel façade — turns only in STORY-02."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

TURNS_PATH = "/v1/channel/turns"


class BridgeClientError(RuntimeError):
    """Ops-visible bridge HTTP failure (no bearer/token values)."""

    def __init__(self, *, path: str, status: int | None, detail: str) -> None:
        self.path = path
        self.status = status
        self.detail = detail
        super().__init__(f"bridge_client_error path={path} status={status} detail={detail}")


class BridgeTurnsClient:
    """POST ``/v1/channel/turns`` with Channel Bearer (OpenAPI ChannelBearer)."""

    def __init__(self, *, base_url: str, channel_bearer: str, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer = channel_bearer
        self._timeout = timeout

    def post_turns(self, envelope: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{TURNS_PATH}"
        body = json.dumps(envelope).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._bearer}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise BridgeClientError(path=TURNS_PATH, status=resp.status, detail="non_object")
                return data
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")[:300]
            logger.error(
                "ops_bridge_http_error path=%s status=%s body_prefix=%s",
                TURNS_PATH,
                exc.code,
                err_body.replace("\n", " "),
            )
            raise BridgeClientError(path=TURNS_PATH, status=exc.code, detail="http_error") from exc
        except urllib.error.URLError as exc:
            logger.error(
                "ops_bridge_url_error path=%s reason=%s",
                TURNS_PATH,
                type(exc.reason).__name__,
            )
            raise BridgeClientError(path=TURNS_PATH, status=None, detail="url_error") from exc
        except TimeoutError as exc:
            logger.error("ops_bridge_timeout path=%s", TURNS_PATH)
            raise BridgeClientError(path=TURNS_PATH, status=None, detail="timeout") from exc
