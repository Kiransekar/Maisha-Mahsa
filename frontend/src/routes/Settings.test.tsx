// P1-3 CA seat invite/accept UI — the settings screen's load-bearing branches:
//   1. caSectionDeniedReason — a 403 must produce the disabled-with-reason text (non-owner path),
//      and nothing else may (a network error must not be mistaken for "not your role").
//   2. canSubmitInvite       — the client-side guard against submitting an empty/garbage form.
//   3. inviteErrorText       — every server refusal (app/core/ca_seat.invite_ca) gets its own
//      sentence, never a generic "error".
//   4. CaSeatSection render  — the free+unlimited fact is stated, the pending list renders real
//      emails, and an empty list reads as honest-empty (not a blank panel).
//
// No @testing-library/react in this repo (package.json) — renderToStaticMarkup for a real React
// render of the presentational piece (see BankCsvImport.test.tsx for the precedent).

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ApiError } from "../lib/api";
import {
  CaInviteForm,
  PendingInvitesList,
  canSubmitInvite,
  caSectionDeniedReason,
  inviteErrorText,
} from "./Settings";

describe("caSectionDeniedReason — the non-owner disabled reason", () => {
  it("names the reason for a 403 (missing manage_users)", () => {
    const reason = caSectionDeniedReason(new ApiError(403, "403 Forbidden"));
    expect(reason).toContain("Owner");
    expect(reason).toContain("Admin");
  });

  it("is null for anything that isn't a permission denial — a 500 is not 'wrong role'", () => {
    expect(caSectionDeniedReason(new ApiError(500, "500"))).toBeNull();
    expect(caSectionDeniedReason(new TypeError("network"))).toBeNull();
    expect(caSectionDeniedReason(null)).toBeNull();
  });
});

describe("canSubmitInvite — client-side guard only, server is the real validator", () => {
  it("rejects empty, spaced, and no-@ input", () => {
    expect(canSubmitInvite("")).toBe(false);
    expect(canSubmitInvite("   ")).toBe(false);
    expect(canSubmitInvite("not-an-email")).toBe(false);
    expect(canSubmitInvite("a b@c.in")).toBe(false);
  });

  it("accepts a plausible address", () => {
    expect(canSubmitInvite("ca@theirfirm.in")).toBe(true);
    expect(canSubmitInvite("  ca@theirfirm.in  ")).toBe(true);
  });
});

describe("inviteErrorText — every server refusal gets its own sentence", () => {
  it("409 duplicate", () => {
    expect(inviteErrorText(new ApiError(409, "409"))).toMatch(/already/i);
  });
  it("400 bad email", () => {
    expect(inviteErrorText(new ApiError(400, "400"))).toMatch(/email address/i);
  });
  it("403 wrong role", () => {
    expect(inviteErrorText(new ApiError(403, "403"))).toMatch(/Owner\/Admin/);
  });
  it("anything else falls to a generic retry, never blank", () => {
    expect(inviteErrorText(new TypeError("offline"))).toMatch(/try again/i);
  });
});

describe("CaInviteForm — the invite form itself", () => {
  const noop = () => {};

  it("states the entitlement fact in the rendered text", () => {
    const html = renderToStaticMarkup(
      <CaInviteForm email="" onEmailChange={noop} onSubmit={noop} submitting={false} errorText={null} />,
    ).replace(/\s+/g, " ");
    expect(html).toContain("free and unlimited");
    expect(html).toContain("never counts against your plan");
  });

  it("the button starts disabled — the form opens with an empty address", () => {
    const html = renderToStaticMarkup(
      <CaInviteForm email="" onEmailChange={noop} onSubmit={noop} submitting={false} errorText={null} />,
    );
    expect(html).toContain('disabled=""');
  });

  it("a plausible address enables the button", () => {
    const html = renderToStaticMarkup(
      <CaInviteForm
        email="ca@theirfirm.in"
        onEmailChange={noop}
        onSubmit={noop}
        submitting={false}
        errorText={null}
      />,
    );
    expect(html).not.toContain('disabled=""');
  });

  it("submitting disables the button even with a valid address", () => {
    const html = renderToStaticMarkup(
      <CaInviteForm
        email="ca@theirfirm.in"
        onEmailChange={noop}
        onSubmit={noop}
        submitting={true}
        errorText={null}
      />,
    );
    expect(html).toContain('disabled=""');
    expect(html).toContain("Sending…");
  });

  it("renders the server's own error text when present", () => {
    const html = renderToStaticMarkup(
      <CaInviteForm email="x" onEmailChange={noop} onSubmit={noop} submitting={false} errorText="already invited" />,
    );
    expect(html).toContain("already invited");
  });
});

