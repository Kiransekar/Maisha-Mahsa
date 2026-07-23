# WS11.2 — WhatsApp support macros (pilot)

Copy-paste replies for the pilot support number. Keep them verbatim where possible — every
claim below is grounded in what the product actually does; do not improvise about statutory
values or verification states. If a question needs a statutory interpretation, escalate to
the retained CA — never answer it from chat.

Conventions: `{name}` placeholders are filled before sending. One message per macro; WhatsApp
formatting (*bold*) included.

---

## M1 — What do the badges mean?

> Quick guide to the marks you see next to numbers:
>
> *✓ Verified* — Mahsa (our independent Rust engine) recomputed this exact figure from the
> same inputs and matched it *to the paisa*. Tap the number to see the inputs, formula,
> rule citations and source documents behind it.
>
> *◐ Pending verification* — the figure is computed by the books, but Mahsa's independent
> recomputation for this path isn't live yet, so we refuse to show a ✓ we can't stand
> behind. It is never a guess — just not yet double-checked.
>
> *✕ / ⚠ Blocked* — Mahsa recomputed and got a *different* number, or a rule was violated.
> The figure is blocked from approval until resolved. This is the product working, not
> breaking.
>
> A ✓ can also downgrade to ◐ with a note if the cited source document changed or the data
> went stale ("as of {date}") — we never leave a ✓ standing that we can't currently prove.

## M2 — My bank statement import failed

> Two common causes:
>
> 1. *"unrecognised bank CSV: need a date column and a debit/credit column"* — the file must
> have a header row with a date column and at least one of debit/withdrawal or
> credit/deposit. Export the account statement as CSV from netbanking (not the PDF) and try
> again. If your bank's CSV still fails, send me the header row (just the first line, no
> transactions) and we'll add the format.
>
> 2. *Nothing imported / all rows skipped* — rows without a readable date or with 0 in both
> debit and credit are skipped and reported; the summary tells you exactly how many.
>
> Good to know: re-uploading the *same* file is always safe — already-imported rows are
> detected and skipped, balances don't double-count.

## M3 — My Tally import was refused

> The importer is deliberately all-or-nothing: either every voucher lands exactly, or
> nothing is written. The refusal message names the exact voucher:
>
> - *"voucher … is not balanced"* — that voucher's debits ≠ credits in the exported XML.
>   Fix it in Tally and re-export.
> - *"unmapped Tally ledger(s): …"* — map each named ledger to one of your accounts (or
>   create a new account) on the review screen, then confirm again.
> - Asked to type *import*? That's the confirmation step — it's shown after you've reviewed
>   the parse report, so a wrong file can't slip in.
>
> Nothing is ever partially imported, so you can retry safely.

## M4 — How do approvals work? / Why is this payment stuck?

> Anything Mahsa flags (a yellow/red domain, a draft payroll run, a blocked figure) waits in
> *Approvals* until a human decides. On the approval screen you see the totals *restated
> with their verification badges* — and to approve you type the domain name back as
> confirmation. Every decision is sealed into the tamper-evident audit log with who/when.
>
> If an item says *Mahsa blocked*, the engine found a mismatch — open it to see both values
> and the diagnostic. Don't work around it; that's the number-guardrail doing its job. Send
> me a screenshot and we'll trace it.

## M5 — How do I give my CA access?

> Settings → invite your CA by email. The CA seat is *free and unlimited* — it never counts
> against your plan's seats. Your CA gets read-only access to the *Audit Room*: statements,
> registers, the evidence behind every figure, and query threads pinned to specific entries
> (their questions and your answers are sealed to the audit chain too). They cannot edit
> books or approve payments.

## M6 — Is this filed with the government? (e-invoice / returns)

> No — artifacts generated in-app are labelled *DRAFT — not IRP-registered; not a valid
> e-invoice until registered*, and return JSONs are prepare-and-download. Filing happens on
> the government portal (or through your CA) for now; the app prepares exact, verified
> numbers and tracks the deadline. Never represent a draft as filed.

## M7 — A number looks wrong

> Treat this as our highest-priority ticket class. Please send:
> 1. a screenshot of the figure with its badge,
> 2. the screen/tap path ("Working" panel screenshot if open),
> 3. what you expected instead.
>
> Every figure's working panel shows its inputs, formula, rule citations and verdict hash —
> that's usually enough for us to reproduce it exactly. If a ✓-verified figure is ever
> actually wrong, it goes straight to the founders (that is our existential defect class).

## M8 — Escalation ladder (internal, not a customer reply)

1. Product behaviour / imports / navigation → support answers from these macros.
2. Numbers, badges, verification mismatches → engineering on-call, same day.
3. Statutory interpretation ("which rate applies to me?") → retained CA. Support and
   engineering NEVER answer statutory questions ad hoc (§0.6) — the product cites its
   rules; humans don't freestyle them.
