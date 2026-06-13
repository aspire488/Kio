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
        logger.info("[ROOT_YT] ENTER query=%s kwargs=%s", query, kwargs)
        conn = self._get_conn()
        if not conn:
            logger.info("[ROOT_YT] RETURN=R1 conn=None")
            return MediaResult(success=False, error="Browser Connector not available", player="youtube")
        if not conn.is_connected():
            logger.info("[ROOT_YT] RETURN=R2 conn_not_connected")
            return MediaResult(success=False, error="Browser Connector not available", player="youtube")

        clean_query = query.strip()
        if not clean_query:
            logger.info("[ROOT_YT] RETURN=R3 empty_query")
            return MediaResult(success=False, error="No query", player="youtube")

        encoded = urllib.parse.quote_plus(clean_query)
        url = _YOUTUBE_SEARCH_URL.format(encoded=encoded)
        logger.info("[ROOT_YT] search_url=%s", url)

        try:
            logger.info("[ROOT_YT] opening_tab url=%s", url)
            result = asyncio.run(conn.open_tab(url))
            logger.info("[ROOT_YT] open_tab result success=%s error=%s", result.success, getattr(result, 'error', 'none'))
            if not result.success:
                logger.info("[ROOT_YT] RETURN=R4 tab_open_failed error=%s", result.error)
                return MediaResult(success=False, error=f"Failed to open YouTube: {result.error}", player="youtube")

            tab_id = result.tab.tab_id if result.tab else None
            logger.info("[ROOT_YT] tab_id=%s", tab_id)

            playback_state = MediaState.IDLE
            if not tab_id:
                logger.info("[ROOT_YT] tab_id is None — no tab returned by connector")
            else:
                # Brief pause for the search results page to render
                time.sleep(0.5)

                # ── INSTRUMENTATION: URL before bootstrap ──────────────
                try:
                    _pre_bootstrap = asyncio.run(conn.execute_script(tab_id, "get_page_info"))
                    if _pre_bootstrap.success and isinstance(_pre_bootstrap.message, dict):
                        logger.info("[YT_INSTRUMENT] pre-bootstrap url=%s title=%s hasVideo=%s hasWatchFlexy=%s hasMoviePlayer=%s",
                                    _pre_bootstrap.message.get("url"), _pre_bootstrap.message.get("title"),
                                    _pre_bootstrap.message.get("hasVideo"), _pre_bootstrap.message.get("hasWatchFlexy"),
                                    _pre_bootstrap.message.get("hasMoviePlayer"))
                except Exception as _pbe:
                    logger.warning("[YT_INSTRUMENT] pre-bootstrap page info failed: %s", _pbe)
                # ────────────────────────────────────────────────────────

                try:
                    logger.info("[ROOT_YT] invoking bootstrap")
                    bootstrap_result = asyncio.run(conn.execute_script(tab_id, "youtube_bootstrap"))
                    logger.info("[ROOT_YT] bootstrap result success=%s message=%s msg_type=%s", 
                                bootstrap_result.success, bootstrap_result.message, 
                                type(bootstrap_result.message).__name__)
                    if bootstrap_result.success and bootstrap_result.message == "navigating":
                        # ── INSTRUMENTATION: URL immediately after bootstrap ──
                        try:
                            _post_bootstrap = asyncio.run(conn.execute_script(tab_id, "get_page_info"))
                            if _post_bootstrap.success and isinstance(_post_bootstrap.message, dict):
                                logger.info("[YT_INSTRUMENT] post-bootstrap url=%s title=%s hasVideo=%s hasWatchFlexy=%s hasMoviePlayer=%s",
                                            _post_bootstrap.message.get("url"), _post_bootstrap.message.get("title"),
                                            _post_bootstrap.message.get("hasVideo"), _post_bootstrap.message.get("hasWatchFlexy"),
                                            _post_bootstrap.message.get("hasMoviePlayer"))
                        except Exception as _pbe2:
                            logger.warning("[YT_INSTRUMENT] post-bootstrap page info failed: %s", _pbe2)
                        # ───────────────────────────────────────────────────────

                        # Poll for video element with shorter intervals since
                        # bootstrap already verified the URL transition.
                        for attempt in range(5):
                            time.sleep(1.0)

                            # ── INSTRUMENTATION: URL before each play attempt ──
                            try:
                                _pre_play = asyncio.run(conn.execute_script(tab_id, "get_page_info"))
                                if _pre_play.success and isinstance(_pre_play.message, dict):
                                    logger.info("[YT_INSTRUMENT] pre-play attempt=%d url=%s title=%s hasVideo=%s",
                                                attempt + 1,
                                                _pre_play.message.get("url"), _pre_play.message.get("title"),
                                                _pre_play.message.get("hasVideo"))
                            except Exception as _ppe:
                                logger.warning("[YT_INSTRUMENT] pre-play page info failed: %s", _ppe)
                            # ────────────────────────────────────────────────────

                            logger.info("[ROOT_YT] invoking play attempt=%d", attempt + 1)
                            play_result = asyncio.run(conn.execute_script(tab_id, "play"))
                            logger.info("[ROOT_YT] play_result success=%s msg_type=%s msg=%s", 
                                        play_result.success, 
                                        type(play_result.message).__name__ if hasattr(play_result, 'message') else 'N/A',
                                        str(play_result.message)[:200] if hasattr(play_result, 'message') else 'N/A')
                            if play_result.success and isinstance(play_result.message, dict):
                                msg = play_result.message
                                _status = msg.get("status")
                                logger.info("[ROOT_YT] play_loop status=%s attempt=%d", _status, attempt + 1)
                                if msg.get("status") == "playing":
                                    logger.info("[ROOT_YT] PLAY_LOOP_EXIT=playing")
                                    playback_state = MediaState.PLAYING
                                    if self._session:
                                        self._session.current_time = msg.get("currentTime")
                                        self._session.duration = msg.get("duration")
                                        self._session.volume = msg.get("volume")
                                        self._session.muted = msg.get("muted")
                                    break
                                elif msg.get("status") == "blocked":
                                    logger.info("[ROOT_YT] PLAY_LOOP_EXIT=blocked")
                                    playback_state = MediaState.READY
                                    break
                                elif msg.get("status") == "no media" and attempt < 4:
                                    logger.info("[ROOT_YT] PLAY_LOOP_EXIT=no_media_retry attempt=%d", attempt + 1)
                                    continue
                                elif msg.get("status") == "no media":
                                    logger.info("[ROOT_YT] PLAY_LOOP_EXIT=no_media_exhausted attempt=%d", attempt + 1)
                                    break
                                elif msg.get("status", "").startswith("error:"):
                                    logger.info("[ROOT_YT] PLAY_LOOP_EXIT=script_error status=%s", msg.get("status"))
                                    break
                                else:
                                    logger.info("[ROOT_YT] PLAY_LOOP_EXIT=unknown_status status=%s", msg.get("status"))
                                    break
                            elif play_result.success and isinstance(play_result.message, str) and play_result.message == "navigating":
                                logger.info("[ROOT_YT] PLAY_LOOP_EXIT=navigating_retry attempt=%d", attempt + 1)
                                continue
                            elif not play_result.success:
                                logger.info("[ROOT_YT] PLAY_LOOP_EXIT=script_failed error=%s", getattr(play_result, 'error', 'unknown'))
                                break
                            else:
                                logger.info("[ROOT_YT] PLAY_LOOP_EXIT=unexpected_msg msg=%s", str(play_result.message)[:200] if hasattr(play_result, 'message') else 'N/A')
                                break
                    else:
                        logger.info("[ROOT_YT] BOOTSTRAP_EXIT=did_not_navigate msg=%s", bootstrap_result.message)
                except Exception as exc:
                    logger.warning("[YT] bootstrap/play failed: %s", exc)

            # Extract artist/title from query for context resolution
            # e.g., "thunder by imagine dragons" → title="thunder", artist="imagine dragons"
            _artist = ""
            _title = clean_query
            if " by " in clean_query.lower():
                _parts = clean_query.rsplit(" by ", 1)
                _title = _parts[0].strip()
                _artist = _parts[1].strip()

            self._tab_id = tab_id
            self._session = MediaSession(
                player=PlayerType.YOUTUBE,
                tab_id=tab_id,
                state=playback_state,
                query=clean_query,
                title=_title,
                artist=_artist,
                url=url,
                domain_hint="youtube.com",
                media_type=self._detect_type(clean_query),
            )
            self._session.touch()

            message = (
                f"Playing on YouTube: {clean_query}" if playback_state == MediaState.PLAYING else
                "Video ready on YouTube." if playback_state == MediaState.READY else
                f"Opened on YouTube: {clean_query}"
            )
            return MediaResult(
                success=playback_state in (MediaState.PLAYING, MediaState.READY, MediaState.PAUSED),
                message=message,
                session=self._session,
                player="youtube",
            )
            logger.info("[ROOT_YT] FINAL_RETURN playback_state=%s success=%s has_session=%s message=%s", 
                        playback_state.value if isinstance(playback_state, MediaState) else str(playback_state),
                        playback_state in (MediaState.PLAYING, MediaState.READY, MediaState.PAUSED),
                        self._session is not None,
                        message)
            return MediaResult(
                success=playback_state in (MediaState.PLAYING, MediaState.READY, MediaState.PAUSED),
                message=message,
                session=self._session,
                player="youtube",
            )
        except Exception as exc:
            logger.info("[ROOT_YT] RETURN=R5 outer_exception exc=%s", exc)
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
                        new_state = MediaState.READY
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
                            new_state = MediaState.READY
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
