from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.parse
import urllib.request
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

_YOUTUBE_API_SEARCH = "https://www.googleapis.com/youtube/v3/search"

# RC9: generic channel-authority provenance words — markers of official
# studios / labels / broadcasters. Deliberately NOT an entity list (no
# franchise, movie, or artist names), so the signal generalizes to any query
# without hardcoding specific channels.
_AUTHORITY_MARKERS = (
    "official", "vevo", "pictures", "studios", "entertainment", "records",
    "films", "networks", "trailers", "presents", "distribution", "label",
)

# RC8: terms that carry no relevance signal on their own. Excluded from
# query tokenization so "a song by the weeknd" ranks on "weeknd" only and
# generic titles cannot win on filler words alone.
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or",
    "with", "me", "my", "your", "you", "it", "its", "is", "are",
    "was", "be", "that", "this", "at", "by", "from", "as",
    "official", "video", "song", "trailer", "review", "lyrics",
})


def _query_terms(query: str) -> list[str]:
    """Significant word-boundary tokens of a query (stopwords removed)."""
    return [
        t for t in re.findall(r"[a-z0-9']+", query.lower())
        if len(t) > 1 and t not in _STOPWORDS
    ]


def _video_id_from_url(url: str) -> str:
    """Extract the canonical YouTube video ID from a URL (or "").

    Handles all three canonical forms so the RC8 identity gate works for
    watch pages AND Shorts:
      * https://www.youtube.com/watch?v=VIDEO_ID
      * https://youtu.be/VIDEO_ID
      * https://www.youtube.com/shorts/VIDEO_ID
    """
    try:
        u = (url or "").strip()
        if not u:
            return ""
        parsed = urllib.parse.urlparse(u)
        qid = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
        if qid:
            return qid
        # https://youtu.be/VIDEO_ID
        if parsed.netloc.lower() == "youtu.be":
            seg = parsed.path.strip("/")
            return seg.split("?")[0].split("/")[0] if seg else ""
        # https://www.youtube.com/shorts/VIDEO_ID (Shorts pages have no ?v=)
        if parsed.netloc.lower().endswith("youtube.com"):
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[0].lower() == "shorts":
                return parts[1].split("?")[0]
        return ""
    except Exception:
        return ""


