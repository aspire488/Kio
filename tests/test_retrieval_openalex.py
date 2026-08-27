"""
test_retrieval_openalex.py

Focused tests for the OpenAlex scholarly probe in the retrieval hierarchy
(no key). The HTTP call is stubbed — asserts the probe's result shape,
abstract reconstruction, and that it participates in retrieve_evidence.
"""

import pytest

from mini_kio.intelligence.retrieval_router import (
    RetrievalRouter,
    _reconstruct_abstract,
)

OPENALEX_WORK = {
    "display_name": "Attention Is All You Need",
    "publication_date": "2017-06-12",
    "doi": "https://doi.org/10.48550/arXiv.1706.03762",
    "abstract_inverted_index": {
        "the": [0],
        "dominant": [1],
        "sequence": [2],
        "transduction": [3],
        "models": [4],
        "are": [5],
        "based": [6],
        "on": [7],
        "complex": [8],
        "recurrent": [9],
        "or": [10],
        "convolutional": [11],
        "neural": [12],
        "networks": [13],
        "that": [14],
        "include": [15],
        "attention": [16],
    },
}


def _fake_abstract():
    return ("the dominant sequence transduction models are based on complex "
            "recurrent or convolutional neural networks that include attention")


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"results": [OPENALEX_WORK]}


def _stub_requests(monkeypatch, resp):
    def _fake_get(url, headers=None, timeout=8):
        assert "api.openalex.org/works" in url
        return resp
    monkeypatch.setattr("mini_kio.intelligence.retrieval_router.requests.get", _fake_get)


def test_reconstruct_abstract():
    assert _reconstruct_abstract(OPENALEX_WORK["abstract_inverted_index"]) == _fake_abstract()
    assert _reconstruct_abstract(None) == ""
    assert _reconstruct_abstract({}) == ""


def test_try_openalex_result_shape(monkeypatch):
    _stub_requests(monkeypatch, _FakeResponse())
    router = RetrievalRouter(timeout_s=5)
    res = router._try_openalex("attention is all you need", None)
    assert res is not None
    assert res.source == "OpenAlex"
    assert res.title == "Attention Is All You Need"
    assert res.published_date == "2017-06-12"
    assert res.url == OPENALEX_WORK["doi"]
    assert "recurrent or convolutional neural networks" in res.raw_content


def test_try_openalex_empty(monkeypatch):
    _stub_requests(monkeypatch, _FakeResponse())
    router = RetrievalRouter(timeout_s=5)
    with pytest.MonkeyPatch.context() as mp:
        for name in ("_try_exa", "_try_tavily", "_try_jina", "_try_wikipedia",
                     "_try_ddg", "_try_media_providers"):
            mp.setattr(router, name, lambda q, t: None)
        evidence = router.retrieve_evidence("attention is all you need")
    assert evidence and evidence[0].source == "OpenAlex"


def test_openalex_stats_tracking(monkeypatch):
    _stub_requests(monkeypatch, _FakeResponse())
    router = RetrievalRouter(timeout_s=5)
    with pytest.MonkeyPatch.context() as mp:
        for name in ("_try_exa", "_try_tavily", "_try_jina", "_try_wikipedia",
                     "_try_ddg", "_try_media_providers"):
            mp.setattr(router, name, lambda q, t: None)
        res = router.retrieve("attention is all you need")
    assert res is not None and res.source == "OpenAlex"
    assert router.stats["openalex_hits"] == 1