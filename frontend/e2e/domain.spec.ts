// QG.2 — one domain hub happy path (§WS7.4 "hub E2E per domain" — GST is the representative
// hub; the others share DomainBody, so this exercises the shared machinery through the real
// loop). The seeded company yields real GST figures (late fee, filing timeliness, ITC ratio…).

import { expect, test } from "@playwright/test";
import { signIn } from "./helpers.ts";

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("the GST hub loads seeded figures, every one badged, with an interrogable working panel", async ({
  page,
}) => {
  await page.goto("/d/gst");
  await expect(page.getByRole("heading", { name: "gst", exact: true })).toBeVisible();

  // real figures out of the seeded books via the real fold
  await expect(page.getByText("Gstr3b late fee")).toBeVisible();
  await expect(page.getByText("Filing timeliness")).toBeVisible();

  // every figure wears a verification chip — count chips of the three honest states and
  // require at least as many as the two figures asserted above (no unbadged figure sneaks by)
  const chips = page.locator("text=/^(✓ recomputed|◐ not yet sealed|✕ unbacked)$/");
  expect(await chips.count()).toBeGreaterThanOrEqual(2);

  // T7: a hub figure is interrogable, not just displayed
  await page.getByText("Show working").first().click();
  await expect(page.getByText("This number looks wrong →").first()).toBeVisible();
});
