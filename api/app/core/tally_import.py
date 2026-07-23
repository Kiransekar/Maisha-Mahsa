"""WS9.1 — Tally XML import parser (ENVELOPE/TALLYMESSAGE export format). Pure: no DB, no
network, no clock. The router (app/web/api_tally.py) owns matching, mapping and commit.

UNTRUSTED INPUT. Uploaded XML is parsed with stdlib ``xml.etree`` hardened the way defusedxml's
``forbid_dtd`` does it (defusedxml is not a dependency — checked pyproject.toml): any DOCTYPE is
rejected outright BEFORE parsing. Entity definitions (billion-laughs) and external entities (XXE)
can only exist inside a DTD's internal subset, and stray ``<!ENTITY``/``&undefined;`` without a
DTD are expat parse errors — so no-DTD ⇒ no entity expansion of any kind. A size cap is enforced
on the raw bytes first.

MONEY IS EXACT. Tally amounts are decimal rupees; conversion to integer paise must be lossless
(``Decimal * 100`` integral) or the amount is REJECTED with its voucher/ledger named — never
rounded silently (CLAUDE.md §2).

SIGN CONVENTION. Tally XML signs every amount credit-positive / debit-negative
(``ISDEEMEDPOSITIVE`` = Yes ⇔ negative ⇔ debit). This codebase's ledger is debit-positive
(``general_ledger``: balance = opening + debit − credit). The conversion happens HERE, at the
edge, once: every paise figure this module returns is debit-positive.
"""

from __future__ import annotations

import calendar
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.core.audit import canonical_json

#: Upload cap. A real Tally Day Book year-export is single-digit MB; 20 MB is generous headroom
#: while still bounding parse memory. ponytail: raise if a real corpus file exceeds it.
MAX_BYTES = 20 * 1024 * 1024

#: Tally's default primary groups -> this codebase's five Indian-GAAP account types
#: (ledger_calc.DEBIT_NATURED / CREDIT_NATURED). Standard accounting classification, not a
#: statutory value. Used only as a SUGGESTION for the mapping UI — never silently applied.
TALLY_GROUP_TYPE: dict[str, str] = {
    # assets
    "current assets": "asset",
    "fixed assets": "asset",
    "investments": "asset",
    "bank accounts": "asset",
    "cash-in-hand": "asset",
    "deposits (asset)": "asset",
    "loans & advances (asset)": "asset",
    "stock-in-hand": "asset",
    "sundry debtors": "asset",
    "misc. expenses (asset)": "asset",
    "branch / divisions": "asset",
    "suspense a/c": "asset",
    # liabilities
    "current liabilities": "liability",
    "duties & taxes": "liability",
    "provisions": "liability",
    "sundry creditors": "liability",
    "loans (liability)": "liability",
    "bank od a/c": "liability",
    "secured loans": "liability",
    "unsecured loans": "liability",
    # equity
    "capital account": "equity",
    "reserves & surplus": "equity",
    # income
    "sales accounts": "income",
    "direct incomes": "income",
    "indirect incomes": "income",
    # expense
    "purchase accounts": "expense",
    "direct expenses": "expense",
    "indirect expenses": "expense",
}


class TallyImportError(ValueError):
    """A file-level refusal (too big, not XML, DTD present). Nothing was parsed."""


@dataclass(frozen=True)
class TallyLedgerMaster:
    name: str
    parent: str | None
    #: Debit-positive paise; None when the master carries no OPENINGBALANCE tag (Tally omits
    #: zero fields — the reconciliation treats absent as 0, stated in the report).
    opening_paise: int | None
    #: Debit-positive paise; None when absent — an absent checksum is "not yet known", never a
    #: fabricated match.
    closing_paise: int | None
    #: Suggested account_type from the (sub-)group chain, or None — we don't guess.
    suggested_type: str | None


@dataclass(frozen=True)
class TallyVoucherLine:
    ledger: str
    debit_paise: int
    credit_paise: int


@dataclass(frozen=True)
class TallyVoucher:
    #: VOUCHERNUMBER, or a content-hash id when absent (CITE.P0-4: positional ids silently
    #: drift when the file is re-exported or re-ordered; a content hash does not).
    voucher_id: str
    #: sha256 over the voucher's canonical content (number, date, type, narration, lines) —
    #: the tally_voucher citation anchor identity (SPEC-MEMCITE-1.0 §B3.2).
    voucher_hash: str
    date: str | None  # ISO, None when DATE is missing/unreadable (listed in errors)
    voucher_type: str
    narration: str
    lines: tuple[TallyVoucherLine, ...]

    @property
    def total_debit(self) -> int:
        return sum(ln.debit_paise for ln in self.lines)

    @property
    def total_credit(self) -> int:
        return sum(ln.credit_paise for ln in self.lines)

    @property
    def balanced(self) -> bool:
        return self.total_debit == self.total_credit


