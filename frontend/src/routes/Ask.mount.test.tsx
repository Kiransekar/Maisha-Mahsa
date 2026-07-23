// @vitest-environment jsdom
// MED-2 — mounted Ask flow. The pure tests (Ask.test.ts) prove toVerifyState/askWorking in
// isolation; this file proves the WIRING: submitting the form POSTs the trimmed question to
// /ask, the answer card renders the payload's own verdicts (a figure's chip comes from the
// server state, an unknown state fails closed to ✕), citations reach the working panel, and
// Mahsa-down is an explicit banner — never a silently thinner answer.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Ask } from "./Ask";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: apiMock };
});

function mount() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <Ask />
    </QueryClientProvider>,
  );
}

const ANSWER = {
  query: "What's our runway?",
  domain: "forecast",
  narrative: "At the current burn the company has 11 months of runway.",
  figures: [
    { label: "Runway", value: "11 months", state: "verified" },
    { label: "Monthly burn", value: "₹4,20,000", state: "honest_pending" },
    // an unrecognised server state MUST fail closed to ✕ in the rendered chip
    { label: "Cash", value: "₹46,00,000", state: "somehow_new_state" },
  ],
  citations: [
    {
      rule_id: "FC-RUNWAY-1",
      text: "Runway = cash / trailing burn",
      citation: "internal forecast rule",
      domain: "forecast",
    },
  ],
  status: "green",
  requires_approval: false,
  abstained: false,
  mahsa_up: true,
  provenance: "recomputed by Mahsa",
};

beforeEach(() => {
  apiMock.mockReset();
});

afterEach(cleanup);

describe("Ask — mounted submit → answer flow (MED-2)", () => {
  it("POSTs the trimmed question to /ask and renders figures with the SERVER'S verdicts", async () => {
    let posted: { q: string } | null = null;
    apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
      expect(path).toBe("/ask");
      expect(init?.method).toBe("POST");
      posted = JSON.parse(String(init?.body)) as { q: string };
      return ANSWER;
    });
    mount();

    fireEvent.change(screen.getByLabelText("Ask Maisha"), {
      target: { value: "  What's our runway?  " },
    });
    fireEvent.click(screen.getByText("Ask"));

    await waitFor(() => expect(posted).toEqual({ q: "What's our runway?" }));
    expect(
      await screen.findByText("At the current burn the company has 11 months of runway."),
    ).toBeTruthy();

    // per-figure chips come from the payload — one of each state, and the unknown one is ✕
    expect(screen.getByText("11 months")).toBeTruthy();
    expect(screen.getByText("✓ recomputed")).toBeTruthy();
    expect(screen.getByText("◐ not yet sealed")).toBeTruthy();
    expect(screen.getByText("✕ unbacked")).toBeTruthy(); // fail-closed on "somehow_new_state"

    // citations reached every figure's working panel (askWorking wiring, not just the helper)
    expect(screen.getAllByText("FC-RUNWAY-1 · internal forecast rule").length).toBe(3);

    // the suggestion chips leave the screen once a question was asked
    expect(screen.queryByText("Try asking")).toBeNull();

    // status pill + provenance are the payload's own words
    expect(screen.getByText("green")).toBeTruthy();
    expect(screen.getByText("recomputed by Mahsa")).toBeTruthy();
  });

  it("a suggestion chip submits its own question immediately", async () => {
    let posted: { q: string } | null = null;
    apiMock.mockImplementation(async (_path: string, init?: RequestInit) => {
      posted = JSON.parse(String(init?.body)) as { q: string };
      return { ...ANSWER, query: "Any MSME payments overdue?" };
    });
    mount();

    fireEvent.click(screen.getByText("Any MSME payments overdue?"));
    await waitFor(() => expect(posted).toEqual({ q: "Any MSME payments overdue?" }));
  });

  it("an empty question never reaches the API — the button is disabled", () => {
    mount();
    const button = screen.getByText("Ask") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Ask Maisha"), { target: { value: "   " } });
    expect(button.disabled).toBe(true);
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("mahsa_up=false renders the explicit down note above the narrative", async () => {
    apiMock.mockResolvedValue({ ...ANSWER, mahsa_up: false, provenance: "not recomputed" });
    mount();

    fireEvent.change(screen.getByLabelText("Ask Maisha"), { target: { value: "runway?" } });
    fireEvent.click(screen.getByText("Ask"));

    expect(
      await screen.findByText(
        "Mahsa is unreachable — figures below are shown as-is, not independently recomputed.",
      ),
    ).toBeTruthy();
  });

  it("abstention with no figures renders the honest empty state, not a blank card", async () => {
    apiMock.mockResolvedValue({
      ...ANSWER,
      narrative: "",
      figures: [],
      citations: [],
      status: null,
      abstained: true,
    });
    mount();

    fireEvent.change(screen.getByLabelText("Ask Maisha"), { target: { value: "runway?" } });
    fireEvent.click(screen.getByText("Ask"));

    expect(
      await screen.findByText(
        "Not enough data to answer confidently — add the underlying records first.",
      ),
    ).toBeTruthy();
  });
});
