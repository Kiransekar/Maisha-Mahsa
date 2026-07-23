// @vitest-environment jsdom
// MED-2 — mounted VerifiedNumber interaction. The pure tests (VerifiedNumber.test.ts) prove
// effectiveState/hasBrokenCitation as functions; this file proves the RENDERED behaviour:
// the <details> working panel actually toggles open, the downgrade sentences appear (and say
// only what is true — stale vs unknown vs broken are different facts), and the report-issue
// escape hatch carries the verdict hash. No fetch here — the component is pure props.

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { VerifiedNumber, type Working } from "./VerifiedNumber";

afterEach(cleanup);

const WORKING: Working = {
  inputs: [{ label: "Cash on hand", value: "₹46,00,000" }],
  formula: "runway = cash / burn",
  citations: [{ text: "FC-RUNWAY-1 · internal forecast rule" }],
  documents: [{ label: "Bank stmt HDFC-May.csv, row 47", url: "/d/vault?doc=abc" }],
  verdict_hash: "a1b2c3d4e5f6",
};

describe("VerifiedNumber — mounted full interaction (MED-2)", () => {
  it("the working panel opens on summary click and shows inputs → formula → citations → documents → verdict", () => {
    render(
      <VerifiedNumber label="Runway" value="11 months" state="verified" working={WORKING} />,
    );

    const details = document.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    fireEvent.click(screen.getByText("Show working"));
    expect(details.open).toBe(true);

    // T7 — every layer of the interrogation trail is really in the panel
    expect(screen.getByText("Cash on hand")).toBeTruthy();
    expect(screen.getByText("runway = cash / burn")).toBeTruthy();
    expect(screen.getByText("FC-RUNWAY-1 · internal forecast rule")).toBeTruthy();
    const doc = screen.getByText("Bank stmt HDFC-May.csv, row 47") as HTMLAnchorElement;
    expect(doc.getAttribute("href")).toBe("/d/vault?doc=abc");
    expect(screen.getByText("a1b2c3d4e5f6")).toBeTruthy();

    // the ✓-state explainer only renders on a verified figure
    expect(
      screen.getByText(/Recomputed independently by Mahsa/),
    ).toBeTruthy();
  });

  it("report-issue link carries the verdict hash; 'unsealed' when there is none", () => {
    const { unmount } = render(
      <VerifiedNumber label="Runway" value="11 months" state="verified" working={WORKING} />,
    );
    let link = screen.getByText("This number looks wrong →") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/inbox?report=a1b2c3d4e5f6");
    unmount();

    render(
      <VerifiedNumber
        label="Runway"
        value="11 months"
        state="honest_pending"
        working={{ ...WORKING, verdict_hash: null }}
      />,
    );
    link = screen.getByText("This number looks wrong →") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/inbox?report=unsealed");
    expect(screen.getByText("Not yet sealed to the audit chain.")).toBeTruthy();
  });

  it("a BROKEN citation downgrades ✓ to ◐ on screen, states why, and the panel names the break", () => {
    render(
      <VerifiedNumber
        label="Runway"
        value="11 months"
        state="verified"
        working={{
          ...WORKING,
          documents: [
            {
              label: "Bank stmt HDFC-May.csv, row 47",
              resolution: "broken",
              note: "no row with this hash",
            },
          ],
        }}
      />,
    );

    // the chip is ◐, not the server's ✓ — and the ✓ chip is nowhere on screen
    expect(screen.getByText("◐ not yet sealed")).toBeTruthy();
    expect(screen.queryByText("✓ recomputed")).toBeNull();
    // the downgrade is stated, never silent
    expect(screen.getByText(/a source citation behind this figure is broken/)).toBeTruthy();
    // and inside the panel, the document row names the break with the server's note
    expect(screen.getByText(/citation broken: no row with this hash/)).toBeTruthy();
  });

  it("a MOVED citation keeps ✓ but the panel shows the visible moved note", () => {
    render(
      <VerifiedNumber
        label="Runway"
        value="11 months"
        state="verified"
        working={{
          ...WORKING,
          documents: [
            {
              label: "Bank stmt HDFC-May.csv, row 47",
              resolution: "moved",
              note: "row moved from 47 to 52",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("✓ recomputed")).toBeTruthy();
    expect(screen.getByText(/row moved from 47 to 52/)).toBeTruthy();
  });

  it("stale=true and stale='unknown' downgrade with DIFFERENT sentences — two different facts", () => {
    const { unmount } = render(
      <VerifiedNumber label="Cash" value="₹46,00,000" state="verified" stale={true} />,
    );
    expect(screen.getByText("◐ not yet sealed")).toBeTruthy();
    expect(screen.getByText(/inputs behind this figure are stale/)).toBeTruthy();
    unmount();

    render(<VerifiedNumber label="Cash" value="₹46,00,000" state="verified" stale="unknown" />);
    expect(screen.getByText("◐ not yet sealed")).toBeTruthy();
    expect(screen.getByText(/we couldn't check how fresh the inputs/)).toBeTruthy();
  });

  it("an empty working panel says WHY the figure reads ◐ instead of rendering blank", () => {
    render(<VerifiedNumber label="PF due" value="₹18,000" state="honest_pending" working={{}} />);
    fireEvent.click(screen.getByText("Show working"));
    expect(
      screen.getByText(/No working has been sealed for this figure yet/),
    ).toBeTruthy();
  });
});
