// P1-1 — the one honesty gate on the Ask Maisha screen: a figure's badge can only ever be one
// of the server's three states, and anything else fails closed to unbacked (✕), never verified.

import { describe, expect, it } from "vitest";
import { toVerifyState } from "./Ask";

describe("toVerifyState — the payload decides, and unknown fails closed", () => {
  it("passes through each real server state unchanged", () => {
    expect(toVerifyState("verified")).toBe("verified");
    expect(toVerifyState("honest_pending")).toBe("honest_pending");
    expect(toVerifyState("unbacked")).toBe("unbacked");
  });

  it("an unrecognised or missing state renders unbacked, never verified", () => {
    expect(toVerifyState("")).toBe("unbacked");
    expect(toVerifyState("bogus")).toBe("unbacked");
    expect(toVerifyState("Verified")).toBe("unbacked"); // case-sensitive: no fuzzy upgrade
  });
});
