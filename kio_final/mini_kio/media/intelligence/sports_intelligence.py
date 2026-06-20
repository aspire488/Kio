from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from mini_kio.media.intelligence.media_intelligence_models import SportsMode, EventRecord, EventStatus
from mini_kio.media.intelligence.sports_event_extractor import extract_events, best_event


# ── mode detection ─────────────────────────────────────────────────────────────

_MODE_PATTERNS: list[tuple[SportsMode, re.Pattern]] = [
    (SportsMode.STANDINGS, re.compile(r"\b(standing|table|league table|ranking|points table)\b", re.I)),
    (SportsMode.FIXTURES,  re.compile(r"\b(fixture|upcoming|schedule|next match|when.*play)\b", re.I)),
    (SportsMode.RESULTS,   re.compile(r"\b(result|score|scoreline|final score|what.*score)\b", re.I)),
    (SportsMode.HIGHLIGHTS,re.compile(r"\b(highlight|clip|watch|video of)\b", re.I)),
]


def detect_sports_mode(query: str) -> SportsMode:
    for mode, pattern in _MODE_PATTERNS:
        if pattern.search(query):
            return mode
    return SportsMode.GENERAL


# ── competition detection ──────────────────────────────────────────────────────

_COMPETITIONS = {
    "world cup": "FIFA World Cup",
    "fifa": "FIFA World Cup",
    "premier league": "Premier League",
    "champions league": "UEFA Champions League",
    "la liga": "La Liga",
    "bundesliga": "Bundesliga",
    "serie a": "Serie A",
    "nba": "NBA",
    "nfl": "NFL",
    "ipl": "IPL",
}


def detect_competition(query: str) -> str:
    q = query.lower()
    for key, label in _COMPETITIONS.items():
        if key in q:
            return label
    return ""


# ── response builder ───────────────────────────────────────────────────────────

@dataclass
class SportsIntelligenceResponse:
    mode: SportsMode
    competition: str
    response_text: str
    followup_options: list[str]
    events: list[EventRecord]


def build_sports_response(
    raw_text: str,
    query: str,
    competition_hint: str = "",
) -> SportsIntelligenceResponse:
    mode = detect_sports_mode(query)
    competition = competition_hint or detect_competition(query) or detect_competition(raw_text)
    events = extract_events(raw_text, competition)

    if mode == SportsMode.RESULTS:
        return _build_results(events, competition)
    if mode == SportsMode.FIXTURES:
        return _build_fixtures(events, competition)
    if mode == SportsMode.STANDINGS:
        return _build_standings(raw_text, competition)
    if mode == SportsMode.HIGHLIGHTS:
        return _build_highlights(events, competition)
    return _build_general(events, raw_text, competition)


def _build_results(events: list[EventRecord], competition: str) -> SportsIntelligenceResponse:
    completed = [e for e in events if e.status == EventStatus.COMPLETED]
    if not completed:
        text = f"⚽ {competition or 'Sports'} Results\n\nNo completed results found."
        opts = ["show fixtures", "show standings"]
    else:
        lines = [f"⚽ {competition or 'Results'}\n"]
        for e in sorted(completed, key=lambda x: x.timestamp, reverse=True)[:5]:
            lines.append(f"{e.entity_a} {e.score_a}–{e.score_b} {e.entity_b}")
        text = "\n".join(lines)
        top = best_event(completed)
        opts = [f"show {top.entity_a} highlights", "show standings", "show fixtures"] if top else ["show standings", "show fixtures"]
    return SportsIntelligenceResponse(SportsMode.RESULTS, competition, text, opts, completed)


def _build_fixtures(events: list[EventRecord], competition: str) -> SportsIntelligenceResponse:
    upcoming = [e for e in events if e.status == EventStatus.UPCOMING]
    if not upcoming:
        text = f"📅 {competition or 'Fixtures'}\n\nNo upcoming fixtures found."
        opts = ["show results", "show standings"]
    else:
        lines = [f"📅 {competition or 'Upcoming Fixtures'}\n"]
        for e in upcoming[:5]:
            lines.append(f"{e.entity_a} vs {e.entity_b}")
        text = "\n".join(lines)
        opts = ["show results", "show standings", "show highlights"]
    return SportsIntelligenceResponse(SportsMode.FIXTURES, competition, text, opts, upcoming)


def _build_standings(raw_text: str, competition: str) -> SportsIntelligenceResponse:
    # standings are in raw text — extract table-like content
    lines = raw_text.splitlines()
    table_lines = [l.strip() for l in lines if re.search(r"\d+\s+\w", l)][:8]
    if table_lines:
        text = f"🏆 {competition or 'Standings'}\n\n" + "\n".join(table_lines)
    else:
        # fallback: just use first 150 chars of raw
        snippet = raw_text[:200].replace("\n", " ").strip()
        text = f"🏆 {competition or 'Standings'}\n\n{snippet}"
    opts = ["show results", "show fixtures", "show highlights"]
    return SportsIntelligenceResponse(SportsMode.STANDINGS, competition, text, opts, [])


def _build_highlights(events: list[EventRecord], competition: str) -> SportsIntelligenceResponse:
    completed = [e for e in events if e.status == EventStatus.COMPLETED]
    top = best_event(completed) if completed else None
    if top:
        text = f"🎬 {competition or 'Highlights'}\n\n{top.display()}\n\nPlaying highlights now."
        opts = ["show standings", "show fixtures", f"show {top.entity_a} interview"]
    else:
        text = f"🎬 {competition or 'Highlights'}\n\nNo recent completed matches for highlights."
        opts = ["show results", "show fixtures"]
    return SportsIntelligenceResponse(SportsMode.HIGHLIGHTS, competition, text, opts, completed)


def _build_general(events: list[EventRecord], raw_text: str, competition: str) -> SportsIntelligenceResponse:
    completed = [e for e in events if e.status == EventStatus.COMPLETED]
    upcoming = [e for e in events if e.status == EventStatus.UPCOMING]
    lines = [f"🏆 {competition or 'Sports Update'}\n"]

    if completed:
        top = best_event(completed)
        lines.append(f"{top.display()}.")
    if upcoming:
        nxt = upcoming[0]
        lines.append(f"\nNext up:\n{nxt.entity_a} vs {nxt.entity_b}.")

    if not completed and not upcoming:
        snippet = raw_text[:200].replace("\n", " ").strip()
        lines.append(snippet)

    opts = []
    if completed:
        top = best_event(completed)
        opts.append(f"show {top.entity_a} highlights")
    opts += ["show standings", "show fixtures"]
    if completed:
        opts.append("show results")

    text = "\n".join(lines)
    return SportsIntelligenceResponse(SportsMode.GENERAL, competition, text, opts[:4], events)
