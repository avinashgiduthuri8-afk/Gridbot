"""Tests for replay/fetch_coindcx_history.py's retry-with-backoff and
post-fetch coverage-check logic. Network calls are monkeypatched — this
script needs live internet access to actually run, which this test
environment doesn't have, so only the retry/coverage logic itself (which
doesn't require a real network call) is exercised here.
"""
from __future__ import annotations

import pytest

pytest.importorskip("requests")

# fetch_coindcx_history.py lives outside the normal package import path
# assumptions (it's a standalone script), but is still a valid module.
from replay import fetch_coindcx_history as fetch_mod


class _FakeResponse:
    def __init__(self, status_code: int, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise fetch_mod.requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


def test_get_with_retry_succeeds_on_first_try(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(1)
        return _FakeResponse(200, json_data={"ok": True})

    monkeypatch.setattr(fetch_mod.requests, "get", fake_get)
    resp = fetch_mod._get_with_retry("http://example.test", timeout=5)
    assert resp.json() == {"ok": True}
    assert len(calls) == 1


def test_get_with_retry_retries_on_429_then_succeeds(monkeypatch):
    responses = [_FakeResponse(429), _FakeResponse(429), _FakeResponse(200, {"ok": True})]
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(1)
        return responses[len(calls) - 1]

    monkeypatch.setattr(fetch_mod.requests, "get", fake_get)
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: None)  # don't actually wait in tests

    resp = fetch_mod._get_with_retry("http://example.test", timeout=5)
    assert resp.json() == {"ok": True}
    assert len(calls) == 3


def test_get_with_retry_gives_up_after_max_retries_on_5xx(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _FakeResponse(503)

    monkeypatch.setattr(fetch_mod.requests, "get", fake_get)
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: None)

    with pytest.raises(fetch_mod.requests.exceptions.HTTPError):
        fetch_mod._get_with_retry("http://example.test", timeout=5)


def test_get_with_retry_does_not_retry_permanent_4xx_errors(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(1)
        return _FakeResponse(404)

    monkeypatch.setattr(fetch_mod.requests, "get", fake_get)
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: None)

    with pytest.raises(fetch_mod.requests.exceptions.HTTPError):
        fetch_mod._get_with_retry("http://example.test", timeout=5)
    assert len(calls) == 1, "a permanent 4xx error must not be retried"


def test_get_with_retry_retries_transient_connection_errors(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(1)
        if len(calls) < 3:
            raise fetch_mod.requests.exceptions.ConnectionError("connection reset")
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(fetch_mod.requests, "get", fake_get)
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: None)

    resp = fetch_mod._get_with_retry("http://example.test", timeout=5)
    assert resp.json() == {"ok": True}
    assert len(calls) == 3


def test_check_coverage_passes_when_range_matches():
    start_ms, end_ms = 0, 1_000_000
    candles = [{"time": 0}, {"time": 500_000}, {"time": 999_000}]
    assert fetch_mod._check_coverage("BTCINR", candles, start_ms, end_ms) is True


def test_check_coverage_fails_when_range_is_much_shorter(capsys):
    start_ms, end_ms = 0, 1_000_000
    candles = [{"time": 0}, {"time": 100_000}]  # only 10% of the requested span
    assert fetch_mod._check_coverage("BTCINR", candles, start_ms, end_ms) is False
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "BTCINR" in captured.err


def test_check_coverage_fails_for_empty_candles(capsys):
    assert fetch_mod._check_coverage("BTCINR", [], 0, 1_000_000) is False
    captured = capsys.readouterr()
    assert "WARNING" in captured.err


def test_check_coverage_handles_zero_requested_span():
    # start == end shouldn't divide by zero
    assert fetch_mod._check_coverage("BTCINR", [{"time": 0}], 500, 500) is True
