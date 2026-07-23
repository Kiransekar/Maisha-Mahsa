// QG.2 — sign-in happy path + the two gates around it: a guest never sees a protected screen,
// and bad credentials never produce a session. Auth server = the stand-in in stack.mjs; the
// API-side JWT verification these flows lead into is real (JWKS, signature, iss/aud/exp).

import { expect, test } from "@playwright/test";
import { E2E_EMAIL, E2E_PASSWORD } from "./helpers.ts";

test("a guest asking for /today is redirected to /sign-in, with no figures rendered", async ({
  page,
}) => {
  await page.goto("/today");
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  // the guard renders NO product chrome for a guest — no nav, no cash figures
  await expect(page.getByText("Cash on hand")).toHaveCount(0);
});

test("wrong credentials stay on /sign-in with a visible error, not a session", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(E2E_EMAIL);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  // the failure renders through the product's standard 4-question ErrorState (SignIn.tsx
  // deliberately does NOT echo the server's raw sentence), and we are still on /sign-in
  await expect(page.getByText("What happened")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page).toHaveURL(/\/sign-in$/);
});

test("sign-in happy path: form → session → /today, and the return-to path is honoured", async ({
  page,
}) => {
  // arrive as a guest wanting a specific protected screen
  await page.goto("/approvals");
  await expect(page).toHaveURL(/\/sign-in$/);

  await page.getByLabel("Email").fill(E2E_EMAIL);
  await page.getByLabel("Password").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();

  // `from` state returns the user to what they actually asked for, not a hardcoded landing
  await expect(page).toHaveURL(/\/approvals$/);
  await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible();
});
