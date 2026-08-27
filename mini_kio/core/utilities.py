"""
utilities.py — Deterministic Utility Owners (canonical)
========================================================

KIO owns simple utility requests itself and answers them with clean,
normalized results — they NEVER fall through to generic web search, and a
provider's raw UI/JSON/text never becomes the user-facing reply.

    what's the time                    -> "It's 8:52 PM."
    what time is it in New York        -> "It's 6:52 PM in New York."
    what's the date / what day is it   -> "It's Thursday, August 15."
    what's the weather                 -> live Open-Meteo answer (no key), honest offline fallback
    convert 100 dollars to euros       -> live ECB rate (Frankfurter, no key), static fallback
    latest version of requests         -> live PyPI answer (no key), installed-version comparison
    latest releases of owner/repo      -> GitHub releases.atom / PyPI RSS (no key)
    what's new in fastapi              -> recent releases from the project feed

Every answer returns a canonical internal structure
    {"success": bool, "message": str, "type": "time"|"date"|"weather"|"convert"|
     "calculate"|"package"|"feed", "location": ..., "datetime": ..., ...}
so the conversational layer decides what to expose. Nothing here invokes a
browser or the LLM — pure stdlib + the local clock, plus a few no-key
HTTPS providers (Open-Meteo weather, Frankfurter FX, PyPI, RSS/Atom feeds).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── timezone resolution ──────────────────────────────────────────────────────
# City/region -> (IANA name, base UTC offset in hours, DST scheme).
# DST scheme: "us" (2nd Sun Mar -> 1st Sun Nov), "eu" (last Sun Mar -> last
# Sun Oct), "au" (1st Sun Oct -> 1st Sun Apr), None (no DST modeled).
_LOCATIONS: dict[str, tuple[str, float, Optional[str]]] = {
    "new york": ("America/New_York", -5.0, "us"),
    "nyc": ("America/New_York", -5.0, "us"),
    "new york city": ("America/New_York", -5.0, "us"),
    "boston": ("America/New_York", -5.0, "us"),
    "miami": ("America/New_York", -5.0, "us"),
    "washington": ("America/New_York", -5.0, "us"),
    "atlanta": ("America/New_York", -5.0, "us"),
    "los angeles": ("America/Los_Angeles", -8.0, "us"),
    "la": ("America/Los_Angeles", -8.0, "us"),
    "san francisco": ("America/Los_Angeles", -8.0, "us"),
    "seattle": ("America/Los_Angeles", -8.0, "us"),
    "las vegas": ("America/Los_Angeles", -8.0, "us"),
    "chicago": ("America/Chicago", -6.0, "us"),
    "austin": ("America/Chicago", -6.0, "us"),
    "dallas": ("America/Chicago", -6.0, "us"),
    "houston": ("America/Chicago", -6.0, "us"),
    "denver": ("America/Denver", -7.0, "us"),
    "phoenix": ("America/Phoenix", -7.0, None),
    "toronto": ("America/Toronto", -5.0, "us"),
    "ottawa": ("America/Toronto", -5.0, "us"),
    "montreal": ("America/Toronto", -5.0, "us"),
    "vancouver": ("America/Vancouver", -8.0, "us"),
    "mexico city": ("America/Mexico_City", -6.0, None),
    "london": ("Europe/London", 0.0, "eu"),
    "manchester": ("Europe/London", 0.0, "eu"),
    "paris": ("Europe/Paris", 1.0, "eu"),
    "berlin": ("Europe/Berlin", 1.0, "eu"),
    "frankfurt": ("Europe/Berlin", 1.0, "eu"),
    "madrid": ("Europe/Madrid", 1.0, "eu"),
    "barcelona": ("Europe/Madrid", 1.0, "eu"),
    "rome": ("Europe/Rome", 1.0, "eu"),
    "milan": ("Europe/Rome", 1.0, "eu"),
    "amsterdam": ("Europe/Amsterdam", 1.0, "eu"),
    "brussels": ("Europe/Brussels", 1.0, "eu"),
    "zurich": ("Europe/Zurich", 1.0, "eu"),
    "geneva": ("Europe/Zurich", 1.0, "eu"),
    "vienna": ("Europe/Vienna", 1.0, "eu"),
    "stockholm": ("Europe/Stockholm", 1.0, "eu"),
    "copenhagen": ("Europe/Copenhagen", 1.0, "eu"),
    "oslo": ("Europe/Oslo", 1.0, "eu"),
    "warsaw": ("Europe/Warsaw", 1.0, "eu"),
    "prague": ("Europe/Prague", 1.0, "eu"),
    "budapest": ("Europe/Budapest", 1.0, "eu"),
    "athens": ("Europe/Athens", 2.0, "eu"),
    "istanbul": ("Europe/Istanbul", 3.0, None),
    "moscow": ("Europe/Moscow", 3.0, None),
    "kiev": ("Europe/Kiev", 2.0, "eu"),
    "dubai": ("Asia/Dubai", 4.0, None),
    "abu dhabi": ("Asia/Dubai", 4.0, None),
    "mumbai": ("Asia/Kolkata", 5.5, None),
    "delhi": ("Asia/Kolkata", 5.5, None),
    "new delhi": ("Asia/Kolkata", 5.5, None),
    "bengaluru": ("Asia/Kolkata", 5.5, None),
    "bangalore": ("Asia/Kolkata", 5.5, None),
    "chennai": ("Asia/Kolkata", 5.5, None),
    "hyderabad": ("Asia/Kolkata", 5.5, None),
    "kolkata": ("Asia/Kolkata", 5.5, None),
    "india": ("Asia/Kolkata", 5.5, None),
    "karachi": ("Asia/Karachi", 5.0, None),
    "dhaka": ("Asia/Dhaka", 6.0, None),
    "bangkok": ("Asia/Bangkok", 7.0, None),
    "jakarta": ("Asia/Jakarta", 7.0, None),
    "singapore": ("Asia/Singapore", 8.0, None),
    "hong kong": ("Asia/Hong_Kong", 8.0, None),
    "beijing": ("Asia/Shanghai", 8.0, None),
    "shanghai": ("Asia/Shanghai", 8.0, None),
    "shenzhen": ("Asia/Shanghai", 8.0, None),
    "taipei": ("Asia/Taipei", 8.0, None),
    "seoul": ("Asia/Seoul", 9.0, None),
    "tokyo": ("Asia/Tokyo", 9.0, None),
    "osaka": ("Asia/Tokyo", 9.0, None),
    "manila": ("Asia/Manila", 8.0, None),
    "kuala lumpur": ("Asia/Kuala_Lumpur", 8.0, None),
    "sydney": ("Australia/Sydney", 10.0, "au"),
    "melbourne": ("Australia/Melbourne", 10.0, "au"),
    "brisbane": ("Australia/Brisbane", 10.0, None),
    "perth": ("Australia/Perth", 8.0, None),
    "auckland": ("Pacific/Auckland", 12.0, "au"),
    "wellington": ("Pacific/Auckland", 12.0, "au"),
    "honolulu": ("Pacific/Honolulu", -10.0, None),
    "anchorage": ("America/Anchorage", -9.0, "us"),
    "rio de janeiro": ("America/Sao_Paulo", -3.0, None),
    "sao paulo": ("America/Sao_Paulo", -3.0, None),
    "buenos aires": ("America/Argentina/Buenos_Aires", -3.0, None),
    "lima": ("America/Lima", -5.0, None),
    "bogota": ("America/Bogota", -5.0, None),
    "santiago": ("America/Santiago", -4.0, None),
    "cairo": ("Africa/Cairo", 2.0, None),
    "lagos": ("Africa/Lagos", 1.0, None),
    "nairobi": ("Africa/Nairobi", 3.0, None),
    "johannesburg": ("Africa/Johannesburg", 2.0, None),
    "casablanca": ("Africa/Casablanca", 1.0, None),
    # Country/region-level defaults
    "usa": ("America/New_York", -5.0, "us"),
    "united states": ("America/New_York", -5.0, "us"),
    "america": ("America/New_York", -5.0, "us"),
    "uk": ("Europe/London", 0.0, "eu"),
    "united kingdom": ("Europe/London", 0.0, "eu"),
    "europe": ("Europe/Paris", 1.0, "eu"),
    "canada": ("America/Toronto", -5.0, "us"),
    "australia": ("Australia/Sydney", 10.0, "au"),
    "japan": ("Asia/Tokyo", 9.0, None),
    "china": ("Asia/Shanghai", 8.0, None),
    "germany": ("Europe/Berlin", 1.0, "eu"),
    "france": ("Europe/Paris", 1.0, "eu"),
    "spain": ("Europe/Madrid", 1.0, "eu"),
    "italy": ("Europe/Rome", 1.0, "eu"),
    "brazil": ("America/Sao_Paulo", -3.0, None),
    "russia": ("Europe/Moscow", 3.0, None),
    "south korea": ("Asia/Seoul", 9.0, None),
    "uae": ("Asia/Dubai", 4.0, None),
}


def _dst_active(scheme: Optional[str], dt_utc: datetime) -> bool:
    """Approximate DST window check for the curated fallback table.

    zoneinfo is tried first wherever the OS tz database exists; this heuristic
    only backs up systems without tzdata (e.g. stock Windows). Rules:
      us: 2nd Sun Mar 07:00 UTC -> 1st Sun Nov 06:00 UTC
      eu: last Sun Mar 01:00 UTC  -> last Sun Oct 01:00 UTC
      au: 1st Sun Oct 02:00 UTC   -> 1st Sun Apr 02:00 UTC
    """
    if not scheme:
        return False
    y = dt_utc.year

    def _sunday(year: int, month: int, nth: int) -> datetime:
        d = datetime(year, month, 1, tzinfo=timezone.utc)
        first_sun = d + timedelta(days=(6 - d.weekday()) % 7)
        return first_sun + timedelta(weeks=nth - 1)

    def _last_sunday(year: int, month: int) -> datetime:
        d = datetime(year, month, 1, tzinfo=timezone.utc) + timedelta(days=31)
        d = d.replace(day=1) - timedelta(days=1)  # last day of month
        return d - timedelta(days=(d.weekday() + 1) % 7)

    if scheme == "us":
        start = _sunday(y, 3, 2) + timedelta(hours=7)
        end = _sunday(y, 11, 1) + timedelta(hours=6)
    elif scheme == "eu":
        start = _last_sunday(y, 3) + timedelta(hours=1)
        end = _last_sunday(y, 10) + timedelta(hours=1)
    elif scheme == "au":
        start = _sunday(y, 10, 1) + timedelta(hours=2)
        end = _sunday(y, 4, 1) + timedelta(hours=2)
        # southern hemisphere DST straddles new year
        return start <= dt_utc or dt_utc < end
    else:
        return False
    return start <= dt_utc < end


def _resolve_zone(location: str):
    """Return (label, tz) for a resolved location, or None when unknown."""
    key = location.strip().lower()
    entry = _LOCATIONS.get(key)
    if entry is None:
        # tolerance for "newyork", "ny", "sf", country adjectives
        compact = re.sub(r"[^a-z]", "", key)
        for k, v in _LOCATIONS.items():
            if re.sub(r"[^a-z]", "", k) == compact:
                entry = v
                break
    if entry is None and compact == "ny":
        entry = _LOCATIONS["new york"]
    if entry is None:
        return None
    name, base_offset, scheme = entry
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(name)
        return (key, tz)
    except Exception:
        # Fallback: base offset + approximate DST
        dt_utc = datetime.now(timezone.utc)
        offset = base_offset + (1.0 if _dst_active(scheme, dt_utc) else 0.0)
        return (key, timezone(timedelta(hours=offset)))


def _extract_location(query: str) -> Optional[str]:
    """'in New York' / 'at the office' -> location string, else None."""
    m = re.search(
        r"\b(?:in|at|for)\s+([a-z][a-z .'-]{1,40}?)(?:\s+right\s+now|\s+now|\?|\.)?\s*$",
        query.lower(),
    )
    if m:
        loc = m.group(1).strip().strip(".,!?;:")
        if loc and loc not in ("the", "a", "an", "here", "there", "my", "your", "this", "that", "office", "the office"):
            return loc
    # "what time is it in new york right now"
    m2 = re.search(r"\bin\s+([a-z][a-z .'-]{1,40}?)\s+(?:right\s+now|now)\b", query.lower())
    if m2:
        return m2.group(1).strip()
    return None


def _format_12h(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def _location_display(loc: str) -> str:
    overrides = {"nyc": "New York", "la": "Los Angeles", "uk": "the UK", "uae": "the UAE", "usa": "the US"}
    return overrides.get(loc.lower(), loc.title())


# ── owners ───────────────────────────────────────────────────────────────────

def time_answer(query: str, ctx=None, location_hint: str = "") -> dict:
    """'what's the time' -> clean local time; 'in <place>' -> that place."""
    loc = _extract_location(query)
    # 'what time is it there' resolves against the last-mentioned location
    # in the conversation when one exists; otherwise falls back to local.
    if not loc and re.search(r"\bthere\b", query.lower()) and ctx is not None:
        loc = getattr(ctx, "last_location", "") or ""
    loc = loc or location_hint or ""
    if loc:
        resolved = _resolve_zone(loc)
        if resolved is None:
            return {
                "success": False,
                "message": f"I can't pin down the timezone for {_location_display(loc)}.",
                "type": "time",
                "location": loc,
            }
        _label, tz = resolved
        dt = datetime.now(tz)
        display = _location_display(loc)
        return {
            "success": True,
            "message": f"It's {_format_12h(dt)} in {display}.",
            "type": "time",
            "location": display,
            "timezone": str(tz),
            "datetime": dt.isoformat(),
            "formatted_time": _format_12h(dt),
            "formatted_date": dt.strftime("%A, %B %d").replace(" 0", " "),
        }
    now = datetime.now()
    return {
        "success": True,
        "message": f"It's {_format_12h(now)} here.",
        "type": "time",
        "location": "here",
        "datetime": now.isoformat(),
        "formatted_time": _format_12h(now),
        "formatted_date": now.strftime("%A, %B %d").replace(" 0", " "),
    }


