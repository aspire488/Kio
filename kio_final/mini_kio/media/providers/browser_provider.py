from __future__ import annotations

import asyncio
import logging
from typing import Optional

from mini_kio.browser_connector.connector import Connector
from mini_kio.core import config
from mini_kio.media.media_session import MediaResult, MediaSession
from mini_kio.media.media_state import MediaState, PlayerType, MediaType
from mini_kio.media.providers import MediaProvider

logger = logging.getLogger(__name__)

_CONTROL_ACTIONS = {
    "play": "play",
    "pause": "pause",
    "stop": "stop",
    "mute": "mute",
    "unmute": "unmute",
    "volume_up": "volume_up",
    "volume_down": "volume_down",
    "seek_forward": "seek_forward",
    "seek_backward": "seek_backward",
}


class BrowserProvider(MediaProvider):
    def __init__(self, conn: Optional[Connector] = None):
        self._conn = conn
        self._session: Optional[MediaSession] = None

    @property
    def name(self) -> str:
        return "browser"

    def _get_conn(self) -> Optional[Connector]:
        if self._conn is not None:
            return self._conn
        if config.BROWSER_CONNECTOR_ENABLED:
            from mini_kio.core.command_router import _get_connector
            self._conn = _get_connector()
        return self._conn

    def _resolve_tab(self, domain_hint: str = "") -> Optional[int]:
        conn = self._get_conn()
        if not conn:
            return None
        try:
            tab = asyncio.run(conn._resolve_media_tab(domain_hint))
            if tab:
                return tab.tab_id
        except Exception:
            pass
        return None

    def play(self, query: str = "", **kwargs) -> MediaResult:
        tab_id = self._resolve_tab(kwargs.get("domain_hint", ""))
        if not tab_id:
            return MediaResult(success=False, error="No browser media tab found", player="browser")
        return self._execute("play", tab_id)

    def pause(self) -> MediaResult:
        tab_id = self._resolve_tab()
        if not tab_id:
            return MediaResult(success=False, error="No active browser media", player="browser")
        return self._execute("pause", tab_id)

    def resume(self) -> MediaResult:
        return self.play()

    def stop(self) -> MediaResult:
        tab_id = self._resolve_tab()
        if not tab_id:
            return MediaResult(success=False, error="No active browser media", player="browser")
        return self._execute("stop", tab_id)

    def next_track(self) -> MediaResult:
        return MediaResult(success=False, error="Next track not supported for browser media", player="browser")

    def previous_track(self) -> MediaResult:
        return MediaResult(success=False, error="Previous track not supported for browser media", player="browser")

    def seek(self, seconds: int) -> MediaResult:
        conn = self._get_conn()
        tab_id = self._resolve_tab()
        if not conn or not tab_id:
            return MediaResult(success=False, error="No active browser media", player="browser")
        action = "seek_forward" if seconds >= 0 else "seek_backward"
        try:
            result = asyncio.run(conn.execute_script(tab_id, action))
            if result.success:
                if self._session:
                    self._session.touch()
                return MediaResult(success=True, message=f"Seeked {abs(seconds)}s", player="browser")
            return MediaResult(success=False, error=result.error, player="browser")
        except Exception as exc:
            return MediaResult(success=False, error=str(exc), player="browser")

    def volume(self, level: Optional[float] = None, direction: Optional[str] = None) -> MediaResult:
        conn = self._get_conn()
        tab_id = self._resolve_tab()
        if not conn or not tab_id:
            return MediaResult(success=False, error="No active browser media", player="browser")
        action = "volume_up" if direction != "down" else "volume_down"
        try:
            result = asyncio.run(conn.execute_script(tab_id, action))
            if result.success:
                return MediaResult(success=True, message=result.message or "Volume adjusted", player="browser")
            return MediaResult(success=False, error=result.error, player="browser")
        except Exception as exc:
            return MediaResult(success=False, error=str(exc), player="browser")

    def search(self, query: str) -> MediaResult:
        return MediaResult(success=False, error="Search not supported for browser media", player="browser")

    def close(self) -> MediaResult:
        self._session = None
        return MediaResult(success=True, message="Browser media session closed", player="browser")

    def check_active(self) -> Optional[MediaSession]:
        tab_id = self._resolve_tab()
        if tab_id:
            if self._session is None:
                return None
            if self._session.state == MediaState.IDLE:
                return None
            self._session.tab_id = tab_id
            self._session.touch()
            return self._session
        if self._session:
            self._session.state = MediaState.IDLE
        return None

    def _execute(self, action: str, tab_id: int) -> MediaResult:
        conn = self._get_conn()
        if not conn:
            return MediaResult(success=False, error="Connector not available", player="browser")
        script = _CONTROL_ACTIONS.get(action)
        if not script:
            return MediaResult(success=False, error=f"Unknown action: {action}", player="browser")
        try:
            result = asyncio.run(conn.execute_script(tab_id, script))
            if result.success:
                new_state = MediaState.IDLE
                if result.message:
                    if result.message == "playing":
                        new_state = MediaState.PLAYING
                    elif result.message == "paused":
                        new_state = MediaState.PAUSED
                    elif result.message == "stopped":
                        new_state = MediaState.STOPPED
                    elif result.message == "muted":
                        pass
                    elif result.message == "unmuted":
                        pass
                self._session = MediaSession(
                    player=PlayerType.BROWSER,
                    tab_id=tab_id,
                    state=new_state,
                    media_type=MediaType.BROWSER_MEDIA,
                )
                self._session.touch()
                return MediaResult(success=True, message=result.message or f"{action.capitalize()}d", player="browser", session=self._session)
            return MediaResult(success=False, error=result.error, player="browser")
        except Exception as exc:
            return MediaResult(success=False, error=str(exc), player="browser")
