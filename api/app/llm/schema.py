"""The ``ActionClaim`` — the strict, typed structure the Maisha LLM layer must emit, and the
only shape the eval harness (and, in P0-②, the ``run_loop`` LLM step) accepts.

It is *drafted* by the model and never trusted as a verdict: every number is recomputed by
Mahsa downstream (Golden Rule, CLAUDE.md §1). Two deliberate strictnesses:

* ``extra="forbid"`` — the model cannot smuggle in fields the harness won't inspect.
* money is integer **paise as decimal strings**, never floats — ``StrictStr`` rejects a raw
  ``float`` outright, so no ``0.1``-style rounding error can enter through a claim. Strings
  also make equality exact, which is what the pass^k consistency check relies on.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class RuleAssertion(BaseModel):
    """A statutory rule the model claims applies. Every assertion must name a statute and a
    section (no bare rule ids) so a citation can never be fabricated without a source."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    statute: str
    section: str

    @property
    def citation(self) -> str:
        return f"{self.statute} / {self.section}"


class ActionClaim(BaseModel):
    """A single drafted answer to a user query for one domain.

    ``claims`` maps a metric name to its canonical decimal **string** (paise for money,
    plain integers/decimals for counts and ratios). String-typed so equality is exact and a
    pass^k run is a literal string comparison.
    """

    model_config = ConfigDict(extra="forbid")

    domain: str
    narrative: str = ""
    claims: dict[str, StrictStr] = Field(default_factory=dict)
    rule_assertions: list[RuleAssertion] = Field(default_factory=list)
    abstained: bool = False
    confidence: float | None = None

    def canonical(self) -> str:
        """A stable serialization for pass^k equality (sorted keys, so dict ordering in
        ``claims`` can't make two equivalent claims look inconsistent)."""
        return json.dumps(self.model_dump(mode="json"), sort_keys=True)