def date_answer(query: str) -> dict:
    """'what's the date' / 'what day is it' — clean date answers."""
    now = datetime.now()
    day = now.strftime("%A")
    date = now.strftime("%B %d").replace(" 0", " ")
    lower = query.lower()
    if re.search(r"\bwhat\s+day\b|\bday\s+is\s+(?:it|today)\b", lower):
        return {"success": True, "message": f"It's {day}.", "type": "date",
                "day": day, "date": date, "datetime": now.isoformat()}
    return {"success": True, "message": f"It's {date}, {now.year}.", "type": "date",
            "day": day, "date": date, "year": now.year, "datetime": now.isoformat()}


_WMO_DESC = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog", 51: "light drizzle", 53: "drizzle", 55: "dense drizzle",
    56: "freezing drizzle", 57: "dense freezing drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 66: "freezing rain", 67: "heavy freezing rain", 71: "light snow",
    73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "heavy showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "heavy thunderstorm with hail",
}


def _live_weather(loc: str) -> Optional[dict]:
    """Live weather via Open-Meteo (no key). Returns a weather dict or None
    when the place can't be resolved or the network call fails."""
    import json
    import urllib.parse
    import urllib.request

    try:
        with urllib.request.urlopen(
            "https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&format=json&name="
            + urllib.parse.quote(loc),
            timeout=6,
        ) as r:
            geo = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    results = geo.get("results") or []
    if not results:
        return None
    place = results[0]
    lat, lon = place.get("latitude"), place.get("longitude")
    name = place.get("name") or loc.title()
    if lat is None or lon is None:
        return None
    try:
        with urllib.request.urlopen(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
            "&timezone=auto",
            timeout=6,
        ) as r:
            cur = json.loads(r.read().decode("utf-8"))["current"]
    except Exception:
        return None
    desc = _WMO_DESC.get(cur.get("weather_code"), "variable conditions")
    return {
        "location": name,
        "description": desc,
        "temperature_c": cur.get("temperature_2m"),
        "feels_like_c": cur.get("apparent_temperature"),
        "humidity_pct": cur.get("relative_humidity_2m"),
        "wind_kmh": cur.get("wind_speed_10m"),
    }


