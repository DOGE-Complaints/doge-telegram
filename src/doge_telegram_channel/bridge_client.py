"""Outbound HTTP to doge-ai-bridge channel façade — turns + actions."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

TURNS_PATH = "/v1/channel/turns"
ACTIONS_PATH = "/v1/channel/actions"


class BridgeClientError(RuntimeError):
    """Ops-visible bridge HTTP failure (no bearer/token values)."""

    def __init__(self, *, path: str, status: int | None, detail: str) -> None:
        self.path = path
        self.status = status
        self.detail = detail
        super().__init__(f"bridge_client_error path={path} status={status} detail={detail}")


class BridgeTurnsClient:
    """POST ``/v1/channel/turns`` and ``/v1/channel/actions`` with Channel Bearer."""

    def __init__(self, *, base_url: str, channel_bearer: str, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer = channel_bearer
        self._timeout = timeout

    def post_turns(self, envelope: dict[str, Any]) -> dict[str, Any]:
        return self._post(TURNS_PATH, envelope)

    def post_actions(self, envelope: dict[str, Any]) -> dict[str, Any]:
        return self._post(ACTIONS_PATH, envelope)

    def _post(self, path: str, envelope: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
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
                    raise BridgeClientError(path=path, status=resp.status, detail="non_object")
                return data
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")[:300]
            logger.error(
                "ops_bridge_http_error path=%s status=%s body_prefix=%s",
                path,
                exc.code,
                err_body.replace("\n", " "),
            )
            raise BridgeClientError(path=path, status=exc.code, detail="http_error") from exc
        except urllib.error.URLError as exc:
            logger.error(
                "ops_bridge_url_error path=%s reason=%s",
                path,
                type(exc.reason).__name__,
            )
            raise BridgeClientError(path=path, status=None, detail="url_error") from exc
        except TimeoutError as exc:
            logger.error("ops_bridge_timeout path=%s", path)
            raise BridgeClientError(path=path, status=None, detail="timeout") from exc
