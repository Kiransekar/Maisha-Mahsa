"""The domain-module contract. Every one of the 12 PRD domains implements
``BaseDomainService`` so they are uniform, independently testable, and discoverable by the
``DomainRouter``. A module declares a ``DomainManifest`` — the unit of build progress."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session


class FeatureState(enum.StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"


@dataclass(frozen=True)
class Feature:
    key: str
    title: str
    state: FeatureState = FeatureState.NOT_STARTED


@dataclass(frozen=True)
class DomainManifest:
    """Declares a domain's PRD features and their build state. `make verify` plus the
    `tests/unit/test_manifests.py` guard keep this honest."""

    domain: str
    features: list[Feature] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return bool(self.features) and all(f.state is FeatureState.DONE for f in self.features)

    def pct_done(self) -> float:
        if not self.features:
            return 0.0
        done = sum(1 for f in self.features if f.state is FeatureState.DONE)
        return round(100.0 * done / len(self.features), 1)


class BaseDomainService(ABC):
    """Contract for a domain module.

    Concrete services build a deterministic *snapshot* dict from their SQLite data and the
    ``DomainRouter`` hands it to Mahsa for fold/validate/unfold. Business math lives here
    (in exact paise); presentation decisions live in Mahsa.
    """

    #: Domain key, must match a `Domain` variant in the Rust core.
    domain: str
    #: Keywords used by the `DomainRouter` to classify free-text queries.
    keywords: tuple[str, ...] = ()
    #: Feature manifest (build progress).
    manifest: DomainManifest

    @abstractmethod
    def build_snapshot(self, session: Session) -> dict[str, Any]:
        """Compute the Mahsa snapshot for this domain from persisted data.

        Must be pure with respect to ``session`` (read-only) and deterministic given the
        same rows. Money values go in as integer paise.
        """
        raise NotImplementedError


class PendingDomainService(BaseDomainService):
    """Placeholder for a domain that is scaffolded but not yet built. It is a *typed,
    explicit* pending state — never a silent stub. Calling ``build_snapshot`` raises so a
    half-built domain can never quietly emit a zero snapshot to Mahsa."""

    def __init__(self, domain: str, keywords: tuple[str, ...], manifest: DomainManifest):
        self.domain = domain
        self.keywords = keywords
        self.manifest = manifest

    def build_snapshot(self, session: Session) -> dict[str, Any]:
        raise NotImplementedError(
            f"domain '{self.domain}' is not implemented yet — see BUILD_PROGRESS.md"
        )