def weather_answer(query: str) -> dict:
    """Live weather capability answer via Open-Meteo (no key, no auth).

    Falls back to an honest offline message when the place can't be resolved
    or the network is unreachable — KIO never fakes a forecast.
    """
    loc = _extract_location(query)
    where = f" for {_location_display(loc)}" if loc else ""
    if loc:
        w = _live_weather(loc)
        if w is not None:
            parts = [f"{w['temperature_c']:.0f}°C ({w['description']})"]
            if w["feels_like_c"] is not None:
                parts.append(f"feels like {w['feels_like_c']:.0f}°C")
            if w["wind_kmh"] is not None:
                parts.append(f"{w['wind_kmh']:.0f} km/h wind")
            if w["humidity_pct"] is not None:
                parts.append(f"{w['humidity_pct']:.0f}% humidity")
            return {
                "success": True,
                "message": f"It's {', '.join(parts)} in {w['location']}.",
                "type": "weather",
                "location": w["location"],
                "weather": w,
            }
    return {
        "success": True,
        "message": f"I can't check live weather{where} from this machine right now — no weather service is connected.",
        "type": "weather",
        "location": loc or "",
    }


# ── conversions ──────────────────────────────────────────────────────────────

_UNITS: dict[str, tuple[str, float]] = {
    # name -> (canonical unit, factor to canonical base)
    # mass base: kg
    "kg": ("kg", 1.0), "kilogram": ("kg", 1.0), "kilograms": ("kg", 1.0), "kgs": ("kg", 1.0),
    "lb": ("lb", 1.0), "lbs": ("lb", 1.0), "pound": ("lb", 1.0), "pounds": ("lb", 1.0),
    "g": ("g", 1.0), "gram": ("g", 1.0), "grams": ("g", 1.0),
    "oz": ("oz", 1.0), "ounce": ("oz", 1.0), "ounces": ("oz", 1.0),
    # length base: km
    "km": ("km", 1.0), "kilometer": ("km", 1.0), "kilometers": ("km", 1.0), "kms": ("km", 1.0),
    "mi": ("mi", 1.0), "mile": ("mi", 1.0), "miles": ("mi", 1.0),
    "m": ("m", 1.0), "meter": ("m", 1.0), "meters": ("m", 1.0), "metre": ("m", 1.0), "metres": ("m", 1.0),
    "ft": ("ft", 1.0), "foot": ("ft", 1.0), "feet": ("ft", 1.0),
    "cm": ("cm", 1.0), "centimeter": ("cm", 1.0), "centimeters": ("cm", 1.0),
    "in": ("in", 1.0), "inch": ("in", 1.0), "inches": ("in", 1.0),
    # volume base: l
    "l": ("l", 1.0), "liter": ("l", 1.0), "liters": ("l", 1.0), "litre": ("l", 1.0), "litres": ("l", 1.0),
    "gal": ("gal", 1.0), "gallon": ("gal", 1.0), "gallons": ("gal", 1.0),
    # speed base: kmh
    "kmh": ("kmh", 1.0), "km/h": ("kmh", 1.0), "kph": ("kmh", 1.0), "kmph": ("kmh", 1.0),
    "mph": ("mph", 1.0),
    # currency base: usd
    "usd": ("usd", 1.0), "dollar": ("usd", 1.0), "dollars": ("usd", 1.0), "$": ("usd", 1.0),
    "eur": ("eur", 1.0), "euro": ("eur", 1.0), "euros": ("eur", 1.0), "€": ("eur", 1.0),
    "gbp": ("gbp", 1.0), "pound sterling": ("gbp", 1.0), "pounds sterling": ("gbp", 1.0),
    "inr": ("inr", 1.0), "rupee": ("inr", 1.0), "rupees": ("inr", 1.0), "₹": ("inr", 1.0),
    "jpy": ("jpy", 1.0), "yen": ("jpy", 1.0), "¥": ("jpy", 1.0),
    "aed": ("aed", 1.0), "dirham": ("aed", 1.0), "dirhams": ("aed", 1.0),
    "cad": ("cad", 1.0), "c$": ("cad", 1.0),
    "aud": ("aud", 1.0), "a$": ("aud", 1.0),
    # temperature
    "c": ("c", 1.0), "celsius": ("c", 1.0), "°c": ("c", 1.0), "degree celsius": ("c", 1.0),
    "f": ("f", 1.0), "fahrenheit": ("f", 1.0), "°f": ("f", 1.0), "degrees fahrenheit": ("f", 1.0),
}

# Conversion factors between canonical units (non-currency, non-temperature)
_FACTORS: dict[tuple[str, str], float] = {
    ("kg", "lb"): 2.20462, ("lb", "kg"): 1 / 2.20462,
    ("kg", "g"): 1000.0, ("g", "kg"): 0.001,
    ("lb", "g"): 453.592, ("g", "lb"): 1 / 453.592,
    ("lb", "oz"): 16.0, ("oz", "lb"): 1 / 16.0,
    ("g", "oz"): 0.035274, ("oz", "g"): 28.3495,
    ("kg", "oz"): 35.274, ("oz", "kg"): 1 / 35.274,
    ("km", "mi"): 0.621371, ("mi", "km"): 1.60934,
    ("km", "m"): 1000.0, ("m", "km"): 0.001,
    ("km", "ft"): 3280.84, ("ft", "km"): 1 / 3280.84,
    ("km", "cm"): 100000.0, ("cm", "km"): 1e-5,
    ("m", "ft"): 3.28084, ("ft", "m"): 0.3048,
    ("m", "cm"): 100.0, ("cm", "m"): 0.01,
    ("m", "in"): 39.3701, ("in", "m"): 0.0254,
    ("cm", "in"): 0.393701, ("in", "cm"): 2.54,
    ("ft", "in"): 12.0, ("in", "ft"): 1 / 12.0,
    ("mi", "ft"): 5280.0, ("ft", "mi"): 1 / 5280.0,
    ("mi", "m"): 1609.34, ("m", "mi"): 1 / 1609.34,
    ("mi", "in"): 63360.0, ("in", "mi"): 1 / 63360.0,
    ("l", "gal"): 0.264172, ("gal", "l"): 3.78541,
    ("l", "ml"): 1000.0, ("kmh", "mph"): 0.621371, ("mph", "kmh"): 1.60934,
}

# Approximate reference currency rates (1 unit -> target). Labeled approximate —
# real rates move; the answer always says "about".
_CURRENCY_RATES: dict[tuple[str, str], float] = {
    ("usd", "eur"): 0.92, ("eur", "usd"): 1.09,
    ("usd", "gbp"): 0.79, ("gbp", "usd"): 1.27,
    ("usd", "inr"): 84.0, ("inr", "usd"): 0.012,
    ("usd", "jpy"): 147.0, ("jpy", "usd"): 0.0068,
    ("usd", "aed"): 3.67, ("aed", "usd"): 0.27,
    ("usd", "cad"): 1.36, ("cad", "usd"): 0.74,
    ("usd", "aud"): 1.52, ("aud", "usd"): 0.66,
    ("eur", "gbp"): 0.86, ("gbp", "eur"): 1.16,
    ("eur", "inr"): 91.0, ("inr", "eur"): 0.011,
    ("gbp", "inr"): 106.0, ("inr", "gbp"): 0.0094,
    ("eur", "jpy"): 160.0, ("jpy", "eur"): 0.0063,
    ("gbp", "jpy"): 186.0, ("jpy", "gbp"): 0.0054,
    ("eur", "aed"): 3.99, ("gbp", "aed"): 4.64,
    ("gbp", "cad"): 1.72, ("eur", "cad"): 1.48,
    ("gbp", "aud"): 1.92, ("eur", "aud"): 1.65,
}

_CURRENCY_SYMBOL = {"usd": "$", "eur": "€", "gbp": "£", "inr": "₹", "jpy": "¥", "aed": "AED ", "cad": "C$", "aud": "A$"}
_CURRENCY_NAME = {"usd": "dollars", "eur": "euros", "gbp": "pounds", "inr": "rupees",
                  "jpy": "yen", "aed": "dirhams", "cad": "Canadian dollars", "aud": "Australian dollars"}
