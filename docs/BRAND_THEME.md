# BRAND_THEME.md — Maisha-Mahsa visual identity

Grounded in the brand research run of 2026-07-21 (workflow `wf_ac62dda1-ec7`, 5 angles →
per-angle adversarial citation verification). **Every hex and typeface attributed to another
company below was re-fetched from a live source by a verifier.** Findings that could not be
re-confirmed were dropped, not softened — see §6.

Companion docs: `WS7_UX_RESEARCH.md` (behaviour), `WS7_DESIGN_TOKENS.md` (token mechanics).
This doc governs **what we look like and why**. It does not restate MMX-1.0 §0.4 — it obeys it.

---

## 1. The positioning problem

Our differentiator is not "AI for finance". It is that **every number is independently
recomputed by a second engine before a human sees it**, and figures that have not been
recomputed say so (◐) instead of pretending (✓). The brand's only real job is to make that
distinction *legible at a glance* — and to not look like the thing it is arguing against.

Two failure modes to design away from:

**(a) The generic AI-startup look.** The research found one company in our exact segment
wearing it — Digits: acid/lime-green accent on dark backgrounds with an animated gradient
video hero (`digits.com`, verified). Linear's own design doc names the same clichés as
prohibitions: *"Don't add atmospheric gradients or spotlight cards"*
(`awesome-design-md/linear.app`, verified). Across every premium Indian fintech fetched
(CRED, RazorpayX, Jupiter, Open, Zoho Books) the verifier found **zero** instances of
cream+serif+terracotta, lone-acid-green-on-near-black, or purple→blue gradient heroes.

> ⚠️ **Our current `frontend/src/theme/tokens.css` placeholder is this failure mode**:
> `#0e1116` near-black canvas + `#2dd4bf` teal accent. It was explicitly labelled a
> placeholder; §3 replaces it.

**(b) Sea-of-blue Indian fintech.** Open (`open.money`) deliberately escaped it by making
purple primary rather than blue (verified). We need our own escape, and it cannot be purple,
indigo, or teal — those are already spoken for by our verification family (§4).

---

## 2. What the research says premium finance brands actually do

Five patterns held up under adversarial verification. All five are cheap for us to adopt.

| # | Pattern | Evidence |
|---|---|---|
| 1 | **One reserved chromatic accent, everything else neutral.** | Mercury: indigo `#5266eb` is *"the ONLY saturated/chromatic note… reserved for CTAs/links. No secondary brand colors."* Ramp: chartreuse `#e4f222` *"only for primary action fills"* over bone `#f4f2f0`. Brex: orange `#ff5900` as sole filled-CTA color. Linear: `#5e6ad2` restricted to *"brand mark, focus rings, and primary CTA only"*. |
| 2 | **Status/semantic colors live in a token family separate from the brand accent.** | GitHub Primer: success `#1a7f37`, danger `#d1242f`, attention `#9a6700`, done `#8250df` — all distinct from brand accent `#0969da`. |
| 3 | **Borders, not shadows, create depth.** | Mercury: flat surfaces, 1px borders + tone-shifts; *the only shadow in the entire system* is the modal's. Ramp: avoids `box-shadow` entirely — 1px hairlines are the sole elevation primitive. |
| 4 | **Tabular figures are mandatory, and numerals often get their own face.** | Inter ships `tnum`: *"Fixed-width numbers are useful for tabular data, where comparing columns across rows is desired."* Mercury uses Arcadia's tabular variant on every balance and chart label, IBM Plex Mono for transaction IDs. Brex reserves Space Mono specifically for money amounts and account codes. |
| 5 | **Precision-as-decoration: lead with an exact number, never an adjective.** | Stripe sets figures large as the design element itself (*"US$1.9tn in payments volume processed in 2025"*, *"99.999% historical uptime"*). Ramp: *"27M+ hours saved"*, *"75% faster closes"*. |

