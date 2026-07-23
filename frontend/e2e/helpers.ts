// Shared E2E helpers. Credentials match the auth stand-in in stack.mjs — one source would be
// nicer, but importing stack.mjs would RUN the stack; two constants with a cross-reference
// comment is the honest cheap version.

import type { Page } from "@playwright/test";

export const E2E_EMAIL = "owner@example.com"; // stack.mjs E2E_EMAIL
export const E2E_PASSWORD = "e2e-password"; // stack.mjs E2E_PASSWORD

/** Sign the browser context in WITHOUT the form: POST the stand-in's sign-in endpoint so the
 *  session cookie lands in the context. The form itself is exercised by signin.spec.ts — every
 *  other spec starts authenticated, same division of labour as the backend suite (conftest
 *  mints a token; test_auth_e2e.py is the one that proves the minting flow). */
export async function signIn(page: Page): Promise<void> {
  const res = await page.request.post("/api/auth/sign-in/email", {
    data: { email: E2E_EMAIL, password: E2E_PASSWORD },
  });
  if (!res.ok()) throw new Error(`stand-in sign-in failed: ${res.status()}`);
}
