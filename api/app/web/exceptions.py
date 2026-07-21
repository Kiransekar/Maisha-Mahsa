"""Exception Inbox assembler (WS7.5 — the research's #1 feature signal: Xero's 243-vote,
3-year bulk-reconcile request; docs/WS7_UX_RESEARCH.md). Pure view-model layer: takes
already-fetched inputs (approvals from app.core.approvals.pending_approvals; blocked figures
from a Mahsa recompute fold via app.core.verify / mahsa_client) and groups them into the five
WS7.5 queues, ranked by rupee impact. No IO here — the router does the fetching.

Grammar for every item (research T5/T6, ban bare "Something went wrong"): each item states
what happened / when / the ₹-consequence / one one-tap next action. A figure that failed Mahsa's
recompute carries verify_state="unbacked" so the UI renders the ✕ verification glyph (§0.4 — an
unverified figure is never dressed up as ✓).

The three queues without a real data source yet (Needs document / Needs categorization /
Feed broken) render an honest empty state with a noted stub source for later wiring — they are
NEVER populated with fabricated items.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

# ── Queue catalogue ──────────────────────────────────────────────────────────
# Order = display order. `source` names where real items come from (None = not yet wired,
# honest-empty). `stub_note` is the later-wiring pointer for the un-sourced queues.
QUEUE_ORDER = (
    "needs_document",
    "needs_categorization",
    "mahsa_blocked",
    "awaiting_approval",
    "feed_broken",
)

QUEUE_META: dict[str, dict[str, str | None]] = {
    "needs_document": {
        "label": "Needs document",
        "source": None,
        "empty": "Nothing waiting on a document. A figure that needs a source file you "
        "haven't uploaded would appear here.",
        "stub_note": "Stub source: vault document-requirement gaps "
        "(app/domains/vault) — wire when the requirement tracker lands.",
    },
    "needs_categorization": {
        "label": "Needs categorization",
        "source": None,
        "empty": "No uncategorized transactions. Bank/expense lines with no ledger head "
        "would appear here.",
        "stub_note": "Stub source: uncategorized bank/expense lines "
        "(app/domains/expense, app/domains/ledger) — wire on bank-import ingest.",
    },
    "mahsa_blocked": {
        "label": "Mahsa blocked",
        "source": "app.core.verify / mahsa recompute fold",
        "empty": "No blocked figures — every recomputed figure matched Mahsa to the paisa.",
        "stub_note": None,
    },
    "awaiting_approval": {
        "label": "Awaiting approval",
        "source": "app.core.approvals.pending_approvals",
        "empty": "Nothing awaiting sign-off.",
        "stub_note": None,
    },
    "feed_broken": {
        "label": "Feed broken",
        "source": None,
        "empty": "All data feeds healthy. A stale or disconnected bank/GSTN feed would "
        "appear here.",
        "stub_note": "Stub source: connection-health strip (WS7.7) — wire when feed "
        "health checks land.",
    },
}


# ── Inputs the router hands the (pure) assembler ─────────────────────────────
@dataclass(frozen=True)
class ApprovalInput:
    """One pending sign-off (from ApprovalItem). ``amount_paise`` is the figure at stake when
    the domain exposes a recompute claim, else None (honest 'not quantified')."""

    domain: str
    status: str
    resolution: str | None
    amount_paise: int | None


@dataclass(frozen=True)
class BlockedFigureInput:
    """A figure whose Mahsa recompute did NOT match (a MAHSA-PARITY block). Both values are
    real recompute outputs — the ₹ impact is their difference, never invented."""

    domain: str
    target: str
    label: str | None
    claimed_paise: int
    recomputed_paise: int | None
    note: str


# ── View model ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class InboxItem:
    id: str
    queue: str
    what: str  # what happened
    when: str | None  # when (None if not time-stamped)
    impact_paise: int | None  # ₹-consequence for ranking + display; None = honestly unknown
    impact_label: str
    action_label: str  # the one-tap next action
    domain: str  # target for a bulk decision
    selectable: bool  # eligible for a bulk op
    detail: str = ""
    verify_state: str | None = None  # "unbacked" -> ✕ verification glyph (never a fake ✓)


@dataclass(frozen=True)
class Queue:
    key: str
    label: str
    source: str | None
    stub_note: str | None
    empty: str
    items: list[InboxItem] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class Inbox:
    queues: list[Queue]
    items: list[InboxItem]  # flat, for bulk-op lookup by id

    @property
    def total(self) -> int:
        return len(self.items)


def _rank_key(item: InboxItem) -> tuple[int, int]:
    # Items with a known ₹ impact sort first, largest impact first (research: rank by ₹/ITC).
    return (1 if item.impact_paise is not None else 0, item.impact_paise or 0)


def build_awaiting_approval(approvals: list[ApprovalInput]) -> list[InboxItem]:
    items: list[InboxItem] = []
    for a in approvals:
        if a.resolution is not None:
            continue  # already approved/rejected — no longer pending
        quantified = a.amount_paise is not None
        items.append(
            InboxItem(
                id=f"approval:{a.domain}",
                queue="awaiting_approval",
                what=f"{a.domain.capitalize()} needs your sign-off — Mahsa flagged it "
                f"{a.status}",
                when=None,
                impact_paise=a.amount_paise,
                impact_label="At stake" if quantified else "Sign-off pending (₹ not quantified)",
                action_label="Review & approve",
                domain=a.domain,
                selectable=True,
                detail="Approving or rejecting is sealed into the hash-chained audit log.",
            )
        )
    return items


def build_mahsa_blocked(blocked: list[BlockedFigureInput]) -> list[InboxItem]:
    items: list[InboxItem] = []
    for b in blocked:
        name = b.label or b.target
        delta = (
            abs(b.claimed_paise - b.recomputed_paise)
            if b.recomputed_paise is not None
            else None
        )
        items.append(
            InboxItem(
                id=f"blocked:{b.domain}:{b.target}",
                queue="mahsa_blocked",
                what=f"{b.domain.capitalize()}: {name} did not survive Mahsa's recompute — "
                f"figure blocked (MAHSA-PARITY)",
                when=None,
                impact_paise=delta,
                impact_label="Figure off by",
                action_label="Open figure",
                domain=b.domain,
                selectable=False,  # a blocked figure must be fixed, never bulk-waved through
                detail=b.note,
                verify_state="unbacked",  # ✕ — never a fabricated ✓
            )
        )
    return items


def build_items(
    approvals: list[ApprovalInput], blocked: list[BlockedFigureInput]
) -> list[InboxItem]:
    """Every real inbox item, flat. The un-sourced queues contribute nothing (honest-empty)."""
    return build_mahsa_blocked(blocked) + build_awaiting_approval(approvals)


def build_inbox(items: list[InboxItem]) -> Inbox:
    by_queue: dict[str, list[InboxItem]] = {k: [] for k in QUEUE_ORDER}
    for it in items:
        by_queue[it.queue].append(it)
    queues = [
        Queue(
            key=k,
            label=str(QUEUE_META[k]["label"]),
            source=QUEUE_META[k]["source"],
            stub_note=QUEUE_META[k]["stub_note"],
            empty=str(QUEUE_META[k]["empty"]),
            items=sorted(by_queue[k], key=_rank_key, reverse=True),
        )
        for k in QUEUE_ORDER
    ]
    return Inbox(queues=queues, items=items)


# ── Bulk op with preview (research #1: never a silent bulk mutation) ──────────
@dataclass(frozen=True)
class BulkRow:
    id: str
    domain: str
    what: str
    impact_paise: int | None
    will: str  # exactly what will change


@dataclass(frozen=True)
class BulkPreview:
    action: str
    rows: list[BulkRow]  # eligible, will change on confirm
    skipped: list[BulkRow]  # selected but not eligible for this action
    total_impact_paise: int
    committed: bool  # False = dry-run preview (default); True = has been applied

    @property
    def eligible_ids(self) -> list[str]:
        return [r.id for r in self.rows]


_BULK_ACTIONS = {"approve": "approved", "reject": "rejected"}


def preview_bulk(
    items: list[InboxItem],
    selected_ids: list[str],
    action: str,
    *,
    committed: bool = False,
) -> BulkPreview:
    """Dry-run by default: list the exact rows that would change and the total ₹ impact, without
    mutating anything. The router only commits when the user explicitly confirms; even then this
    stays a pure description of the change (``committed`` is a display flag)."""
    if action not in _BULK_ACTIONS:
        raise ValueError(f"unknown bulk action {action!r}")
    verb = _BULK_ACTIONS[action]
    chosen = set(selected_ids)
    selected = [i for i in items if i.id in chosen]
    rows: list[BulkRow] = []
    skipped: list[BulkRow] = []
    for i in selected:
        row = BulkRow(id=i.id, domain=i.domain, what=i.what, impact_paise=i.impact_paise, will="")
        if i.selectable and i.queue == "awaiting_approval":
            rows.append(replace(row, will=f"Seal a {verb} decision onto the audit chain"))
        else:
            skipped.append(replace(row, will="Not eligible for this bulk action"))
    total = sum(r.impact_paise or 0 for r in rows)
    return BulkPreview(
        action=action, rows=rows, skipped=skipped, total_impact_paise=total, committed=committed
    )