_CURRENCY_SET = frozenset(c for pair in _CURRENCY_RATES for c in pair)


def _parse_amount_unit(text: str):
    """Extract (amount, canonical_unit) from text, or None."""
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if not m:
        return None
    amount = float(m.group(1).replace(",", ""))
    before = text[: m.start()].strip()
    after = text[m.end():].strip()
    ctx_text = (before + " " + after).lower()
    # find the unit nearest the number
    for u, (canon, _f) in sorted(_UNITS.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"(^|\s)" + re.escape(u) + r"($|\s)", ctx_text):
            return amount, canon
    return None


def try_parse_conversion(query: str):
    """Parse a conversion request into (src, dst) parse tuples, or None when
    the text is not a valid conversion (used by the classifier for routing)."""
    low = query.lower().strip()
    low = low.replace("how much is", "").replace("what is", "").replace("convert", "").strip()
    m = re.match(r"^(.+?)\s+(?:to|in|into)\s+(.+?)\s*$", low)
    if not m:
        return None
    src = _parse_amount_unit(m.group(1).strip())
    dst = _parse_amount_unit("0 " + m.group(2).strip())
    if not src or not dst:
        return None
    _amount, src_unit = src
    _a2, dst_unit = dst
    if src_unit in ("c", "f") and dst_unit in ("c", "f"):
        return (src, dst)
    if src_unit in _CURRENCY_SET and dst_unit in _CURRENCY_SET:
        return (src, dst)
    if (src_unit, dst_unit) in _FACTORS:
        return (src, dst)
    return None


def convert_answer(query: str) -> dict:
    """'convert 100 dollars to euros', '5 kg in pounds', 'how much is 2 miles in km'."""
    parsed = try_parse_conversion(query)
    if parsed is None:
        return {"success": False, "message": "Tell me what to convert — like 'convert 100 dollars to euros'.", "type": "convert"}
    (amount, src_unit), (_, dst_unit) = parsed

    # temperature special case
    if src_unit in ("c", "f") and dst_unit in ("c", "f"):
        if src_unit == "c":
            result = amount * 9 / 5 + 32
        else:
            result = (amount - 32) * 5 / 9
        dst_disp = "°F" if dst_unit == "f" else "°C"
        return {"success": True, "message": f"{_num(amount)}°{'C' if src_unit=='c' else 'F'} is {_num(result)}{dst_disp}.",
                "type": "convert", "amount": amount, "from": src_unit, "to": dst_unit, "result": result}

    # currency
    if src_unit in _CURRENCY_SET and dst_unit in _CURRENCY_SET:
        # Live ECB rates (Frankfurter, no key) when both sides are covered;
        # the static table below stays as the honest offline fallback.
        live = _live_fx_rates()
        if live and src_unit in live and dst_unit in live:
            if src_unit == "usd":
                rate = live[dst_unit]
            elif dst_unit == "usd":
                rate = 1.0 / live[src_unit]
            else:
                rate = live[dst_unit] / live[src_unit]
            result = amount * rate
            return {
                "success": True,
                "message": f"{_num(amount)} {_CURRENCY_NAME[src_unit]} is {_CURRENCY_SYMBOL[dst_unit]}{_num(result)} (live rate).",
                "type": "convert", "amount": amount, "from": src_unit, "to": dst_unit,
                "result": result, "approximate": False,
            }
        rate = _CURRENCY_RATES.get((src_unit, dst_unit))
        if rate is None:
            # derive via USD
            to_usd = _CURRENCY_RATES.get((src_unit, "usd"))
            from_usd = _CURRENCY_RATES.get(("usd", dst_unit))
            if to_usd and from_usd:
                rate = to_usd * from_usd
        if rate:
            result = amount * rate
            return {
                "success": True,
                "message": f"{_num(amount)} {_CURRENCY_NAME[src_unit]} is about {_CURRENCY_SYMBOL[dst_unit]}{_num(result)} (approximate rate).",
                "type": "convert", "amount": amount, "from": src_unit, "to": dst_unit,
                "result": result, "approximate": True,
            }
        return {"success": False, "message": f"I can't convert {src_unit} to {dst_unit} right now.", "type": "convert"}

    # physical units
    factor = _FACTORS.get((src_unit, dst_unit))
    if factor is None:
        return {"success": False, "message": f"I don't know a conversion from {src_unit} to {dst_unit}.", "type": "convert"}
    result = amount * factor
    return {"success": True, "message": f"{_num(amount)} {src_unit} is {_num(result)} {dst_unit}.",
            "type": "convert", "amount": amount, "from": src_unit, "to": dst_unit, "result": result}


def _num(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


# ── shared no-key HTTP helpers (stdlib) ──────────────────────────────────────
_UTIL_UA = {"User-Agent": "KIO/1.0 (utilities)"}


def _http_get_bytes(url: str, timeout: float = 6.0):
    """Minimal keyless GET (stdlib). Returns raw bytes or None on failure."""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers=_UTIL_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def _http_get_json(url: str, timeout: float = 6.0):
    """Minimal keyless JSON GET (stdlib). Returns dict or None on failure."""
    import json
    raw = _http_get_bytes(url, timeout)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _date_only(value) -> str:
    """Normalize any timestamp/date to YYYY-MM-DD ('' when unparseable)."""
    if not value:
        return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(value))
    return m.group(1) if m else ""


def _live_fx_rates():
    """Live USD-based FX rates from Frankfurter (ECB, no key), or None."""
    data = _http_get_json("https://api.frankfurter.app/latest?base=USD")
    if not data or not isinstance(data.get("rates"), dict):
        return None
    rates = {}
    for code, rate in data["rates"].items():
        try:
            rates[str(code).lower()] = float(rate)
        except (TypeError, ValueError):
            continue
    rates["usd"] = 1.0
    return rates


def _feed_rss_date(value) -> str:
    """RFC822 pubDate ('Sun, 16 Aug 2026 04:15:27 +0000') -> YYYY-MM-DD."""
    if not value:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(str(value))
        if dt is not None:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return _date_only(value)


def _parse_feed_items(xml_bytes: bytes, limit: int = 5):
    """Parse RSS 2.0 / Atom 1.0 into [(title, link, date)] via stdlib XML.

    Handles both Atom feeds (GitHub releases.atom) and RSS 2.0 channels
    (PyPI / hnrss.org) — one parser covers the whole 'what's new' family.
    """
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return []
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    items = []
    if root.tag == ns + "feed":  # Atom 1.0
        for e in root.findall(ns + "entry"):
            title = (e.findtext(ns + "title") or "").strip()
            if not title:
                continue
            link = ""
            ln = e.find(ns + "link")
            if ln is not None:
                link = ln.get("href") or ""
            date = _date_only(e.findtext(ns + "published") or e.findtext(ns + "updated"))
            items.append((title, link, date))
    else:  # RSS 2.0: channel/item
        channel = root.find(ns + "channel")
        src = channel if channel is not None else root
        for it in src.findall(ns + "item")[:limit]:
            title = (it.findtext(ns + "title") or "").strip()
            if not title:
                continue
            items.append((title, it.findtext(ns + "link") or "",
                          _feed_rss_date(it.findtext(ns + "pubDate"))))
    return items[:limit]


# ── package status owner (PyPI, no key) ──────────────────────────────────────
_PACKAGE_STOP = frozenset({"the", "a", "an", "this", "that", "it", "you", "your", "my", "its", "their"})


def _extract_package_name(query: str):
    """'latest version of requests' / 'is requests outdated' -> package name."""
    low = query.lower().strip()
    m = re.search(r"(?:latest|newest)\s+version\s+of\s+([a-z0-9][a-z0-9._-]{1,50})", low)
    if m and m.group(1) not in _PACKAGE_STOP:
        return m.group(1)
    m = re.search(r"\b(?:is|are)\s+([a-z0-9][a-z0-9._-]{1,50})\s+out(?:dated| of date)\b", low)
    if m and m.group(1) not in _PACKAGE_STOP:
        return m.group(1)
    return None


def looks_like_package(query: str) -> bool:
    """Routing hook: True when the text is a package version/status request."""
    return _extract_package_name(query) is not None


