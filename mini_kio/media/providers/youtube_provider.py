from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from mini_kio.browser_connector.connector import Connector
from mini_kio.core import config
from mini_kio.core.async_utils import safe_run_async
from mini_kio.media.media_session import MediaResult, MediaSession, MediaCandidate, user_facing_media_label
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


def _resolve_search_to_watch_url(query: str) -> str:
    """No-connector best-effort: scrape the first real videoId from the
    YouTube search results page and return its watch URL, or "" when
    unresolvable. Used ONLY by the honest browser-fallback play path — with
    the connector, candidate selection is the richer controlled path."""
    try:
        encoded = urllib.parse.quote_plus(query)
        req = urllib.request.Request(
            "https://www.youtube.com/results?search_query=" + encoded,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=6.0) as r:
            html = r.read().decode("utf-8", "replace")
        m = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
        return "https://www.youtube.com/watch?v=" + m.group(1) if m else ""
    except Exception:
        return ""


def _score_candidate(
    title: str,
    url: str,
    query: str,
    channel: str = "",
    description: str = "",
    media_type: str = "",
    view_count: int = 0,
    published_at: str = "",
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

    # Content-type synonym map: when the user asks for a content type by one
    # name, titles using a synonym should still count as a term match.
    # "play cosmic samson teaser" → "Curtain Raiser" counts as matching "teaser".
    _CONTENT_SYNONYMS = {
        "teaser": ("curtain raiser", "first look", "sneak peek", "glimpse"),
        "trailer": ("curtain raiser", "official preview", "glimpse"),
        "interview": ("conversation with", "talks with", "sits down with"),
        "review": ("verdict", "analysis"),
        "documentary": ("full documentary", "feature documentary"),
        "gameplay": ("lets play", "playthrough", "walkthrough"),
        "highlights": ("best moments", "top plays"),
        "music video": ("official video", "mv"),
        "podcast": ("episode", "pod"),
        "live": ("live performance", "live concert", "live session", "acoustic"),
    }

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
        elif term in _CONTENT_SYNONYMS:
            # Content-type synonym resolution: "curtain raiser" in title
            # counts as matching the term "teaser" in the query.
            for syn in _CONTENT_SYNONYMS[term]:
                if syn in tl:
                    score += 8 if len(term) >= 5 else 3
                    matched += 1
                    break

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
    # RC11: when user explicitly asks for teaser/trailer/song, reaction/review
    # framing is an especially strong mismatch — penalize harder so the
    # official upload always wins. A "teaser reaction" must never beat the
    # actual teaser.
    _NON_REACTION_TYPES = ("teaser", "trailer", "song", "music video", "official")
    if any(ct in ql for ct in _NON_REACTION_TYPES):
        _reaction_strong = ("reaction", "reacts", "react to", "review",
                            "reviewing", "breakdown", "explained", "explains",
                            "analysis", "what happens", "ending explained")
        for _rs in _reaction_strong:
            if _rs in tl and _rs not in ql:
                framing_penalty += 10
                if framing_penalty >= 40:
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

    # ── RC10b: semantic content-type boost ─────────────────────────────────
    # When the user explicitly requests a content type (interview, trailer,
    # documentary, etc.), videos whose titles or descriptions contain that
    # exact content type get a strong boost. This prevents "Bethlehem
    # documentary" from returning an interview, or "Messi interview" from
    # returning a highlight reel.
    #
    # RC12: the boost does NOT apply when the title also carries strong
    # framing words (reaction, review, breakdown, explained, ...). A title
    # "Cosmic Samson Teaser Reaction" is NOT a teaser — it is a reaction
    # ABOUT a teaser. The content-type keyword is incidental, not the actual
    # content. Without this gate, reaction/review titles accumulate a
    # +36 content-type bonus that overwhelms their framing penalty, causing
    # them to beat the official upload.
    #
    # RC13: the caller's media_type (from the pipeline) may not carry the
    # user's explicit content-type intent — e.g. "play cosmic samson teaser"
    # gets media_type="music" because "play" dominates the pipeline's
    # weighted scorer. Detect the content type from the query directly so
    # the boost fires for ALL explicit content-type requests.
    _CONTENT_TYPE_KEYWORDS = {
        "interview": ("interview", "conversation with", "talks with", "sits down with"),
        "trailer": ("trailer", "teaser", "official preview", "curtain raiser", "glimpse"),
        "teaser": ("teaser", "first look", "sneak peek", "curtain raiser", "glimpse", "official teaser"),
        "documentary": ("documentary", "full documentary", "feature documentary"),
        "review": ("review", "reviewing", "verdict", "analysis"),
        "gameplay": ("gameplay", "lets play", "playthrough", "walkthrough"),
        "highlights": ("highlights", "best moments", "top plays"),
        "music video": ("music video", "official video", "mv"),
        "podcast": ("podcast", "episode", "pod"),
        "live": ("live performance", "live concert", "live session", "acoustic"),
    }
    _FRAMING_WORDS = (
        "reaction", "reacts", "review", "reviewing", "breakdown",
        "explained", "explains", "analysis", "what happens", "ending",
        "theory", "theories", "leaked", "leak", "recap",
    )
    _title_is_framing = any(fw in tl for fw in _FRAMING_WORDS)
    # RC13: detect content type from query first; fall back to caller's
    # media_type when the query doesn't contain an explicit content word.
    _effective_type = media_type
    if not _effective_type or _effective_type not in _CONTENT_TYPE_KEYWORDS:
        for _ct in _CONTENT_TYPE_KEYWORDS:
            if _ct in ql:
                _effective_type = _ct
                break
    if _effective_type in _CONTENT_TYPE_KEYWORDS:
        _ct_markers = _CONTENT_TYPE_KEYWORDS[_effective_type]
        _ct_match = any(m in tl for m in _ct_markers)
        if _ct_match and not _title_is_framing:
            score += 18  # strong boost: title explicitly matches requested type
        elif _effective_type in ql and _effective_type not in tl:
            # User asked for type X but title doesn't mention it — penalize
            score -= 10

    # RC10b-cross: extract ALL explicit content-type words from the query.
    # "Bethlehem interview" → media_type might be "podcast" but the query
    # explicitly says "interview". Any mismatched content-type word in the
    # query that is MISSING from the title gets a strong penalty — this is
    # the primary mechanism preventing "interview" from resolving to
    # "trailer".
    _EXPLICIT_CONTENT_TYPES = {
        "interview": ("interview", "conversation with", "talks with", "sits down with"),
        "trailer": ("trailer", "teaser", "official preview", "curtain raiser", "glimpse"),
        "teaser": ("teaser", "first look", "sneak peek", "curtain raiser", "glimpse", "official teaser"),
        "documentary": ("documentary", "full documentary", "feature documentary"),
        "review": ("review", "reviewing", "verdict", "analysis"),
        "gameplay": ("gameplay", "lets play", "playthrough", "walkthrough"),
        "highlights": ("highlights", "best moments", "top plays"),
        "music video": ("music video", "official video", "mv"),
        "podcast": ("podcast", "episode", "pod"),
        "song": ("song", "track", "single"),
        "live": ("live performance", "live concert", "live session", "acoustic"),
        "official": ("official", "studio"),
        "full movie": ("full movie", "full film", "full version", "full episode"),
        "tutorial": ("tutorial", "how to", "guide", "walkthrough"),
    }
    for _ct_word, _ct_markers in _EXPLICIT_CONTENT_TYPES.items():
        if _ct_word in ql:
            _ct_match = any(m in tl for m in _ct_markers)
            if _ct_match and not _title_is_framing:
                score += 18  # strong boost: title matches requested content type
            elif not _ct_match:
                # Content-type MISMATCH: user asked for X but title doesn't
                # contain any X marker — strong penalty to prevent type confusion.
                # "Bethlehem interview" must not select a trailer; penalty
                # must be large enough to overcome entity-name match bonuses.
                score -= 22
            break  # only the FIRST explicit content type matters

    # ── RC10: emoji / clickbait reupload penalty ─────────────────────────
    # "I'm Game - Trailer 🥵🔥 Latest Update | ..." is a fan reupload; the
    # emoji is a clickbait signature. Generic — no entity or channel names.
    if re.search(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u2764\uFE0F]", title):
        score -= 8

    # ── Shorts / short-form penalty ─────────────────────────────────────
    # Normal "play X" requests must NEVER select a Short unless the user
    # explicitly asks for one. The URL path and title are both checked;
    # the penalty is large enough to overcome a full phrase match (+30).
    _wants_short = "short" in ql or "shorts" in ql
    if not _wants_short:
        if "/shorts/" in url:
            score -= 28  # Shorts URL: almost always wrong for normal play
        # Title-level short-form markers (vertical video metadata)
        if re.search(r"\b#shorts?\b", tl) or re.search(r"\b(shorts?\s*video|vertical)\b", tl):
            score -= 18

    # ── Edit / reaction / compilation / fan-upload penalty ──────────────
    # Edits, reactions, compilations, fan remixes, and "vs" mashups should
    # not beat an exact/canonical result unless the user explicitly asked
    # for them. Generic morphology, never per-entity.
    if not any(kw in ql for kw in ("edit", "reaction", "compilation", "remix", "vs")):
        _WEAK_UPLOAD_MARKERS = (
            "fan edit", "edit ", " edits", "reaction to", " reacts to",
            "compilation", "remix", "mashup", "vs ", " vs",
            "best of", "top 10", "top 20",
        )
        for _wm in _WEAK_UPLOAD_MARKERS:
            if _wm in tl:
                score -= 12
                break

    # ── Exact title match bonus ────────────────────────────────────────
    # For an exact named request ("Play Cosmic Samson"), a title that IS
    # the requested entity gets a strong bonus over a title that merely
    # contains the words. "Cosmic Samson" == title vs "Cosmic Samson | Fan
    # Edit" which only contains it.
    _title_norm = tl.strip()
    _query_norm = ql.strip()
    if _title_norm == _query_norm:
        score += 20  # exact title == query: strongest possible match
    elif len(terms) >= 2 and all(t in _title_norm for t in terms):
        # All query terms present in title: partial exact match.
        score += 8

    # ── View count / popularity signal ──────────────────────────────────
    # Popularity is ONE weak signal — it must NEVER dominate relevance.
    # A semantically perfect match with 1K views beats a viral unrelated
    # video with 100M views. Logarithmic scaling: 1M views ≈ +3, 10M ≈ +4,
    # 100M ≈ +5. Never exceeds +5 to keep relevance dominant.
    if view_count > 0:
        import math
        _log_views = math.log10(max(view_count, 1))
        # 1M = 6.0, 10M = 7.0, 100M = 8.0 → normalize to 0-5 range
        _pop_bonus = max(0, min(5, int(_log_views - 3)))
        score += _pop_bonus

    # ── Recency signal (weak, supporting) ────────────────────────────────
    # A recent official upload should beat an older reaction video when
    # relevance is otherwise comparable. Parsed from ISO 8601 published_at.
    # Never exceeds +3 — recency is a tiebreaker, not a ranking criterion.
    if published_at:
        try:
            from datetime import datetime, timezone
            _pub = published_at.replace("Z", "+00:00")
            _pub_dt = datetime.fromisoformat(_pub)
            _now = datetime.now(timezone.utc)
            _days_old = (_now - _pub_dt).total_seconds() / 86400
            if _days_old <= 7:
                score += 3  # very recent (within a week)
            elif _days_old <= 30:
                score += 2  # recent (within a month)
            elif _days_old <= 90:
                score += 1  # somewhat recent (within 3 months)
        except (ValueError, TypeError, OverflowError):
            pass

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

    def _get_raw_conn(self) -> Optional[Connector]:
        """The raw (unverified) connector for the play/verification loop.

        The state-verification wrapper (VerifiedConnector) re-probes Chrome
        for up to its full deadline on EVERY play-family execute_script call.
        The provider's own acceptance loop (get_player_state, status,
        currentTime progression, stabilization) IS the state verification for
        playback, so routing retry/stabilization play calls through the raw
        connector eliminates the duplicated 10s-per-attempt verification that
        produced the multi-minute retry spiral (BUG 4) — without losing any
        truthfulness (the final acceptance still requires observed player
        state, and open_tab remains verified by the wrapper).
        """
        conn = self._get_conn()
        if conn is None:
            return None
        return getattr(conn, "_raw", conn)

    def _api_search_candidates(self, query: str) -> list[dict]:
        """Discover candidates via the YouTube Data API when a key exists.

        Returns [{title, url, video_id, channel, view_count}]. Any failure
        (missing key, network, quota) degrades silently to the browser-scrape
        path — the API enhances discovery but never becomes a hard dependency.
        """
        key = (getattr(config, "YOUTUBE_API_KEY", "") or "").strip()
        if not key:
            return []
        try:
            params = urllib.parse.urlencode({
                "part": "snippet,statistics",
                "type": "video",
                "maxResults": 25,
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
                st = item.get("statistics") or {}
                title = (sn.get("title") or "").strip()
                if not vid or not title:
                    continue
                view_count = 0
                try:
                    view_count = int(st.get("viewCount", 0))
                except (ValueError, TypeError):
                    pass
                out.append({
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "video_id": vid,
                    "channel": (sn.get("channelTitle") or "").strip(),
                    "description": (sn.get("description") or "").strip(),
                    "view_count": view_count,
                    "published_at": (sn.get("publishedAt") or "").strip(),
                })
            logger.info("[YT_API_SEARCH] query=%s results=%d", query, len(out))
            return out
        except urllib.error.HTTPError as exc:
            # RC-quota: Google rejected the request on quota/rate limits. Log it
            # EXPLICITLY (this is why API discovery silently went missing) but
            # never leak the key, never retry (a 429 retry storm worsens quota),
            # and keep the graceful degrade to the browser-scrape path.
            if exc.code == 429:
                logger.error("[YT_API_SEARCH] QUOTA_EXHAUSTED query=%s (key present, quota exceeded; falling back to browser scrape)", query)
            else:
                logger.warning("[YT_API_SEARCH] failed query=%s http_err=%s", query, exc.code)
            return []
        except Exception as exc:
            logger.warning("[YT_API_SEARCH] failed query=%s err=%s", query, exc)
            return []

    def _select_best_candidate(self, tab_id: int, query: str,
                               media_type: str = "",
                               rejected_ids: Optional[list] = None) -> Optional[dict]:
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

        Rejection: when rejected_ids is provided, candidates whose video_id
        or URL matches any rejected ID are excluded from selection.  This
        prevents "nah" → re-search → same candidate from being picked again.
        """
        conn = self._get_conn()
        if not conn:
            return None
        _rej_raw = set(rejected_ids or [])
        # Build a unified rejection set: extract video_ids from URLs so that
        # a rejected URL like "https://www.youtube.com/watch?v=XYZ&list=..."
        # correctly excludes candidates with video_id "XYZ" even when the
        # URL strings differ (query params, etc.).
        _rej_vids: set[str] = set()
        _rej_urls: set[str] = set()
        for r in _rej_raw:
            r = str(r).strip()
            if not r:
                continue
            _rej_urls.add(r.lower())
            # Extract video_id from URL
            vid = _video_id_from_url(r)
            if vid:
                _rej_vids.add(vid)
            else:
                # Might be a bare video_id or title
                _rej_vids.add(r)
        candidates: list[dict] = []
        def _is_rejected(vid: str, curl: str) -> bool:
            if vid and vid in _rej_vids:
                return True
            if curl and curl.lower() in _rej_urls:
                return True
            # Also check if the URL contains a rejected video_id
            if curl and vid:
                curl_vid = _video_id_from_url(curl)
                if curl_vid and curl_vid in _rej_vids:
                    return True
            return False
        for c in self._api_search_candidates(query):
            vid = c.get("video_id", "")
            curl = c.get("url", "")
            if _is_rejected(vid, curl):
                logger.info("[YT_CANDIDATE] excluded (rejected) vid=%s title=%s", vid, c.get("title", ""))
                continue
            candidates.append(c)
        for _attempt in range(3):
            scrape = safe_run_async(conn.execute_script(tab_id, "search_results"))
            if scrape.success and isinstance(scrape.message, list):
                for item in scrape.message:
                    if isinstance(item, dict) and item.get("title") and item.get("url"):
                        vid = item.get("video_id", "")
                        curl = item.get("url", "")
                        if _is_rejected(vid, curl):
                            continue
                        candidates.append(item)
                if candidates:
                    break
            time.sleep(0.8)
        if not candidates:
            logger.info("[YT_CANDIDATE] no candidates scraped for query=%s (rejected=%d)", query, len(_rej_raw))
            return None

        # Deduplicate by video_id: the same video with different URL params
        # (e.g. &list=..., &t=..., ?si=...) must not appear as separate
        # candidates. Keep the first occurrence (API results preferred over
        # browser-scrape since they carry richer metadata).
        _seen_vids: set[str] = set()
        _deduped: list[dict] = []
        for c in candidates:
            vid = c.get("video_id", "") or _video_id_from_url(c.get("url", ""))
            if vid and vid in _seen_vids:
                continue
            if vid:
                _seen_vids.add(vid)
            _deduped.append(c)
        if len(_deduped) < len(candidates):
            logger.info("[YT_CANDIDATE] dedup %d -> %d candidates", len(candidates), len(_deduped))
        candidates = _deduped

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
                    view_count=c.get("view_count", 0) or 0,
                    published_at=c.get("published_at", "") or "",
                ),
                -len(c.get("title", "") or ""),
            )

        best = max(candidates, key=_candidate_key)
        score, _ = _candidate_key(best)
        # Allow weak-but-relevant candidates (score > -5) rather than
        # rejecting everything at score <= 0 which causes blind bootstrap.
        # A score of -5 means the candidate has SOME relevance signal.
        if score <= -5:
            logger.info("[YT_CANDIDATE] best score=%d too weak for query=%s title=%s",
                        score, query, best.get("title", ""))
            return None
        logger.info("[YT_CANDIDATE] query=%s selected=%s score=%d video_id=%s rejected_count=%d",
                    query, best.get("title", ""), score, best.get("video_id", ""), len(_rej_raw))
        return best

    def _browser_fallback(self, query: str) -> MediaResult:
        """Open the ACTUAL best video in the default browser and report truthfully.

        Without the connector KIO cannot verify playback, so it must never claim
        PLAYING (that claim was a lie: the old fallback opened a search page and
        said 'Playing X.').
        """
        from mini_kio.core.browser_operator import open_url
        encoded = urllib.parse.quote_plus(query.strip())
        watch_url = _resolve_search_to_watch_url(query.strip())
        opened = open_url(watch_url) if watch_url else open_url(_YOUTUBE_SEARCH_URL.format(encoded=encoded))
        if not opened.get("success"):
            return MediaResult(success=False, error=opened.get("message", "Couldn't open YouTube"), player="youtube")
        display = query.strip()
        if display.startswith(("http://", "https://", "www.")):
            display = "the requested media"
        self._session = MediaSession(
            player=PlayerType.YOUTUBE,
            tab_id=None,
            state=MediaState.IDLE,
            query=query.strip(),
            title=query.strip(),
            url=watch_url or _YOUTUBE_SEARCH_URL.format(encoded=encoded),
            domain_hint="youtube.com",
            media_type=self._detect_type(query),
        )
        self._session.touch()
        _display_label = user_facing_media_label(display) or "the requested media"
        _verdict = f"Opened {_display_label} in your browser."
        if not watch_url:
            _verdict = f"Opened YouTube search results for {_display_label} in your browser."
        _verdict += " I can't verify playback without the browser extension."
        return MediaResult(success=True, message=_verdict, session=self._session, player="youtube")

    def play(self, query: str, **kwargs) -> MediaResult:
        logger.info("[ROOT_YT] ENTER query=%s kwargs=%s", query, kwargs)
        conn = self._get_conn()
        if not conn:
            # No connector object at all (disabled / failed to construct).
            if config.BROWSER_CONNECTOR_ENABLED:
                logger.info("[ROOT_YT] RETURN=R1 conn=None -> configured connector unavailable")
                return MediaResult(success=False, error="Browser Connector not available", player="youtube")
            return self._browser_fallback(query)
        if not conn.is_connected():
            if config.BROWSER_CONNECTOR_ENABLED:
                logger.info("[ROOT_YT] RETURN=R2 conn_not_connected -> configured connector unavailable")
                return MediaResult(success=False, error="Browser Connector not connected", player="youtube")
            # No Chrome extension attached and connector support is disabled.
            # Open the ACTUAL best video in the default browser and report
            # truthfully — without the connector KIO cannot verify playback, so
            # it must never claim PLAYING (that claim was a lie: the old
            # fallback opened a search page and said 'Playing X.').
            return self._browser_fallback(query)

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
            _tab_lost: Optional[str] = None
            # BUG 4: the play/verification loop must run on the RAW connector.
            # VerifiedConnector re-probes Chrome for up to its full deadline on
            # every play-family execute_script call; retrying through it turned
            # a genuine autoplay failure into a 5x10s+ spiral. The provider's
            # own acceptance (playerState==1, status, currentTime progression,
            # stabilization) is the state verification for playback, so the
            # raw loop keeps truthfulness while bounding the worst case.
            play_conn = self._get_raw_conn() or conn
            if not tab_id:
                logger.info("[ROOT_YT] tab_id is None — no tab returned by connector")
            else:
                # Brief pause for the page to render
                time.sleep(0.3)

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
                    _selected = self._select_best_candidate(
                        tab_id, clean_query, media_type=_mt_hint,
                        rejected_ids=kwargs.get("rejected_ids") or [],
                    )
                _selected_video_id = (_selected or {}).get("video_id", "") or ""
                _selected_title = (_selected or {}).get("title", "") or ""
                # Media contract: an exact video was resolved (user URL parsed
                # to a video id, or an intelligent candidate was selected). A
                # playback failure on the resolved tab must NOT fall back to a
                # generic browser search page (MediaManager respects no_fallback).
                _resolved_exact = _is_direct_url or bool(_selected)
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
                        _BOOTSTRAP_DELAYS = (1.0, 1.5, 2.0)  # staged waits
                        for _ba, _bs_delay in enumerate(_BOOTSTRAP_DELAYS):
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
                                time.sleep(_bs_delay)
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

                        # Poll for video element with staged readiness polling.
                        # Warm paths resolve fast (0.5s); cold YouTube SPA loads
                        # get progressively longer waits. Total budget: ~8s.
                        # RC8: when the identity gate already failed, do NOT
                        # attempt play on the wrong video — fail fast.
                        _PLAY_POLL_DELAYS = (0.5, 0.7, 1.0, 1.5, 2.0)  # staged waits
                        for attempt, _poll_delay in enumerate(_PLAY_POLL_DELAYS):
                            if _identity_fail is not None:
                                logger.info("[ROOT_YT] skipping play attempts (identity_fail)")
                                break
                            time.sleep(_poll_delay)

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
                            play_result = safe_run_async(play_conn.execute_script(tab_id, "play"))
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

                                _player_state_result = safe_run_async(play_conn.execute_script(tab_id, "get_player_state"))
                                _player_state = -1
                                if _player_state_result.success and isinstance(_player_state_result.message, dict):
                                    _player_state = _player_state_result.message.get("playerState", -1)
                                logger.info("[PLAY_VERIFY] actual_player_state=%s [PLAYER_STATE_DEBUG]", _player_state)

                                # Determine if playing based on multiple sources.
                                # Truthful-playback contract: the extension play
                                # script (build 0.3.3+) reports player_status
                                # 'playing' ONLY when it OBSERVED the element
                                # unpaused with currentTime advancing (it performs
                                # its own in-page stabilization + audio-restore
                                # re-verification). A payload claiming 'playing'
                                # while paused=True is therefore SELF-
                                # CONTRADICTORY (a legacy/stale snapshot) —
                                # accepting it is the exact false-success that
                                # reported "Playing" while the element sat at
                                # 0:00/paused. Only YouTube's own player state
                                # (getPlayerState()==1) overrides paused, and it
                                # is authoritative.
                                _accepted_reason = "none"
                                _is_playing = False

                                if _player_state == 1 and not _paused: # YouTube Iframe API state for playing — authoritative, but the element must still be observed unpaused
                                    _is_playing = True
                                    _accepted_reason = "player_state_1"
                                elif _player_status_from_script == "playing" and not _paused:
                                    _is_playing = True
                                    _accepted_reason = "script_player_status_playing"
                                elif _status == "playing" and not _paused:
                                    _is_playing = True
                                    _accepted_reason = "legacy_status_playing"
                                elif _status == "ad_playing" and not _paused and _rs and _rs >= 3:
                                    # YouTube player sometimes misreports actual video as ad_playing
                                    # when readyState>=3 (have future data) and paused=False,
                                    # the video IS playing despite the misleading status label.
                                    _is_playing = True
                                    _accepted_reason = "ad_playing_but_playing"

                                # (stabilization removed: the 0.3.3+ script already
                                # stabilizes in-page and re-verifies playback after
                                # restoring audio; provider-side re-play retries of
                                # a self-contradictory payload only produced the
                                # multi-minute false-success spiral.)

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
                                elif msg.get("status") == "ad_playing":
                                    # An advertisement is playing instead of the
                                    # target video. Wait briefly for the ad to
                                    # finish, then re-check. Bounded: max 2 ad
                                    # cycles to avoid infinite wait on long ads.
                                    logger.info("[ROOT_YT] AD_WAIT attempt=%d", attempt + 1)
                                    if attempt < 4:
                                        time.sleep(3.0)
                                        continue
                                    # Ad persisted through retry budget — re-verify
                                    # the TARGET video is now playing (not still an
                                    # ad). Do NOT blindly accept as PLAYING.
                                    _recheck = safe_run_async(play_conn.execute_script(tab_id, "play"))
                                    if _recheck.success and isinstance(_recheck.message, dict):
                                        _rc_status = _recheck.message.get("status")
                                        _rc_paused = _recheck.message.get("paused", True)
                                        _rc_player = -1
                                        _rc_ps = safe_run_async(play_conn.execute_script(tab_id, "get_player_state"))
                                        if _rc_ps.success and isinstance(_rc_ps.message, dict):
                                            _rc_player = _rc_ps.message.get("playerState", -1)
                                        _rc_playing = (
                                            (_rc_player == 1 and not _rc_paused) or
                                            (_rc_status == "playing" and not _rc_paused)
                                        )
                                        logger.info("[ROOT_YT] AD_REVERIFY status=%s paused=%s playerState=%s playing=%s",
                                                    _rc_status, _rc_paused, _rc_player, _rc_playing)
                                        if _rc_playing and _rc_status != "ad_playing":
                                            playback_state = MediaState.PLAYING
                                            if self._session:
                                                self._session.current_time = _recheck.message.get("currentTime")
                                                self._session.duration = _recheck.message.get("duration")
                                            break
                                        # Still an ad or not playing — report as
                                        # degraded (user needs to know the ad is
                                        # still running, not fabricate success).
                                        logger.info("[ROOT_YT] AD_PERSISTED after retry budget")
                                        playback_state = MediaState.READY
                                        break
                                    # Re-verify script failed — degrade honestly.
                                    playback_state = MediaState.READY
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
                                elif msg.get("name") == "PlayerNotReady" and attempt < 4:
                                    # A cold YouTube watch page can take longer
                                    # than the script's readiness window to attach
                                    # media data (readyState stays 0 while the SPA
                                    # warms up). That is a TIMING signal, not a
                                    # verdict: retry within the bounded loop, same
                                    # tab, same resolved video.
                                    logger.info("[ROOT_YT] PLAY_LOOP_EXIT=player_not_ready_retry attempt=%d", attempt + 1)
                                    continue
                                elif msg.get("name") == "PlayerNotReady":
                                    logger.info("[ROOT_YT] PLAY_LOOP_EXIT=player_not_ready_exhausted attempt=%d", attempt + 1)
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
                                _err_lower = _err.lower()
                                # BUG 5: a lost tab is a DEFINITIVE condition, not
                                # a timing signal. Chrome reports "No tab with id" /
                                # "Cannot access contents of the page" when the tab
                                # was closed/crashed mid-operation. Stop retrying,
                                # classify it, and let the caller fail truthfully.
                                _TAB_LOST_MARKERS = (
                                    "no tab with id", "cannot access contents",
                                    "tab was closed", "no tab", "tab not found",
                                    "could not access the tab",
                                )
                                if any(k in _err_lower for k in _TAB_LOST_MARKERS):
                                    _tab_lost = "The YouTube tab closed during playback."
                                    break
                                # Otherwise the watch page may still be building its
                                # <video> element (or the extension payload may be
                                # a transient non-state). A no-media / not-yet-
                                # playing failure is a timing signal, not a verdict:
                                # retry within the bounded loop and only give up
                                # after the last attempt. A definitive verification
                                # verdict ("did not advance" / "cannot read
                                # playback") is NOT retried — retrying it is what
                                # produced the multi-minute spiral (BUG 4).
                                _retryable = any(
                                    k in _err_lower
                                    for k in (
                                        "no media", "returned no payload",
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
            # Never report success on the wrong video. The detailed mismatch (with
            # video IDs) stays in the diagnostics log; the user-facing error is
            # natural and never exposes internal IDs.
            if _identity_fail:
                logger.info("[ROOT_YT] RETURN=R9 identity_fail %s", _identity_fail)
                _label = user_facing_media_label(clean_query) or _selected_title or "the requested media"
                return MediaResult(
                    success=False,
                    error=f"I couldn't start {_label}.",
                    player="youtube",
                    no_fallback=_resolved_exact,
                )

            # BUG 5: the tab disappeared mid-operation. Report the loss
            # truthfully instead of "Opened on YouTube" (which would be false
            # — the tab is gone) or a generic script error. The resolved media
            # is gone with it, so no other provider can take over.
            if _tab_lost:
                logger.info("[ROOT_YT] RETURN=R10 tab_lost %s", _tab_lost)
                return MediaResult(
                    success=False,
                    error=_tab_lost,
                    player="youtube",
                    no_fallback=_resolved_exact,
                )

            self._tab_id = tab_id
            # RC8: the session's canonical URL must be the ACTUAL loaded watch
            # URL (the video really playing), not the search-results URL.
            _session_url = _actual_watch_url or url

            # Read the actual page title after playback — this is the TRUE
            # media identity regardless of whether it was a direct URL or
            # search result. The page title is the actual video title.
            _page_title = ""
            _page_channel = ""
            if playback_state in (
                MediaState.PLAYING, MediaState.READY, MediaState.PAUSED,
            ):
                try:
                    _info = safe_run_async(play_conn.execute_script(tab_id, "get_page_info"))
                    if _info.success and isinstance(_info.message, dict):
                        _pt = str(_info.message.get("title") or "").strip()
                        if _pt and _pt.lower() not in ("youtube", "- youtube"):
                            # Strip Chrome tab ID prefix like "(30) " and YouTube suffix
                            _pt = re.sub(r"^\(\d+\)\s*", "", _pt)  # remove "(30) " prefix
                            _pt = re.sub(r"\s*[-|–]\s*YouTube\s*$", "", _pt).strip()
                            if _pt and _pt.lower() not in ("youtube", "- youtube"):
                                _page_title = _pt
                        _page_channel = str(_info.message.get("channel") or "").strip()
                except Exception:
                    pass

            if playback_state == MediaState.PLAYING:
                # Use the ACTUAL candidate metadata for the response, not the
                # search query. The selected candidate has the real title/channel.
                _candidate_title = (_selected or {}).get("title", "") or ""
                _candidate_channel = (_selected or {}).get("channel", "") or ""
                # Clean title: strip " - YouTube" suffix
                _clean_title = re.sub(r"\s*[-|]\s*YouTube\s*$", "", _candidate_title).strip() if _candidate_title else ""
                # Session title: prefer page title (actual loaded video), then candidate, then query
                # Never use bare "YouTube" as a title
                _session_title = _page_title or _clean_title or _title
                if _session_title.lower().strip() in ("youtube", "- youtube", ""):
                    _session_title = _clean_title or user_facing_media_label(clean_query) or "the requested media"
                # Artist: prefer page channel, then candidate channel, then parsed artist
                _session_artist = _page_channel or _candidate_channel or _artist

                self._session = MediaSession(
                    player=PlayerType.YOUTUBE,
                    tab_id=tab_id,
                    state=playback_state,
                    query=clean_query,
                    title=_session_title,
                    artist=_session_artist,
                    url=_session_url,
                    domain_hint="youtube.com",
                    media_type=self._detect_type(clean_query),
                )
                self._session.touch()

                # Build user-facing response from ACTUAL metadata
                # Vary response wording based on context for natural feel
                import random as _rnd
                _display_title = _clean_title or _page_title or user_facing_media_label(clean_query) or "the requested media"
                _mt = self._detect_type(clean_query)
                _is_rejection = bool(kwargs.get("rejected_ids"))
                if _is_rejection:
                    # After rejection: varied "trying this instead" responses
                    _rej_variants = [
                        f"How about this one: {_display_title}.",
                        f"Trying something different: {_display_title}.",
                        f"Let's try {_display_title} instead.",
                    ]
                    message = _rnd.choice(_rej_variants)
                elif _session_artist:
                    # With known artist/channel
                    _with_artist_variants = [
                        f"Playing {_display_title} by {_session_artist}.",
                        f"{_display_title} by {_session_artist}.",
                        f"Now playing: {_display_title} by {_session_artist}.",
                    ]
                    message = _rnd.choice(_with_artist_variants)
                else:
                    # Without artist
                    _no_artist_variants = [
                        f"Playing {_display_title}.",
                        f"{_display_title}.",
                        f"Now playing: {_display_title}.",
                    ]
                    message = _rnd.choice(_no_artist_variants)
                logger.info("[ROOT_YT] FINAL_RETURN playback_state=%s success=True media_type=%s message=%s candidate_title=%s candidate_channel=%s",
                            playback_state.value if isinstance(playback_state, MediaState) else str(playback_state),
                            _mt.value, message, _clean_title, _candidate_channel)
                return MediaResult(
                    success=True,
                    message=message,
                    session=self._session,
                    player="youtube",
                )

            # Truthful failure: playback was NOT established on the resolved tab.
            # Report it naturally (never the internal URL/video ID) and set
            # no_fallback so MediaManager does not abandon the resolved media
            # for a generic browser search page.
            _label = user_facing_media_label(clean_query) or _page_title or "the requested media"
            _err = f"I couldn't start {_label}."
            logger.info("[ROOT_YT] FINAL_RETURN failure error=%s", _err)
            return MediaResult(
                success=False,
                error=_err,
                player="youtube",
                no_fallback=_resolved_exact,
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

    def _verify_playback_after_navigation(self) -> bool:
        """After navigation (next/prev), verify the new video is actually playing.
        Bounded: one wait + one play attempt, never a loop."""
        conn = self._get_raw_conn() or self._get_conn()
        tab_id = self._resolve_tab_id()
        if not conn or not tab_id:
            return False
        try:
            # Wait briefly for the new page to render
            time.sleep(1.5)
            # Check player state
            status = safe_run_async(conn.execute_script(tab_id, "status"))
            if status.success and isinstance(status.message, dict):
                ps = status.message.get("playerState")
                paused = status.message.get("paused", True)
                # playerState 1 = PLAYING, 3 = BUFFERING (transient → will play)
                if ps in (1, 3) and not paused:
                    return True
                # If paused or idle, try to play
                play_res = safe_run_async(conn.execute_script(tab_id, "play"))
                if play_res.success and isinstance(play_res.message, dict):
                    ps2 = play_res.message.get("status")
                    if ps2 == "playing":
                        return True
            # One more brief check
            time.sleep(0.5)
            status2 = safe_run_async(conn.execute_script(tab_id, "status"))
            if status2.success and isinstance(status2.message, dict):
                ps3 = status2.message.get("playerState")
                paused3 = status2.message.get("paused", True)
                return ps3 in (1, 3) and not paused3
        except Exception as exc:
            logger.warning("[PLAYBACK_VERIFY] failed: %s", exc)
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
                # Verify playback actually started on the new video.
                playback_ok = self._verify_playback_after_navigation()
                if playback_ok:
                    res.message = "Next track."
                else:
                    # Navigation happened but playback didn't start —
                    # partial success with honest caveat.
                    res.message = "Navigated to next video, but playback didn't start automatically."
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
                playback_ok = self._verify_playback_after_navigation()
                if playback_ok:
                    res.message = "Previous track."
                else:
                    res.message = "Navigated to previous video, but playback didn't start automatically."
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
                elif "teaser" in _ql:
                    _st = "teaser"
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

                # Deduplicate by video_id (same video, different URL params)
                _seen: set[str] = set()
                _deduped: list[dict] = []
                for c in candidates:
                    vid = c.get("video_id", "") or _video_id_from_url(c.get("url", ""))
                    if vid and vid in _seen:
                        continue
                    if vid:
                        _seen.add(vid)
                    _deduped.append(c)
                candidates = _deduped

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
                    message=f"YouTube search: {title}",
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
                    self._session.state = MediaState.PLAYING
                    self._session.touch()
                    return self._session
                else:
                    # Tab exists but is not audible. A paused video is NOT audible —
                    # do NOT override PAUSED to STOPPED (this was the root cause of
                    # resume failure: the registry lost track of the paused session).
                    # Only override PLAYING→STOPPED (the user may have stopped playback
                    # externally). PAUSED stays PAUSED so resume can find it.
                    if self._session.state == MediaState.PLAYING:
                        self._session.state = MediaState.STOPPED
                        self._session.touch()
                        return None
                    # PAUSED or READY: tab exists, session is valid — return it.
                    self._session.touch()
                    return self._session
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
                    # Truthful play/resume verdict (BUG 3 contract): the play
                    # script reports status='paused' when playback was NOT
                    # observed in the final state. For a play/resume request a
                    # paused outcome means the action did NOT take effect — it
                    # must be a truthful failure, never a success that Media
                    # Manager would echo as "Resumed.".
                    if action in ("play", "resume") and msg.get("status") != "playing":
                        # After pause, the player may briefly report 'paused'
                        # while transitioning to 'playing'. Retry with increasing
                        # delays (resume is a state-transition, not a fresh search).
                        # Also handle ad_playing: the extension may detect residual
                        # ad DOM elements even when the content is actually playing.
                        _original_status = msg.get("status")
                        logger.info("[MM_TRANSPORT] play/resume not immediately observed: status=%s -- retrying", _original_status)

                        # Accept ad_playing when the element is clearly not paused
                        # and has progress (currentTime > 0) — this means the content
                        # IS playing despite the ad DOM residual. Live proof: after
                        # pause→resume, the extension's ad detectors fire on stale
                        # DOM elements while the actual video resumes.
                        if _original_status == "ad_playing" and not msg.get("paused", True) and msg.get("currentTime", 0) > 0:
                            logger.info("[MM_TRANSPORT] ad_playing but content confirmed playing (currentTime=%s)", msg.get("currentTime"))
                            msg["status"] = "playing"
                            msg["paused"] = False

                        if msg.get("status") != "playing":
                            for _retry_delay in (0.5, 1.0, 1.5):
                                time.sleep(_retry_delay)
                                # Use sample_media for retries — it's more reliable
                                # than get_player_state which returns -1 during
                                # YouTube SPA transitions.
                                _retry = safe_run_async(conn.execute_script(tab_id, "sample_media"))
                                if _retry.success and isinstance(_retry.message, dict):
                                    _rm = _retry.message
                                    _retry_status = _rm.get("status", "")
                                    _retry_paused = _rm.get("paused", True)
                                    _retry_ct = _rm.get("currentTime", 0)
                                    # Playing: not paused AND has progress OR reports playing
                                    if (_retry_status == "playing" and not _retry_paused and _retry_ct > 0):
                                        logger.info("[MM_TRANSPORT] sample_media confirmed playing (status=%s, paused=%s, ct=%s) after %ss",
                                                    _retry_status, _retry_paused, _retry_ct, _retry_delay)
                                        msg["status"] = "playing"
                                        msg["paused"] = False
                                        break
                                    # Also accept: not paused with playerState=1
                                    _ps = _rm.get("playerState", -1)
                                    if _ps == 1 and not _retry_paused:
                                        logger.info("[MM_TRANSPORT] sample_media playerState=1 confirmed playing after %ss", _retry_delay)
                                        msg["status"] = "playing"
                                        msg["paused"] = False
                                        break
                                    logger.info("[MM_TRANSPORT] retry sample_media status=%s paused=%s ct=%s ps=%s after %ss",
                                                _retry_status, _retry_paused, _retry_ct, _ps, _retry_delay)

                        # Second pass: if still not playing, try get_player_state
                        # (some YouTube pages only expose the Iframe API, not sample_media)
                        if msg.get("status") != "playing":
                            for _retry_delay2 in (0.5, 1.0):
                                time.sleep(_retry_delay2)
                                _retry2 = safe_run_async(conn.execute_script(tab_id, "get_player_state"))
                                if _retry2.success and isinstance(_retry2.message, dict):
                                    _ps2 = _retry2.message.get("playerState", -1)
                                    if _ps2 == 1:
                                        logger.info("[MM_TRANSPORT] playerState=1 confirmed playing after %ss", _retry_delay2)
                                        msg["status"] = "playing"
                                        msg["paused"] = False
                                        break
                                    logger.info("[MM_TRANSPORT] retry get_player_state=%s after %ss", _ps2, _retry_delay2)

                        if msg.get("status") != "playing":
                            # Final attempt: re-run the full play script (not just
                            # get_player_state) to trigger the extension's play logic.
                            try:
                                _final_retry = safe_run_async(play_conn.execute_script(tab_id, "play"))
                                if _final_retry.success and isinstance(_final_retry.message, dict):
                                    _fr_msg = _final_retry.message
                                    _fr_status = _fr_msg.get("status", "")
                                    _fr_paused = _fr_msg.get("paused", True)
                                    _fr_ct = _fr_msg.get("currentTime", 0)
                                    if _fr_status == "playing" and not _fr_paused:
                                        msg.update(_fr_msg)
                                        logger.info("[MM_TRANSPORT] final play script retry succeeded")
                                    elif _fr_status == "ad_playing" and not _fr_paused and _fr_ct > 0:
                                        msg["status"] = "playing"
                                        msg["paused"] = False
                                        logger.info("[MM_TRANSPORT] final play retry: ad_playing but content playing")
                            except Exception:
                                pass

                        if msg.get("status") != "playing":
                            logger.info("[MM_TRANSPORT] all retries exhausted for %s", action)
                            return MediaResult(
                                success=False,
                                error="I couldn't resume playback." if action == "resume" else "I couldn't start playback.",
                                session=self._session,
                                player="youtube",
                            )
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
        if any(kw in ql for kw in ("trailer", "teaser")):
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
