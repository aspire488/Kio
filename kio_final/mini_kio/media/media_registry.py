from __future__ import annotations

import time
import logging
from typing import Optional

from mini_kio.media.media_session import MediaSession
from mini_kio.media.media_state import MediaState

logger = logging.getLogger(__name__)

ACTIVE_SESSION_TTL_S = 300


class MediaRegistry:
    def __init__(self):
        self._sessions: dict[str, MediaSession] = {}

    def set(self, player: str, session: MediaSession):
        session.touch()
        self._sessions[player] = session
        logger.debug("[MEDIA_REGISTRY] set %s (tab=%s, state=%s)", player, session.tab_id, session.state.value)

    def get(self, player: str) -> Optional[MediaSession]:
        s = self._sessions.get(player)
        if s is None:
            return None
        if time.time() - s.updated_at > ACTIVE_SESSION_TTL_S:
            logger.debug("[MEDIA_REGISTRY] expired session for %s", player)
            return None
        return s

    def get_active(self) -> Optional[MediaSession]:
        best: Optional[MediaSession] = None
        for s in self._sessions.values():
            if time.time() - s.updated_at > ACTIVE_SESSION_TTL_S:
                continue
            if s.state == MediaState.PLAYING:
                if best is None or s.updated_at > best.updated_at:
                    best = s
        if best:
            return best
        for s in self._sessions.values():
            if time.time() - s.updated_at > ACTIVE_SESSION_TTL_S:
                continue
            if s.state == MediaState.PAUSED:
                if best is None or s.updated_at > best.updated_at:
                    best = s
        if best:
            return best
        for s in self._sessions.values():
            if time.time() - s.updated_at > ACTIVE_SESSION_TTL_S:
                continue
            if best is None or s.updated_at > best.updated_at:
                best = s
        return best

    def get_active_by_player(self) -> Optional[tuple[str, MediaSession]]:
        for p, s in self._sessions.items():
            if time.time() - s.updated_at <= ACTIVE_SESSION_TTL_S:
                if s.state in (MediaState.PLAYING, MediaState.PAUSED):
                    return p, s
        for p, s in self._sessions.items():
            if time.time() - s.updated_at <= ACTIVE_SESSION_TTL_S:
                return p, s
        return None

    def remove(self, player: str):
        self._sessions.pop(player, None)

    def clear(self):
        self._sessions.clear()

    def list_all(self) -> list[MediaSession]:
        now = time.time()
        return [s for s in self._sessions.values() if now - s.updated_at <= ACTIVE_SESSION_TTL_S]

    def resolve_by_domain(self, domain_hint: str) -> Optional[MediaSession]:
        if not domain_hint:
            return None
        dl = domain_hint.lower()
        for s in self._sessions.values():
            if dl in s.domain_hint.lower() or dl in s.url.lower():
                return s
        return None

    def resolve_by_tab_id(self, tab_id: int) -> Optional[MediaSession]:
        for s in self._sessions.values():
            if s.tab_id == tab_id:
                return s
        return None

    def get_player_for_session(self, session: MediaSession) -> Optional[str]:
        for p, s in self._sessions.items():
            if s is session:
                return p
        return None

    def update_state(self, player: str, state: MediaState):
        s = self.get(player)
        if s:
            s.state = state
            s.touch()