def package_answer(query: str) -> dict:
    """'what's the latest version of requests' / 'is requests outdated'.

    Live PyPI JSON (no key). Compares against the installed version when the
    package is present on this machine; otherwise reports the latest only.
    """
    name = _extract_package_name(query)
    if not name:
        return {"success": False,
                "message": "Tell me a package name — like 'what's the latest version of requests'.",
                "type": "package"}
    data = _http_get_json("https://pypi.org/pypi/" + name + "/json")
    if not data:
        return {"success": False, "package": name,
                "message": f"I couldn't reach PyPI for {name!r} — no package lookup available right now.",
                "type": "package"}
    info = data.get("info") or {}
    version = info.get("version") or ""
    if not version:
        return {"success": False, "package": name,
                "message": f"I couldn't find the package {name!r} on PyPI.", "type": "package"}
    released = ""
    rel = (data.get("releases") or {}).get(version) or []
    if rel:
        released = _date_only(rel[0].get("upload_time_iso_8601") or rel[0].get("upload_time"))
    installed = None
    try:
        from importlib.metadata import version as _ver
        installed = _ver(name)
    except Exception:
        installed = None
    when = f" (released {released})" if released else ""
    if installed and installed != version:
        msg = f"The latest version of {name} is {version}{when}. You have {installed} installed — it's outdated."
        current = False
    else:
        msg = f"The latest version of {name} is {version}{when}."
        current = True
    return {"success": True, "message": msg, "type": "package", "package": name,
            "version": version, "released": released, "installed": installed,
            "current": current, "summary": (info.get("summary") or "").strip()}


# ── feed / release watcher owner (RSS+Atom, no key) ──────────────────────────
def _extract_feed_target(query: str):
    """'latest releases of owner/repo' / 'what's new in <pkg>' -> target."""
    low = query.lower().strip()
    m = re.search(r"(?:latest|recent)\s+releases?\s+of\s+([a-z0-9][a-z0-9._/\-]{1,60}?)\s*$", low)
    if m:
        t = m.group(1).strip(" ./!?;:")
        if t and t not in _PACKAGE_STOP:
            return t
    m = re.search(r"what(?:'?s|\s+is)\s+new\s+in\s+([a-z0-9][a-z0-9._\-]{1,40}?)\s*$", low)
    if m:
        t = m.group(1).strip(" ./!?;:")
        if t and t not in _PACKAGE_STOP:
            return t
    return None


def looks_like_feed(query: str) -> bool:
    """Routing hook: True when the text asks for recent feed/release items."""
    return _extract_feed_target(query) is not None


def _feed_url_for_target(target: str):
    """'owner/repo' -> (GitHub releases.atom, 'github'); bare name ->
    (PyPI releases RSS, 'pypi'). Single mapping shared by the 'what's new'
    answer and the release watcher so both resolve targets identically."""
    if "/" in target:
        return "https://github.com/" + target.strip("/") + "/releases.atom", "github"
    # ponytail: bare names resolve to PyPI only — a bare GitHub repo can't
    # be watched without a name->repo lookup. Add GitHub repo search when
    # the PyPI-first guess misroutes real traffic.
    return "https://pypi.org/rss/project/" + target + "/releases.xml", "pypi"


def feed_answer(query: str) -> dict:
    """'latest releases of openai/openai' (GitHub) / 'what's new in requests'
    (PyPI) — the 'what's new' capability. A slash target is a GitHub
    owner/repo; a bare name is a PyPI project.
    """
    target = _extract_feed_target(query)
    if not target:
        return {"success": False,
                "message": "Tell me what to watch — like 'latest releases of openai/openai' or 'what's new in requests'.",
                "type": "feed"}
    url, kind = _feed_url_for_target(target)
    label = f"{target} (GitHub)" if kind == "github" else f"{target} (PyPI)"
    items = _parse_feed_items(_http_get_bytes(url) or b"", limit=5)
    if not items:
        return {"success": False, "feed": label,
                "message": f"I couldn't fetch recent releases for {label} — no feed available right now.",
                "type": "feed"}
    parts = [f"{t}{' (' + d + ')' if d else ''}" for t, _l, d in items[:3]]
    return {"success": True, "message": f"Recent releases of {label}: " + "; ".join(parts) + ".",
            "type": "feed", "feed": label, "kind": kind,
            "items": [{"title": t, "url": l, "date": d} for t, l, d in items]}


# ── project summary owner (GitHub / PyPI, no key) ────────────────────────────
def _extract_project_target(query: str):
    """'summarize the project openai/openai' -> target; None otherwise."""
    low = query.lower().strip()
    m = re.search(
        r"summarize\s+(?:the\s+)?(?:project|repo(?:sitory)?)\s+(?:of\s+)?"
        r"([a-z0-9][a-z0-9._/\-]{1,80}?)\s*$",
        low,
    )
    if m:
        t = m.group(1).strip(" ./!?;:")
        if t and t not in _PACKAGE_STOP:
            return t
    return None


def looks_like_project_summary(query: str) -> bool:
    """Routing hook: True when the text asks for a project/repo summary."""
    return _extract_project_target(query) is not None


def project_answer(query: str) -> dict:
    """'summarize the project openai/openai' -> GitHub repo meta + latest
    releases + top open issues. 'summarize the project requests' (bare name)
    -> PyPI metadata. Deterministic, keyless, never a raw provider page."""
    target = _extract_project_target(query)
    if not target:
        return {"success": False,
                "message": "Tell me a project — like 'summarize the project openai/openai' or 'summarize the project requests'.",
                "type": "project"}
    if "/" in target:
        owner, _, repo = target.partition("/")
        repo = repo.strip("/")
        meta = _http_get_json(f"https://api.github.com/repos/{owner}/{repo}")
        if not meta:
            return {"success": False, "project": target,
                    "message": f"I couldn't reach GitHub for {target} right now.",
                    "type": "project"}
        if isinstance(meta, dict) and meta.get("message"):
            # Distinguish "repo doesn't exist" from "GitHub unreachable /
            # rate-limited" — both are truthful, one is actionable.
            status = str(meta.get("status") or meta.get("status_code") or "")
            if status == "404":
                msg = f"I couldn't find the GitHub project {target}."
            else:
                msg = f"I couldn't reach GitHub for {target} right now."
            return {"success": False, "project": target, "message": msg,
                    "type": "project"}
        desc = (meta.get("description") or "").strip()
        lang = meta.get("language") or "unknown"
        stars = meta.get("stargazers_count") or 0
        rel = _parse_feed_items(
            _http_get_bytes(f"https://github.com/{owner}/{repo}/releases.atom") or b"",
            limit=2,
        )
        rel_txt = "; ".join(t for t, _l, d in rel[:2]) if rel else "none listed"
        issues = _http_get_json(
            f"https://api.github.com/repos/{owner}/{repo}/issues?state=open&per_page=5"
        )
        issue_txt = "no open issues"
        if isinstance(issues, list):
            open_issues = [i for i in issues if "pull_request" not in i]
            if open_issues:
                issue_txt = "; ".join((i.get("title") or "") for i in open_issues[:3])
        msg = (f"{owner}/{repo}: {desc} ({lang}, {stars} stars). "
               f"Latest releases: {rel_txt}. Open issues: {issue_txt}.")
        return {"success": True, "message": msg, "type": "project",
                "project": f"{owner}/{repo}", "language": lang,
                "stars": stars, "summary": msg}
    info = _http_get_json(f"https://pypi.org/pypi/{target}/json")
    if not info or not isinstance(info, dict) or not info.get("info"):
        return {"success": False, "project": target,
                "message": f"I couldn't find the Python package {target} on PyPI.",
                "type": "project"}
    i = info["info"]
    version = i.get("version") or "unknown"
    summary = (i.get("summary") or "").strip()
    msg = f"{target} (PyPI): {summary} Latest version: {version}."
    return {"success": True, "message": msg, "type": "project",
            "project": target, "version": version, "summary": msg}


# ── deterministic arithmetic (calculator) ────────────────────────────────────
# Canonical owner for math: the numerical answer ALWAYS originates here —
# never the LLM, never web retrieval. The expression is parsed and evaluated
# with a restricted AST walk (no eval, no exec, no builtins). Supports
# + - * / % ** ( ) decimals, postfix factorial (!), and natural-language
# forms ("times", "divided by", "squared", "factorial", "square root of",
# "to the power of", "N% of M").

