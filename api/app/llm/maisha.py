"""Maisha — the drafting orchestrator. Turns ``(snapshot, query, domain)`` into a strict
:class:`ActionClaim` by: enriching the snapshot into deterministic FACTS (tools, never LLM
math), building the prompt, asking the LLM for a schema-constrained claim, and parsing it.

It is a *drafter*: the claim it returns is recomputed/validated by Mahsa and (in eval) checked
paise-exact against ground truth. The same object satisfies the :class:`ClaimProducer`
protocol used by both ``core.loop.run_loop`` and the eval harness.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.llm import prompt, tools
from app.llm.client import LLMClient
from app.llm.guardrails import scan_input
from app.llm.schema import ActionClaim

_log = logging.getLogger("maisha.guardrails")


class ClaimProducer(Protocol):
    """Anything that drafts an :class:`ActionClaim` from a snapshot + query. Implemented by
    :class:`MaishaGenerator` (real LLM) and by the eval harness's scripted stub."""

    async def produce(
        self,
        *,
        snapshot: dict[str, Any],
        query: str,
        domain: str,
        case_id: str = "",
        feedback: str | None = None,
        memory: str | None = None,
    ) -> ActionClaim: ...


class MaishaGenerator:
    def __init__(self, client: LLMClient, *, redact_pii: bool = False, label: str = "llm") -> None:
        self._client = client
        self._redact_pii = redact_pii
        #: short identifier (e.g. "ollama:qwen3:14b") recorded in the LLM trace.
        self.label = label

    async def produce(
        self,
        *,
        snapshot: dict[str, Any],
        query: str,
        domain: str,
        case_id: str = "",
        feedback: str | None = None,
        memory: str | None = None,
    ) -> ActionClaim:
        # Input guardrails run before the model sees anything (Agents-SDK input-guard pattern).
        guard = scan_input(query, redact_pii=self._redact_pii)
        if not guard.allowed:
            _log.warning("query for domain %r blocked: %s", domain, guard.findings)
            return ActionClaim(
                domain=domain,
                narrative="Query blocked by input guardrails (possible prompt injection).",
                abstained=True,
            )
        if guard.findings:
            _log.info("redacted PII before send for domain %r: %s", domain, guard.findings)

        # SPEC-MEMCITE-1.0 §A6: remembered text is DATA, not instructions — the memory block
        # passes the SAME injection screen the query gets. A block that trips it is DROPPED from
        # the prompt (the query still gets answered) and the event is logged loudly, never
        # silently. PII redaction applies on the cloud path exactly as for the query.
        mem: str | None = None
        if memory:
            mguard = scan_input(memory, redact_pii=self._redact_pii)
            if mguard.injection:
                _log.warning(
                    "memory block for domain %r dropped by injection screen: %s",
                    domain,
                    mguard.findings,
                )
            else:
                mem = mguard.text
                if mguard.findings:
                    _log.info("redacted PII in memory block for domain %r: %s", domain,
                              mguard.findings)

        facts = tools.enrich(snapshot)
        user = prompt.build_user_prompt(
            domain=domain,
            query=guard.text,
            facts=facts,
            rules=prompt.rules_for_domain(domain),
            feedback=feedback,
            memory=mem,
        )
        raw = await self._client.complete(
            system=prompt.SYSTEM_PROMPT,
            user=user,
            schema=ActionClaim.model_json_schema(),
        )
        claim = ActionClaim.model_validate(raw)
        # The router already decided the domain; the model doesn't get to reclassify it.
        if claim.domain != domain:
            claim = claim.model_copy(update={"domain": domain})
        return claim
