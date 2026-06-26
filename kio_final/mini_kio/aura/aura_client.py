"""
aura_client.py — Reusable AURA communication client.

Provides health(), reason(), retrieve(), store() methods.
No-op when AURA_ENABLED=false. Configurable timeout, graceful failures.
"""

import json
import logging
from typing import Any, Optional

import httpx

from mini_kio.core import config

logger = logging.getLogger(__name__)


class AuraClient:
    """Async HTTP client for the remote AURA server.

    All methods return None on any failure (connection, timeout, HTTP
    error) rather than raising. When AURA_ENABLED is false, all methods
    are no-ops returning None.
    """

    def __init__(self) -> None:
        self._enabled: bool = config.AURA_ENABLED
        self._base_url: str = config.AURA_BASE_URL
        self._timeout: float = config.AURA_TIMEOUT
        self._client: Optional[httpx.AsyncClient] = None

        if self._enabled and not self._base_url:
            logger.warning("AURA_ENABLED=true but AURA_BASE_URL is empty; disabling client")
            self._enabled = False

    # ── Lifecycle ───────────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── HTTP helpers ────────────────────────────────────────────────

    async def _get(self, path: str) -> Optional[Any]:
        if not self._enabled:
            return None
        client = await self._get_client()
        try:
            resp = await client.get(f"{self._base_url}{path}")
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            logger.warning("AURA GET %s: timeout", path)
        except httpx.ConnectError:
            logger.warning("AURA GET %s: connection refused", path)
        except httpx.HTTPStatusError as e:
            logger.warning("AURA GET %s: HTTP %s", path, e.response.status_code)
        except Exception as e:
            logger.warning("AURA GET %s: %s", path, e)
        return None

    async def _post(self, path: str, payload: dict) -> Optional[Any]:
        if not self._enabled:
            return None
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self._base_url}{path}",
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            logger.warning("AURA POST %s: timeout", path)
        except httpx.ConnectError:
            logger.warning("AURA POST %s: connection refused", path)
        except httpx.HTTPStatusError as e:
            logger.warning("AURA POST %s: HTTP %s", path, e.response.status_code)
        except Exception as e:
            logger.warning("AURA POST %s: %s", path, e)
        return None

    # ── Public API ──────────────────────────────────────────────────

    async def health(self) -> Optional[dict]:
        """Check if the remote AURA server is reachable.

        Returns the health payload (e.g. {"status": "ok"}) or None.
        """
        result = await self._get("/health")
        if result is not None:
            logger.info("AURA health: %s", result)
        else:
            logger.info("AURA health: unreachable")
        return result

    async def reason(self, query: str, **kwargs: Any) -> Optional[dict]:
        """Send a reasoning query to AURA.

        Returns the AURA response dict or None on failure.
        """
        payload: dict[str, Any] = {"query": query}
        payload.update(kwargs)
        result = await self._post("/reason", payload)
        if result is not None:
            logger.info("AURA reason: response received (len=%s)", len(str(result)))
        else:
            logger.info("AURA reason: no response")
        return result

    async def retrieve(self, query: str, **kwargs: Any) -> Optional[dict]:
        """Send a retrieval query to AURA.

        Returns the AURA response dict or None on failure.
        """
        payload: dict[str, Any] = {"query": query}
        payload.update(kwargs)
        result = await self._post("/retrieve", payload)
        if result is not None:
            logger.info("AURA retrieve: response received (len=%s)", len(str(result)))
        else:
            logger.info("AURA retrieve: no response")
        return result

    async def store(self, data: dict, **kwargs: Any) -> Optional[dict]:
        """Store data on AURA.

        Returns the AURA response dict or None on failure.
        """
        payload: dict[str, Any] = {"data": data}
        payload.update(kwargs)
        result = await self._post("/store", payload)
        if result is not None:
            logger.info("AURA store: response received")
        else:
            logger.info("AURA store: no response")
        return result
