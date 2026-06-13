from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from typing import Optional

from mini_kio.browser_connector.connector import Connector
from mini_kio.core import config
from mini_kio.media.media_session import MediaResult, MediaSession, MediaCandidate
from mini_kio.media.media_state import MediaState, PlayerType, MediaType
from mini_kio.media.providers import MediaProvider

logger = logging.getLogger(__name__)

_YOUTUBE_SEARCH_URL = (
    "https://www.youtube.com/results?search_query={encoded}&sp=EgIQAQ%253D%253D"
)


class YouTubeProvider(MediaProvider):
    def __init__(self, conn: Optional[Connector] = None):
        self._conn = conn
        self._session: Optional[MediaSession] = None
        self._tab_id: Optional[int] = None

    @property
    def name(self) -> str:
        return "youtube"

    def _get_conn(self) -> Optional[Connector]:
        if self._conn is not None:
            return self._conn
        if config.BROWSER_CONNECTOR_ENABLED:
            from mini_kio.core.command_router import _get_connector
            self._conn = _get_connector()
        return self._conn

    def play(self, query: str, **kwargs) -> MediaResult:
        conn = self._get_conn()
        if not conn or not conn.is_connected():
            return MediaResult(success=False, error="Browser Connector not available", player="youtube")

        clean_query = query.strip()
        if not clean_query:
            return MediaResult(success=False, error="No query", player="youtube")

        encoded = urllib.parse.quote_plus(clean_query)
        url = _YOUTUBE_SEARCH_URL.format(encoded=encoded)

        try:
            result = asyncio.run(conn.open_tab(url))
            if not result.success:
                return MediaResult(success=False, error=f"Failed to open YouTube: {result.error}", player="youtube")

            tab_id = result.tab.tab_id if result.tab else None
            logger.info("[YT] opened tab tab_id=%s query=%s", tab_id, clean_query)

            playback_state = MediaState.IDLE
            if tab_id:
                time.sleep(1.5)
                try:
                    bootstrap_result = asyncio.run(conn.execute_script(tab_id, "youtube_bootstrap"))
                    if bootstrap_result.success and bootstrap_result.message == "navigating":
                        # Retry play with backoff to handle SPA navigation timing
                        for attempt in range(3):
                            time.sleep(2.0)
                            play_result = asyncio.run(conn.execute_script(tab_id, "play"))
                            if play_result.success and isinstance(play_result.message, dict):
                                msg = play_result.message
                                if msg.get("status") == "playing":
                                    playback_state = MediaState.PLAYING
                                    if self._session:
                                        self._session.current_time = msg.get("currentTime")
                                        self._session.duration = msg.get("duration")
                                        self._session.volume = msg.get("volume")
                                        self._session.muted = msg.get("muted")
                                    break
                                elif msg.get("status") == "blocked":
                                    logger.warning("[YT] autoplay blocked by browser")
                                    playback_state = MediaState.PAUSED
                                    break
                                elif msg.get("status") == "no media" and attempt < 2:
                                    logger.info("[YT] video element not yet available (attempt %d/3)", attempt + 1)
                                    continue
                                elif msg.get("status", "").startswith("error:"):
                                    logger.warning("[YT] play script error: %s", msg.get("name", "unknown"))
                                    break
                                else:
                                    break
                            elif play_result.success and play_result.message == "navigating":
                                # This can happen if bootstrap didn't finish navigating before the play script runs
                                # Treat as still navigating, continue retrying
                                logger.info("[YT] play script returned 'navigating', retrying (attempt %d/3)", attempt + 1)
                                continue
                            elif not play_result.success:
                                logger.warning("[YT] play script failed: %s", play_result.error)
                                break
                            else:
                                logger.warning("[YT] play script returned unexpected message type: %s", type(play_result.message))
                                break
                    else:
                        logger.warning("[YT] bootstrap did not navigate (message=%s)", bootstrap_result.message)
                except Exception as exc:
                    logger.warning("[YT] bootstrap/play failed: %s", exc)

            self._tab_id = tab_id
            self._session = MediaSession(
                player=PlayerType.YOUTUBE,
                tab_id=tab_id,
                state=playback_state,
                query=clean_query,
                url=url,
                domain_hint="youtube.com",
                media_type=self._detect_type(clean_query),
            )
            self._session.touch()

            message = (
                f"Playing on YouTube: {clean_query}" if playback_state == MediaState.PLAYING else
                "Autoplay blocked. Click play once." if playback_state == MediaState.PAUSED else
                f"Opened on YouTube: {clean_query}"
            )
            return MediaResult(
                success=playback_state in (MediaState.PLAYING, MediaState.PAUSED),
                message=message,
                session=self._session,
                player="youtube",
            )
        except Exception as exc:
            logger.warning("[YT] play failed: %s", exc)
            return MediaResult(success=False, error=str(exc), player="youtube")

    def pause(self) -> MediaResult:
        return self._transport("pause")

    def resume(self) -> MediaResult:
        return self._transport("play")

    def stop(self) -> MediaResult:
        return self._transport("stop")

    def next_track(self) -> MediaResult:
        return MediaResult(success=False, error="Next track not supported on YouTube", player="youtube")

    def previous_track(self) -> MediaResult:
        return MediaResult(success=False, error="Previous track not supported on YouTube", player="youtube")

    def seek(self, seconds: int) -> MediaResult:
        conn = self._get_conn()
        tab_id = self._resolve_tab_id()
        if not conn or not tab_id:
            return MediaResult(success=False, error="No active YouTube session", player="youtube")
        # Seek via script injection using currentTime
        script = "seek_forward" if seconds >= 0 else "seek_backward"
        try:
            result = asyncio.run(conn.execute_script(tab_id, script))
            if result.success:
                return MediaResult(success=True, message=f"Seeked {abs(seconds)}s", player="youtube")
            return MediaResult(success=False, error=result.error, player="youtube")
        except Exception as exc:
            return MediaResult(success=False, error=str(exc), player="youtube")

    def volume(self, level: Optional[float] = None, direction: Optional[str] = None) -> MediaResult:
        return self._transport("volume_up" if direction != "down" else "volume_down")

    def search(self, query: str) -> MediaResult:
        return self.play(query)

    def close(self) -> MediaResult:
        conn = self._get_conn()
        tab_id = self._resolve_tab_id()
        if conn and tab_id:
            asyncio.run(conn.close_tab(tab_id))
        self._session = None
        self._tab_id = None
        return MediaResult(success=True, message="YouTube session closed", player="youtube")

    def check_active(self) -> Optional[MediaSession]:
        if self._session is None:
            return None
        if self._tab_id is None:
            return None

        conn = self._get_conn()
        if not conn or not conn.is_connected():
            return None

        try:
            tab_list_result = asyncio.run(conn.list_tabs())
            if not tab_list_result.success or not tab_list_result.tabs:
                logger.debug("[YT] Failed to list tabs or no tabs returned.")
                # If no tabs are listed, assume the session is no longer active
                if self._session.state in (MediaState.PLAYING, MediaState.PAUSED):
                    self._session.state = MediaState.STOPPED
                    self._session.touch()
                return None

            current_tab_info = next((t for t in tab_list_result.tabs if t.tab_id == self._tab_id), None)

            if current_tab_info:
                if current_tab_info.audible:
                    # Media is still playing or audible in the tab
                    # Set state to PLAYING, even if it was PAUSED, as audible implies activity.
                    # KIO will need to check the exact script status for PLAYING vs PAUSED if more granular control is needed.
                    self._session.state = MediaState.PLAYING
                    self._session.touch()
                    return self._session
                else:
                    # Tab exists but is not audible. If it was playing, it's now stopped/paused
                    if self._session.state in (MediaState.PLAYING, MediaState.PAUSED):
                        self._session.state = MediaState.STOPPED # Assume stopped if not audible
                        self._session.touch()
                    return None
            else:
                # Tab no longer exists or is not found.
                if self._session.state in (MediaState.PLAYING, MediaState.PAUSED):
                    self._session.state = MediaState.STOPPED
                    self._session.touch()
                return None
        except Exception as exc:
            logger.warning("[YT] Error checking active status: %s", exc)
            return None

    def _resolve_tab_id(self) -> Optional[int]:
        if self._tab_id:
            return self._tab_id
        if self._session:
            return self._session.tab_id
        return None

    def _transport(self, action: str) -> MediaResult:
        conn = self._get_conn()
        tab_id = self._resolve_tab_id()
        if not conn or not tab_id:
            return MediaResult(success=False, error="No active YouTube session", player="youtube")
        try:
            result = asyncio.run(conn.execute_script(tab_id, action))
            if result.success:
                new_state = self._session.state if self._session else MediaState.IDLE
                if isinstance(result.message, dict):
                    msg = result.message
                    if msg.get("status") == "playing":
                        new_state = MediaState.PLAYING
                    elif msg.get("status") == "paused":
                        new_state = MediaState.PAUSED
                    elif msg.get("status") == "stopped":
                        new_state = MediaState.STOPPED
                    elif msg.get("status") == "blocked":
                        new_state = MediaState.PAUSED
                    elif msg.get("status") == "no media":
                        new_state = MediaState.IDLE

                    if self._session:
                        self._session.state = new_state
                        self._session.current_time = msg.get("currentTime", self._session.current_time)
                        self._session.duration = msg.get("duration", self._session.duration)
                        self._session.volume = msg.get("volume", self._session.volume)
                        self._session.muted = msg.get("muted", self._session.muted)
                        self._session.touch()
                    return MediaResult(success=True, message=msg.get("status", action.capitalize()), session=self._session, player="youtube")
                else:
                    # Fallback for non-JSON messages (e.g., youtube_bootstrap's "navigating")
                    if self._session:
                        if result.message == "playing":
                            new_state = MediaState.PLAYING
                        elif result.message == "paused":
                            new_state = MediaState.PAUSED
                        elif result.message == "stopped":
                            new_state = MediaState.STOPPED
                        elif result.message == "blocked":
                            new_state = MediaState.PAUSED
                        elif result.message == "no media":
                            new_state = MediaState.IDLE
                        self._session.state = new_state
                        self._session.touch()
                    return MediaResult(success=True, message=result.message or f"{action.capitalize()}d", session=self._session, player="youtube")
            return MediaResult(success=False, error=result.error, player="youtube")
        except Exception as exc:
            return MediaResult(success=False, error=str(exc), player="youtube")

    def _detect_type(self, query: str) -> MediaType:
        ql = query.lower()
        if any(kw in ql for kw in ("tutorial", "how to", "guide", "learn")):
            return MediaType.TUTORIAL
        if any(kw in ql for kw in ("trailer",)):
            return MediaType.MOVIE_TRAILER
        if any(kw in ql for kw in ("podcast", "episode")):
            return MediaType.PODCAST
        if any(kw in ql for kw in ("live", "streaming")):
            return MediaType.LIVESTREAM
        if any(kw in ql for kw in ("news", "update", "announcement")):
            return MediaType.NEWS
        if any(kw in ql for kw in ("highlight", "match", "game", "sport")):
            return MediaType.SPORTS
        return MediaType.MUSIC