@dataclass
class TallyParse:
    ledgers: list[TallyLedgerMaster] = field(default_factory=list)
    vouchers: list[TallyVoucher] = field(default_factory=list)
    #: Row-level refusals (non-lossless amount, unreadable date), each naming its voucher or
    #: ledger. A commit must refuse while this is non-empty.
    errors: list[str] = field(default_factory=list)

    @property
    def unbalanced(self) -> list[TallyVoucher]:
        return [v for v in self.vouchers if not v.balanced]

    def ledger_names(self) -> list[str]:
        """Every ledger name the file references (masters ∪ voucher lines), original casing,
        first-seen order — the set that must resolve to an account before commit."""
        seen: dict[str, str] = {}
        for master in self.ledgers:
            seen.setdefault(master.name.casefold(), master.name)
        for v in self.vouchers:
            for ln in v.lines:
                seen.setdefault(ln.ledger.casefold(), ln.ledger)
        return list(seen.values())

    def reconciliation(self) -> list[dict[str, object]]:
        """The checksum report: per ledger, opening + Σdebits − Σcredits vs Tally's own stated
        closing balance. ``match`` is None (unknown) when Tally stated no closing — an absent
        checksum is never reported as a pass."""
        totals: dict[str, list[int]] = {}
        for v in self.vouchers:
            for ln in v.lines:
                t = totals.setdefault(ln.ledger.casefold(), [0, 0])
                t[0] += ln.debit_paise
                t[1] += ln.credit_paise
        masters = {m.name.casefold(): m for m in self.ledgers}
        rows: list[dict[str, object]] = []
        for name in self.ledger_names():
            key = name.casefold()
            master = masters.get(key)
            debits, credits = totals.get(key, [0, 0])
            opening = master.opening_paise if master else None
            stated = master.closing_paise if master else None
            computed = (opening or 0) + debits - credits
            rows.append(
                {
                    "name": name,
                    "opening_paise": opening,
                    "debits_paise": debits,
                    "credits_paise": credits,
                    "computed_closing_paise": computed,
                    "stated_closing_paise": stated,
                    "match": None if stated is None else computed == stated,
                }
            )
        return rows


# ── hardened decode + parse ──────────────────────────────────────────────────────────