describe("PendingInvitesList", () => {
  it("renders honest-empty when no invites are pending", () => {
    const html = renderToStaticMarkup(<PendingInvitesList invites={[]} />);
    expect(html).toContain("No CA invites are pending");
  });

  it("renders each pending invite's real email and status, not a placeholder", () => {
    const html = renderToStaticMarkup(
      <PendingInvitesList
        invites={[
          { membership_id: 1, email: "ca@theirfirm.in", invited_at: "2026-07-22T10:00:00" },
        ]}
      />,
    );
    expect(html).toContain("ca@theirfirm.in");
    expect(html).toContain("pending");
    expect(html).not.toContain("No CA invites are pending");
  });
});

// ── WS10.1 Privacy section — the load-bearing pure branches ──────────────────────────────────

import {
  DpdpRequestsList,
  noticeLine,
  requestStatusLine,
  type DpdpRequest,
} from "./Settings";

const REQ: DpdpRequest = {
  id: 7,
  requester: "A. Kumar",
  request_type: "erasure",
  details: null,
  received_date: "2026-07-23",
  due_date: "2026-10-21",
  status: "open",
  hold_basis: null,
  closed_date: null,
};

describe("requestStatusLine — the status/date pairing is honest per state", () => {
  it("open shows the SLA due date", () => {
    expect(requestStatusLine(REQ)).toBe("open · respond by 2026-10-21");
  });

  it("held names the legal hold AND keeps the SLA date visible", () => {
    const line = requestStatusLine({ ...REQ, status: "held" });
    expect(line).toContain("legal hold");
    expect(line).toContain("2026-10-21");
  });

  it("completed shows the close date, not the stale due date", () => {
    const line = requestStatusLine({ ...REQ, status: "completed", closed_date: "2026-08-01" });
    expect(line).toBe("completed 2026-08-01");
    expect(line).not.toContain("2026-10-21");
  });

  it("an unknown future status renders verbatim, never re-interpreted", () => {
    expect(requestStatusLine({ ...REQ, status: "escalated" })).toBe("escalated");
  });
});

describe("noticeLine — nothing published renders NOTHING (never a fabricated notice)", () => {
  it("null current_version -> null (no card)", () => {
    expect(
      noticeLine({ doc_type: "dpdp_notice", current_version: null, needs_acceptance: false }),
    ).toBeNull();
  });

  it("in force + unaccepted -> asks for acceptance, naming the version", () => {
    const line = noticeLine({
      doc_type: "dpdp_notice",
      current_version: "v1",
      needs_acceptance: true,
    });
    expect(line).toContain("v1");
    expect(line).toContain("not accepted");
  });

  it("in force + accepted -> states the accepted version", () => {
    const line = noticeLine({
      doc_type: "dpdp_notice",
      current_version: "v2",
      needs_acceptance: false,
    });
    expect(line).toBe("DPDP notice v2 accepted.");
  });
});

describe("DpdpRequestsList", () => {
  it("renders honest-empty", () => {
    const html = renderToStaticMarkup(<DpdpRequestsList requests={[]} />);
    expect(html).toContain("No data-principal rights requests");
  });

  it("a held request surfaces the statutory basis verbatim", () => {
    const html = renderToStaticMarkup(
      <DpdpRequestsList
        requests={[{ ...REQ, status: "held", hold_basis: "Companies Act 2013 s.128(5) …" }]}
      />,
    );
    expect(html).toContain("A. Kumar");
    expect(html).toContain("legal hold");
    expect(html).toContain("Companies Act 2013 s.128(5)");
  });
});
