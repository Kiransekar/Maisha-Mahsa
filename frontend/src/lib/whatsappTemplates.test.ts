import { describe, expect, it } from "vitest";
import { approvalAlertMessage, dailyBriefMessage, troubleAlertMessage } from "./whatsappTemplates";

describe("WhatsApp templates — strings only, deep-link into the app", () => {
  it("daily brief carries the real figures and a /today deep link, not a confirm action", () => {
    const msg = dailyBriefMessage({
      ownerName: "Asha",
      asOf: "2026-07-22",
      cashLabel: "₹4,32,000",
      needsYouCount: 2,
      troubleCount: 1,
      appUrl: "https://app.example",
    });
    expect(msg).toContain("₹4,32,000");
    expect(msg).toContain("2 item(s)");
    expect(msg).toContain("https://app.example/today");
  });

  it("approval alert never lets WhatsApp itself approve — it only deep-links to /approvals", () => {
    const msg = approvalAlertMessage({
      domain: "gst",
      headline: "3 figures recomputed, all verified",
      amountLabel: "₹12,340",
      appUrl: "https://app.example",
    });
    expect(msg).toContain("https://app.example/approvals");
    expect(msg).toMatch(/cannot approve/i);
  });

  it("trouble alert accepts the honest 'not yet known' consequence label verbatim", () => {
    // Invariant 2 (Today.tsx): unknown ₹ impact is never invented as ₹0.
    const msg = troubleAlertMessage({
      what: "GSTR-1 overdue",
      when: "2 days overdue",
      consequenceLabel: "₹ impact not yet known — we don't guess",
      appUrl: "https://app.example",
    });
    expect(msg).toContain("₹ impact not yet known — we don't guess");
    expect(msg).not.toContain("₹0");
  });
});