def _decode(raw: bytes) -> str:
    """Tally exports UTF-8 or (commonly) UTF-16 with a BOM. Decode by BOM, default UTF-8."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TallyImportError(
            "file is not UTF-8/UTF-16 text — is this a Tally XML export?"
        ) from exc


def _text(el: ET.Element, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def rupees_to_paise_exact(text: str) -> int:
    """Tally-signed decimal rupees -> tally-signed integer paise, LOSSLESSLY or not at all.
    '10.005' (sub-paisa) raises rather than rounding silently."""
    try:
        d = Decimal(text.strip())
    except InvalidOperation as exc:
        raise ValueError(f"amount {text.strip()!r} is not a decimal rupee value") from exc
    paise = d * 100
    if paise != paise.to_integral_value():
        raise ValueError(
            f"amount {text.strip()!r} does not convert to whole paise — refusing to round"
        )
    return int(paise)


def _tally_date_to_iso(raw: str) -> str | None:
    """Tally DATE is YYYYMMDD. Returns ISO or None (caller records the error)."""
    s = raw.strip()
    if len(s) != 8 or not s.isdigit():
        return None
    y, m, d = int(s[:4]), int(s[4:6]), int(s[6:8])
    if not (1 <= m <= 12) or not (1 <= d <= calendar.monthrange(y, m)[1]):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def parse_tally_xml(raw: bytes) -> TallyParse:
    """Parse a Tally XML export (masters and/or vouchers). File-level problems raise
    :class:`TallyImportError`; row-level problems are collected in ``result.errors`` so the
    parse report can show everything at once."""
    if len(raw) > MAX_BYTES:
        raise TallyImportError(
            f"file is {len(raw)} bytes; the import cap is {MAX_BYTES} bytes"
        )
    text = _decode(raw)
    # defusedxml-style forbid_dtd: a DTD is the only place entity definitions (billion-laughs)
    # or external entities (XXE) can live. Tally exports never carry one.
    if "<!doctype" in text.casefold():
        raise TallyImportError("XML with a DOCTYPE declaration is refused (entity hardening)")
    # ET.fromstring(str) rejects an encoding declaration; we already decoded, so strip it.
    if text.lstrip().startswith("<?xml"):
        text = text[text.index("?>") + 2 :]
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise TallyImportError(f"not well-formed XML: {exc}") from exc
    if root.tag != "ENVELOPE":
        raise TallyImportError(f"expected a Tally <ENVELOPE> export, got <{root.tag}>")

    result = TallyParse()

    # Custom sub-group chains: GROUP masters (NAME attr or child, PARENT child) let a ledger
    # under "My Debtors" -> "Sundry Debtors" still suggest 'asset'.
    group_parent: dict[str, str] = {}
    for g in root.iter("GROUP"):
        g_name = (g.get("NAME") or _text(g, "NAME")).strip()
        g_parent = _text(g, "PARENT")
        if g_name and g_parent:
            group_parent[g_name.casefold()] = g_parent

    def suggested_type(parent: str | None) -> str | None:
        cur, hops = parent, 0
        while cur is not None and hops < 20:  # hop cap: a parent cycle must not hang the import
            t = TALLY_GROUP_TYPE.get(cur.casefold())
            if t is not None:
                return t
            cur = group_parent.get(cur.casefold())
            hops += 1
        return None

    for el in root.iter("LEDGER"):
        name = (el.get("NAME") or _text(el, "NAME")).strip()
        if not name:
            result.errors.append("a LEDGER master has no name; skipped")
            continue
        parent = _text(el, "PARENT") or None

        def balance(tag: str, ledger_name: str = name, el: ET.Element = el) -> int | None:
            txt = _text(el, tag)
            if not txt:
                return None
            try:
                return -rupees_to_paise_exact(txt)  # tally credit-positive -> debit-positive
            except ValueError as exc:
                result.errors.append(f"ledger {ledger_name!r}: {tag} {exc}")
                return None

        result.ledgers.append(
            TallyLedgerMaster(
                name=name,
                parent=parent,
                opening_paise=balance("OPENINGBALANCE"),
                closing_paise=balance("CLOSINGBALANCE"),
                suggested_type=suggested_type(parent),
            )
        )

    fallback_seen: dict[str, int] = {}
    for i, el in enumerate(root.iter("VOUCHER"), start=1):
        vnum = _text(el, "VOUCHERNUMBER")
        # Error-naming label only — never stored. Stored ids are VOUCHERNUMBER or the
        # content hash below (CITE.P0-4: positional ids drift on re-export/re-order).
        label = vnum or f"unnumbered voucher (file position {i})"
        date = _tally_date_to_iso(_text(el, "DATE"))
        if date is None:
            result.errors.append(
                f"Tally voucher {label}: DATE {_text(el, 'DATE')!r} is not a readable "
                "YYYYMMDD date"
            )
        lines: list[TallyVoucherLine] = []
        line_error = False
        # Both spellings appear in real exports (voucher mode vs accounting-invoice mode).
        entries = el.findall(".//ALLLEDGERENTRIES.LIST") + el.findall(".//LEDGERENTRIES.LIST")
        for entry in entries:
            ledger = _text(entry, "LEDGERNAME")
            if not ledger:
                result.errors.append(f"Tally voucher {label}: a line has no LEDGERNAME")
                line_error = True
                continue
            try:
                amt = rupees_to_paise_exact(_text(entry, "AMOUNT"))
            except ValueError as exc:
                result.errors.append(f"Tally voucher {label}, ledger {ledger!r}: {exc}")
                line_error = True
                continue
            # tally sign: negative = debit
            lines.append(
                TallyVoucherLine(
                    ledger=ledger,
                    debit_paise=-amt if amt < 0 else 0,
                    credit_paise=amt if amt > 0 else 0,
                )
            )
        if line_error:
            continue  # a voucher with an unreadable line must not import partially
        voucher_type = _text(el, "VOUCHERTYPENAME") or (el.get("VCHTYPE") or "")
        narration = _text(el, "NARRATION")
        voucher_hash = hashlib.sha256(
            canonical_json(
                {
                    "voucher_number": vnum or None,
                    "date": date,
                    "voucher_type": voucher_type,
                    "narration": narration,
                    "lines": [[ln.ledger, ln.debit_paise, ln.credit_paise] for ln in lines],
                }
            ).encode("utf-8")
        ).hexdigest()
        if vnum:
            voucher_id = vnum
        else:
            n = fallback_seen.get(voucher_hash, 0) + 1
            fallback_seen[voucher_hash] = n
            # content-identical duplicates are interchangeable; the /n suffix only keeps
            # their ids distinct within the file
            voucher_id = f"voucher {voucher_hash[:12]}" + (f"/{n}" if n > 1 else "")
        result.vouchers.append(
            TallyVoucher(
                voucher_id=voucher_id,
                voucher_hash=voucher_hash,
                date=date,
                voucher_type=voucher_type,
                narration=narration,
                lines=tuple(lines),
            )
        )
    return result
