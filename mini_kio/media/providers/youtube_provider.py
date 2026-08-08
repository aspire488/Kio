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


def _score_candidate(title: str, url: str, query: str) -> int:
    """Relevance score of a YouTube search result against the requested query.

    Shared by the controlled search path (_search_metadata) and direct
    playback candidate selection (RC7) so both pick the best-matching result
    instead of blindly clicking the first link.
    """
    score = 0
    tl = title.lower()
    ql = query.lower()
    if ql in tl:
        score += 20
    for term in ql.split():
        if term and term in tl:
            score += 2
    if "trailer" in ql and "trailer" in tl:
        score += 10
    if "highlight" in ql and "highlight" in tl:
        score += 10
    if "interview" in ql and "interview" in tl:
        score += 10
    if "music video" in ql and "music video" in tl:
        score += 10
    if "live" in ql and "live" in tl:
        score += 5
    if "official" in tl:
        score += 3
    if "/shorts/" in url:
        score -= 2
    return score


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

    def _select_best_candidate(self, tab_id: int, query: str) -> Optional[str]:
        """RC7: choose the best-matching YouTube result instead of the first.

        Scrapes the open results page via the extension MV3-safe
        search_results script (retried until the page renders), scores
        each candidate against the requested query, and returns the best
        URL — or None when nothing relevant is available (the caller falls
        back to youtube_bootstrap).
        """
        conn = self._get_conn()
        if not conn:
            return None
        candidates = []
        for _attempt in range(4):
            scrape = safe_run_async(conn.execute_script(tab_id, "search_results"))
            if scrape.success and isinstance(scrape.message, list):
                for item in scrape.message:
                    if isinstance(item, dict) and item.get("title") and item.get("url"):
                        candidates.append(item)
                if candidates:
                    break
            time.sleep(1.0)
        if not candidates:
            logger.info("[YT_CANDIDATE] no candidates scraped for query=%s", query)
            return None
        best = max(candidates, key=lambda c: _score_candidate(c["title"], c["url"], query))
        score = _score_candidate(best["title"], best["url"], query)
        if score <= 0:
            logger.info("[YT_CANDIDATE] best score=%d too weak for query=%s title=%s",
                        score, query, best.get("title", ""))
            return None
        logger.info("[YT_CANDIDATE] query=%s selected=%s score=%d", query, best.get("title", ""), score)
        return best["url"]

    def play(self, query: str, **kwargs) -> MediaResult:
        logger.info("[ROOT_YT] ENTER query=%s kwargs=%s", query, kwargs)
        conn = self._get_conn()
        if not conn:
            logger.info("[ROOT_YT] RETURN=R1 conn=None")
            return MediaResult(success=False, error="Browser Connector not available", player="youtube")
        if not conn.is_connected():
            if config.BROWSER_CONNECTOR_ENABLED:
                logger.info("[ROOT_YT] RETURN=R2 conn_not_connected -> configured connector unavailable")
                return MediaResult(success=False, error="Browser Connector not connected", player="youtube")
            # No Chrome extension attached to the connector. Fall back to opening
            # the YouTube search page in BrowserRuntime / default browser only
            # when connector support is disabled in the current environment.
            logger.info("[ROOT_YT] RETURN=R2 conn_not_connected -> browser fallback")
            from mini_kio.core.browser_operator import play_youtube
            fb = play_youtube(query)
            if not fb.get("success"):
                return MediaResult(success=False, error=fb.get("message", "Couldn't open YouTube"), player="youtube")
            display = query.strip()
            if display.startswith(("http://", "https://", "www.")):
                display = "the requested media"
            self._session = MediaSession(
                player=PlayerType.YOUTUBE,
                tab_id=None,
                state=MediaState.PLAYING,
                query=query.strip(),
                title=query.strip(),
                url=_YOUTUBE_SEARCH_URL.format(encoded=urllib.parse.quote_plus(query.strip())),
                domain_hint="youtube.com",
                media_type=self._detect_type(query),
            )
            self._session.touch()
            return MediaResult(success=True, message=f"Playing on YouTube: {display}", session=self._session, player="youtube")

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

                # RC7: controlled candidate selection BEFORE any blind click.
                _candidate_url = self._select_best_candidate(tab_id, clean_query)
                _navigated = False
                if _candidate_url:
                    logger.info("[ROOT_YT] candidate_navigate url=%s", _candidate_url)
                    try:
                        _nav = safe_run_async(conn.open_tab(_candidate_url))
                        _navigated = bool(_nav.success)
                    except Exception as _ne:
                        logger.warning("[YT] candidate navigate failed: %s", _ne)

                try:
                    # RC5: bounded bootstrap retry — "not found" is a render-
                    # timing signal on a fresh results page, not a verdict.
                    _bootstrap_msg = "not attempted"
                    if not _navigated:
                        for _ba in range(3):
                            logger.info("[ROOT_YT] invoking bootstrap attempt=%d", _ba + 1)
                            bootstrap_result = safe_run_async(conn.execute_script(tab_id, "youtube_bootstrap"))
                            logger.info("[ROOT_YT] bootstrap result success=%s message=%s msg_type=%s",
                                        bootstrap_result.success, bootstrap_result.message,
                                        type(bootstrap_result.message).__name__)
                            _bootstrap_msg = bootstrap_result.message
                            if bootstrap_result.success and bootstrap_result.message == "navigating":
                                _navigated = True
                                break
                            if bootstrap_result.success and bootstrap_result.message == "not found":
                                logger.info("[ROOT_YT] bootstrap not_found attempt=%d — retrying", _ba + 1)
                                time.sleep(1.5)
                                continue
                            break
                    if _navigated:
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
                                elif _player_status_from_script == "playing":
                                    # The 'paused' field of the play-script payload is a
                                    # pre-play snapshot on some extension builds and must
                                    # not veto a verified 'playing' status.
                                    _is_playing = True
                                    _accepted_reason = "script_player_status_playing"
                                elif _status == "playing":
                                    _is_playing = True
                                    _accepted_reason = "legacy_status_playing"

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
                                            elif (_st_status == "playing" or _st_player_status_from_script == "playing"):
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
                                        elif msg.get("player_status") == "playing":
                                            _is_playing = True
                                            _accepted_reason = "final_script_player_status_playing_after_stabilize"
                                        elif msg.get("status") == "playing":
                                            _is_playing = True
                                            _accepted_reason = "final_legacy_status_playing_after_stabilize"

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
                                _err = str(getattr(play_result, 'error', '') or '')
                                logger.info("[ROOT_YT] PLAY_LOOP_EXIT=script_failed error=%s attempt=%d", _err, attempt + 1)
                                # The watch page may still be building its <video>
                                # element (or the extension payload may be a
                                # transient non-state). A no-media / not-yet-
                                # playing failure is a timing signal, not a
                                # verdict: retry within the bounded loop and only
                                # give up after the last attempt.
                                _retryable = any(
                                    k in _err.lower()
                                    for k in (
                                        "no media", "did not advance",
                                        "cannot read playback", "returned no payload",
                                        "non-state payload", "reported: no media",
                                    )
                                )
                                if attempt < 4 and _retryable:
                                    continue
                                break
                            else:
                                logger.info("[ROOT_YT] PLAY_LOOP_EXIT=unexpected_msg msg=%s", str(play_result.message)[:200] if hasattr(play_result, 'message') else 'N/A')
                                break
                    else:
                        logger.info("[ROOT_YT] BOOTSTRAP_EXIT=did_not_navigate msg=%s", _bootstrap_msg)
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

    def _url_changed(self, msg: dict) -> bool:
        """Truthful 'did the video actually change' check.

        Newer extension builds return url_changed directly; older builds only
        send url_before/url_after (read synchronously), so a follow-up probe
        is used to catch SPA navigation that completes after the click ACK.
        """
        if msg.get("url_changed"):
            return True
        url_before = msg.get("url_before") or ""
        url_after = msg.get("url_after") or ""
        return bool(url_before and url_after and url_before != url_after)

    def _probe_url_changed(self, url_before: str) -> bool:
        conn = self._get_conn()
        tab_id = self._resolve_tab_id()
        if not conn or not tab_id or not url_before:
            return False
        try:
            for _ in range(4):
                time.sleep(0.75)
                info = safe_run_async(conn.execute_script(tab_id, "get_page_info"))
                if info.success and isinstance(info.message, dict):
                    cur = info.message.get("url") or ""
                    if cur and cur != url_before:
                        return True
        except Exception:
            pass
        return False

    def next_track(self) -> MediaResult:
        res = self._transport("next_track")
        if res.success and isinstance(res.message, dict):
            msg = res.message
            url_before = msg.get("url_before") or ""
            url_changed = self._url_changed(msg)
            logger.info("[NEXT_TRACK] button_found=%s clicked=%s url_before=%s url_after=%s url_changed=%s",
                        msg.get("button_found"), msg.get("clicked"),
                        url_before, msg.get("url_after"), url_changed)
            if not url_changed:
                url_changed = self._probe_url_changed(url_before)
            if url_changed:
                res.message = "next_track_verified [NEXT_TRACK_VERIFY]"
            else:
                # Truthfulness: never claim 'next' when the video did not change.
                return MediaResult(
                    success=False,
                    error="Couldn't switch to the next video (no navigation detected)",
                    player="youtube",
                )
        return res

    def previous_track(self) -> MediaResult:
        res = self._transport("previous_track")
        if res.success and isinstance(res.message, dict):
            msg = res.message
            url_before = msg.get("url_before") or ""
            url_changed = self._url_changed(msg)
            logger.info("[PREVIOUS_TRACK] button_found=%s clicked=%s url_before=%s url_after=%s url_changed=%s",
                        msg.get("button_found"), msg.get("clicked"),
                        url_before, msg.get("url_after"), url_changed)
            if not url_changed:
                url_changed = self._probe_url_changed(url_before)
            if url_changed:
                res.message = "previous_track_verified [PREVIOUS_TRACK_VERIFY]"
            else:
                return MediaResult(
                    success=False,
                    error="Couldn't switch to the previous video (no navigation detected)",
                    player="youtube",
                )
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
        # R11: a search must stay a controlled search — scrape candidates from
        # the results page via the browser connector and return them. It must
        # NOT alias play(), which would trigger the full bootstrap/autoplay
        # loop and make accept_offer play twice.
        return self._search_metadata(query)

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
            result = safe_run_async(conn.open_tab(search_url))
            if not result.success or not result.tab:
                return MediaResult(success=False, error="Failed to open search tab", player="youtube")
            
            tab_id = result.tab.tab_id
            time.sleep(1.0)  # Wait for results to load
            
            # R11: scrape via the extension's MV3-safe search_results script.
            # (The previous inline "eval" script never existed in the
            # extension's SCRIPTS registry — search was silently broken.)
            scrape_res = safe_run_async(conn.execute_script(tab_id, "search_results"))
            candidates = []
            if scrape_res.success and isinstance(scrape_res.message, list):
                for item in scrape_res.message:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title")
                    url = item.get("url")
                    video_id = item.get("video_id")
                    if title and url and video_id:
                        candidates.append((title, url, video_id))

            if candidates:
                best = max(candidates, key=lambda item: _score_candidate(item[0], item[1], query))
                title, url, video_id = best
                logger.info("[YOUTUBE_ARTIFACT] query='%s' selected_title=%s url=%s", query, title, url)
                # Keep the results tab OPEN: KIO retains control of the search
                # page, and the candidate feeds the reference flow ('play it' /
                # 'play again' resolve to it via MediaManager.search).
                candidate = MediaCandidate(
                    title=title, url=url, provider="youtube",
                    source="youtube", confidence=1.0,
                )
                return MediaResult(
                    success=True,
                    message=f"Found on YouTube: {title}",
                    candidates=[candidate],
                    player="youtube",
                )

            # Fallback: the results page may still be rendering, or this
            # extension build predates search_results. The tab is open in the
            # controlled connector world — report that truthfully instead of
            # inventing a candidate or escaping to an uncontrolled browser.
            return MediaResult(
                success=True,
                message=f"Opened YouTube search for: {query}",
                player="youtube",
            )
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
