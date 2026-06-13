from __future__ import annotations

import logging
import re
from typing import Optional

from mini_kio.core import config
from mini_kio.media.media_state import MediaState, MediaType, PlayerType
from mini_kio.media.media_session import MediaResult, MediaSession, MediaCandidate
from mini_kio.media.media_context import MediaContext
from mini_kio.media.media_registry import MediaRegistry
from mini_kio.media.media_discovery import MediaDiscovery
from mini_kio.media.media_recommender import MediaRecommender
from mini_kio.media.providers.youtube_provider import YouTubeProvider
from mini_kio.media.providers.spotify_provider import SpotifyProvider
from mini_kio.media.providers.browser_provider import BrowserProvider
from mini_kio.media.providers.local_media_provider import LocalMediaProvider

logger = logging.getLogger(__name__)

_FUZZY_MAP: dict[str, str] = {
    "pasue": "pause",
    "resme": "resume",
    "unmut": "unmute",
    "colume": "volume",
    "volme": "volume",
    "seak": "seek",
    "foward": "forward",
    "backword": "backward",
    "unmute": "unmute",
    "volum": "volume",
}

_CONTENT_TYPE_PRIORITY: dict[str, list[str]] = {
    "music": ["spotify", "youtube"],
    "video": ["youtube", "browser"],
    "educational": ["youtube", "browser"],
    "trailer": ["youtube"],
    "tutorial": ["youtube", "browser"],
    "podcast": ["spotify", "youtube"],
    "audiobook": ["local", "youtube"],
    "livestream": ["youtube"],
    "sports": ["youtube"],
    "news": ["youtube"],
    "browser_media": ["browser"],
    "local_media": ["local", "browser"],
}

_MEDIA_TYPE_KEYWORDS: dict[str, str] = {
    "music": "music song album artist singer band playlist",
    "video": "video watch movie film clip",
    "trailer": "trailer preview coming soon",
    "tutorial": "tutorial how to guide learn walkthrough",
    "educational": "explain what is how does why is science history lesson",
    "podcast": "podcast episode talk show interview",
    "livestream": "live stream streaming",
    "sports": "sports highlights match game nfl nba soccer",
    "news": "news update announcement latest",
}

_SEEK_PATTERNS = [
    (r"(?:jump|go)\s+ahead\s+(\d+)\s*min(?:ute)?s?", lambda m: int(m.group(1)) * 60),
    (r"(?:jump|go)\s+back\s+(\d+)\s*min(?:ute)?s?", lambda m: int(m.group(1)) * -60),
    (r"(?:seek|skip|go|move)\s+(?:forward|ahead)\s+(\d+)\s*(?:second|sec|s)?", 1),
    (r"(?:seek|skip|go|move)\s+(?:back|backward|rewind)\s+(\d+)\s*(?:second|sec|s)?", -1),
    (r"(?:forward|ahead)\s+(\d+)\s*(?:second|sec|s)?", 1),
    (r"(?:back|backward|rewind)\s+(\d+)\s*(?:second|sec|s)?", -1),
    (r"(?:skip)\s+ahead\s+(\d+)\s*(?:second|sec|s)?", 1),
    (r"^skip\s+(\d+)\s*(?:second|sec|s)?", 1),
    (r"^(?:seek|skip)\s+(\d+)\s*(?:second|sec|s)?", 1),
]


def _detect_media_type(query: str) -> str:
    ql = query.lower()
    scores: dict[str, int] = {}
    for mt, keywords in _MEDIA_TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords.split() if kw in ql)
        if score > 0:
            scores[mt] = score
    if not scores:
        return "music"
    return max(scores, key=scores.get)


def _parse_seek(text: str) -> Optional[int]:
    tl = text.lower().strip()
    for pattern, direction in _SEEK_PATTERNS:
        m = re.search(pattern, tl)
        if m:
            if callable(direction):
                try:
                    return direction(m)
                except Exception:
                    continue
            try:
                amount = int(m.group(1))
            except (ValueError, IndexError):
                continue
            if direction == -1:
                return -amount
            return amount
    return None


