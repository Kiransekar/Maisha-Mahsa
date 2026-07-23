"""WS10.2 — CERT-In posture config tests (the ticket's "config tests" verify clause).

These parse the REAL infra files — a hand-edit that silently drops the 180-day retention,
the journald log pipeline, or the NTP deploy gate fails here, not in an incident.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA = REPO_ROOT / "infra"

DAY_S = 86400


def test_every_prod_service_logs_to_journald():
    compose = yaml.safe_load((INFRA / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert services, "prod compose has no services?"
    for name, svc in services.items():
        logging = svc.get("logging")
        assert logging is not None, f"service {name!r} has no logging config (WS10.2 retention)"
        assert logging["driver"] == "journald", (
            f"service {name!r} logs via {logging.get('driver')!r}, not journald — the 180-day "
            "retention window (infra/host/journald-maisha.conf) only covers the journal"
        )


def test_journald_retention_window_is_at_least_180_days():
    conf = (INFRA / "host/journald-maisha.conf").read_text(encoding="utf-8")
    m = re.search(r"^MaxRetentionSec=(\S+)$", conf, re.MULTILINE)
    assert m, "journald-maisha.conf must set MaxRetentionSec"
    value = m.group(1)
    seconds = int(value[:-3]) * DAY_S if value.endswith("day") else int(value)
    assert seconds >= 180 * DAY_S, f"retention window {value} is below the CERT-In 180 days"
    assert re.search(r"^Storage=persistent$", conf, re.MULTILINE), (
        "journal must be persistent — volatile storage loses the retention window on reboot"
    )


def test_deploy_script_gates_on_host_ntp_sync():
    deploy = (INFRA / "deploy.sh").read_text(encoding="utf-8")
    assert "NTPSynchronized" in deploy, "deploy.sh lost the WS10.2 NTP sync gate"
    # the gate must be a hard stop (exit 1), not a warning that scrolls past
    ntp_block = deploy.split("NTPSynchronized", 1)[1][:400]
    assert "exit 1" in ntp_block, "the NTP gate must refuse to deploy, not just warn"


def test_alert_webhook_env_var_is_documented_in_both_env_examples():
    for env_file in (REPO_ROOT / ".env.example", REPO_ROOT / "api/.env.example"):
        assert "MAISHA_ALERT_WEBHOOK_URL" in env_file.read_text(encoding="utf-8"), (
            f"{env_file.name} lost the WS10.2 alert-webhook OWNER-STEP"
        )
