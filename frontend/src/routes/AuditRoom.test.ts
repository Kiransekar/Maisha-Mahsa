// The two pure branches on the Audit Room that must never lie to a CA:
//   1. chainBanner — can a broken chain ever come out looking like a good one?
//   2. pageInfo    — off-by-ones at the edges (empty log, partial last page).

import { describe, expect, it } from "vitest";
import { chainBanner, pageInfo } from "./AuditRoom";

describe("chainBanner — tone can only ever come from the server's own verdict", () => {
  it("reports the failure loudly and never softens the wording", () => {
    const b = chainBanner(false, 12);
    expect(b.tone).toBe("broken");
    expect(b.headline).toContain("FAILED");
    expect(b.detail).toMatch(/altered|deleted|reordered/);
  });

  it("only reports intact when the server says intact, and names the count", () => {
    const b = chainBanner(true, 12);
    expect(b.tone).toBe("intact");
    expect(b.detail).toContain("12");
  });

  it("singular/plural on the entry count reads naturally", () => {
    expect(chainBanner(true, 1).detail).toContain("1 entry");
    expect(chainBanner(true, 0).detail).toContain("0 entries");
  });
});

describe("pageInfo — paging math at the edges", () => {
  it("empty log: no range to show, no prev/next", () => {
    const p = pageInfo(0, 50, 0);
    expect(p.from).toBe(0);
    expect(p.to).toBe(0);
    expect(p.hasPrev).toBe(false);
    expect(p.hasNext).toBe(false);
  });

  it("first page of a full log offers only next", () => {
    const p = pageInfo(120, 50, 0);
    expect(p.from).toBe(1);
    expect(p.to).toBe(50);
    expect(p.hasPrev).toBe(false);
    expect(p.hasNext).toBe(true);
    expect(p.nextOffset).toBe(50);
  });

  it("partial last page caps `to` at total, not offset+limit", () => {
    const p = pageInfo(120, 50, 100);
    expect(p.from).toBe(101);
    expect(p.to).toBe(120);
    expect(p.hasNext).toBe(false);
    expect(p.hasPrev).toBe(true);
    expect(p.prevOffset).toBe(50);
  });

  it("middle page offers both directions", () => {
    const p = pageInfo(120, 50, 50);
    expect(p.hasPrev).toBe(true);
    expect(p.hasNext).toBe(true);
  });
});