def _score_candidate(
    title: str,
    url: str,
    query: str,
    channel: str = "",
    description: str = "",
    media_type: str = "",
) -> int:
    """Relevance score of a YouTube result against the requested query.

    Shared by the controlled search path (_search_metadata) and direct
    playback candidate selection (RC7/RC8/RC9) so both pick the best-matching
    result instead of blindly clicking the first link.

    RC8: word-boundary tokens, stopword filtering, distinctive-term weights,
    channel matches, and a coverage gate so weakly-related results cannot win
    on filler alone.

    RC9: the score used to saturate — a title containing the full query phrase
    and all its terms scored IDENTICALLY to every other such title (live proof:
    8/8 candidates for "brand new day" all scored 44, so Python's max() picked
    the FIRST in API order — a random Spider-Verse|Avengers|Venom compilation —
    over Sony Pictures' official trailers). This version adds discriminating,
    query-agnostic signals:
      * phrase POSITION (leading title = subject; buried = aggregation)
      * aggregation/dash-chain penalty (multi-IP mashup titles)
      * channel authority (generic provenance markers, not entity names)
      * exact-title bonus (title is essentially the query itself)
      * description coverage (API snippet corroboration)

    RC10: content-type validation. The caller detects the user's requested
    media type ("trailer", "review", "interview", "gameplay", ...) before
    selection. When a VISUAL/artifact type is requested, an audio-only
    candidate (YouTube auto-generated "- Topic" channel, or a title carrying
    soundtrack/theme/OST markers) is a TYPE MISMATCH, not a candidate — the
    official film trailer must beat its own "Trailer Theme - Malayalam"
    soundtrack. Also applies an emoji/clickbait penalty (reupload spam).
    """
    tl = title.lower()
    ql = query.lower()
    terms = _query_terms(query)
    if not terms:
        return 0

    score = 0
    phrase_at = tl.find(ql)
    phrase_full = 30
    rel_pos = 0.0
    tail_len = 0
    if phrase_at >= 0:
        rel_pos = phrase_at / len(tl)
        tail_len = len(tl) - (phrase_at + len(ql))
        score += phrase_full  # full contiguous phrase -> strong signal
    else:
        # RC9: separator-tolerant phrase — the same significant terms in the
        # same order with only light punctuation/separators between them
        # ("The Weeknd - Blinding Lights (Official Video)" matches the query
        # "the weeknd blinding lights"). Half the contiguous-phrase weight, so
        # the canonical upload can outrank a keyword-stuffed bootleg.
        _sep = r"[\s\-\u2013\u2014|:()&,.'\"]*"
        ordered = _sep.join(re.escape(t) for t in terms)
        if len(terms) >= 2 and re.search(rf"\b{ordered}\b", tl):
            score += 15

    matched = 0
    for term in terms:
        if re.search(rf"\b{re.escape(term)}\b", tl):
            # Distinctive (rarer) terms carry more weight than filler.
            score += 8 if len(term) >= 5 else 3
            matched += 1

    if matched == 0:
        return -100  # clearly unrelated
    coverage = matched / len(terms)
    if coverage < 0.5:
        score -= 25  # half the query missing -> strong negative signal

    # Channel identity is a strong relevance signal (e.g. the query names
    # a channel, or the channel is the canonical uploader of the track).
    if channel:
        cl = channel.lower()
        for term in terms:
            if len(term) >= 5 and term in cl:
                score += 10
                break

    # Artifact keywords must be present when requested ("trailer" query ->
    # a video literally containing "trailer" scores higher than a clip).
    for kw in ("trailer", "highlight", "interview", "music video", "live",
               "official", "review", "song", "lyrics", "podcast", "episode"):
        if kw in ql and kw in tl:
            score += 6
            # "Official Trailer" / "Official Video": canonical upload of the
            # requested artifact gets a strong bonus.
            if "official" in tl:
                score += 12

    # RC9: generic "official" marker in a title is an authoritative-upload
    # signal even when the user didn't name the artifact kind explicitly.
    if "official" in tl:
        score += 6

    # ── RC9: phrase POSITION ────────────────────────────────────────────
    # A title that LEADS with the requested subject is the subject itself
    # ("LIONEL MESSI INTERVIEW | quote"); a buried phrase
    # ("... | Avengers: Brand New Day - Venom 3") is an aggregation.
    if phrase_at >= 0 and len(tl) > 0:
        if rel_pos <= 0.20 and tail_len <= 40:
            score += 10  # title IS the query (quote suffix still allowed)
        elif rel_pos >= 0.60:
            score -= 10  # phrase buried at the end

    # ── RC9: "live" bootleg penalty ─────────────────────────────────────
    # "...LIVE" / "live at..." titles are concert recordings — not the
    # canonical studio upload. Penalized unless the user asked for live OR
    # already requested a live-captured artifact (interview, podcast, concert,
    # match) where a live recording is exactly the canonical content.
    if "live" in tl and "live" not in ql:
        _live_exempt = any(k in ql for k in
                           ("interview", "podcast", "concert", "live performance",
                            "match", "game", "highlight", "set", "gig"))
        if not _live_exempt:
            score -= 10

    # ── RC9: analysis/framing penalty ───────────────────────────────────
    # Reaction / breakdown / explained / leaked / review titles ride the
    # query phrase but are NOT the canonical media ("Avengers Doomsday
    # Trailer: What Happens To...", "Avengers Doomsday Trailer Review | ...",
    # "...Ending Explained"). Penalized unless the user explicitly asked for
    # that framing ("play messi interview review" must still pick reviews).
    _FRAMING = ("breakdown", "reaction", "reacts", "explained", "explains",
                "explain", "theory", "theories", "recap", "analysis",
                "what happens", "leaked", "leak", "ending", "review")
    framing_penalty = 0
    for fw in _FRAMING:
        if fw in tl and fw not in ql:
            framing_penalty += 12
            if framing_penalty >= 24:
                break
    score -= framing_penalty

    # ── RC9: aggregation / mashup penalty ──────────────────────────────
    # Multi-IP compilation titles chain dash-separated subjects
    # ("... Brand New Day - Spiderman - Venom 3"). Pipes are NOT penalized:
    # "Title | Official Trailer | In Theaters Dec 18" is the canonical
    # official-upload format, and RC10 live proof shows a 3-pipe official
    # trailer ("I'M GAME TRAILER (Malayalam) | Dulquer Salmaan | Nahas
    # Hidhayath | Wayfarer Films Music") losing to its own soundtrack because
    # of a standalone pipe penalty. Two dashes are common in legit official
    # titles ("Interstellar - Trailer 2 - Official WB"), so the full mashup
    # penalty requires dash-chains to coexist with a pipe separator — the true
    # multi-subject signature — or a bare 3+ dash chain.
    dash_chains = len(re.findall(r"\s-\s", tl))
    pipe_count = tl.count("|")
    if dash_chains >= 3 or (dash_chains >= 2 and pipe_count >= 1):
        score -= 14
    elif dash_chains == 2:
        score -= 4  # mild: official multi-segment titles stay competitive
    if len(title) > 90:
        score -= 6
    if re.search(r"\bvs\b", tl) and not re.search(r"\bvs\b", ql):
        score -= 8  # "A vs B" mashup/duel titles when user didn't ask for one

    # ── RC9: channel authority (generic provenance markers) ─────────────
    if channel:
        cl = channel.lower()
        auth = 0
        if "vevo" in cl:
            auth += 10  # VEVO is the canonical music-video publisher
        for marker in _AUTHORITY_MARKERS:
            if marker in cl:
                auth += 4
        score += min(auth, 14)

    # ── RC9: description corroboration (weak, bounded) ──────────────────
    if description:
        dl = description.lower()
        desc_hits = sum(
            1 for t in terms
            if re.search(rf"\b{re.escape(t)}\b", dl)
        )
        if desc_hits >= max(1, len(terms) // 2):
            score += 6

    # ── RC10: content-type validation (requested media type ≠ audio-only) ──
    # A "trailer"/"review"/"interview"/"gameplay"/etc. request must not select
    # the soundtrack/theme upload of that same title. YouTube's auto-generated
    # music channels end in " - Topic"; soundtrack uploads announce themselves
    # in the title. Both are strong type-mismatch signals.
    _VISUAL_TYPES = {
        "trailer", "video", "movie", "review", "interview", "gameplay",
        "highlights", "music video", "podcast", "episode", "teaser",
        "clips", "official video", "live performance",
    }
    if media_type in _VISUAL_TYPES:
        cl = (channel or "").lower().rstrip()
        is_audio_channel = cl.endswith("- topic")
        _AUDIO_TITLE_MARKERS = ("soundtrack", "theme", "ost", "score from",
                                "music from", "theme song")
        is_audio_title = any(m in tl for m in _AUDIO_TITLE_MARKERS)
        if is_audio_channel or is_audio_title:
            score -= 14

    # ── RC10: emoji / clickbait reupload penalty ─────────────────────────
    # "I'm Game - Trailer 🥵🔥 Latest Update | ..." is a fan reupload; the
    # emoji is a clickbait signature. Generic — no entity or channel names.
    if re.search(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u2764\uFE0F]", title):
        score -= 8

    if "/shorts/" in url:
        score -= 5
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

    def _api_search_candidates(self, query: str) -> list[dict]:
        """Discover candidates via the YouTube Data API when a key exists.

        Returns [{title, url, video_id, channel}]. Any failure (missing key,
        network, quota) degrades silently to the browser-scrape path — the
        API enhances discovery but never becomes a hard dependency.
        """
        key = (getattr(config, "YOUTUBE_API_KEY", "") or "").strip()
        if not key:
            return []
        try:
            params = urllib.parse.urlencode({
                "part": "snippet",
                "type": "video",
                "maxResults": 15,
                "q": query,
                "key": key,
            })
            req = urllib.request.Request(
                f"{_YOUTUBE_API_SEARCH}?{params}",
                headers={"User-Agent": "KIO/1.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            out = []
            for item in data.get("items", []):
                vid = (item.get("id") or {}).get("videoId")
                sn = item.get("snippet") or {}
                title = (sn.get("title") or "").strip()
                if not vid or not title:
                    continue
                out.append({
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "video_id": vid,
                    "channel": (sn.get("channelTitle") or "").strip(),
                    "description": (sn.get("description") or "").strip(),
                })
            logger.info("[YT_API_SEARCH] query=%s results=%d", query, len(out))
            return out
        except Exception as exc:
            logger.warning("[YT_API_SEARCH] failed query=%s err=%s", query, exc)
            return []

    def _select_best_candidate(self, tab_id: int, query: str,
                               media_type: str = "") -> Optional[dict]:
        """RC7/RC8: choose the best-matching YouTube result instead of the first.

        Discovery source order:
          1. YouTube Data API (when YOUTUBE_API_KEY is configured) — high-quality
             metadata with channel identity and canonical video IDs.
          2. Browser scrape of the open results page via the MV3-safe
             search_results script (retried until the page renders).
        Candidates are merged, scored against the query, and the best is
        returned as {title, url, video_id, channel} — or None when nothing
        relevant is available (the caller falls back to youtube_bootstrap).

        RC10: media_type (the caller's detected requested content type) is
        forwarded into the scorer so content-type validation runs BEFORE
        selection — an official trailer beats its own soundtrack upload.
        """
        conn = self._get_conn()
        if not conn:
            return None
        candidates: list[dict] = []
        candidates.extend(self._api_search_candidates(query))
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

        # RC9: deterministic selection. max() alone returns the FIRST candidate
        # on a score tie — the exact failure that let a random 44-scoring mashup
        # beat Sony's official trailers (all 8 tied at 44). Break ties by
        # (score, -title_length): among equal scores, the shorter, more
        # canonical title wins.
        def _candidate_key(c: dict) -> tuple:
            return (
                _score_candidate(
                    c.get("title", ""), c.get("url", ""), query,
                    channel=c.get("channel", "") or "",
                    description=c.get("description", "") or "",
                    media_type=media_type,
                ),
                -len(c.get("title", "") or ""),
            )

        best = max(candidates, key=_candidate_key)
        score, _ = _candidate_key(best)
        if score <= 0:
            logger.info("[YT_CANDIDATE] best score=%d too weak for query=%s title=%s",
                        score, query, best.get("title", ""))
            return None
        logger.info("[YT_CANDIDATE] query=%s selected=%s score=%d video_id=%s",
                    query, best.get("title", ""), score, best.get("video_id", ""))
        return best

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

        # RC11: a direct YouTube URL (watch / youtu.be / SHORTS) must be
        # navigated to directly — searching for the URL text was a proven
        # retrieval bug ("play https://www.youtube.com/shorts/..." opened a
        # search for the URL string and landed on an unrelated video).
        _is_direct_url = clean_query.startswith(("http://", "https://", "www."))
        if _is_direct_url:
            url = clean_query
        else:
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
            _identity_fail: Optional[str] = None
            _actual_watch_url = ""
            if not tab_id:
                logger.info("[ROOT_YT] tab_id is None — no tab returned by connector")
            else:
                # Brief pause for the page to render
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

                # RC7/RC8: controlled candidate selection BEFORE any blind click.
                # _select_best_candidate returns {title, url, video_id, channel}
                # so the actual playing video can be identity-verified against
                # the selected candidate (RC8), not just trusted by URL.
                # RC10: forward the caller's detected media type so content-type
                # validation (official trailer vs soundtrack upload) runs here.
                # RC11: for a direct URL query the URL IS the selected candidate
                # (watch, youtu.be, or shorts) — no search/scrape needed, and the
                # identity gate verifies against the URL's own video ID.
                _mt_hint = (kwargs.get("media_type") or "").strip().lower()
                if _is_direct_url:
                    _direct_vid = _video_id_from_url(url)
                    _selected = {
                        "title": clean_query,
                        "url": url,
                        "video_id": _direct_vid,
                        "channel": "",
                    } if _direct_vid else None
                else:
                    _selected = self._select_best_candidate(tab_id, clean_query, media_type=_mt_hint)
                _selected_video_id = (_selected or {}).get("video_id", "") or ""
                _selected_title = (_selected or {}).get("title", "") or ""
                _navigated = False
                if _selected:
                    _candidate_url = _selected["url"]
                    logger.info("[ROOT_YT] candidate_navigate url=%s title=%s", _candidate_url, _selected_title)
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
                        _actual_watch_url = ""
                        try:
                            _post_bootstrap = safe_run_async(conn.execute_script(tab_id, "get_page_info"))
                            if _post_bootstrap.success and isinstance(_post_bootstrap.message, dict):
                                _actual_watch_url = _post_bootstrap.message.get("url") or ""
                                logger.info("[YT_INSTRUMENT] post-bootstrap url=%s title=%s hasVideo=%s hasWatchFlexy=%s hasMoviePlayer=%s",
                                            _actual_watch_url, _post_bootstrap.message.get("title"),
                                            _post_bootstrap.message.get("hasVideo"), _post_bootstrap.message.get("hasWatchFlexy"),
                                            _post_bootstrap.message.get("hasMoviePlayer"))
                        except Exception as _pbe2:
                            logger.warning("[YT_INSTRUMENT] post-bootstrap page info failed: %s", _pbe2)
                        # ───────────────────────────────────────────────────────

                        # ── RC8: identity gate — the loaded page MUST be the ──
                        # selected candidate. If the API/browser selected video
                        # ID does not match the page's actual video ID, the
                        # content is wrong: fail truthfully, never report
                        # success on the wrong video.
                        if _selected_video_id and _identity_fail is None:
                            _loaded_id = _video_id_from_url(_actual_watch_url)
                            if _loaded_id and _loaded_id != _selected_video_id:
                                logger.warning(
                                    "[YT_IDENTITY] mismatch selected=%s loaded=%s url=%s",
                                    _selected_video_id, _loaded_id, _actual_watch_url,
                                )
                                playback_state = MediaState.IDLE
                                _identity_fail = (
                                    f"Wrong video loaded: selected {_selected_title} "
                                    f"(id={_selected_video_id}) but Chrome loaded id={_loaded_id}"
                                )

                        # Poll for video element with shorter intervals since
                        # bootstrap already verified the URL transition.
                        # RC8: when the identity gate already failed, do NOT
                        # attempt play on the wrong video — fail fast.
                        for attempt in range(5):
                            if _identity_fail is not None:
                                logger.info("[ROOT_YT] skipping play attempts (identity_fail)")
                                break
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

            # RC8: a selected-video identity mismatch is a truthful PLAY FAILURE.
            # Never report success on the wrong video.
            if _identity_fail:
                logger.info("[ROOT_YT] RETURN=R9 identity_fail %s", _identity_fail)
                return MediaResult(
                    success=False,
                    error=_identity_fail,
                    player="youtube",
                )

            self._tab_id = tab_id
            # RC8: the session's canonical URL must be the ACTUAL loaded watch
            # URL (the video really playing), not the search-results URL.
            _session_url = _actual_watch_url or url
            self._session = MediaSession(
                player=PlayerType.YOUTUBE,
                tab_id=tab_id,
                state=playback_state,
                query=clean_query,
                title=_title,
                artist=_artist,
                url=_session_url,
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

    def mute(self) -> MediaResult:
        return self._transport("mute")

    def unmute(self) -> MediaResult:
        return self._transport("unmute")

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
            
            # RC8/RC9: merge YouTube Data API candidates (channel identity +
            # video IDs + description) with the extension MV3-safe
            # search_results scrape so search quality matches playback
            # discovery and the same discriminating ranker is applied.
            candidates = []
            for _api in self._api_search_candidates(query):
                candidates.append({
                    "title": _api.get("title", ""),
                    "url": _api.get("url", ""),
                    "video_id": _api.get("video_id", ""),
                    "channel": _api.get("channel", "") or "",
                    "description": _api.get("description", "") or "",
                })
            scrape_res = safe_run_async(conn.execute_script(tab_id, "search_results"))
            if scrape_res.success and isinstance(scrape_res.message, list):
                for item in scrape_res.message:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title")
                    url = item.get("url")
                    video_id = item.get("video_id")
                    if title and url and video_id:
                        candidates.append({
                            "title": title, "url": url, "video_id": video_id,
                            "channel": "", "description": "",
                        })

            if candidates:
                # RC10: detect the requested content type from the search query
                # so the same type-validation runs on the search path too.
                _st = ""
                _ql = query.lower()
                if "trailer" in _ql:
                    _st = "trailer"
                elif "review" in _ql:
                    _st = "review"
                elif "interview" in _ql:
                    _st = "interview"
                elif "gameplay" in _ql:
                    _st = "gameplay"
                elif "music video" in _ql or "official video" in _ql:
                    _st = "music video"
                elif "podcast" in _ql or "episode" in _ql:
                    _st = "podcast"

                def _art_key(item: dict) -> tuple:
                    return (
                        _score_candidate(
                            item.get("title", ""), item.get("url", ""), query,
                            channel=item.get("channel", "") or "",
                            description=item.get("description", "") or "",
                            media_type=_st,
                        ),
                        -len(item.get("title", "") or ""),
                    )

                best = max(candidates, key=_art_key)
                title, url, video_id = best.get("title", ""), best.get("url", ""), best.get("video_id", "")
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
                        self._session.muted = msg.get("muted", self._session.muted)
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

            # Truthful failure: the extension reported a failed/absent action.
            # The state contract stays intact — never convert a failure into
            # "muted." / "unmuted." / "paused." / "resumed.".
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
