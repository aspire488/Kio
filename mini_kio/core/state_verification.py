"""
state_verification.py - VerifiedConnector

Generic state-verification pipeline that wraps the raw browser Connector.

The defect being fixed: the system treated "API call completed / extension ACKed"
as "user action completed". This wrapper sits on the single execution boundary
every browser/media provider routes through (see command_router._get_connector)
and RE-QUERIES CHROME before giving up success. Observed state is truth; the ACK
is only the trigger.

Policy:
- OPEN:  create tab -> poll until a real tab exists whose host matches -> VERIFIED.
- CLOSE: remove tab -> poll until the tab_id is gone -> VERIFIED.
- EXECUTE (media push): script ACK alone is NOT success. If the returned payload
  contradicts intent (no media / blocked / error) -> FAILED. If intent is
  playback, probe a fresh sample_media snapshot; VERIFIED when the element
  reports status==playing with a loaded duration, or when currentTime advances
  between two probes (progression is a soft signal, not the sole gate).
- Non-media execute_script results are real DOM reads and pass through.

Nothing here generates English responses. Callers see success + a
VerificationCode and compose their own reply.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional
from urllib.parse import urlparse

from mini_kio.browser_connector.protocol import TabResult, VerificationCode

logger = logging.getLogger(__name__)

_PLAY_SCRIPTS = {
    "play", "resume", "seek_forward", "seek_backward",
}

# Scripts whose success must be proven by an observed paused state, not the
# ACK alone (the extension may have paused a stray element, or an autoplay
# may have raced the pause).
_PAUSE_SCRIPTS = {
    "pause", "stop",
}

_FAILED_STATUSES = {
    "no media", "blocked", "no_video", "player_not_ready",
    "player_lost", "video_lost", "ended", "aborted",
}

_PLAY_PROBE_INIT_MS = 300

def _play_deadline_s() -> float:
    return 25.0  # ponytail: fixed bound OK for real-world page load

_MUTATE_POLL_STEP_S = 0.5
_MUTATE_DEADLINE_S = 15.0
_PAUSE_DEADLINE_S = 10.0


# RC1: the expected extension build fingerprint. Chrome serves a cached copy
# of an unpacked MV3 service worker, so the loaded build can lag the working
# tree. When a play-family script returns an empty/non-dict payload, probe
# get_build_info and surface a clear "reload the extension" diagnostic instead
# of the generic (and misleading) "non-state payload" error.
_EXPECTED_BUILD = "0.2.0"


class VerifiedConnector:
    """State-verifying wrapper around a raw browser Connector."""

    def __init__(self, raw: Any):
        self._raw = raw
        self._build_probed = False

    # ── Raw passthrough (non-mutating / infos) ─────────────────────────

    def is_connected(self) -> bool:
        return self._raw.is_connected()

    def start_background(self) -> None:
        self._raw.start_background()

    async def stop(self) -> None:
        await self._raw.stop()

    @property
    def registry(self):
        return self._raw.registry

    @property
    def token(self):
        return self._raw.token

    @property
    def _mock(self):
        return getattr(self._raw, "_mock", False)

    async def list_tabs(self) -> TabResult:
        # list_tabs is itself the truth read; verification is inherent.
        res = await self._raw.list_tabs()
        res.verification = (
            VerificationCode.VERIFIED.value if res.success
            else VerificationCode.FAILED.value
        )
        return res

    async def _resolve_media_tab(self, domain_hint: str = "") -> Any:
        return await self._raw._resolve_media_tab(domain_hint)

    # ── Verifying mutating operations ──────────────────────────────────

    async def open_tab(self, url: str) -> TabResult:
        res = await self._raw.open_tab(url)
        if not res.success:
            return self._verification(res)
        host = self._host(url)
        deadline = time.time() + _MUTATE_DEADLINE_S
        while time.time() < deadline:
            await asyncio.sleep(_MUTATE_POLL_STEP_S)
            probe = await self._raw.list_tabs()
            if probe.success and probe.tabs:
                for t in probe.tabs:
                    if self._host(t.url) == host:
                        res.verification = VerificationCode.VERIFIED.value
                        res.tab = t
                        return res
        res.verification = VerificationCode.TIMEOUT.value
        res.success = False
        res.error = f"tab for '{url}' never appeared in Chrome"
        return res

    async def close_tab(self, target: str) -> TabResult:
        res = await self._raw.close_tab(target)
        if not res.success:
            return self._verification(res)
        tab_id = res.tab.tab_id if res.tab else None
        if tab_id is None:
            res.verification = VerificationCode.NOT_VERIFIED.value
            return res
        deadline = time.time() + _MUTATE_DEADLINE_S
        while time.time() < deadline:
            await asyncio.sleep(_MUTATE_POLL_STEP_S)
            probe = await self._raw.list_tabs()
            if probe.success and probe.tabs is not None:
                if all(t.tab_id != tab_id for t in probe.tabs):
                    res.verification = VerificationCode.VERIFIED.value
                    return res
        res.verification = VerificationCode.TIMEOUT.value
        res.success = False
        res.error = f"tab {tab_id} still present after close"
        return res

    async def focus_tab(self, target: str) -> TabResult:
        res = await self._raw.focus_tab(target)
        if not res.success:
            return self._verification(res)
        res.verification = VerificationCode.VERIFIED.value
        return res

    # ── Verifying script execution ─────────────────────────────────────

    async def execute_script(self, tab_id: int, script: str,
                             args: Optional[list] = None) -> TabResult:
        res = await self._raw.execute_script(tab_id, script, args=args)
        if not res.success:
            return self._verification(res)

        msg = res.message
        if msg is None:
            # ACKed but returned nothing meaningful: never a success.
            res.verification = VerificationCode.NOT_VERIFIED.value
            res.success = False
            res.error = f"script '{script}' returned no payload"
            return res

        if not isinstance(msg, dict):
            # e.g. 'navigating' from youtube_bootstrap. Only trusted as success
            # for scripts that legitimately return a bare string claim.
            if script in _PLAY_SCRIPTS:
                res.verification = VerificationCode.NOT_VERIFIED.value
                res.success = False
                stale = await self._stale_build(tab_id)
                if stale:
                    res.error = stale
                else:
                    res.error = f"script '{script}' returned non-state payload"
            else:
                res.verification = VerificationCode.VERIFIED.value
            return res

        status = (msg.get("status") or msg.get("player_status") or "").strip()
        if status in _FAILED_STATUSES or status.startswith("error"):
            res.verification = VerificationCode.FAILED.value
            res.success = False
            res.error = f"script '{script}' reported: {status}"
            return res

        if script in _PAUSE_SCRIPTS:
            return await self._verify_paused(res, tab_id, script)

        if status == "playing" or script in _PLAY_SCRIPTS:
            return await self._verify_playback(res, tab_id, script)

        res.verification = VerificationCode.VERIFIED.value
        return res

    async def _verify_playback(self, res: TabResult, tab_id: int,
                               script: str) -> TabResult:
        """Prove playback from Chrome's own state, not the play ACK.

        Acceptance: a fresh sample_media probe reports status == "playing"
        with a loaded duration (> 0), OR currentTime advances between two
        probes. Progression is a soft signal only — a genuinely-playing
        element whose clock stalls during startup/buffering is still
        verified, so a real play is not rejected as a false negative.
        A paused / non-advancing element remains a rejection.
        """
        deadline = _play_deadline_s()
        t0 = time.time()
        samples = []
        first = await self._raw.execute_script(tab_id, "sample_media")
        if first.success and isinstance(first.message, dict):
            samples.append(first)
            if _is_playing_snapshot(first.message):
                res.verification = VerificationCode.VERIFIED.value
                return res
        while time.time() - t0 < deadline:
            await asyncio.sleep(_MUTATE_POLL_STEP_S)
            sample = await self._raw.execute_script(tab_id, "sample_media")
            if not sample.success or not isinstance(sample.message, dict):
                continue
            samples.append(sample)
            if _is_playing_snapshot(sample.message):
                res.verification = VerificationCode.VERIFIED.value
                return res
        if not samples:
            res.verification = VerificationCode.NOT_VERIFIED.value
            res.success = False
            res.error = "cannot read playback position"
            return res
        before = _ct(samples[0].message)
        after = _ct(samples[-1].message)
        if before is not None and after is not None and after > before:
            res.verification = VerificationCode.VERIFIED.value
            return res
        res.verification = VerificationCode.TIMEOUT.value
        res.success = False
        res.error = "media position did not advance"
        return res

    async def _verify_paused(self, res: TabResult, tab_id: int,
                             script: str) -> TabResult:
        """Prove the media actually paused from Chrome's own state.

        The ACK (extension called v.pause()) is not proof: the element it
        paused may differ from the one the user hears (stray ad/hover video),
        or an autoplay may have raced the pause. Probe a fresh sample_media
        snapshot and require the element to report paused.
        """
        deadline = time.time() + _PAUSE_DEADLINE_S
        while time.time() < deadline:
            await asyncio.sleep(_MUTATE_POLL_STEP_S)
            sample = await self._raw.execute_script(tab_id, "sample_media")
            if not sample.success or not isinstance(sample.message, dict):
                continue
            msg = sample.message
            status = (msg.get("status") or "").strip()
            if status == "no media":
                res.verification = VerificationCode.FAILED.value
                res.success = False
                res.error = f"script '{script}': no media present after action"
                return res
            if status == "paused" or msg.get("paused") is True:
                res.verification = VerificationCode.VERIFIED.value
                return res
        res.verification = VerificationCode.TIMEOUT.value
        res.success = False
        res.error = f"media still not paused after '{script}'"
        return res

    # ── Internals ──────────────────────────────────────────────────────

    async def _stale_build(self, tab_id: int) -> Optional[str]:
        """Detect a Chrome extension running an outdated build.

        Returns a clear diagnostic when the loaded build is stale or
        unverifiable; returns None when the build matches (so the caller keeps
        the generic error). Cached per connector so repeated failures do not
        re-probe on every retry attempt.
        """
        if self._build_probed:
            return None
        self._build_probed = True
        try:
            probe = await self._raw.execute_script(tab_id, "get_build_info")
            if probe.success and isinstance(probe.message, dict):
                loaded = probe.message.get("build", "")
                if loaded != _EXPECTED_BUILD:
                    return (
                        f"extension build out of date (loaded={loaded or 'unknown'}, "
                        f"expected={_EXPECTED_BUILD}) - reload the KIO Chrome extension"
                    )
            else:
                return (
                    f"extension build out of date (no get_build_info, "
                    f"expected={_EXPECTED_BUILD}) - reload the KIO Chrome extension"
                )
        except Exception:
            return None
        return None

    def _verification(self, res: TabResult) -> TabResult:
        res.verification = VerificationCode.FAILED.value
        return res

    @staticmethod
    def _host(url: str) -> str:
        try:
            return (urlparse(url).hostname or "").lower()
        except Exception:
            return ""


def _float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ct(msg: dict) -> Optional[float]:
    return _float(msg.get("currentTime"))


def _is_playing_snapshot(msg: dict) -> bool:
    """True when a sample_media snapshot proves real playback: the element
    reports status=="playing" with a loaded duration (>0)."""
    dur = _float(msg.get("duration"))
    if not (msg.get("status") == "playing" and dur is not None and dur > 0):
        return False
    # Player identity guard: if the page hosts a real media player
    # (#movie_player on YouTube) but the sampled element is NOT inside it,
    # a stray ad/hover <video> is being mistaken for the requested player.
    # The extension resolves through _playerVideo() and reports these fields.
    if msg.get("hasMoviePlayer") is True and msg.get("isPlayerVideo") is not True:
        return False
    return True