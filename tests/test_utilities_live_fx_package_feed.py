"""
test_utilities_live_fx_package_feed.py

Focused tests for the three no-key capability owners added alongside live
weather: live FX rates (Frankfurter, static fallback), package status
(PyPI), and feed/release watch (GitHub releases.atom + PyPI RSS). Network
calls are stubbed at the single `_http_get_bytes` seam — tests assert ROUTE
and RESULT shape, never live data.
"""

import json

import pytest

from mini_kio.core.utilities import (
    convert_answer,
    feed_answer,
    looks_like_feed,
    looks_like_package,
    package_answer,
)

FRANKFURTER = json.dumps({
    "amount": 1.0, "base": "USD", "date": "2026-08-14",
    "rates": {"EUR": 0.86453, "GBP": 0.73874, "JPY": 159.01},
}).encode("utf-8")

PYPI_JSON = json.dumps({
    "info": {"version": "9.9.9", "summary": "Test package"},
    "releases": {"9.9.9": [{"upload_time_iso_8601": "2026-08-01T10:00:00Z"}]},
}).encode("utf-8")

GITHUB_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Release notes from openai/openai</title>
  <entry>
    <title>v1.2.0</title>
    <link rel="alternate" type="text/html" href="https://github.com/openai/openai/releases/tag/v1.2.0"/>
    <id>tag:github.com,2008:openai/openai/v1.2.0</id>
    <published>2026-08-10T00:00:00Z</published>
    <updated>2026-08-10T00:00:00Z</updated>
  </entry>
  <entry>
    <title>v1.1.0</title>
    <link href="https://github.com/openai/openai/releases/tag/v1.1.0"/>
    <published>2026-07-01T00:00:00Z</published>
  </entry>
</feed>"""

PYPI_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Requests releases</title>
  <item>
    <title>Requests 2.34.2</title>
    <link>https://pypi.org/project/requests/2.34.2/</link>
    <guid>https://pypi.org/project/requests/2.34.2/</guid>
    <pubDate>Wed, 30 Jul 2025 00:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Requests 2.34.1</title>
    <link>https://pypi.org/project/requests/2.34.1/</link>
    <pubDate>Mon, 05 May 2025 00:00:00 GMT</pubDate>
  </item>
</channel></rss>"""


def _stub_http(monkeypatch, payload):
    def _fake(url, timeout=6):
        return payload
    monkeypatch.setattr("mini_kio.core.utilities._http_get_bytes", _fake)


# ── live FX ──────────────────────────────────────────────────────────────────

def test_convert_uses_live_rate(monkeypatch):
    _stub_http(monkeypatch, FRANKFURTER)
    res = convert_answer("convert 100 dollars to euros")
    assert res["success"] is True
    assert res["type"] == "convert"
    assert res["approximate"] is False
    assert res["result"] == pytest.approx(86.453)
    assert "(live rate)" in res["message"]


def test_convert_cross_currency_live(monkeypatch):
    _stub_http(monkeypatch, FRANKFURTER)
    res = convert_answer("convert 100 euros to jpy")
    assert res["success"] is True
    assert res["approximate"] is False
    assert res["result"] == pytest.approx(100 * 159.01 / 0.86453)


def test_convert_static_fallback_when_offline(monkeypatch):
    _stub_http(monkeypatch, None)  # network failure
    res = convert_answer("convert 100 dollars to euros")
    assert res["success"] is True
    assert res["approximate"] is True
    assert res["result"] == 92.0  # static table usd->eur
    assert "about" in res["message"]


# ── package status ──────────────────────────────────────────────────────────

def test_package_latest_and_outdated(monkeypatch):
    _stub_http(monkeypatch, PYPI_JSON)
    res = package_answer("what's the latest version of requests")
    assert res["success"] is True
    assert res["type"] == "package"
    assert res["package"] == "requests"
    assert res["version"] == "9.9.9"
    assert res["released"] == "2026-08-01"
    assert "9.9.9" in res["message"]


def test_package_is_outdated_phrase(monkeypatch):
    _stub_http(monkeypatch, PYPI_JSON)
    res = package_answer("is requests outdated")
    assert res["success"] is True
    assert res["version"] == "9.9.9"
    assert "outdated" in res["message"]


def test_package_unreachable(monkeypatch):
    _stub_http(monkeypatch, None)
    res = package_answer("what's the latest version of requests")
    assert res["success"] is False
    assert "couldn't reach PyPI" in res["message"]


def test_looks_like_package():
    assert looks_like_package("what's the latest version of requests")
    assert looks_like_package("latest version of feedparser")
    assert looks_like_package("is requests outdated")
    assert not looks_like_package("what's the weather in paris")
    assert not looks_like_package("what's the latest version of the plan")


# ── feed / release watch ─────────────────────────────────────────────────────

def test_feed_github_atom(monkeypatch):
    _stub_http(monkeypatch, GITHUB_ATOM)
    res = feed_answer("latest releases of openai/openai")
    assert res["success"] is True
    assert res["type"] == "feed"
    assert res["kind"] == "github"
    assert res["feed"] == "openai/openai (GitHub)"
    assert res["items"][0]["title"] == "v1.2.0"
    assert res["items"][0]["date"] == "2026-08-10"
    assert "v1.2.0" in res["message"]


def test_feed_pypi_rss(monkeypatch):
    _stub_http(monkeypatch, PYPI_RSS)
    res = feed_answer("what's new in requests")
    assert res["success"] is True
    assert res["kind"] == "pypi"
    assert res["items"][0]["title"] == "Requests 2.34.2"
    assert res["items"][0]["date"] == "2025-07-30"
    assert "Requests 2.34.2" in res["message"]


def test_feed_unreachable(monkeypatch):
    _stub_http(monkeypatch, None)
    res = feed_answer("latest releases of openai/openai")
    assert res["success"] is False
    assert "couldn't fetch" in res["message"]


def test_feed_bad_xml(monkeypatch):
    _stub_http(monkeypatch, b"<not xml")
    res = feed_answer("latest releases of openai/openai")
    assert res["success"] is False


def test_looks_like_feed():
    assert looks_like_feed("latest releases of openai/openai")
    assert looks_like_feed("recent releases of feedparser")
    assert looks_like_feed("what's new in requests")
    assert looks_like_feed("what is new in fastapi")
    assert not looks_like_feed("how's the weather in paris")
    assert not looks_like_feed("latest releases of the")