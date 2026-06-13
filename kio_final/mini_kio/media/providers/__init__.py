from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from mini_kio.media.media_session import MediaResult, MediaSession, MediaCandidate


class MediaProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def play(self, query: str, **kwargs) -> MediaResult:
        ...

    @abstractmethod
    def pause(self) -> MediaResult:
        ...

    @abstractmethod
    def resume(self) -> MediaResult:
        ...

    @abstractmethod
    def stop(self) -> MediaResult:
        ...

    @abstractmethod
    def next_track(self) -> MediaResult:
        ...

    @abstractmethod
    def previous_track(self) -> MediaResult:
        ...

    @abstractmethod
    def seek(self, seconds: int) -> MediaResult:
        ...

    @abstractmethod
    def volume(self, level: Optional[float] = None, direction: Optional[str] = None) -> MediaResult:
        ...

    @abstractmethod
    def search(self, query: str) -> MediaResult:
        ...

    @abstractmethod
    def close(self) -> MediaResult:
        ...

    @abstractmethod
    def check_active(self) -> Optional[MediaSession]:
        ...

    def discover(self, topic: str) -> Optional[MediaCandidate]:
        return None

    def recommend(self, query: str) -> list[MediaCandidate]:
        return []
