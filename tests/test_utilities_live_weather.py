"""
test_utilities_live_weather.py

Focused tests for the live weather owner (Open-Meteo, no key) and its honest
offline fallback. Network calls are stubbed — tests assert ROUTE and RESULT
shape, never live conditions.
"""

import pytest

from mini_kio.core.utilities import _extract_location, weather_answer


def _fake_openmeteo(monkeypatch):
    """Stub both geocoding and forecast endpoints with fixed JSON."""

    def _fake_urlopen(url, timeout=6):
        import io
        import json

        if "geocoding-api" in url:
            payload = {"results": [{"name": "London", "latitude": 51.5, "longitude": -0.12}]}
        else:
            payload = {
                "current": {
                    "temperature_2m": 17.3,
                    "apparent_temperature": 16.8,
                    "relative_humidity_2m": 62.0,
                    "weather_code": 2,
                    "wind_speed_10m": 11.4,
                }
            }
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)


def test_extract_location():
    assert _extract_location("what's the weather in london") == "london"
    assert _extract_location("weather in new york right now") == "new york"
    assert _extract_location("what's the weather") is None


def test_weather_answer_live_shape(monkeypatch):
    _fake_openmeteo(monkeypatch)
    res = weather_answer("what's the weather in london")
    assert res["success"] is True
    assert res["type"] == "weather"
    assert res["location"] == "London"
    assert "17" in res["message"]  # 17°C
    assert res["weather"]["description"] == "partly cloudy"


def test_weather_answer_offline_honest(monkeypatch):
    def _boom(url, timeout=6):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    res = weather_answer("what's the weather in london")
    assert res["success"] is True
    assert "can't check live weather" in res["message"]
    assert res["type"] == "weather"


def test_weather_answer_no_location(monkeypatch):
    def _boom(url, timeout=6):
        raise AssertionError("must not hit network without a location")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    res = weather_answer("what's the weather")
    assert res["success"] is True
    assert "no weather service" in res["message"]