import ast  # noqa: E402
import math  # noqa: E402

_CALC_PREFIX_RE = re.compile(
    r"^(?:what(?:'s|s|\s+is)?|whats|calculate|compute|evaluate|work\s+out|solve|"
    r"tell\s+me|can\s+you|please|the\s+answer\s+to|give\s+me|find|what\s+is)\s*",
    re.I,
)

_MAX_CALC_CHARS = 120
_MAX_FACTORIAL = 100
_MAX_POW_EXPONENT = 1000
_MAX_POW_BASE = 10 ** 9


def _normalize_arithmetic(query: str) -> Optional[str]:
    """Convert a user arithmetic request into a safe evaluable expression,
    or None when the text is not arithmetic. Word operators are translated
    to symbols; factorial / sqrt become restricted function calls."""
    if not query or not query.strip():
        return None
    t = query.strip()
    # Trailing punctuation is stripped EXCEPT "!" — a postfix factorial is
    # an operator, not punctuation ("6!" must not become bare "6").
    low = _CALC_PREFIX_RE.sub("", t, count=1).strip()
    low = low.strip("?.,;:\"' ").strip()
    if not low or len(low) > _MAX_CALC_CHARS:
        return None
    # Natural-language arithmetic (generic word forms, never phrase patches)
    low = re.sub(r"\bpercent\s+of\b", "% of", low, flags=re.I)
    low = re.sub(r"\bto\s+the\s+power\s+of\b", "**", low, flags=re.I)
    low = re.sub(r"\braised\s+to\s+(?:the\s+power\s+of\s+)?", "**", low, flags=re.I)
    low = re.sub(r"\bmodulo\b", "%", low, flags=re.I)
    low = re.sub(r"\bmod\b", "%", low, flags=re.I)
    low = re.sub(r"\bdivided\s+by\b", "/", low, flags=re.I)
    low = re.sub(r"\bover\b", "/", low, flags=re.I)
    low = re.sub(r"\bmultiplied\s+by\b", "*", low, flags=re.I)
    low = re.sub(r"\btimes\b", "*", low, flags=re.I)
    low = re.sub(r"\bplus\b", "+", low, flags=re.I)
    low = re.sub(r"\bminus\b", "-", low, flags=re.I)
    low = re.sub(r"\b\*\s+x\s+\*\b", "*", low, flags=re.I)  # stray x
    low = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "*", low, flags=re.I)  # 4x68 -> 4*68
    # "square root of N" / "sqrt of N"
    low = re.sub(
        r"square\s+root\s+of\s+([0-9(]+[^\s]*)|"  # noqa: W605
        r"sqrt\s+of\s+([0-9(]+[^\s]*)",
        r"sqrt(\1\2)", low, flags=re.I,
    )
    # "N factorial" / "factorial of N" / "N!" -> fact(N)
    low = re.sub(r"\bfactorial\s+of\s+(\d+(?:\.\d+)?)", r"fact(\1)", low, flags=re.I)
    low = re.sub(r"(\d+(?:\.\d+)?)\s+factorial\b", r"fact(\1)", low, flags=re.I)
    low = re.sub(r"(\d+(?:\.\d+)?)\s*!", r"fact(\1)", low)
    low = re.sub(r"!", r"fact(", low)  # trailing postfix forms (rare)
    # "N squared" / "N cubed"
    low = re.sub(r"(\d+(?:\.\d+)?)\s+squared\b", r"(\1)**2", low, flags=re.I)
    low = re.sub(r"(\d+(?:\.\d+)?)\s+cubed\b", r"(\1)**3", low, flags=re.I)
    # "N% of M" -> ((N)/100*(M))
    low = re.sub(
        r"(\d+(?:\.\d+)?)\s*%\s+of\s+(\d+(?:\.\d+)?)",
        r"((\1)/100*(\2))", low, flags=re.I,
    )
    low = low.replace("^", "**")
    low = re.sub(r"\s+", "", low)
    if not low:
        return None
    if not re.search(r"\d", low):
        return None
    # Must contain an operator / function — a bare number is not arithmetic.
    if not re.search(r"[+\-*/%!]|\bfact\(|\bsqrt\(|\*\*", low):
        return None
    # Trailing-close cleanup for the function rewrites above.
    return low


