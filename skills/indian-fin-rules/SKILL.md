---
name: indian-fin-rules
description: Reference and authoring guide for the CA-signed rule set that Mahsa enforces (dif/rules/rules.yaml) and the Indian regulatory matrix behind it — GST, TDS, PF/ESI/PT, MSME, advance tax, ROC/Companies Act, SEBI SBEB. Use when adding/editing a validation rule or mapping a statutory deadline.
---

# Indian financial rules (the Mahsa rule set)

Rules are **data, never code**: `dif/rules/rules.yaml`, loaded and integrity-checked at
startup (`RuleSet::from_yaml` → unique ids, non-empty statute+section, ≥1 condition). The
embedded copy (`RuleSet::embedded`) is compiled in so the engine always has a valid set.

## Rule shape
```yaml
- id: GST-001                 # DOMAIN-NNN ; domain: global runs on every request
  domain: gst
  description: "..."          # human-readable
  statute: "CGST Act 2017"    # REQUIRED citation
  section: "Sec 47 / Rule 61" # REQUIRED citation
  severity: block             # info | warning | block  (block ⇒ Red, warning/info ⇒ Yellow)
  all_of:                     # conditions AND-ed; rule fires only if ALL hold
    - { metric: gstr3b_days_late, op: gt, value: 0 }   # op: lt le gt ge eq ne
  action: "..."               # what to tell the founder
```
`metric` is a `Snapshot` metric name, or `intent:<dim>` to read a global intent dimension.
A metric the snapshot can't resolve makes the condition **false** (a rule never fires on
missing data) — so the domain's `build_snapshot` must populate the metrics its rules read.

## Adding a rule
1. Confirm the statute + section and the exact threshold/deadline (cite it in the YAML).
2. Add the rule; pick severity by consequence (a hard statutory bar = `block`).
3. Ensure the owning domain's `build_snapshot` provides the metric(s) (typed field or in the
   `metrics` bag). Add the metric to `Snapshot::metric` in Rust if it's a derived one.
4. Bump `version:` in `rules.yaml`; add/extend a test in `dif/src/validate/mod.rs` and an
   end-to-end assertion if it gates an approval. Mirror the id in the domain's `rules.py`.
5. Record in `BUILD_PROGRESS.md`. A CA must sign off real production rules.

## Seed rules (PRD §4.4 / §12) — already wired
TREASURY-001 (runway<3mo), PAYROLL-001 (PF by 15th), PAYROLL-002 (ESI), GST-001 (GSTR-3B
by 20th), GST-002 (ITC > 105% of 2B, Rule 36(4)), TAX-001 (advance tax 234C), TAX-002 (TDS
by 7th), PAYABLES-001 (MSME 45 days, 43B(h)), REVENUE-001 (e-invoice > ₹5Cr, Rule 48(4)),
EQUITY-001 (ESOP pool > 10% w/o approval), COMPLIANCE-001 (AOC-4 late), COMPLIANCE-002
(any overdue filing — global).

## Key thresholds to respect
PF wage ceiling ₹15,000; ESI ceiling ₹21,000; TDS deposit 7th; GSTR-3B 20th; advance tax
15/45/75/100% by 15 Jun/Sep/Dec/Mar; MSME 45-day payment; e-invoicing > ₹5Cr turnover;
tax audit 44AB ₹1Cr/₹10Cr; bonus ceiling ₹21,000 / 8.33% min.  Always re-verify current
Finance-Act values before signing a rule — these change yearly.
