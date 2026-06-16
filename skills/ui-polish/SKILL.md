---
name: ui-polish
description: Pixel-level UI standards for the Maisha-Mahsa dashboard and emails — design tokens, spacing/type scale, the green/amber/red status system, HTMX patterns, and accessibility. Use when building or reviewing any web page, component, or email template. The product must be perfect down to the minute UI detail.
---

# UI polish standard

Vanilla CSS + HTMX, no build step (PRD §7/§8). The bar is pixel-perfect: nothing ad-hoc.

## Tokens are the law (`api/app/web/static/css/tokens.css`)
Never hard-code a color, space, radius, or font size in a component — use a `var(--…)`.
- **Spacing**: 4px base scale `--sp-1..--sp-8`. No arbitrary px margins.
- **Type**: 1.250 modular scale `--fs-xs..--fs-xl`, 16px base, `--lh-tight/-base`.
- **Radii/elevation**: `--radius-sm/md/lg`, `--shadow-1/2`.
- **Color**: neutral surface/border/text + brand. Dark mode via `prefers-color-scheme`.
- Tabular numbers for money/metrics: `font-variant-numeric: tabular-nums`.

## The traffic light is sacred
Green/amber/red come from Mahsa's `ResponseShape.color`; render with the `.pill--green/
amber/red` classes (and `.pill--pending` for unbuilt modules). Never invent a fourth status
or recolor a status to look nicer — it mirrors `ValidationStatus` and must stay faithful.

## Components (see `dashboard.html` / `app.css`)
- KPI strip, domain health cards, compliance calendar, approvals list, strategic prompt
  (PRD §7.1). Cards: `--shadow-1`, lift to `--shadow-2` on hover via `--transition`.
- Money always rendered with Indian grouping (`Paise.format_inr()` → `₹12,34,567.00`).

## HTMX patterns
- Server renders HTML fragments; HTMX swaps them. Keep handlers in `domains/<d>/router.py`
  returning `TemplateResponse` partials. No client-side state machines.
- Loading/disabled states on every action button; optimistic UI only with a server confirm.

## Accessibility & detail
- Visible focus rings; color is never the only signal (pills carry a text label too).
- Hit targets ≥ 32px; consistent alignment to the 4px grid; no layout shift on load.
- Test changed pages with the `browse:ui-test` skill (functional + a11y + responsive).

A page isn't done until it's flawless at 1× and 2×, light and dark, and keyboard-navigable.