def _calc_eval(node, depth: int = 0):
    """Restricted AST evaluator — only numbers, the 5 binary ops, unary
    +/- and the fact()/sqrt() calls are allowed. Returns the numeric value."""
    if depth > 60:
        raise ValueError("expression too deep")
    if isinstance(node, ast.Expression):
        return _calc_eval(node.body, depth + 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        left = _calc_eval(node.left, depth + 1)
        right = _calc_eval(node.right, depth + 1)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("division by zero")
            return left / right
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError("modulo by zero")
            return left % right
        if isinstance(node.op, ast.Pow):
            if abs(right) > _MAX_POW_EXPONENT or abs(left) > _MAX_POW_BASE:
                raise OverflowError("power too large")
            return left ** right
        raise ValueError("unsupported operator")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        val = _calc_eval(node.operand, depth + 1)
        return val if isinstance(node.op, ast.UAdd) else -val
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "fact" and len(node.args) == 1:
            val = _calc_eval(node.args[0], depth + 1)
            if not isinstance(val, int) or isinstance(val, bool) or val < 0 or val > _MAX_FACTORIAL:
                raise ValueError("factorial needs an integer 0..100")
            return math.factorial(val)
        if node.func.id == "sqrt" and len(node.args) == 1:
            val = _calc_eval(node.args[0], depth + 1)
            if val < 0:
                raise ValueError("sqrt of a negative number")
            return math.sqrt(val)
        raise ValueError("unsupported function")
    raise ValueError("unsupported expression")


def _format_number(value) -> str:
    if isinstance(value, float):
        if abs(value - round(value)) < 1e-9 and abs(value) < 1e15:
            return str(int(round(value)))
        return f"{value:g}"
    return str(value)


def looks_like_arithmetic(query: str) -> bool:
    """Routing hook: True when the text is a deterministic arithmetic request.
    Safe — never raises; a stray chat message ("2-D2", "version 2.0") that
    fails the strict grammar simply returns False. Division-by-zero and
    overflow ARE valid arithmetic (they get deterministic error answers), so
    only grammar/type errors disqualify a candidate."""
    try:
        expr = _normalize_arithmetic(query)
        if not expr:
            return False
        tree = ast.parse(expr, mode="eval")
        _calc_eval(tree)
        return True
    except (ZeroDivisionError, OverflowError):
        return True
    except Exception:
        return False


def calculate_answer(query: str) -> dict:
    """'what's 6*7' / '6!' / '144/12' / '6/0' -> deterministic result.

    The numerical answer always comes from the calculator; invalid or
    out-of-range expressions get an honest deterministic response — never a
    guess and never a provider call."""
    expr = _normalize_arithmetic(query)
    if not expr:
        return {
            "success": False,
            "message": "I can only calculate plain arithmetic — try something like '6*7' or '144/12'.",
            "type": "calculate",
        }
    try:
        tree = ast.parse(expr, mode="eval")
        result = _calc_eval(tree)
    except ZeroDivisionError:
        return {
            "success": False,
            "message": "That would be division by zero, which is undefined.",
            "type": "calculate", "expression": expr,
        }
    except OverflowError:
        return {
            "success": False,
            "message": "That number is too large for me to compute.",
            "type": "calculate", "expression": expr,
        }
    except (ValueError, SyntaxError, TypeError, RecursionError):
        return {
            "success": False,
            "message": "I couldn't work that one out — the expression isn't valid arithmetic.",
            "type": "calculate", "expression": expr,
        }
    return {
        "success": True,
        "message": f"{_format_number(result)}",
        "type": "calculate",
        "expression": expr,
        "result": result,
    }


# ── air quality owner (Open-Meteo Air Quality, no key) ────────────────────────
# Same provider family as the weather owner (Open-Meteo geocoding + forecast) so
# the two answers can never disagree about a location's coordinates.
_AIR_QUALITY_LABEL = {
    0: "Good", 50: "Moderate", 100: "Unhealthy for sensitive groups",
    150: "Unhealthy", 200: "Very unhealthy", 300: "Hazardous",
}


def _openmeteo_geocode(loc: str):
    """Resolve a place name to (lat, lon, name) via Open-Meteo geocoding.
    Shared with the weather owner so both answers resolve locations identically."""
    import json
    import urllib.parse
    import urllib.request
    try:
        with urllib.request.urlopen(
            "https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&format=json&name="
            + urllib.parse.quote(loc),
            timeout=6,
        ) as r:
            geo = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    results = geo.get("results") or []
    if not results:
        return None
    place = results[0]
    lat, lon = place.get("latitude"), place.get("longitude")
    if lat is None or lon is None:
        return None
    return lat, lon, (place.get("name") or loc.title())


def _extract_air_quality_target(query: str):
    """'air quality in Delhi' / 'what's the AQI in Beijing' -> location or None."""
    low = query.lower().strip()
    # 'air quality in <place>' / 'aqi in <place>' / 'is the air good in <place>'
    m = re.search(
        r"\b(?:air\s+quality|aqi|air)\s+(?:index\s+)?(?:in|at|for)\s+"
        r"([a-z][a-z .'-]{1,40}?)\s*$",
        low,
    )
    if m:
        loc = m.group(1).strip().strip(".,!?;:")
        if loc and loc not in ("the", "a", "an", "here", "there", "my", "your", "this", "that", "office"):
            return loc
    m = re.search(r"\b(?:is\s+the\s+)?(?:air|air\s+quality)\s+(?:good|bad|clean|polluted|unhealthy|safe)\s+in\s+([a-z][a-z .'-]{1,40}?)\s*$", low)
    if m:
        loc = m.group(1).strip().strip(".,!?;:")
        if loc and loc not in ("the", "a", "an", "here", "there", "my", "your", "this", "that", "office"):
            return loc
    return None


def looks_like_air_quality(query: str) -> bool:
    """Routing hook: True when the text asks about air quality / AQI."""
    return _extract_air_quality_target(query) is not None


def air_quality_answer(query: str) -> dict:
    """'what's the air quality in Delhi' -> live US AQI + main pollutants.

    Open-Meteo Air Quality API (no key). Honest offline message when the
    place can't be resolved or the network is unreachable."""
    loc = _extract_air_quality_target(query)
    if not loc:
        return {"success": False,
                "message": "Tell me a place — like 'what's the air quality in Delhi'.",
                "type": "air_quality"}
    geo = _openmeteo_geocode(loc)
    if geo is None:
        return {"success": False, "location": loc,
                "message": f"I can't pin down {loc!r} for an air quality check right now.",
                "type": "air_quality"}
    lat, lon, name = geo
    data = _http_get_json(
        f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}"
        "&current=us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide",
        timeout=6.0,
    )
    cur = (data or {}).get("current") if isinstance(data, dict) else None
    if cur is None:
        return {"success": False, "location": name,
                "message": f"I couldn't reach the air quality service for {name} right now.",
                "type": "air_quality"}
    aqi = cur.get("us_aqi")
    if aqi is None:
        return {"success": False, "location": name,
                "message": f"The air quality service didn't return a reading for {name}.",
                "type": "air_quality"}
    label = "Good"
    for threshold, lab in sorted(_AIR_QUALITY_LABEL.items(), key=lambda x: x[0]):
        if aqi >= threshold:
            label = lab
    parts = [f"Air quality in {name}: {label} (AQI {aqi:.0f})"]
    if cur.get("pm2_5") is not None:
        parts.append(f"PM2.5 {cur['pm2_5']:.1f} µg/m³")
    if cur.get("pm10") is not None:
        parts.append(f"PM10 {cur['pm10']:.1f} µg/m³")
    return {"success": True, "message": ". ".join(parts) + ".",
            "type": "air_quality", "location": name, "aqi": aqi,
            "label": label, "pm2_5": cur.get("pm2_5"), "pm10": cur.get("pm10"),
            "ozone": cur.get("ozone")}


# ── public holidays owner (Nager.Date, no key) ───────────────────────────────
def _country_from_query(low: str) -> Optional[str]:
    """Best-effort ISO-3166-1 alpha-2 from a place mention ('in India' -> IN)."""
    m = re.search(r"\b(?:in|for|of)\s+([a-z][a-z .'-]{1,40}?)\s*(?:\?|\.|$)", low)
    if not m:
        return None
    place = m.group(1).strip().strip(".,!?;:")
    # "in the US" -> "the us" -> "us" — a leading article is not part of the
    # country name ("in the United Kingdom" and "in United Kingdom" are the
    # same country). Strip one leading article before matching.
    place = re.sub(r"^(?:the|a|an)\s+", "", place)
    if not place or place in ("here", "there", "my", "your", "this", "that", "week", "year"):
        return None
    _COUNTRY_ISO = {
        "india": "IN", "us": "US", "usa": "US", "united states": "US",
        "united states of america": "US", "america": "US", "uk": "GB",
        "united kingdom": "GB", "britain": "GB", "england": "GB",
        "france": "FR", "germany": "DE", "japan": "JP", "china": "CN",
        "canada": "CA", "australia": "AU", "brazil": "BR", "mexico": "MX",
        "italy": "IT", "spain": "ES", "netherlands": "NL", "russia": "RU",
        "south korea": "KR", "korea": "KR", "singapore": "SG", "uae": "AE",
        "united arab emirates": "AE", "saudi arabia": "SA", "turkey": "TR",
        "switzerland": "CH", "sweden": "SE", "norway": "NO", "denmark": "DK",
        "poland": "PL", "portugal": "PT", "greece": "GR", "ireland": "IE",
        "belgium": "BE", "austria": "AT", "new zealand": "NZ", "pakistan": "PK",
        "bangladesh": "BD", "sri lanka": "LK", "nepal": "NP", "indonesia": "ID",
        "malaysia": "MY", "thailand": "TH", "vietnam": "VN", "philippines": "PH",
        "argentina": "AR", "chile": "CL", "colombia": "CO", "south africa": "ZA",
        "egypt": "EG", "nigeria": "NG", "israel": "IL", "ukraine": "UA",
        "finland": "FI", "czech republic": "CZ", "hungary": "HU", "romania": "RO",
    }
    key = place.lower().strip()
    return _COUNTRY_ISO.get(key)


def _extract_holiday_target(query: str):
    """'is today a holiday in India' / 'next holiday in the US' -> (country_code) or None."""
    low = query.lower().strip()
    if not re.search(r"\b(holiday|public holiday|bank holiday)\b", low):
        return None
    return _country_from_query(low)


def looks_like_holiday(query: str) -> bool:
    """Routing hook: True when the text asks about public holidays."""
    return _extract_holiday_target(query) is not None


def holiday_answer(query: str) -> dict:
    """'is today a holiday in India' / 'when is the next holiday in the US'.

    Nager.Date (no key) — next public holiday, or today's if today is one."""
    cc = _extract_holiday_target(query)
    if not cc:
        return {"success": False,
                "message": "Tell me a country — like 'is today a holiday in India'.",
                "type": "holiday"}
    import datetime as _dt
    today = _dt.date.today()
    low = query.lower()
    if re.search(r"\bnext\b", low):
        data = _http_get_json(f"https://date.nager.at/api/v3/NextPublicHolidays/{cc}")
        if not isinstance(data, list) or not data:
            return {"success": False, "country": cc,
                    "message": f"I couldn't fetch the next holiday for {cc} right now.",
                    "type": "holiday"}
        nxt = data[0]
        d = nxt.get("date") or ""
        label = nxt.get("localName") or nxt.get("name") or "a public holiday"
        msg = f"The next public holiday in {cc} is {label} on {d}."
        return {"success": True, "message": msg, "type": "holiday",
                "country": cc, "name": label, "date": d}
    data = _http_get_json(f"https://date.nager.at/api/v3/PublicHolidays/{today.year}/{cc}")
    if not isinstance(data, list):
        return {"success": False, "country": cc,
                "message": f"I couldn't fetch holiday data for {cc} right now.",
                "type": "holiday"}
    todays = [h for h in data if h.get("date") == today.isoformat()]
    if todays:
        name = todays[0].get("localName") or todays[0].get("name") or "a public holiday"
        msg = f"Yes — today ({today.isoformat()}) is {name} in {cc}."
        return {"success": True, "message": msg, "type": "holiday",
                "country": cc, "name": name, "date": today.isoformat()}
    nxt = None
    for h in sorted(data, key=lambda x: x.get("date") or ""):
        if (h.get("date") or "") > today.isoformat():
            nxt = h
            break
    if nxt:
        name = nxt.get("localName") or nxt.get("name") or "a public holiday"
        msg = f"Today is not a holiday in {cc}. The next one is {name} on {nxt.get('date')}."
        return {"success": True, "message": msg, "type": "holiday",
                "country": cc, "name": name, "date": nxt.get("date")}
    return {"success": True, "country": cc,
            "message": f"No public holidays in {cc} are listed for {today.year}.",
            "type": "holiday"}


