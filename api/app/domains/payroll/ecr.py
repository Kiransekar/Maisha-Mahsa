"""EPFO ECR (Electronic Challan cum Return) text-file builder. The unified-portal upload is a
plain-text file of member detail lines — 11 fields per line, ``#~#``-delimited, amounts in
whole rupees (the wage month / contribution rate are entered on the portal, so no header line).
Pure: it formats already-computed values, it doesn't compute statutory amounts."""

from __future__ import annotations

from dataclasses import dataclass

ECR_DELIMITER = "#~#"

# Column order per the EPFO unified-portal ECR file structure.
COLUMNS = (
    "uan",
    "member_name",
    "gross_wages",
    "epf_wages",
    "eps_wages",
    "edli_wages",
    "epf_contri_remitted",
    "eps_contri_remitted",
    "epf_eps_diff_remitted",
    "ncp_days",
    "refund_of_advances",
)


@dataclass(frozen=True)
class EcrMember:
    uan: str
    member_name: str
    gross_wages: int  # whole rupees
    epf_wages: int
    eps_wages: int
    edli_wages: int
    epf_contri_remitted: int
    eps_contri_remitted: int
    epf_eps_diff_remitted: int
    ncp_days: int = 0
    refund_of_advances: int = 0

    def to_line(self) -> str:
        return ECR_DELIMITER.join(str(getattr(self, c)) for c in COLUMNS)


def build_ecr(members: list[EcrMember]) -> str:
    """The ECR text file body — one ``#~#``-delimited line per member, newline-separated."""
    return "\n".join(m.to_line() for m in members)
