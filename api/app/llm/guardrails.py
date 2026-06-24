"""Input guardrails for the drafting layer (Agents-SDK-style input guards). Two checks run on
the user query BEFORE it reaches the model:

* **prompt-injection / jailbreak detection** — a finance assistant must not obey instructions
  smuggled into a query ("ignore previous instructions", "you are now…", "reveal the system
  prompt"). On a hit we refuse to draft and abstain — the safe default for a zero-error product.
* **PII redaction** — when the model is a *cloud* provider (Claude), Indian PII (PAN, Aadhaar,
  GSTIN, email, phone) is masked before it leaves the box. Local Ollama keeps the original text.

Pure and deterministic: same input → same findings, no IO.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+|the\s+|your\s+)?(previous|prior|above)\s+(instructions|prompts?)",
        r"disregard\s+(all\s+|the\s+|your\s+)?(previous|prior|above)?\s*(instructions|rules)",
        r"\byou\s+are\s+now\b",
        r"\bact\s+as\b",
        r"\bsystem\s+prompt\b",
        r"reveal\s+(the\s+|your\s+)?(system\s+prompt|instructions|secret|password|api[\s_-]?key)",
        r"\bjailbreak\b",
        r"\bnew\s+instructions\s*:",
        r"override\s+(the\s+|your\s+)?(rules|instructions|guardrails)",
    )
)

# name -> (pattern, redaction placeholder). Order matters: GSTIN before PAN (GSTIN embeds a PAN).
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("gstin", re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b")),
    ("pan", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("aadhaar", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("phone", re.compile(r"(?<!\d)(?:\+91[-\s]?)?[6-9]\d{9}(?!\d)")),
)


@dataclass(frozen=True)
class GuardResult:
    allowed: bool  # False when a prompt-injection attempt is detected
    text: str  # the (possibly PII-redacted) query to actually send to the model
    injection: bool
    findings: list[str] = field(default_factory=list)  # e.g. ["injection", "pii:pan"]


def scan_input(query: str, *, redact_pii: bool = False) -> GuardResult:
    findings: list[str] = []
    injection = any(p.search(query) for p in _INJECTION_PATTERNS)
    if injection:
        findings.append("injection")

    text = query
    if redact_pii:
        for name, pat in _PII_PATTERNS:
            if pat.search(text):
                findings.append(f"pii:{name}")
                text = pat.sub(f"[REDACTED-{name.upper()}]", text)

    return GuardResult(allowed=not injection, text=text, injection=injection, findings=findings)