# ── earthquakes owner (USGS FDSN, no key) ────────────────────────────────────
def _extract_earthquake_target(query: str):
    """'earthquakes near Tokyo' / 'any earthquakes today' -> location or None."""
    low = query.lower().strip()
    if not re.search(r"\b(earthquake|earthquakes|quake|quakes)\b", low):
        return None
    m = re.search(r"\b(?:near|in|at|around)\s+([a-z][a-z .'-]{1,40}?)\s*$", low)
    if m:
        loc = m.group(1).strip().strip(".,!?;:")
        if loc and loc not in ("the", "a", "an", "here", "there", "me", "us", "my", "your", "this", "that"):
            return loc
    return None


def looks_like_earthquake(query: str) -> bool:
    """Routing hook: True when the text asks about recent earthquakes."""
    return _extract_earthquake_target(query) is not None


def earthquake_answer(query: str) -> dict:
    """'any earthquakes near Tokyo' -> the most recent significant quake.

    USGS FDSN event feed (no key). Honest 'none recently' vs 'unreachable'."""
    loc = _extract_earthquake_target(query)
    import urllib.parse
    params = ["format=geojson", "limit=3", "orderby=time"]
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query?" + "&".join(params)
    data = _http_get_json(url)
    if not data or not isinstance(data.get("features"), list):
        return {"success": False,
                "message": "I couldn't reach the earthquake service right now.",
                "type": "earthquake"}
    feats = data.get("features") or []
    if not feats:
        return {"success": True, "message": "No earthquakes detected in the last while.",
                "type": "earthquake"}
    top = feats[0]
    props = top.get("properties") or {}
    mag = props.get("mag")
    place = props.get("place") or "somewhere"
    when = props.get("time")
    when_txt = ""
    if when:
        try:
            import datetime as _dt
            when_txt = _dt.datetime.fromtimestamp(when / 1000).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            pass
    if loc:
        place = f"{place} (near {loc})" if loc.lower() not in place.lower() else place
    mag_txt = f"magnitude {mag:.1f}" if mag is not None else "magnitude unknown"
    msg = f"Most recent earthquake: {mag_txt} at {place}." + (f" ({when_txt})" if when_txt else "")
    return {"success": True, "message": msg, "type": "earthquake",
            "magnitude": mag, "place": props.get("place"), "time": when}


# ── books owner (Open Library, no key) ───────────────────────────────────────
# EXPLICIT book intent only: "find the book X" / "books by AUTHOR". A bare
# "who wrote X" is a GENERAL knowledge question (the evidence chain answers
# both "who wrote Dune" and "who wrote the Linux kernel" correctly) — it must
# never be hijacked by the book owner.
def _extract_book_target(query: str):
    """'find the book Dune' -> ("title", Dune); 'books by Frank Herbert'
    -> ("author", Frank Herbert). None for anything else."""
    low = query.lower().strip()
    m = re.search(r"\b(?:find|look\s+up|search\s+for)\s+the\s+book\s+(.+?)\s*$", low)
    if m:
        t = m.group(1).strip().strip(".,!?;:")
        if t and t not in ("the", "a", "an"):
            return "title", t
    m = re.search(r"\b(?:books|what(?:'s|\s+has)?)\s+by\s+(.+?)\s*(?:written)?\s*$", low)
    if m:
        t = m.group(1).strip().strip(".,!?;:")
        if t and t not in ("the", "a", "an", "it", "this", "that"):
            return "author", t
    return None


def looks_like_book(query: str) -> bool:
    """Routing hook: True when the text is an explicit book lookup."""
    return _extract_book_target(query) is not None


def book_answer(query: str) -> dict:
    """'find the book Dune' -> title + author + first publish year.
    'books by Frank Herbert' -> author-oriented answer.
    Open Library search (no key)."""
    parsed = _extract_book_target(query)
    if not parsed:
        return {"success": False,
                "message": "Tell me a book or author — like 'find the book Dune' or 'books by Frank Herbert'.",
                "type": "book"}
    kind, target = parsed
    import urllib.parse
    url = "https://openlibrary.org/search.json?q=" + urllib.parse.quote(target) + "&limit=3"
    data = _http_get_json(url)
    if not data or not isinstance(data.get("docs"), list) or not data["docs"]:
        return {"success": False, "target": target,
                "message": f"I couldn't find any books matching {target!r}.",
                "type": "book"}
    docs = data["docs"]
    top = docs[0]
    title = top.get("title") or ""
    authors = top.get("author_name") or []
    year = top.get("first_publish_year")
    # Open Library returns author names in EVERY language the record holds
    # ("Frank Herbert", "Френк Герберт"). Present one natural variant:
    # prefer Latin-script names, drop case-insensitive duplicates. General
    # dedup, never author-specific.
    def _is_latin(name: str) -> bool:
        return bool(name) and all(ord(ch) < 128 or ch.isspace() or ch.isdigit() for ch in name)
    _seen: set = set()
    _clean = []
    for _a in authors:
        _k = _a.strip().lower()
        if not _k or _k in _seen:
            continue
        _seen.add(_k)
        _clean.append(_a.strip())
    if any(_is_latin(a) for a in _clean):
        _clean = [a for a in _clean if _is_latin(a)]
    authors = _clean
    author_txt = ", ".join(a for a in authors[:2]) if authors else "unknown author"
    if kind == "author":
        msg = f"{title} was written by {author_txt}." + (f" (first published {year})" if year else "")
    else:
        msg = f"{title} — by {author_txt}." + (f" First published {year}." if year else "")
    return {"success": True, "message": msg, "type": "book", "title": title,
            "authors": authors[:2], "first_publish_year": year}


# ── router ───────────────────────────────────────────────────────────────────

def utility_answer(action: str, query: str, ctx=None, decision=None) -> dict:
    if action == "time":
        hint = ""
        if ctx is not None and getattr(ctx, "last_location", ""):
            hint = ctx.last_location
        return time_answer(query, ctx=ctx, location_hint=hint)
    if action == "date":
        return date_answer(query)
    if action == "weather":
        return weather_answer(query)
    if action == "convert":
        return convert_answer(query)
    if action == "package":
        return package_answer(query)
    if action == "feed":
        return feed_answer(query)
    if action == "calculate":
        return calculate_answer(query)
    if action == "project":
        return project_answer(query)
    if action == "watch":
        from mini_kio.monitoring.watches import watch_answer
        return watch_answer(query, ctx=ctx, decision=decision)
    if action == "remind":
        from mini_kio.monitoring.reminders import reminder_answer
        return reminder_answer(query, ctx=ctx, decision=decision)
    if action == "workflow":
        from mini_kio.execution.workflows import workflow_answer
        return workflow_answer(query, ctx=ctx, decision=decision)
    if action == "message":
        from mini_kio.communication.messages import message_answer
        return message_answer(query, ctx=ctx, decision=decision)
    if action == "research":
        from mini_kio.research.briefs import research_answer
        return research_answer(query, ctx=ctx, decision=decision)
    if action == "air_quality":
        return air_quality_answer(query)
    if action == "holiday":
        return holiday_answer(query)
    if action == "earthquake":
        return earthquake_answer(query)
    if action == "book":
        return book_answer(query)
    return {"success": False, "message": "I couldn't handle that utility request.", "type": "utility"}
