"""WS10.2 — the severity-event alerting hook.

Three properties are load-bearing:

1. Dormant by default: no webhook configured -> nothing leaves the box (only a local log).
2. Configured -> the event is POSTed as JSON to exactly the configured URL, with no PII fields.
3. The alerter can never take the request down: a delivery failure is swallowed, not raised —
   the caller is already serving a 500.
"""

from __future__ import annotations

import json
import threading

import pytest

from app.core import alerting


class _Recorder:
    def __init__(self) -> None:
        self.requests: list = []
        self.done = threading.Event()

    def __call__(self, req, timeout=None):
        self.requests.append((req, timeout))
        self.done.set()

        class _Resp:
            status = 200

        return _Resp()


@pytest.fixture
def recorder(monkeypatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(alerting.urllib.request, "urlopen", rec)
    return rec


def test_dormant_without_webhook_url(recorder: _Recorder, monkeypatch):
    monkeypatch.delenv("MAISHA_ALERT_WEBHOOK_URL", raising=False)
    alerting.get_settings.cache_clear()
    try:
        alerting.emit("unhandled_exception", "ValueError on /api/x")
        assert not recorder.done.wait(timeout=0.3)
        assert recorder.requests == []
    finally:
        alerting.get_settings.cache_clear()


def test_configured_webhook_receives_the_event_as_json(recorder: _Recorder, monkeypatch):
    monkeypatch.setenv("MAISHA_ALERT_WEBHOOK_URL", "http://alerts.internal/hook")
    alerting.get_settings.cache_clear()
    try:
        alerting.emit("unhandled_exception", "ValueError on /api/x")
        assert recorder.done.wait(timeout=2), "webhook thread never fired"
        ((req, timeout),) = recorder.requests
        assert req.full_url == "http://alerts.internal/hook"
        assert timeout == alerting._TIMEOUT_S
        body = json.loads(req.data.decode())
        assert body["source"] == "maisha-mahsa"
        assert body["event"] == "unhandled_exception"
        assert body["severity"] == "critical"
        assert body["detail"] == "ValueError on /api/x"
        assert set(body) == {"source", "event", "severity", "detail", "at"}  # no extra fields
    finally:
        alerting.get_settings.cache_clear()


def test_delivery_failure_never_raises(monkeypatch):
    fired = threading.Event()

    def _boom(req, timeout=None):
        fired.set()
        raise OSError("connection refused")

    monkeypatch.setattr(alerting.urllib.request, "urlopen", _boom)
    monkeypatch.setenv("MAISHA_ALERT_WEBHOOK_URL", "http://alerts.internal/hook")
    alerting.get_settings.cache_clear()
    try:
        alerting.emit("unhandled_exception", "boom")  # must not raise from the thread spawn
        assert fired.wait(timeout=2)
        # the daemon thread swallowed the OSError (a raise would surface as an unraisable
        # exception and, more importantly, could never propagate into the request path)
    finally:
        alerting.get_settings.cache_clear()
