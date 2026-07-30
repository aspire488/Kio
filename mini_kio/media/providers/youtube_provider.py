from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from typing import Optional

from mini_kio.browser_connector.connector import Connector
from mini_kio.core import config
from mini_kio.core.async_utils import safe_run_async
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
            result = safe_run_async(conn.open_tab(url))
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
                    _pre_bootstrap = safe_run_async(conn.execute_script(tab_id, "get_page_info"))
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
                    bootstrap_result = safe_run_async(conn.execute_script(tab_id, "youtube_bootstrap"))
                    logger.info("[ROOT_YT] bootstrap result success=%s message=%s msg_type=%s", 
                                bootstrap_result.success, bootstrap_result.message, 
                                type(bootstrap_result.message).__name__)
                    if bootstrap_result.success and bootstrap_result.message == "navigating":
                        # ── INSTRUMENTATION: URL immediately after bootstrap ──
                        try:
                            _post_bootstrap = safe_run_async(conn.execute_script(tab_id, "get_page_info"))
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
                                _pre_play = safe_run_async(conn.execute_script(tab_id, "get_page_info"))
                                if _pre_play.success and isinstance(_pre_play.message, dict):
                                    logger.info("[YT_INSTRUMENT] pre-play attempt=%d url=%s title=%s hasVideo=%s",
                                                attempt + 1,
                                                _pre_play.message.get("url"), _pre_play.message.get("title"),
                                                _pre_play.message.get("hasVideo"))
                            except Exception as _ppe:
                                logger.warning("[YT_INSTRUMENT] pre-play page info failed: %s", _ppe)
                            # ────────────────────────────────────────────────────

                            logger.info("[ROOT_YT] invoking play attempt=%d", attempt + 1)
                            play_result = safe_run_async(conn.execute_script(tab_id, "play"))
                            logger.info("[ROOT_YT] play_result success=%s msg_type=%s msg=%s", 
                                        play_result.success, 
                                        type(play_result.message).__name__ if hasattr(play_result, 'message') else 'N/A',
                                        str(play_result.message)[:200] if hasattr(play_result, 'message') else 'N/A')
                            if play_result.success and isinstance(play_result.message, dict):
                                msg = play_result.message
                                _status = msg.get("status")
                                _paused = msg.get("paused", True)
                                _rs = msg.get("readyState", -1)
                                _player_status_from_script = msg.get("player_status")
                                logger.info("[PLAY_VERIFY] status=%s paused=%s readyState=%s player_status_from_script=%s", _status, _paused, _rs, _player_status_from_script)

                                _player_state_result = safe_run_async(conn.execute_script(tab_id, "get_player_state"))
                                _player_state = -1
                                if _player_state_result.success and isinstance(_player_state_result.message, dict):
                                    _player_state = _player_state_result.message.get("playerState", -1)
                                logger.info("[PLAY_VERIFY] actual_player_state=%s [PLAYER_STATE_DEBUG]", _player_state)

                                # Determine if playing based on multiple sources
                                _accepted_reason = "none"
                                _is_playing = False

                                if _player_state == 1: # YouTube Iframe API state for playing
                                    _is_playing = True
                                    _accepted_reason = "player_state_1"
                                elif _player_status_from_script == "playing" and not _paused:
                                    _is_playing = True
                                    _accepted_reason = "script_player_status_playing_and_not_paused"
                                elif _status == "playing" and not _paused:
                                    _is_playing = True
                                    _accepted_reason = "legacy_status_playing_and_not_paused"

                                # Stabilization: if playing but paused=true, poll for transition to paused=false
                                if (_status == "playing" or _player_status_from_script == "playing") and _paused and not _is_playing:
                                    logger.info("[PLAY_VERIFY] playing+paused=true — stabilizing attempt=%d", attempt + 1)
                                    _stabilized = False
                                    _current_time_before_stabilization = msg.get("currentTime")
                                    for _st in range(5):
                                        time.sleep(0.25)
                                        _st_result = safe_run_async(conn.execute_script(tab_id, "play"))
                                        if _st_result.success and isinstance(_st_result.message, dict):
                                            _st_msg = _st_result.message
                                            _st_player_state_result = safe_run_async(conn.execute_script(tab_id, "get_player_state"))
                                            _st_player_state = -1
                                            if _st_player_state_result.success and isinstance(_st_player_state_result.message, dict):
                                                _st_player_state = _st_player_state_result.message.get("playerState", -1)

                                            _st_status = _st_msg.get("status")
                                            _st_paused = _st_msg.get("paused", True)
                                            _st_player_status_from_script = _st_msg.get("player_status")
                                            _st_current_time = _st_msg.get("currentTime")

                                            logger.info("[PLAY_VERIFY] stabilize_poll=%d status=%s paused=%s player_status_from_script=%s actual_player_state=%s currentTime=%s", 
                                                        _st + 1, _st_status, _st_paused, _st_player_status_from_script, _st_player_state, _st_current_time)

                                            if _st_player_state == 1:
                                                msg = _st_msg # Update message with latest state
                                                _is_playing = True
                                                _accepted_reason = "stabilize_player_state_1"
                                                _stabilized = True
                                                logger.info("[PLAY_VERIFY] stabilized=true via player_state")
                                                break
                                            elif (_st_status == "playing" or _st_player_status_from_script == "playing") and not _st_paused:
                                                msg = _st_msg # Update message with latest state
                                                _is_playing = True
                                                _accepted_reason = "stabilize_script_status_playing_and_not_paused"
                                                _stabilized = True
                                                logger.info("[PLAY_VERIFY] stabilized=true via script status")
                                                break
                                            elif _st_current_time is not None and _current_time_before_stabilization is not None and _st_current_time > _current_time_before_stabilization:
                                                msg = _st_msg # Update message with latest state
                                                _is_playing = True
                                                _accepted_reason = "stabilize_current_time_progression"
                                                _stabilized = True
                                                logger.info("[PLAY_VERIFY] stabilized=true via currentTime progression")
                                                break

                                    if not _stabilized:
                                        logger.info("[PLAY_VERIFY] stabilize_timeout — accepting current state (not fully stable, checking final status)")
                                    # After stabilization loop, re-evaluate _is_playing based on the latest 'msg'
                                    if not _is_playing:
                                        if _player_state == 1:
                                            _is_playing = True
                                            _accepted_reason = "final_player_state_1_after_stabilize"
                                        elif msg.get("player_status") == "playing" and not msg.get("paused", True):
                                            _is_playing = True
                                            _accepted_reason = "final_script_player_status_playing_and_not_paused_after_stabilize"
                                        elif msg.get("status") == "playing" and not msg.get("paused", True):
                                            _is_playing = True
                                            _accepted_reason = "final_legacy_status_playing_and_not_paused_after_stabilize"

                                logger.info("[PLAY_VERIFY_FINAL] status=%s player_status_from_script=%s paused=%s actual_player_state=%s accepted_reason=%s", 
                                            msg.get("status"), msg.get("player_status"), msg.get("paused", True), _player_state, _accepted_reason)

                                if _is_playing:
                                    logger.info("[ROOT_YT] PLAY_LOOP_EXIT=playing (accepted_reason=%s)", _accepted_reason)
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

            display_query = clean_query
            if clean_query.startswith(("http://", "https://", "www.")):
                display_query = "the requested media"
            message = (
                f"Playing on YouTube: {display_query}" if playback_state == MediaState.PLAYING else
                "Video ready on YouTube." if playback_state == MediaState.READY else
                f"Opened on YouTube: {display_query}"
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
        res = self._transport("next_track")
        if res.success and isinstance(res.message, dict):
            msg = res.message
            logger.info("[NEXT_TRACK] button_found=%s clicked=%s fallback_used=%s url_before=%s url_after=%s url_changed=%s",
                        msg.get("button_found"), msg.get("clicked"), not msg.get("button_found"), 
                        msg.get("url_before"), msg.get("url_after"), msg.get("url_changed"))
            
            if msg.get("clicked") and msg.get("url_changed"):
                res.message = f"next_track_verified [NEXT_TRACK_VERIFY]"
        return res

    def previous_track(self) -> MediaResult:
        res = self._transport("previous_track")
        if res.success and isinstance(res.message, dict):
            msg = res.message
            logger.info("[PREVIOUS_TRACK] button_found=%s clicked=%s fallback_used=%s url_before=%s url_after=%s url_changed=%s",
                        msg.get("button_found"), msg.get("clicked"), not msg.get("button_found"),
                        msg.get("url_before"), msg.get("url_after"), msg.get("url_changed"))
            
            if msg.get("clicked") and msg.get("url_changed"):
                res.message = f"previous_track_verified [PREVIOUS_TRACK_VERIFY]"
        return res

    def seek(self, seconds: int) -> MediaResult:
        conn = self._get_conn()
        tab_id = self._resolve_tab_id()
        if not conn or not tab_id:
            return MediaResult(success=False, error="No active YouTube session", player="youtube")
        # Seek via script injection using currentTime
        script = "seek_forward" if seconds >= 0 else "seek_backward"
        try:
            result = safe_run_async(conn.execute_script(tab_id, script))
            if result.success:
                return MediaResult(success=True, message=f"Seeked {abs(seconds)}s", player="youtube")
            return MediaResult(success=False, error=result.error, player="youtube")
        except Exception as exc:
            return MediaResult(success=False, error=str(exc), player="youtube")

    def volume(self, level: Optional[float] = None, direction: Optional[str] = None) -> MediaResult:
        if level is not None:
            conn = self._get_conn()
            tab_id = self._resolve_tab_id()
            if not conn or not tab_id:
                return MediaResult(success=False, error="No active YouTube session", player="youtube")
            try:
                result = safe_run_async(conn.execute_script(tab_id, "set_volume", args=[level]))
                if result.success:
                    if self._session and isinstance(result.message, dict):
                        actual_vol = result.message.get("volume")
                        self._session.volume = actual_vol if actual_vol is not None else level
                        self._session.touch()
                        
                        # Rule: Volume Reliability - Verify video.volume AND player.getVolume()
                        # Our script returns the unified 'volume' property which we trust if matched.
                        if actual_vol is not None and abs(actual_vol - level) < 0.01:
                            return MediaResult(success=True, message=f"volume_verified to {int(level*100)}% [VOLUME_VERIFY]", session=self._session, player="youtube")
                        else:
                            logger.warning("[VOLUME_RELIABILITY] mismatch requested=%s actual=%s", level, actual_vol)
                    
                    return MediaResult(success=True, message=f"Volume set to {int(level*100)}%", session=self._session, player="youtube")
                return MediaResult(success=False, error=result.error, player="youtube")
            except Exception as exc:
                return MediaResult(success=False, error=str(exc), player="youtube")

        return self._transport("volume_up" if direction != "down" else "volume_down")

    def search(self, query: str) -> MediaResult:
        return self.play(query)

    def search_trailer(self, query: str) -> MediaResult:
        return self._search_metadata(f"{query} trailer")

    def search_highlights(self, query: str) -> MediaResult:
        return self._search_metadata(f"{query} highlights")

    def search_best_scenes(self, query: str) -> MediaResult:
        return self._search_metadata(f"{query} best scenes")

    def search_behind_the_scenes(self, query: str) -> MediaResult:
        return self._search_metadata(f"{query} behind the scenes")
    
    def _search_metadata(self, query: str) -> MediaResult:
        """Search YouTube for metadata and return a MediaResult with the best candidate."""
        logger.info("[YOUTUBE_METADATA_SEARCH] query=%s", query)
        
        conn = self._get_conn()
        if not conn or not conn.is_connected():
            logger.warning("[YOUTUBE_METADATA_SEARCH] Browser connector not available")
            return MediaResult(success=False, error="Connector unavailable", player="youtube")

        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"
        
        try:
            # We use open_tab + script execution to scrape the first result
            result = safe_run_async(conn.open_tab(search_url))
            if not result.success or not result.tab:
                return MediaResult(success=False, error="Failed to open search tab", player="youtube")
            
            tab_id = result.tab.tab_id
            time.sleep(1.0) # Wait for results to load
            
            # Scrape the first video result
            # We'll use a script to extract the first video ID and title
            scrape_script = """
            (function() {
                const video = document.querySelector('ytd-video-renderer a#video-title');
                if (video) {
                    const url = video.href;
                    const videoId = new URL(url).searchParams.get('v');
                    return { title: video.title, video_id: videoId, url: url };
                }
                return null;
            })()
            """
            scrape_res = safe_run_async(conn.execute_script(tab_id, "eval", args=[scrape_script]))
            
            if scrape_res.success and isinstance(scrape_res.message, dict):
                data = scrape_res.message
                video_id = data.get("video_id")
                url = data.get("url")
                title = data.get("title")
                
                logger.info("[YOUTUBE_ARTIFACT] query='%s' video_id=%s url=%s", query, video_id, url)
                
                candidate = MediaCandidate(
                    title=title or query,
                    url=url,
                    provider="youtube",
                    source="youtube"
                )
                
                # Close the search tab
                safe_run_async(conn.close_tab(tab_id))
                
                return MediaResult(
                    success=True, 
                    message=f"Found artifact: {title}", 
                    candidates=[candidate],
                    url=url,
                    player="youtube"
                )
            
            safe_run_async(conn.close_tab(tab_id))
            return MediaResult(success=False, error="No video found in search results", player="youtube")
            
        except Exception as e:
            logger.error("[YOUTUBE_METADATA_SEARCH_ERROR] error=%s", e)
            return MediaResult(success=False, error=str(e), player="youtube")

    def close(self) -> MediaResult:
        conn = self._get_conn()
        tab_id = self._resolve_tab_id()
        if conn and tab_id:
            safe_run_async(conn.close_tab(tab_id))
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
            tab_list_result = safe_run_async(conn.list_tabs())
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
            result = safe_run_async(conn.execute_script(tab_id, action))
            if result.success:
                new_state = self._session.state if self._session else MediaState.IDLE
                if isinstance(result.message, dict):
                    msg = result.message
                    # MEDIA_AUDIO instrumentation for play/resume
                    if action in ("play", "resume"):
                        _abm = msg.get("_audio_before_muted")
                        _abv = msg.get("_audio_before_volume")
                        _ar = msg.get("_audio_restored")
                        logger.info("[MEDIA_AUDIO] action=%s before_muted=%s before_volume=%s after_muted=%s after_volume=%s audio_restored=%s",
                                    action, _abm, _abv, msg.get("muted"), msg.get("volume"), _ar)
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
                        self._session.position_s = msg.get("currentTime", self._session.position_s)
                        self._session.duration_s = msg.get("duration", self._session.duration_s)
                        self._session.volume = msg.get("volume", self._session.volume)
                        self._session.touch()
                    
                    # Return the full dict as message to allow rich result inspection
                    return MediaResult(success=True, message=msg, session=self._session, player="youtube")
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
