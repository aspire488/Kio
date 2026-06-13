from __future__ import annotations

import logging
import os
import subprocess
from typing import Optional

from mini_kio.media.media_session import MediaResult, MediaSession, MediaCandidate
from mini_kio.media.media_state import MediaState, PlayerType, MediaType
from mini_kio.media.providers import MediaProvider

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm",
}


class LocalMediaProvider(MediaProvider):
    def __init__(self):
        self._session: Optional[MediaSession] = None
        self._process: Optional[subprocess.Popen] = None

    @property
    def name(self) -> str:
        return "local"

    def play(self, query: str, **kwargs) -> MediaResult:
        filepath = kwargs.get("filepath", "")
        if filepath and os.path.isfile(filepath):
            return self._play_file(filepath)

        results = self._search_local(query)
        if results:
            return self._play_file(results[0])

        return MediaResult(success=False, error=f"No local media found for: {query}", player="local")

    def pause(self) -> MediaResult:
        return MediaResult(success=False, error="Pause not supported for local media", player="local")

    def resume(self) -> MediaResult:
        return MediaResult(success=False, error="Resume not supported for local media", player="local")

    def stop(self) -> MediaResult:
        if self._process:
            self._process.terminate()
            self._process = None
        self._session = None
        return MediaResult(success=True, message="Local media stopped", player="local")

    def next_track(self) -> MediaResult:
        return MediaResult(success=False, error="Next track not supported for local media", player="local")

    def previous_track(self) -> MediaResult:
        return MediaResult(success=False, error="Previous track not supported for local media", player="local")

    def seek(self, seconds: int) -> MediaResult:
        return MediaResult(success=False, error="Seek not supported for local media", player="local")

    def volume(self, level: Optional[float] = None, direction: Optional[str] = None) -> MediaResult:
        return MediaResult(success=False, error="Volume not supported for local media", player="local")

    def search(self, query: str) -> MediaResult:
        files = self._search_local(query)
        candidates = []
        for f in files:
            candidates.append(MediaCandidate(
                title=os.path.basename(f),
                url=f,
                source="local",
                media_type=MediaType.LOCAL_MEDIA,
                confidence=0.8,
                provider="local",
            ))
        return MediaResult(
            success=bool(candidates),
            message=f"Found {len(candidates)} local files" if candidates else "No local files found",
            candidates=candidates,
            player="local",
        )

    def close(self) -> MediaResult:
        return self.stop()

    def check_active(self) -> Optional[MediaSession]:
        if self._process and self._process.poll() is None:
            return self._session
        return None

    def _search_local(self, query: str) -> list[str]:
        query = query.lower()
        search_dirs = []
        for base in (os.path.expanduser("~/Music"), os.path.expanduser("~/Videos"),
                     os.path.expanduser("~/Downloads")):
            if os.path.isdir(base):
                search_dirs.append(base)

        results = []
        for d in search_dirs:
            try:
                for root, _, files in os.walk(d):
                    for f in files:
                        ext = os.path.splitext(f)[1].lower()
                        if ext in SUPPORTED_EXTENSIONS:
                            if query in f.lower() or query in root.lower():
                                results.append(os.path.join(root, f))
                    if len(results) >= 5:
                        break
            except Exception:
                continue
        return results[:5]

    def _play_file(self, filepath: str) -> MediaResult:
        try:
            if os.name == "nt":
                os.startfile(filepath)
            else:
                subprocess.Popen(["xdg-open", filepath])
            self._session = MediaSession(
                player=PlayerType.LOCAL,
                source="local",
                state=MediaState.PLAYING,
                title=os.path.basename(filepath),
                url=filepath,
                media_type=MediaType.LOCAL_MEDIA,
            )
            self._session.touch()
            return MediaResult(
                success=True,
                message=f"Playing local file: {os.path.basename(filepath)}",
                session=self._session,
                player="local",
            )
        except Exception as exc:
            logger.warning("[LOCAL] play failed: %s", exc)
            return MediaResult(success=False, error=str(exc), player="local")
