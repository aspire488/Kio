from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from mini_kio.browser_connector.connector import Connector
from mini_kio.core import config
from mini_kio.core.async_utils import safe_run_async
from mini_kio.media.media_session import MediaResult, MediaSession, MediaCandidate
from mini_kio.media.media_state import MediaState, PlayerType, MediaType
from mini_kio.media.providers import MediaProvider

logger = logging.getLogger(__name__)

_PLAYBACK_DESKTOP = "desktop"
_PLAYBACK_WEB = "web"
_PLAYBACK_SEARCH = "search"
_PLAYBACK_NONE = "none"

_SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SPOTIFY_API_BASE = "https://api.spotify.com/v1"
_SPOTIFY_TOKEN_REFRESH_S = 300  # refresh 5 min early


@dataclass
class SpotifyTarget:
    """A resolved Spotify entity ready for playback."""
    uri: str
    title: str = ""
    artist: str = ""
    album: str = ""
    target_type: str = "track"


def _check_spotify_process() -> bool:
    """Return True if a Spotify Desktop process is currently running."""
    try:
        import subprocess
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Spotify.exe", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        return "Spotify.exe" in result.stdout
    except Exception:
        return False


class SpotifyProvider(MediaProvider):
    def __init__(self, conn: Optional[Connector] = None):
        self._conn = conn
        self._session: Optional[MediaSession] = None
        self._tab_id: Optional[int] = None
        self._launched = False
        self._playback_medium: str = _PLAYBACK_NONE
        # Spotify API token cache
        self._spotify_token: Optional[str] = None
        self._spotify_token_expiry: float = 0.0

    @property
    def name(self) -> str:
        return "spotify"

    def _get_conn(self) -> Optional[Connector]:
        if self._conn is not None:
            return self._conn
        if config.BROWSER_CONNECTOR_ENABLED:
            from mini_kio.core.command_router import _get_connector
            self._conn = _get_connector()
        return self._conn

    # ── Public API ───────────────────────────────────────────────────

    def play(self, query: str, **kwargs) -> MediaResult:
        clean_query = query.strip()
        if not clean_query:
            return MediaResult(success=False, error="No query", player="spotify")

        lp = clean_query.lower()
        explicit = bool(kwargs.get("platform"))

        # Phase 1: Resolve query to a playable Spotify entity via Web API
        target = self._resolve_query(clean_query)
        if target:
            return self._launch_target(target, clean_query)

        # Phase 2: Known auto-play URIs (playlist keywords)
        result = self._try_desktop_playlist(lp, clean_query)
        if result.success:
            return result

        # Phase 3: Desktop resume (if previously launched a URI)
        if self._launched:
            result = self._try_desktop_play(lp, clean_query)
            if result.success:
                return result

        # Phase 4: Desktop search fallback (opens Spotify Desktop directly)
        result = self._try_desktop_search(lp, clean_query)
        if result.success:
            return result

        # Phase 5: Web search via browser connector
        result = self._try_web(clean_query)
        if result.success:
            return result

        # Phase 6: Search fallback in default browser
        return self._search_fallback(clean_query)

    def pause(self) -> MediaResult:
        if self._playback_medium != _PLAYBACK_DESKTOP:
            return MediaResult(success=False, error="No active Spotify session to pause", player="spotify")
        if not _check_spotify_process():
            return MediaResult(success=False, error="Spotify Desktop is not running", player="spotify")
        return self._transport_uri("pause")

    def resume(self) -> MediaResult:
        if self._playback_medium != _PLAYBACK_DESKTOP:
            return MediaResult(success=False, error="No active Spotify session to resume", player="spotify")
        if not _check_spotify_process():
            return MediaResult(success=False, error="Spotify Desktop is not running", player="spotify")
        return self._transport_uri("play")

    def stop(self) -> MediaResult:
        if self._playback_medium != _PLAYBACK_DESKTOP:
            return MediaResult(success=False, error="No active Spotify session to stop", player="spotify")
        return self._transport_uri("pause")

    def next_track(self) -> MediaResult:
        if self._playback_medium != _PLAYBACK_DESKTOP:
            return MediaResult(success=False, error="No active Spotify session for next track", player="spotify")
        return self._transport_uri("next")

    def previous_track(self) -> MediaResult:
        if self._playback_medium != _PLAYBACK_DESKTOP:
            return MediaResult(success=False, error="No active Spotify session for previous track", player="spotify")
        return self._transport_uri("previous")

    def seek(self, seconds: int) -> MediaResult:
        return MediaResult(success=False, error="Seek not supported on Spotify", player="spotify")

    def volume(self, level: Optional[float] = None, direction: Optional[str] = None) -> MediaResult:
        return MediaResult(success=False, error="Volume control not supported on Spotify", player="spotify")

    def search(self, query: str) -> MediaResult:
        return self.play(query)

    def close(self) -> MediaResult:
        self._session = None
        self._tab_id = None
        self._launched = False
        self._playback_medium = _PLAYBACK_NONE
        return MediaResult(success=True, message="Spotify session closed", player="spotify")

    def check_active(self) -> Optional[MediaSession]:
        if self._session is None:
            return None

        # If playback medium is not desktop, we can't control it in a granular way
        # so we assume it's not "active" for KIO's control purposes.
        if self._playback_medium == _PLAYBACK_WEB: # Web search page, not actively playing controllable media
            self._session.state = MediaState.IDLE
            self._session.touch()
            return None
        if self._playback_medium == _PLAYBACK_SEARCH: # Desktop search page, not actively playing controllable media
            self._session.state = MediaState.IDLE
            self._session.touch()
            return None
        if self._playback_medium == _PLAYBACK_NONE:
            return None

        # For desktop playback, verify if Spotify process is still running
        if self._playback_medium == _PLAYBACK_DESKTOP:
            if not _check_spotify_process():
                # If Spotify was supposed to be playing but the process is gone
                if self._session.state in (MediaState.PLAYING, MediaState.PAUSED):
                    self._session.state = MediaState.STOPPED
                    self._session.touch()
                return None # No active process, so no active session

            # If process is running, and KIO believes it's playing/paused, it is considered active
            if self._session.state in (MediaState.PLAYING, MediaState.PAUSED):
                self._session.touch()
                return self._session
            else:
                # Process is running, but KIO's internal state is IDLE/STOPPED.
                # This could happen if Spotify was launched but nothing played,
                # or if it was stopped externally.
                return None

        return None # Should not be reached, but for safety

    # ── Resolution (Spotify Web API) ─────────────────────────────────

    def _get_spotify_token(self) -> Optional[str]:
        """Obtain a client-credentials access token from Spotify.

        Uses stdlib only (urllib, base64, json).  The token is cached
        per-provider instance and refreshed automatically.
        """
        if not config.SPOTIFY_API_ENABLED:
            logger.warning("[SPOTIFY] token acquisition skipped: SPOTIFY_API_ENABLED=False")
            return None
        now = time.time()
        if self._spotify_token and now < self._spotify_token_expiry - _SPOTIFY_TOKEN_REFRESH_S:
            remaining = int(self._spotify_token_expiry - now)
            logger.info("[SPOTIFY] using cached token (expires in %ds)", remaining)
            return self._spotify_token

        credentials = f"{config.SPOTIFY_CLIENT_ID}:{config.SPOTIFY_CLIENT_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()

        data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        req = urllib.request.Request(
            _SPOTIFY_TOKEN_URL,
            data=data,
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        logger.info("[SPOTIFY] requesting token from %s auth_prefix=%s...", _SPOTIFY_TOKEN_URL, encoded[:20])
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                body_bytes = resp.read()
                logger.info("[SPOTIFY] token response status=%d length=%d", status, len(body_bytes))
                body = json.loads(body_bytes.decode())
                self._spotify_token = body["access_token"]
                self._spotify_token_expiry = now + body.get("expires_in", 3600)
                logger.info(
                    "[SPOTIFY] API token acquired (expires in %ds)",
                    body.get("expires_in", 3600),
                )
                return self._spotify_token
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode(errors="replace")[:500]
            except Exception:
                pass
            logger.warning(
                "[SPOTIFY] token acquisition failed: status=%s url=%s body=%s",
                exc.code, _SPOTIFY_TOKEN_URL, detail,
            )
            return None
        except Exception as exc:
            logger.warning("[SPOTIFY] token acquisition failed: %s: %s", type(exc).__name__, exc)
            return None

    def _api_search(self, query: str, search_type: str = "track", limit: int = 1) -> Optional[dict]:
        """Call the Spotify Web API search endpoint.

        Returns the first item from the typed results, or None on
        failure / empty results.  On HTTP error, logs the response body
        for diagnostics and retries once with a fresh token.
        403 errors are NOT retried — they indicate persistent app-level
        authorization issues, not expired tokens.
        """
        for attempt in range(2):
            token = self._get_spotify_token()
            if not token:
                return None

            params = urllib.parse.urlencode({
                "q": query,
                "type": search_type,
                "limit": str(limit),
            })
            url = f"{_SPOTIFY_API_BASE}/search?{params}"
            has_auth = bool(token)
            logger.info(
                "[SPOTIFY] search attempt %d/2: url=%s type=%s has_auth=%s",
                attempt + 1, url, search_type, has_auth,
            )
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "Kio/1.0",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = resp.status
                    resp_headers = dict(resp.headers)
                    body_bytes = resp.read()
                    logger.info(
                        "[SPOTIFY] search response status=%d length=%d headers=%s",
                        status, len(body_bytes), str(resp_headers)[:300],
                    )
                    body = json.loads(body_bytes.decode())
                    items_key = f"{search_type}s"
                    items = body.get(items_key, {}).get("items", [])
                    if items:
                        return items[0]
                    logger.warning(
                        "[SPOTIFY] search returned 0 items for type=%s query=%s",
                        search_type, query,
                    )
            except urllib.error.HTTPError as exc:
                detail = ""
                err_headers = {}
                try:
                    detail = exc.read().decode(errors="replace")[:500]
                    err_headers = dict(exc.headers)
                except Exception:
                    pass
                logger.warning(
                    "[SPOTIFY] search API failed (attempt %d/2): status=%s url=%s headers=%s body=%s",
                    attempt + 1, exc.code, url, str(err_headers)[:300], detail,
                )
                if exc.code == 403:
                    logger.warning("[SPOTIFY] 403 on search — API access not authorized for this app. Skipping retry.")
                    return None
                if attempt == 0:
                    self._spotify_token = None
                    self._spotify_token_expiry = 0.0
                    continue
            except Exception as exc:
                logger.warning("[SPOTIFY] search API failed: %s: %s", type(exc).__name__, exc)
            return None
        return None

    def _resolve_query(self, query: str) -> Optional[SpotifyTarget]:
        """Resolve a free-text query to a playable Spotify entity.

        Tries track → album → playlist in order of likelihood.
        Returns None when no playable entity is found.
        """
        # Already a Spotify URI — use directly.
        if query.startswith("spotify:"):
            parts = query.split(":")
            if len(parts) >= 3 and parts[1] in ("track", "album", "playlist"):
                return SpotifyTarget(uri=query, title=query, target_type=parts[1])

        # 1. Track
        item = self._api_search(query, "track")
        if item:
            artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
            album = item.get("album", {}).get("name", "")
            return SpotifyTarget(
                uri=item["uri"],
                title=item.get("name", query),
                artist=artists,
                album=album,
                target_type="track",
            )

        # 2. Album
        item = self._api_search(query, "album")
        if item:
            artists = ", ".join(a.get("name", "") for a in item.get("artists", []))
            return SpotifyTarget(
                uri=item["uri"],
                title=item.get("name", query),
                artist=artists,
                target_type="album",
            )

        # 3. Playlist
        item = self._api_search(query, "playlist")
        if item:
            owner = item.get("owner", {}).get("display_name", "")
            return SpotifyTarget(
                uri=item["uri"],
                title=item.get("name", query),
                artist=owner,
                target_type="playlist",
            )

        logger.info("[SPOTIFY] API resolution failed for query '%s'. Falling back to other methods.", query)
        return None

    # ─── Playback launch ────────────────────────────────────────────

    def _launch_target(self, target: SpotifyTarget, original_query: str) -> MediaResult:
        """Launch a resolved Spotify entity URI for actual playback."""
        launched = self._launch_desktop_uri(target.uri)
        playback_state = MediaState.PLAYING if launched else MediaState.IDLE
        self._set_session(
            query=original_query,
            url=target.uri,
            state=playback_state,
            title=target.title,
            artist=target.artist,
            album=target.album,
        )
        self._playback_medium = _PLAYBACK_DESKTOP if launched else _PLAYBACK_NONE
        label = f"{target.title}"
        if target.artist:
            label += f" — {target.artist}"
        message = (
            f"Playing {label} on Spotify." if launched else
            f"Failed to launch Spotify for {label}."
        )
        return MediaResult(
            success=launched,
            message=message,
            session=self._session,
            player="spotify",
        )

    # ── Desktop path — playlist keywords that auto-play ──────────────

    def _try_desktop_playlist(self, lp: str, query: str) -> MediaResult:
        """Match known playlist keywords to auto-play Spotify URIs."""
        playlist_map = {
            "liked songs": "spotify:collection:tracks",
            "daily mix": "spotify:playlist:37i9dQZF1E36T3l3E41o2o",
            "workout playlist": "spotify:playlist:37i9dQZF1DX76Wlfdnj7AP",
            "chill playlist": "spotify:playlist:37i9dQZF1DX3Vl51vsCNQP",
            "discover weekly": "spotify:playlist:37i9dQZF1E37uC5D6WgK1k",
            "release radar": "spotify:playlist:37i9dQZF1E38UcdNl4N5Kp",
        }
        for key, uri in playlist_map.items():
            if key in lp:
                launched = self._launch_desktop_uri(uri)
                playback_state = MediaState.PLAYING if launched else MediaState.IDLE
                self._set_session(query, uri, state=playback_state)
                self._playback_medium = _PLAYBACK_DESKTOP if launched else _PLAYBACK_NONE
                return MediaResult(
                    success=launched,
                    message=f"Playing {query} on Spotify." if launched else f"Failed to launch Spotify for {query}.",
                    session=self._session,
                    player="spotify",
                )
        return MediaResult(success=False, player="spotify")

    def _try_desktop_play(self, lp: str, query: str) -> MediaResult:
        """Resume playback on Desktop (called only when _launched is True)."""
        play_uri = "spotify:play"
        try:
            launched = self._launch_desktop_uri(play_uri)
            if not launched:
                return MediaResult(success=False, error="Spotify process not detected", player="spotify")
            logger.info("[SPOTIFY] desktop play URI: %s", play_uri)
            self._set_session(query, play_uri, state=MediaState.PLAYING)
            self._playback_medium = _PLAYBACK_DESKTOP
            return MediaResult(
                success=True,
                message="Playing on Spotify.",
                session=self._session,
                player="spotify",
            )
        except Exception as exc:
            logger.warning("[SPOTIFY] desktop play failed: %s", exc)
            return MediaResult(success=False, player="spotify")

    def _try_desktop_search(self, lp: str, query: str) -> MediaResult:
        """Open a search page in Spotify Desktop (search only)."""
        search_uri = f"spotify:search:{urllib.parse.quote(query)}"
        launched = self._launch_desktop_uri(search_uri)
        self._set_session(query, search_uri, state=MediaState.IDLE)
        self._playback_medium = _PLAYBACK_SEARCH if launched else _PLAYBACK_NONE
        return MediaResult(
            success=launched,
            message=f"Opened Spotify search: {query}" if launched else "Spotify Desktop not available for search.",
            session=self._session,
            player="spotify",
        )

    # ── Web path ─────────────────────────────────────────────────────

    def _try_web(self, query: str) -> MediaResult:
        """Open Spotify search via the browser connector."""
        conn = self._get_conn()
        if not conn or not conn.is_connected():
            return MediaResult(success=False, player="spotify")

        web_url = (
            f"https://open.spotify.com/search/{urllib.parse.quote_plus(query)}"
        )
        try:
            result = safe_run_async(conn.open_tab(web_url))
            if result.success:
                tab_id = result.tab.tab_id if result.tab else None
                logger.info("[SPOTIFY] opened web tab_id=%s", tab_id)
                self._tab_id = tab_id
                self._set_session(query, web_url, state=MediaState.IDLE)
                self._playback_medium = _PLAYBACK_WEB
                return MediaResult(
                    success=True,
                    message=f"Opened Spotify Web search: {query}",
                    session=self._session,
                    player="spotify",
                )
        except Exception as exc:
            logger.warning("[SPOTIFY] web fallback error: %s", exc)
        return MediaResult(success=False, player="spotify")

    # ── Search fallback ──────────────────────────────────────────────

    def _search_fallback(self, query: str) -> MediaResult:
        """Open Spotify search in the default web browser."""
        import webbrowser
        web_url = (
            f"https://open.spotify.com/search/{urllib.parse.quote_plus(query)}"
        )
        webbrowser.open(web_url)
        self._set_session(query, web_url, state=MediaState.IDLE)
        self._playback_medium = _PLAYBACK_SEARCH
        return MediaResult(
            success=True,
            message=f"Opened Spotify search: {query}",
            session=self._session,
            player="spotify",
        )

    # ── Helpers ──────────────────────────────────────────────────────

    def _launch_desktop_uri(self, uri: str) -> bool:
        """Launch a Spotify URI via the Desktop app.

        Returns True if the launch command succeeded AND a Spotify
        process was detected within the verification window.
        """
        try:
            import subprocess
            import sys
            if sys.platform == "win32":
                proc = subprocess.Popen(["cmd", "/c", "start", uri], shell=True)
            else:
                proc = subprocess.Popen(["xdg-open", uri])
            time.sleep(1) # Give Spotify a moment to launch
            try:
                ret = proc.wait(timeout=2)
                if ret != 0:
                    logger.warning("[SPOTIFY] desktop URI process exited with code %d", ret)
                    return False
            except subprocess.TimeoutExpired:
                pass
            # Verify Spotify process appeared after launch
            for v_attempt in range(3):
                time.sleep(0.5)
                if _check_spotify_process():
                    self._launched = True
                    logger.info("[SPOTIFY] desktop URI launched and process verified: %s", uri)
                    return True
            logger.warning("[SPOTIFY] desktop URI launched but process not detected: %s", uri)
            return False
        except Exception as exc:
            logger.warning("[SPOTIFY] desktop URI failed: %s", exc)
            return False

    def _transport_uri(self, action: str) -> MediaResult:
        uri_map = {
            "pause": "spotify:pause",
            "play": "spotify:play",
            "next": "spotify:next",
            "previous": "spotify:previous",
        }
        uri = uri_map.get(action)
        if not uri:
            return MediaResult(
                success=False, error=f"Unknown action: {action}", player="spotify"
            )
        try:
            import subprocess
            import sys
            if sys.platform == "win32":
                subprocess.Popen(["cmd", "/c", "start", uri], shell=True)
            else:
                subprocess.Popen(["xdg-open", uri])
            logger.info("[SPOTIFY] transport=%s for URI=%s", action, uri)
            time.sleep(0.5) # Give Spotify a moment to react to the transport command
            return MediaResult(
                success=True, message=f"{action.capitalize()}d", player="spotify"
            )
        except Exception as exc:
            return MediaResult(success=False, error=str(exc), player="spotify")

    def _set_session(
        self,
        query: str,
        url: str,
        state: MediaState = MediaState.IDLE,
        title: str = "",
        artist: str = "",
        album: str = "",
    ):
        self._session = MediaSession(
            player=PlayerType.SPOTIFY,
            state=state,
            query=query,
            url=url,
            tab_id=self._tab_id,
            domain_hint="open.spotify.com",
            media_type=MediaType.MUSIC,
            title=title,
            artist=artist,
            album=album,
        )
        self._session.touch()
