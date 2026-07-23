// @vitest-environment jsdom
// MED-2 — the FIRST mounted-component test in this repo (jsdom + @testing-library/react; the
// pure-helper tests in Settings.test.tsx stay untouched). What the pure tests could not prove
// and this file does: MemorySection's WIRING — that clicking Edit prefills the textarea from the
// server payload, Save actually PUTs the draft, Cancel writes nothing, Add appends and clears,
// and the 422 overflow reject renders the SERVER'S OWN sentence verbatim end-to-end (§0.4: the
// dynamic char count must survive the whole ApiError → memoryWriteErrorText → DOM path).
//
// Mock seam: `../lib/api` (repo precedent — Shell.test.tsx/Today.test.ts), with the REAL
// ApiError class re-exported so `error instanceof ApiError` in memoryWriteErrorText stays true.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import { MemorySection } from "./Settings";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, api: apiMock };
});

type Handler = (init?: RequestInit) => unknown;

/** Route table for the mock: `"METHOD /path"` -> response (or throw). Unrouted calls fail loudly
 *  so a test can never silently pass while hitting an endpoint it did not declare. */
function route(table: Record<string, Handler>) {
  apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${path}`;
    const h = table[key];
    if (!h) throw new Error(`unrouted api call in test: ${key}`);
    return h(init);
  });
}

/** The CFO-posture textarea, distinguished from the always-present append <input> (both are
 *  role=textbox — the tag is the honest discriminator). null when not in edit mode. */
function editTextarea(): HTMLTextAreaElement | null {
  return (
    (screen
      .queryAllByRole("textbox")
      .find((el) => el.tagName === "TEXTAREA") as HTMLTextAreaElement | undefined) ?? null
  );
}

function mount() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MemorySection />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const CFO = { content: "Prefer conservative runway estimates.", used: 37, limit: 4000 };
const MEMORY = { profile: "Acme Innovations Pvt Ltd · Chennai", cfo: CFO };
const HISTORY = {
  history: [
    {
      content: "Old posture line.",
      superseded_at: "2026-07-20T10:00:00Z",
      superseded_by: "owner@example.com",
      audit_seq: 41,
    },
  ],
};

beforeEach(() => {
  apiMock.mockReset();
});

afterEach(cleanup);

describe("MemorySection — mounted view/edit/save/cancel/append (MED-2)", () => {
  it("renders profile, CFO posture, char meter and the sealed history row from the payloads", async () => {
    route({
      "GET /memory": () => MEMORY,
      "GET /memory/history": () => HISTORY,
    });
    mount();

    expect(await screen.findByText("Acme Innovations Pvt Ltd · Chennai")).toBeTruthy();
    expect(screen.getByText("Prefer conservative runway estimates.")).toBeTruthy();
    expect(screen.getByText("37/4000 chars")).toBeTruthy();
    // history row: content + the audit-chain link derived by historyAuditLine
    expect(await screen.findByText("Old posture line.")).toBeTruthy();
    const auditLink = screen.getByText("sealed · audit #41") as HTMLAnchorElement;
    expect(auditLink.getAttribute("href")).toBe("/audit");
  });

  it("Edit prefills the textarea with the CURRENT content; Save PUTs the draft and exits edit mode", async () => {
    let saved: string | null = null;
    let cfoNow = CFO;
    route({
      "GET /memory": () => ({ ...MEMORY, cfo: cfoNow }),
      "GET /memory/history": () => HISTORY,
      "PUT /memory": (init) => {
        saved = (JSON.parse(String(init?.body)) as { content: string }).content;
        cfoNow = { content: saved, used: saved.length, limit: 4000 };
        return cfoNow;
      },
    });
    mount();

    fireEvent.click(await screen.findByText("Edit"));
    const textarea = editTextarea()!;
    // the prefill IS the wiring under test: draft starts as the server's content, not ""
    expect(textarea.value).toBe("Prefer conservative runway estimates.");

    fireEvent.change(textarea, { target: { value: "New posture: fund 18 months." } });
    // the live char meter follows the DRAFT while editing, not the stale server count
    expect(screen.getByText("28/4000 chars")).toBeTruthy();

    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(saved).toBe("New posture: fund 18 months."));
    // edit mode exited and the invalidated query refetched the new content
    expect(await screen.findByText("New posture: fund 18 months.")).toBeTruthy();
    expect(editTextarea()).toBeNull();
  });

  it("Cancel exits edit mode without any PUT", async () => {
    route({
      "GET /memory": () => MEMORY,
      "GET /memory/history": () => HISTORY,
    });
    mount();

    fireEvent.click(await screen.findByText("Edit"));
    fireEvent.change(editTextarea()!, { target: { value: "discarded draft" } });
    fireEvent.click(screen.getByText("Cancel"));

    expect(editTextarea()).toBeNull();
    // the original content is back on screen and no write ever left the component
    expect(screen.getByText("Prefer conservative runway estimates.")).toBeTruthy();
    const putCalls = apiMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "PUT");
    expect(putCalls).toHaveLength(0);
  });

  it("422 overflow on Save renders the server's DYNAMIC detail verbatim and stays in edit mode", async () => {
    const serverSentence =
      "CFO posture is limited to 4000 characters; this save would make it 4123. Trim it first.";
    route({
      "GET /memory": () => MEMORY,
      "GET /memory/history": () => HISTORY,
      "PUT /memory": () => {
        throw new ApiError(422, "422 Unprocessable Entity", serverSentence);
      },
    });
    mount();

    fireEvent.click(await screen.findByText("Edit"));
    fireEvent.click(screen.getByText("Save"));

    // §0.4: the exact server sentence, char count and all — never a re-derived client message
    expect(await screen.findByText(serverSentence)).toBeTruthy();
    expect(editTextarea()).toBeTruthy(); // still editing — the draft is not lost
  });

  it("403 on Save renders the role sentence (Owner/Admin only), not a generic error", async () => {
    route({
      "GET /memory": () => MEMORY,
      "GET /memory/history": () => HISTORY,
      "PUT /memory": () => {
        throw new ApiError(403, "403 Forbidden");
      },
    });
    mount();

    fireEvent.click(await screen.findByText("Edit"));
    fireEvent.click(screen.getByText("Save"));
    expect(await screen.findByText("Only Owner and Admin can edit company memory.")).toBeTruthy();
  });

  it("Add appends the trimmed line via POST and clears the input on success", async () => {
    let appended: string | null = null;
    route({
      "GET /memory": () => MEMORY,
      "GET /memory/history": () => HISTORY,
      "POST /memory/append": (init) => {
        appended = (JSON.parse(String(init?.body)) as { line: string }).line;
        return CFO;
      },
    });
    mount();

    const input = (await screen.findByPlaceholderText("Add one durable fact…")) as HTMLInputElement;
    const addButton = screen.getByText("Add") as HTMLButtonElement;
    expect(addButton.disabled).toBe(true); // empty line cannot submit

    fireEvent.change(input, { target: { value: "  We bill annually in advance.  " } });
    expect(addButton.disabled).toBe(false);
    fireEvent.click(addButton);

    await waitFor(() => expect(appended).toBe("We bill annually in advance."));
    await waitFor(() => expect(input.value).toBe("")); // cleared only on success
  });

  it("422 overflow on Append renders the server's detail verbatim and keeps the line for editing", async () => {
    const serverSentence = "Appending this line would exceed the 4000-character limit (4051).";
    route({
      "GET /memory": () => MEMORY,
      "GET /memory/history": () => HISTORY,
      "POST /memory/append": () => {
        throw new ApiError(422, "422 Unprocessable Entity", serverSentence);
      },
    });
    mount();

    const input = (await screen.findByPlaceholderText("Add one durable fact…")) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "one fact too many" } });
    fireEvent.click(screen.getByText("Add"));

    expect(await screen.findByText(serverSentence)).toBeTruthy();
    expect(input.value).toBe("one fact too many"); // not cleared — the user can trim, not retype
  });
});
