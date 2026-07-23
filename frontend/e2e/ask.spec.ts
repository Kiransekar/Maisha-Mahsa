// QG.2 — Ask happy path: question → answer with badged figures AND citations, through the real
// app.core.ask pipeline (deterministic figures; no LLM is configured in the E2E stack, which is
// itself the honest default — the answer is entirely fact-built and every figure badged).
//
// The question is chosen because the seeded books make payables YELLOW, and a yellow verdict
// carries its rule citations (PAYABLES-001, MSME 45-day) — so this proves citations actually
// reach the working panel, not just that the panel exists.

import { expect, test } from "@playwright/test";
import { signIn } from "./helpers.ts";

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("ask a question → answer with badged figures and real rule citations", async ({ page }) => {
  await page.goto("/ask");
  await expect(page.getByRole("heading", { name: "Ask Maisha" })).toBeVisible();

  await page.getByLabel("Ask Maisha").fill("Any MSME payments overdue?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  // the answer card: provenance names the domain and the deterministic pipeline
  await expect(page.getByText(/payables · deterministic figures/)).toBeVisible();

  // figures render with verification chips (the seeded, unsealed figures read ◐ — honest)
  await expect(page.getByRole("heading", { name: "Figures" })).toBeVisible();
  const chips = page.locator("text=/^(✓ recomputed|◐ not yet sealed|✕ unbacked)$/");
  expect(await chips.count()).toBeGreaterThanOrEqual(1);

  // citations: expand a working panel and find the payables rule the yellow verdict cites
  await page.getByText("Show working").first().click();
  await expect(page.getByText(/PAYABLES-001/).first()).toBeVisible();

  // the verdict pill states the server's status in its own words
  await expect(page.getByText("yellow", { exact: true })).toBeVisible();
});
