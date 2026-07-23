// QG.2 — the approval flow (§WS7.6): preview → typed confirm → commit → persistent audit
// receipt. This is the one place a human commits real money, and the E2E writes a REAL
// hash-chained audit entry through the real fold (fresh throwaway DB per run, so the write is
// safe AND genuine). The typed-confirm gate is asserted, not skipped around.

import { expect, test } from "@playwright/test";
import { signIn } from "./helpers.ts";

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("approval preview → typed confirm → audit receipt with the sealed chain hash", async ({
  page,
}) => {
  await page.goto("/approvals");
  await expect(page.getByRole("heading", { name: "Approvals", exact: true })).toBeVisible();

  // the seeded books put revenue + payables in the queue (yellow verdicts awaiting sign-off)
  const confirmInput = page.locator('input[id^="confirm-"]').first();
  await expect(confirmInput).toBeVisible();
  const domain = (await confirmInput.getAttribute("id"))!.replace("confirm-", "");

  // the preview restates what is being signed: the domain's card names its books hash
  await expect(page.getByText("This writes a permanent, hash-chained entry").first()).toBeVisible();

  // typed-confirm gate: Approve is dead until the domain is typed exactly
  const approve = page.getByRole("button", { name: "Approve" }).first();
  await expect(approve).toBeDisabled();
  await confirmInput.fill("wrong-text");
  await expect(approve).toBeDisabled();
  await confirmInput.fill(domain);
  await expect(approve).toBeEnabled();

  await approve.click();

  // the persistent receipt (never a toast): decision line + the REAL sealed chain hashes
  await expect(page.getByRole("heading", { name: "Recorded this session" })).toBeVisible();
  const receipt = page
    .getByText(new RegExp(`${domain} approved by u-owner`))
    .first();
  await expect(receipt).toBeVisible();
  await expect(page.getByText(/audit hash/).first()).toBeVisible();
  await expect(page.getByText(/sealed against books/).first()).toBeVisible();
});