def _correct_fuzzy(text: str) -> str:
    words = text.lower().split()
    corrected = []
    for w in words:
        corrected.append(_FUZZY_MAP.get(w, w))
    result = " ".join(corrected)
    if result != text.lower():
        logger.info("[MM] fuzzy correction: '%s' -> '%s'", text, result)
    return result


class MediaManager:
    _instance: Optional[MediaManager] = None

    def __init__(self):
        self._registry = MediaRegistry()
        self._context = MediaContext()
        self._discovery = MediaDiscovery()
        self._recommender = MediaRecommender()
        self._providers: dict[str, type] = {}
        self._provider_instances: dict[str, object] = {}
        self._init_providers()

    def _init_providers(self):
        self._providers = {
            "youtube": YouTubeProvider,
            "spotify": SpotifyProvider,
            "browser": BrowserProvider,
            "local": LocalMediaProvider,
        }

    def _get_provider(self, name: str):
        if name not in self._provider_instances:
            cls = self._providers.get(name)
            if cls:
                self._provider_instances[name] = cls()
        return self._provider_instances.get(name)

    def _get_connector(self):
        from mini_kio.core.command_router import _get_connector
        return _get_connector()

    @classmethod
    def get_instance(cls) -> MediaManager:
        if cls._instance is None:
            cls._instance = MediaManager()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def _select_provider(self, query: str = "", platform: str = "", media_type: str = "") -> Optional[str]:
        if platform:
            return platform

        active = self._registry.get_active_by_player()
        if active:
            return active[0]

        if not media_type:
            media_type = _detect_media_type(query)

        priority = _CONTENT_TYPE_PRIORITY.get(media_type, ["youtube"])
        for pname in priority:
            prov = self._get_provider(pname)
            if prov and hasattr(prov, "check_active"):
                session = prov.check_active()
                if session:
                    return pname
        return priority[0] if priority else "youtube"

    def _register_session(self, provider_name: str, result: MediaResult):
        if result.success and result.session:
            self._registry.set(provider_name, result.session)
            candidate = MediaCandidate(
                title=result.session.query or result.session.title,
                url=result.session.url,
                provider=provider_name,
                media_type=result.session.media_type,
                confidence=1.0,
                artist=result.session.artist,
                duration_s=result.session.duration_s,
            )
            self._context.set_current(candidate)
            self._context.last_query = result.session.query

    def _to_dict(self, result: MediaResult) -> dict:
        d = {"success": result.success, "message": result.message, "player": result.player}
        if result.error:
            d["error"] = result.error
        if result.session:
            d["session"] = result.session.to_dict()
        return d

    # ── Public API ────────────────────────────────────────────────────

    def _playing(self, result: MediaResult) -> bool:
        """True if the provider result actually established playback."""
        return bool(
            result.success
            and result.session
            and result.session.state == MediaState.PLAYING
        )

    def play(self, query: str = "", platform: str = "") -> dict:
        if not query and not platform:
            active = self._registry.get_active()
            if active:
                prov = self._registry.get_player_for_session(active)
                if prov:
                    p = self._get_provider(prov)
                    if p:
                        result = p.resume()
                        self._register_session(prov, result)
                        return self._to_dict(result)
            return {"success": True, "message": "Play on YouTube or Spotify?", "_gate3_eligible": True}

        mt = _detect_media_type(query)

        if platform:
            prov = self._get_provider(platform)
            if not prov:
                return {"success": False, "message": f"No provider available: {platform}"}
            try:
                result = prov.play(query, media_type=mt, platform=platform)
                if self._playing(result):
                    self._register_session(platform, result)
                return self._to_dict(result)
            except Exception as exc:
                return {"success": False, "message": f"Playback on {platform} failed: {exc}"}

        # Automatic selection — try priority chain until PLAYING
        priority = _CONTENT_TYPE_PRIORITY.get(mt, ["youtube"])
        last_result = None
        last_provider = ""

        def _result_score(r: MediaResult) -> int:
            if not r or not r.success:
                return -1
            if r.session and r.session.state == MediaState.PLAYING:
                return 2
            if r.session and r.session.state == MediaState.PAUSED:
                return 1
            return 0

        for provider_name in priority:
            prov = self._get_provider(provider_name)
            if not prov:
                continue
            try:
                result = prov.play(query, media_type=mt)
                if self._playing(result):
                    self._register_session(provider_name, result)
                    return self._to_dict(result)
                if _result_score(result) > _result_score(last_result):
                    last_result = result
                    last_provider = provider_name
            except Exception as exc:
                logger.warning("[MM] %s.play failed: %s", provider_name, exc)
                continue

        if last_result:
            self._register_session(last_provider, last_result)
            return self._to_dict(last_result)

        return {"success": True, "message": "Play on YouTube or Spotify?", "_gate3_eligible": True}

    def pause(self, domain_hint: str = "") -> dict:
        active = self._registry.get_active_by_player()
        if active:
            pname, _ = active
            prov = self._get_provider(pname)
            if prov:
                result = prov.pause()
                if result.success:
                    state = MediaState.PAUSED
                    if result.session:
                        state = result.session.state
                    self._registry.update_state(pname, state)
                    return self._to_dict(result)
                return {"success": True, "message": "Paused."}

        prov = self._get_provider("browser")
        if prov:
            result = prov.pause()
            if result.success:
                self._register_session("browser", result)
                return self._to_dict(result)

        return {"success": True, "message": "No media to pause."}

    def resume(self, domain_hint: str = "") -> dict:
        active = self._registry.get_active_by_player()
        if active:
            pname, session = active
            prov = self._get_provider(pname)
            if prov:
                result = prov.resume()
                if result.success:
                    state = MediaState.PLAYING
                    if result.session:
                        state = result.session.state
                    self._registry.update_state(pname, state)
                    return self._to_dict(result)
                return {"success": True, "message": "Resumed."}

        prov = self._get_provider("browser")
        if prov:
            result = prov.resume()
            if result.success:
                self._register_session("browser", result)
                return self._to_dict(result)

        return {"success": True, "message": "No media to resume."}

    def stop(self, domain_hint: str = "") -> dict:
        active = self._registry.get_active_by_player()
        if active:
            pname, _ = active
            prov = self._get_provider(pname)
            if prov:
                result = prov.stop()
                if result.success:
                    state = MediaState.STOPPED
                    if result.session:
                        state = result.session.state
                    self._registry.update_state(pname, state)
                    return self._to_dict(result)
        return {"success": True, "message": "No media to stop."}

    def next_track(self) -> dict:
        active = self._registry.get_active_by_player()
        if active:
            pname, _ = active
            prov = self._get_provider(pname)
            if prov:
                result = prov.next_track()
                if result.success:
                    return self._to_dict(result)
                return {"success": False, "message": result.error}
        return {"success": False, "message": "No active media session for next track."}

    def previous_track(self) -> dict:
        active = self._registry.get_active_by_player()
        if active:
            pname, _ = active
            prov = self._get_provider(pname)
            if prov:
                result = prov.previous_track()
                if result.success:
                    return self._to_dict(result)
                return {"success": False, "message": result.error}
        return {"success": False, "message": "No active media session for previous track."}

    def mute(self, domain_hint: str = "") -> dict:
        prov = self._get_provider("browser")
        if prov:
            result = prov.volume(level=0.0)
            if result.success:
                return self._to_dict(result)
        return {"success": True, "message": "No media to mute."}

    def unmute(self, domain_hint: str = "") -> dict:
        prov = self._get_provider("browser")
        if prov:
            result = prov.volume(level=0.7)
            if result.success:
                return self._to_dict(result)
        return {"success": True, "message": "No media to unmute."}

    def volume_up(self, domain_hint: str = "") -> dict:
        prov = self._get_provider("browser")
        if prov:
            result = prov.volume(direction="up")
            if result.success:
                return self._to_dict(result)
        return {"success": True, "message": "No media to adjust."}

    def volume_down(self, domain_hint: str = "") -> dict:
        prov = self._get_provider("browser")
        if prov:
            result = prov.volume(direction="down")
            if result.success:
                return self._to_dict(result)
        return {"success": True, "message": "No media to adjust."}

    def seek(self, seconds: int) -> dict:
        active = self._registry.get_active_by_player()
        if active:
            pname, _ = active
            prov = self._get_provider(pname)
            if prov:
                result = prov.seek(seconds)
                if result.success:
                    return self._to_dict(result)
                return {"success": True, "message": "Seek not supported for this player."}
        return {"success": True, "message": "No active media to seek."}

    def seek_forward(self, domain_hint: str = "", seconds: int = 10) -> dict:
        return self.seek(seconds)

    def seek_backward(self, domain_hint: str = "", seconds: int = 10) -> dict:
        return self.seek(-seconds)

    def search(self, query: str, platform: str = "") -> dict:
        if platform:
            prov = self._get_provider(platform)
            if prov:
                result = prov.search(query)
                return self._to_dict(result)
        return {"success": False, "message": "No provider for search."}

    def resolve_query(self, text: str) -> Optional[str]:
        return self._context.resolve_reference(text)

    def get_context(self) -> MediaContext:
        return self._context

    def get_registry(self) -> MediaRegistry:
        return self._registry

    def get_discovery(self) -> MediaDiscovery:
        return self._discovery

    def get_recommender(self) -> MediaRecommender:
        return self._recommender

    def process_nl_seek(self, text: str) -> Optional[dict]:
        seconds = _parse_seek(text)
        if seconds is not None:
            return self.seek(seconds)
        return None

    def correct_fuzzy(self, text: str) -> str:
        return _correct_fuzzy(text)

    def is_fuzzy_match(self, text: str) -> bool:
        tl = text.lower().strip()
        return tl in _FUZZY_MAP or any(
            w in _FUZZY_MAP for w in tl.split()
        )

    def offer_media(self, topic: str) -> Optional[dict]:
        opportunity = self._discovery.detect_opportunity(topic)
        if opportunity:
            self._discovery.set_last_offer(opportunity)
            self._context.current_topic = topic
            self._context.last_query = topic
            return opportunity
        return None

    def get_last_offer(self) -> Optional[dict]:
        return self._discovery.get_last_offer()

    def accept_offer(self, query: str = "") -> Optional[dict]:
        offer = self._discovery.get_last_offer()
        if not offer:
            return None
        topic = query or offer.get("topic", "")
        if not topic:
            self._discovery.clear_last_offer()
            return None
        mt = offer.get("media_type", "video")
        provider_name = self._select_provider(topic, media_type=mt)
        prov = self._get_provider(provider_name)
        if not prov:
            self._discovery.clear_last_offer()
            return None
        try:
            search_result = prov.search(topic)
            if search_result.success and search_result.candidates:
                best = search_result.candidates[0]
                result = prov.play(best.title)
                self._register_session(provider_name, result)
                self._discovery.clear_last_offer()
                return self._to_dict(result)
            result = prov.play(topic)
            self._register_session(provider_name, result)
            self._discovery.clear_last_offer()
            return self._to_dict(result)
        except Exception as exc:
            logger.warning("[MM] accept_offer failed: %s", exc)
            self._discovery.clear_last_offer()
            return None

    def get_status(self) -> dict:
        active = self._registry.get_active()
        if active:
            return {"success": True, "message": active.to_dict()}
        return {"success": True, "message": "No active media session."}