One further gem, directly load-bearing for us — **weight duplexing**: in some faces the
tabular figures *"all advance the same distance in all weights, so you can highlight certain
numbers in lists by changing their weight without disrupting their vertical alignment"*
(Type Network, on Miles Newlyn's New Rubrik). That is exactly what we need to bold a verified
total inside a column without the column moving.

## 2b. What Indian finance users specifically expect

Verified from live Indian sites — these are conventions, not preferences:

- **Lakh/crore-native social proof.** Jupiter: *"Trusted by 30 Lakh+ Indians"*. RecurClub:
  *"₹3,000 Cr+ Funded"*. Not "3 million".
- **Name the statute, don't say "compliance".** RazorpayX names TDS / PF / PT / ESIC / GST
  explicitly. Increase (US) does the analogous thing with ACH/Fedwire/FedNow rather than
  generic feature language. Our WS7 alert grammar already does this.
- **Regulatory disclosure up front, as a trust device.** Jupiter states DICGC insurance
  *"100% insured for up to ₹5 Lakh"* on the marketing surface; Mercury similarly states
  *"Mercury is a fintech company, not an FDIC-insured bank"* rather than burying it.
  **For us this is not optional decoration — it is the honest-pending principle applied to
  the marketing page.**
- **Flat declaratives beat hedged reassurance.** CRED: *"complete security. no asterisks."*
  Open: *"Agents propose. Humans approve."*
- ⚠️ **Note the adjacency**: Open's *"Agents propose. Humans approve."* is one sentence away
  from our own thesis. Our differentiation is *not* human-in-the-loop (they have it) — it is
  **machine-in-the-loop verification**: a second deterministic engine recomputes the number.
  The brand must say *recomputed*, not *reviewed*.
- **Spacious shell, dense interior.** Zoho Books keeps generous whitespace on marketing while
  the real density lives in product screenshots. Do not let a spacious marketing aesthetic
  leak into the working screens — CA/accountant users want Tally-grade density there.

---

## 3. Our system

**Canvas: light, warm, paper.** Rationale: (a) it is where the premium references actually
live — Mercury cream `#f6f5f2`, Ramp bone `#f4f2f0`, Brex `#fcfcfd`, all verified; (b) dark
canvas is where the AI-generic look lives in *our* segment (Digits); (c) our users read
statutory tables for hours in daylit offices. Dark mode ships as a *supported alternative*,
never the default identity.

**Accent: brass.** Chosen by elimination — green and red belong to money direction, teal /
indigo / violet belong to verification state (§4), blue is the Indian fintech default we're
escaping, purple is Open's, orange is Brex's, acid-lime is the tell we're avoiding. Brass is
unclaimed in the segment and carries the right metaphor: **the seal on an attested document**.

> These values are **our decisions**, not extracted from any company. Nothing here is copied
> from a competitor's palette.

```css
/* Ground — warm paper, never pure white */
--color-ground:        #faf8f4;  /* app canvas */
--color-surface:       #ffffff;  /* cards, tables */
--color-surface-sunk:  #f2efe8;  /* wells, table header, code */
--color-border:        #e3ded3;  /* hairline — the ONLY elevation primitive */
--color-border-strong: #cfc7b6;

/* Ink */
--color-ink:           #1c1a17;  /* primary text */
--color-ink-muted:     #6b6459;  /* secondary/labels */
--color-ink-faint:     #9a9287;  /* disabled, placeholders */

/* Accent — brass. One reserved chromatic note (pattern #1). */
--color-accent:        #8a6a1f;  /* primary CTA fill, links, focus ring */
--color-accent-hover:  #6f5518;
--color-accent-sunk:   #f5eeda;  /* tint for selected rows only */
```

**Dark mode** (alternative, not identity) — warm-neutral, *not* blue-black; keeps brass:
`--color-ground:#17150f; --color-surface:#1f1c15; --color-border:#332e23; --color-ink:#ece7dc;
--color-accent:#d9ad4a;`

### Elevation, radius, motion
- **No `box-shadow`** except modals/popovers. Depth = 1px `--color-border` + tone shift
  (pattern #3). No gradients. No glow. No spotlight cards.
- Radius, closed set: `4px` (default — controls, cells), `8px` (cards), `12px` (modals),
  `9999px` (pills only). Nothing else.
- Spacing, 4px ladder: `4 8 12 16 24 32 48`.
- Motion: color/background transitions only, `150–250ms ease`. The **one** permitted
  expressive motion in the product is the ◐→✓ lock-in (already built in WS7.2). Nothing
  else animates; a number that animates for decoration undermines a number that animates
  because it was just verified.

---

## 4. Verification is the brand (non-negotiable)

Per pattern #2, three token families that must never bleed into each other:

| Family | Meaning | Tokens |
|---|---|---|
| **Verification** | Has this number been recomputed? | ✓ `--c-verify` · ◐ `--c-verify-pending` · ✕ `--c-verify-unbacked` |
| **Money direction** | Is this in or out, up or down? | `--c-money-in` / `--c-money-out` |
| **Brand** | Is this the primary action? | `--color-accent` (brass) |

This separation is **already implemented and gate-tested** (WS7.1 killed the
`.vmark--ok = money-green` trust-confusion bug). The research independently validates it via
Primer. Keep the existing verification hues — they are load-bearing and already tested — and
note that brass sits outside all three ramps, which is precisely why it was chosen.

**The verification chip is the logo.** Wherever the brand appears next to a number, the
◐/✓ chip is the brand expression. We do not need a decorative mark competing with it.

### Numerals
- Every figure renders `font-variant-numeric: tabular-nums` (`.tnum` exists). Non-negotiable —
  pattern #4.
- **Money and statutory identifiers get a mono face**: GSTIN, PAN, challan/CIN, IRN, ARN,
  verdict hashes. Following Brex/Mercury's split. `ui-monospace` stack; no webfont needed.
- Indian grouping always (`₹12,34,567`), via the single `format.py :: inr()` renderer already
  enforced by the `check_money_format.sh` gate.
- A bolded total must not shift its column — prefer a face with duplexed tabular figures, or
  bold via color/background rather than weight if the shipped face doesn't duplex.

### Type
Body/UI **Inter** (ships `tnum` + `cv01`/`cv02` variants, verified at `rsms.me/inter`);
mono `ui-monospace` stack. Hierarchy from **size and tracking, not weight** — Ramp runs its
entire scale at a single weight, Brex its whole 14–72px display tier at Inter 500 (both
verified). Scale: `12 13 14 16 20 24 32 48`.
*Skipped:* a custom/licensed display face (Mercury's Arcadia, Ramp's Lausanne). Real cost,
zero effect on whether a CA trusts the number. Revisit only if brand recall becomes a
measured problem.

---

## 5. Voice

Flat declaratives, exact numbers, named statutes. Never "AI-powered", never "seamless",
never "trust us".

| Don't | Do |
|---|---|
| "AI-powered compliance you can trust" | "Every figure is recomputed by a second engine before you see it." |
| "Smart insights into your finances" | "₹12,34,567 GST payable. Recomputed ✓. Sealed 2026-07-21." |
| "We take security seriously" | State the mechanism, or state that it's pending. |
| "Verified" (when it isn't) | "◐ Not yet recomputed — here's what's missing." |

The ◐ state is a **brand asset, not an apology**. Every competitor's number is a claim; ours
is either proven or openly marked unproven. Say that plainly — it is the strongest sentence
we own, and CRED/Open's zero-hedge register is the right register for it.

---

## 6. Provenance & what was dropped

The verifier pass **dropped 2 findings and materially narrowed 4**, which is why this doc
should be trusted over an unverified brand brief:

- **Dropped — a Bloomberg Terminal amber (`#FFB000`) "machine-readability" rationale.** The
  hex existed on the cited page, but the page was an LLM-authored prompt pack in a personal
  GitHub repo and the quoted rationale appeared nowhere in it. It carries no authority over
  the real Bloomberg Terminal. *(Our brass in §3 is an independent choice and is deliberately
  not that value.)*
- **Dropped — Wise rebrand quotes** ("evokes stability without sterility" etc.) that were
  paraphrase presented as quotation.
- **Corrected — Stripe's background token is `#ffffff`, not `#f6f9fc`** as originally claimed.
- **Corrected — "one accent, no rainbow" is *not* Wise's system**: its own source documents
  secondary palettes of orange, yellow, blue, pink, purple, gold, charcoal, maroon. The
  single-accent pattern is evidenced by Mercury/Ramp/Brex/Linear instead, and cited to them.
- Mercury whitespace/layout claims that weren't in the fetched text were stripped; only
  verbatim-verifiable copy was kept.
- Several verified sources (`shadcn.io/design/*`, `awesome-design-md`, `refero.design`,
  `dembrandt.com`) are **third-party extractors, not official brand kits**. They are cited as
  observed-token evidence at medium confidence, and nothing in §3 depends on any single one.

---

## 7. Open decisions

- **`--color-accent: #8a6a1f`** — brass is reasoned by elimination, not user-tested. The
  reasoning (avoid money ramps, verification ramps, and every competitor hue) constrains it
  hard, but the exact value is a judgement call.
- Light-default vs dark-default is a **product decision** with real downstream cost; §3 makes
  the case for light. Reversing it later is a token swap, not a rebuild.
- No logo/wordmark is specified. §4 argues the verification chip does that job; a formal mark
  can wait until there's a reason for one.
