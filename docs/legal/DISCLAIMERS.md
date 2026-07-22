> **DRAFT FOR COUNSEL REVIEW — NOT FINAL, NOT LEGAL ADVICE.**
> This document records the exact wording ticket §WS10.4 requires and where it must appear.
> The wording itself is fixed by the ticket, not authored here; nothing below asserts the
> product's compliance with any law.

# In-product and PDF disclaimer text (§WS10.4)

## The exact string (byte-exact — do not reword, translate, or truncate)

```
software tool, not the practice of chartered accountancy; outputs require professional verification
```

This is exported as `app.core.legal.DISCLAIMER_TEXT`. Any surface that renders it must render
this constant verbatim, not a paraphrase — `test_legal.py` asserts the constant equals this
string byte-for-byte so a future edit is caught as a test failure, not a silent drift.

## Where it must appear (wiring for the orchestrator — not owned by this ticket's files)

- Every screen/page that displays a Maisha-computed or Mahsa-verified figure (domain pages,
  Ask Maisha answers, CFO strategy views, exported registers).
- Every PDF export (audit pack, compliance registers, investor update) — footer or header,
  legible, not buried in fine print smaller than the surrounding body text.
- Any place a ✓-verified badge is shown (per CLAUDE.md §0.4 Prime Directive) — the disclaimer
  and the verified badge should appear together, since "verified" means "Mahsa recomputed it",
  not "a professional reviewed it".

## What this disclaimer does and does not do

- It does **not** replace the ToS's limitation-of-reliance clause (`TOS_DRAFT.md` §2) — it is
  the short-form, always-visible version of the same substantive point.
- It does **not** make the product's outputs a substitute for the retained-CA engagement
  referenced in MASTER_PLAN §WS10.3.
- `TODO(counsel)`: confirm this placement policy is sufficient, and whether any specific
  regulator/professional-body guidance (e.g. ICAI) requires additional or different wording for
  outputs that resemble accounting work product. No such requirement is asserted here.

---
*Generated as scaffolding for ticket §WS10.4. Remove this notice block only after actual
counsel review confirms the wording and placement policy.*
