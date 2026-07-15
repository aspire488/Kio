"""Session persistence — save/restore cookies, localStorage, and auth state per workspace."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext

logger = logging.getLogger("browser_runtime.session")


class SessionPersistence:
    """Persists and restores browser session state (cookies, localStorage, sessionStorage).

    Each workspace gets its own session file under the storage root.
    Enables login persistence across browser restarts without re-authentication.
    """

    def __init__(self, storage_root: Path) -> None:
        self._storage_root = storage_root / "sessions"
        self._storage_root.mkdir(parents=True, exist_ok=True)

    def _session_path(self, workspace: str) -> Path:
        safe = workspace.replace(" ", "_").replace("/", "_")
        return self._storage_root / f"{safe}.json"

    async def save(self, context: BrowserContext, workspace: str) -> dict[str, Any]:
        """Save all session state from a BrowserContext."""
        path = self._session_path(workspace)
        try:
            cookies = await context.cookies()
            state = await context.storage_state()
            payload = {
                "workspace": workspace,
                "saved_at": time.time(),
                "cookies": cookies,
                "storage_state": state,
                "origins": state.get("origins", []),
            }
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            logger.info("Session saved for workspace '%s': %d cookies, %d origins",
                        workspace, len(cookies), len(payload["origins"]))
            return payload
        except Exception as exc:
            logger.warning("Session save failed for workspace '%s': %s", workspace, exc)
            return {}

    async def restore(self, context: BrowserContext, workspace: str) -> bool:
        """Restore session state into a BrowserContext. Returns True if restored."""
        path = self._session_path(workspace)
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cookies = payload.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)
            origins = payload.get("origins", [])
            if origins:
                for origin_data in origins:
                    try:
                        page = await context.new_page()
                        await page.goto(origin_data.get("origin", "about:blank"), wait_until="domcontentloaded")
                        storage = origin_data.get("localStorage", [])
                        if storage:
                            for item in storage:
                                try:
                                    await page.evaluate(
                                        "k => window.localStorage.setItem(k[0], k[1])",
                                        [item.get("name", ""), item.get("value", "")],
                                    )
                                except Exception:
                                    pass
                        await page.close()
                    except Exception:
                        pass
            logger.info("Session restored for workspace '%s': %d cookies, %d origins",
                        workspace, len(cookies), len(origins))
            return True
        except Exception as exc:
            logger.warning("Session restore failed for workspace '%s': %s", workspace, exc)
            return False

    def has_session(self, workspace: str) -> bool:
        return self._session_path(workspace).exists()

    def delete_session(self, workspace: str) -> None:
        path = self._session_path(workspace)
        if path.exists():
            path.unlink()
            logger.info("Session deleted for workspace '%s'", workspace)

    def list_sessions(self) -> list[str]:
        return [p.stem for p in self._storage_root.glob("*.json") if p.is_file()]


class CookieManager:
    """Fine-grained cookie operations for browser contexts."""

    @staticmethod
    async def get_cookies(context: BrowserContext, domain: str | None = None) -> list[dict]:
        cookies = await context.cookies()
        if domain:
            cookies = [c for c in cookies if domain in c.get("domain", "")]
        return cookies

    @staticmethod
    async def set_cookies(context: BrowserContext, cookies: list[dict]) -> None:
        await context.add_cookies(cookies)

    @staticmethod
    async def delete_cookies(context: BrowserContext, domain: str | None = None, name: str | None = None) -> None:
        existing = await context.cookies()
        to_delete = existing
        if domain:
            to_delete = [c for c in to_delete if domain in c.get("domain", "")]
        if name:
            to_delete = [c for c in to_delete if c.get("name") == name]
        for c in to_delete:
            await context.clear_cookies()
            break

    @staticmethod
    async def export_cookies(context: BrowserContext, path: Path) -> None:
        cookies = await context.cookies()
        path.write_text(json.dumps(cookies, indent=2), encoding="utf-8")

    @staticmethod
    async def import_cookies(context: BrowserContext, path: Path) -> int:
        cookies = json.loads(path.read_text(encoding="utf-8"))
        await context.add_cookies(cookies)
        return len(cookies)
