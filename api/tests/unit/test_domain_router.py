import pytest

from app.core.domain import (
    BaseDomainService,
    DomainManifest,
    Feature,
    FeatureState,
    PendingDomainService,
)
from app.domains import build_registry

ALL_DOMAINS = (
    "treasury",
    "revenue",
    "payables",
    "payroll",
    "gst",
    "tax",
    "ledger",
    "forecast",
    "equity",
    "compliance",
    "expense",
    "vault",
)


def test_registry_has_all_twelve_domains():
    r = build_registry()
    assert len(r.domains()) == 12
    for d in ALL_DOMAINS:
        assert r.get(d) is not None


def test_classify_routes_by_keyword():
    r = build_registry()
    assert r.classify("what is my cash runway?") == "treasury"
    assert r.classify("generate the gstr-3b for may") == "gst"
    assert r.classify("run payroll and check pf") == "payroll"
    assert r.classify("file the documents in the vault") == "vault"
    assert r.classify("hello there") is None


def test_all_domains_are_implemented():
    """Every one of the 12 domains now ships a real service (no PendingDomainService)."""
    r = build_registry()
    for d in ALL_DOMAINS:
        svc = r.get(d)
        assert isinstance(svc, BaseDomainService)
        assert not isinstance(svc, PendingDomainService)
        assert svc.manifest.features  # every module declares a feature manifest


def test_pending_domain_service_contract():
    """The PendingDomainService scaffold still refuses to emit a snapshot (kept for any
    future domain added ahead of its implementation)."""
    manifest = DomainManifest(
        domain="future",
        features=[Feature("scaffold", "Module scaffold", FeatureState.DONE)],
    )
    svc = PendingDomainService("future", ("future",), manifest)
    with pytest.raises(NotImplementedError):
        svc.build_snapshot(None)
