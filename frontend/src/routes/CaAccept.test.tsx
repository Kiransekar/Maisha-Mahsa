// P1-3 CA seat invite/accept UI — the accept screen's load-bearing branches:
//   1. isNoPendingInvite — a 404 (app/core/ca_seat.accept_ca's LookupError) is the honest
//      "nothing to accept" outcome, distinct from a real failure; nothing else may read as that.
//   2. CaAcceptCard render — idle/pending/404/other-error states each render their own text,
//      and the entitlement fact is stated here too (accepting is still the free+unlimited seat).
//
// CaAcceptCard is deliberately router-free (the real redirect lives in CaAccept, the hooked
// parent) so it renders via renderToStaticMarkup with no <MemoryRouter> needed — see CaAccept.tsx.

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ApiError } from "../lib/api";
import { CaAcceptCard, isNoPendingInvite } from "./CaAccept";

describe("isNoPendingInvite — 404 is honest-empty, not a failure", () => {
  it("true only for a 404", () => {
    expect(isNoPendingInvite(new ApiError(404, "404"))).toBe(true);
  });
  it("false for every other error, including other ApiErrors", () => {
    expect(isNoPendingInvite(new ApiError(500, "500"))).toBe(false);
    expect(isNoPendingInvite(new ApiError(403, "403"))).toBe(false);
    expect(isNoPendingInvite(new TypeError("offline"))).toBe(false);
    expect(isNoPendingInvite(null)).toBe(false);
  });
});

describe("CaAcceptCard — render per state", () => {
  it("idle: an enabled Accept button, the entitlement fact stated", () => {
    const html = renderToStaticMarkup(
      <CaAcceptCard onAccept={() => {}} pending={false} error={null} success={false} traceId="t1" />,
    ).replace(/\s+/g, " ");
    expect(html).toContain("Accept CA seat");
    expect(html).not.toContain("disabled=\"\"");
    expect(html).toContain("free and unlimited");
  });

  it("pending: the button is disabled and says so", () => {
    const html = renderToStaticMarkup(
      <CaAcceptCard onAccept={() => {}} pending={true} error={null} success={false} traceId="t1" />,
    );
    expect(html).toContain("Accepting…");
    expect(html).toContain('disabled=""');
  });

  it("404: the honest 'no pending invite' sentence, not a generic error template", () => {
    const html = renderToStaticMarkup(
      <CaAcceptCard
        onAccept={() => {}}
        pending={false}
        error={new ApiError(404, "404")}
        success={false}
        traceId="t1"
      />,
    );
    expect(html).toContain("No pending CA invite was found");
    expect(html).not.toContain("What happened"); // that's ErrorState's template, not this one
  });

  it("a real failure (500) goes through the 4-question ErrorState instead", () => {
    const html = renderToStaticMarkup(
      <CaAcceptCard
        onAccept={() => {}}
        pending={false}
        error={new ApiError(500, "500")}
        success={false}
        traceId="t1"
      />,
    );
    expect(html).toContain("What happened");
    expect(html).not.toContain("No pending CA invite was found");
  });

  it("success renders a plain confirmation, no fabricated Audit Room content", () => {
    const html = renderToStaticMarkup(
      <CaAcceptCard onAccept={() => {}} pending={false} error={null} success={true} traceId="t1" />,
    );
    expect(html).toContain("Seat active");
  });
});
