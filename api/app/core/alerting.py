"""WS10.2 — CERT-In posture: the severity-event alerting hook.

CERT-In's reporting direction gives 6 hours from *noticing* an incident — so the engineering
control this module provides is noticing: any severity event (today: every unhandled 5xx via
``app.main._unhandled_error``; callers may add more) is pushed to the operator's webhook the
moment it happens, instead of waiting to be found in a log. The human reporting steps live in
``docs/legal/CERTIN_INCIDENT_REPORT_TEMPLATE.md``.

Design constraints, in order:

* **Never take the request down.** An alert is best-effort telemetry about a failure already in
  progress — a second failure inside the alerter must not mask or amplify the first. Every
  exception is swallowed (logged locally, no PII).
* **No new dependency.** stdlib ``urllib`` + a daemon thread (the caller is mid-500; never
  block the response on an outbound HTTP call).
* **Dormant by default.** With ``MAISHA_ALERT_WEBHOOK_URL`` unset the event is logged locally
  at ERROR and nothing leaves the box (dev/test default). OWNER-STEP: set the env var to a real
  webhook (Slack/Discord/alertmanager receiver) — docs/DEPLOYMENT.md §10.

No PII in payloads (§0.8): callers pass an event name and a short technical detail (exception
class, route path), never request bodies or user data.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
from datetime import UTC, datetime

from app.config import get_settings

_log = logging.getLogger("maisha.alerting")

_TIMEOUT_S = 5.0


def _post(url: str, payload: bytes) -> None:
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=_TIMEOUT_S)  # noqa: S310 — operator-configured URL
    except Exception as exc:  # noqa: BLE001 — best-effort: never raise out of the alerter
        _log.error("alert webhook delivery failed: %s", exc)


def emit(event: str, detail: str, severity: str = "critical") -> None:
    """Emit one severity event: local ERROR log always; webhook POST when configured.

    ``detail`` must be PII-free (exception class, route path — never bodies or user data).
    Returns immediately; delivery happens on a daemon thread so a caller that is already
    serving a failure never blocks on the network.
    """
    _log.error("severity event [%s/%s]: %s", severity, event, detail)
    url = get_settings().alert_webhook_url
    if not url:
        return
    payload = json.dumps(
        {
            "source": "maisha-mahsa",
            "event": event,
            "severity": severity,
            "detail": detail,
            "at": datetime.now(UTC).isoformat(),
        }
    ).encode()
    threading.Thread(target=_post, args=(url, payload), daemon=True).start()
