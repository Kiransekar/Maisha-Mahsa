// P1-1 — the one honesty gate on the Ask Maisha screen: a figure's badge can only ever be one
// of the server's three states, and anything else fails closed to unbacked (✕), never verified.

import { describe, expect, it } from "vitest";
import { askWorking, toVerifyState, type AskAnchor } from "./Ask";

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

// CITE.P1-2 — anchored citations become working-panel documents (deep-link + §B2 resolution),
// so a broken anchor downgrades the badge through the SAME hasBrokenCitation path as every
// other surface; unanchored citations stay text-only, never a fabricated document row.
describe("askWorking — anchors map to documents, nothing is fabricated", () => {
  const anchor: AskAnchor = {
    doc_sha256: "abc123",
    file_name: "HDFC-May.csv",
    locator: { kind: "csv_row", source_row: 2 },
    row_hash: "def456",
    occurrence: 1,
    excerpt: "HDFC-May.csv, row 2: 2026-07-01 NEFT ₹1,20,000.00 Cr",
    resolution: "broken",
    note: "no row matches",
    url: "/d/vault?doc=abc123",
  };
  const statutory = { rule_id: "GST-001", text: "t", citation: "CGST Act 2017 / Sec 47", domain: "gst" };
  const anchored = { rule_id: "source:abc123", text: anchor.excerpt, citation: "HDFC-May.csv, row 2", domain: "treasury", anchor };

  it("returns undefined with no citations — never a fabricated empty panel", () => {
    expect(askWorking([])).toBeUndefined();
  });

  it("keeps every citation as text and maps only anchored ones to documents", () => {
    const w = askWorking([statutory, anchored]);
    expect(w?.citations).toEqual([
      { text: "GST-001 · CGST Act 2017 / Sec 47" },
      { text: "source:abc123 · HDFC-May.csv, row 2" },
    ]);
    expect(w?.documents).toEqual([
      {
        label: anchor.excerpt,
        url: "/d/vault?doc=abc123",
        resolution: "broken",
        note: "no row matches",
      },
    ]);
  });

  it("statutory-only citations produce no document rows", () => {
    expect(askWorking([statutory])?.documents).toEqual([]);
  });
});
