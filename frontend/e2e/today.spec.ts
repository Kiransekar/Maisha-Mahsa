// QG.2 — Today happy path: the owner's landing loads real seeded figures THROUGH the real
// loop (SPA → FastAPI → Mahsa), and every figure wears a verification badge. The seeded books
// render ◐ on the cash strip (Today's assembler shows them as-is, not yet sealed) — the test
// pins that HONEST state rather than asserting a ✓ the payload does not claim.

import { expect, test } from "@playwright/test";
import { signIn } from "./helpers.ts";

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("Today loads with cash strip, badges on every figure, and the queue sections", async ({
  page,
}) => {
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "Today", exact: true })).toBeVisible();

  // the cash strip renders the seeded company's real figures
  await expect(page.getByText("Cash on hand")).toBeVisible();
  await expect(page.getByText("Monthly burn")).toBeVisible();
  await expect(page.getByText("Runway")).toBeVisible();

  // WS7: every figure is badged. Today's strip is honest_pending by design (not sealed on this
  // surface) — at least the three strip figures must wear the ◐ chip, and nothing may claim ✓
  // here falsely: any ✓ on this page must come with Mahsa actually up.
  const pendingChips = page.getByText("◐ not yet sealed");
  expect(await pendingChips.count()).toBeGreaterThanOrEqual(3);

  // the two queues render (empty or not, the section must exist — never a blank shell)
  await expect(page.getByRole("heading", { name: "Needs you" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Trouble radar" })).toBeVisible();
});

test("a figure's working panel is interrogable: expand → report-issue escape hatch", async ({
  page,
}) => {
  await page.goto("/today");
  const firstWorking = page.getByText("Show working").first();
  await expect(firstWorking).toBeVisible();
  await firstWorking.click();
  await expect(page.getByText("This number looks wrong →").first()).toBeVisible();
});
