// P1-2 — the honesty gates of the Audit Room's thread/sampling/pack extension.
//
// Repo convention (see Statements.test.tsx): no jsdom/@testing-library — pure functions plus
// renderToStaticMarkup for a REAL React render of the presentational pieces.
//
// What must never happen here:
//   · a respond control enabled for a caller the SERVER said cannot respond (the CA
//     answering its own query is the exact failure WS8.2 built the write-gate to prevent);
//   · pack download links visible to a caller without the export capability;
//   · a resolve offered on a thread that was never answered.

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  PackDownloads,
  SampleResult,
  ThreadCard,
  sampleQueryString,
  threadChip,
  threadGates,
  type CaThread,
  type SampleData,
} from "./AuditRoom";

const thread = (state: string, events = 1): CaThread => ({
  id: 7,
  created_at: "2026-07-01T10:00:00+00:00",
  domain: "ledger",
  entry_ref: "journal:14",
  question: "Support for this entry?",
  state,
  raised_by: "user-ca",
  events: Array.from({ length: events }, (_, i) => ({
    timestamp: `2026-07-0${i + 1}T10:00:00+00:00`,
    event: ["raise", "respond", "resolve"][i] ?? "raise",
    user_id: i === 1 ? "user-accountant" : "user-ca",
    note: i === 0 ? "Support for this entry?" : null,
    doc_id: i === 1 ? "d".repeat(64) : null,
    audit_hash: `${"a".repeat(63)}${i}`,
  })),
});

const card = (t: CaThread, canRespond: boolean, reason: string | null) =>
  renderToStaticMarkup(
    <ThreadCard
      thread={t}
      gates={threadGates(t.state, canRespond, reason)}
      onRespond={() => {}}
      onResolve={() => {}}
      busy={false}
      error={null}
      traceId="t-test"
    />,
  );

describe("threadGates — enabled/disabled comes ONLY from the server's capability verdict", () => {
  it("an answerable thread with the capability offers respond, with no denial reason", () => {
    const g = threadGates("open", true, null);
    expect(g.showRespond).toBe(true);
    expect(g.respondDisabledReason).toBeNull();
  });

  it("without the capability, the SERVER's own reason is shown verbatim — never invented", () => {
    const g = threadGates("open", false, "missing capability: write — responding attaches evidence");
    expect(g.showRespond).toBe(false);
    expect(g.respondDisabledReason).toBe(
      "missing capability: write — responding attaches evidence",
    );
  });

  it("a missing server reason falls to an honest default, NEVER to an enabled control", () => {
    const g = threadGates("open", false, null);
    expect(g.showRespond).toBe(false);
    expect(g.respondDisabledReason).toContain("write");
  });

  it("a resolved thread offers nothing — no respond, no denial, no resolve", () => {
    const g = threadGates("resolved", true, null);
    expect(g.showRespond).toBe(false);
    expect(g.respondDisabledReason).toBeNull();
    expect(g.showResolve).toBe(false);
  });

  it("resolve is offered ONLY on a responded thread (an unanswered query can never resolve)", () => {
    expect(threadGates("open", true, null).showResolve).toBe(false);
    expect(threadGates("responded", true, null).showResolve).toBe(true);
  });
});

describe("ThreadCard — the lifecycle renders, seals visible, controls capability-gated", () => {
  it("open + capable: the respond form renders, and the raise event's chain seal is shown", () => {
    const html = card(thread("open"), true, null);
    expect(html).toContain("Respond with document");
    expect(html).toContain("Vault document id");
    expect(html).toContain("a".repeat(63) + "0"); // the audit-chain seal ref
    expect(html).toContain("journal:14");
  });

  it("open + incapable (the CA itself): disabled control with the server's reason, no form", () => {
    const html = card(thread("open"), false, "missing capability: write — an Accountant answers");
    expect(html).toContain("missing capability: write — an Accountant answers");
    expect(html).toContain("disabled");
    expect(html).not.toContain("Vault document id"); // no live form for the incapable
  });

  it("responded: resolve appears, and the respond event carries its doc + seal refs", () => {
    const html = card(thread("responded", 2), true, null);
    expect(html).toContain("Resolve query");
    expect(html).toContain("d".repeat(64));
    expect(html).toContain("a".repeat(63) + "1");
  });

  it("resolved: no respond, no resolve — the record is read-only", () => {
    const html = card(thread("resolved", 3), true, null);
    expect(html).not.toContain("Respond with document");
    expect(html).not.toContain("Resolve query");
  });

  it("an unknown state renders verbatim, never hidden or upgraded", () => {
    expect(threadChip("weird").label).toBe("weird");
  });
});

describe("PackDownloads — visible ONLY on the server's export capability", () => {
  it("without export, the row does not render AT ALL (hidden, not disabled)", () => {
    expect(renderToStaticMarkup(<PackDownloads canExport={false} />)).toBe("");
  });

  it("with export, both download controls render", () => {
    const html = renderToStaticMarkup(<PackDownloads canExport={true} />);
    expect(html).toContain("Download .zip");
    expect(html).toContain("Download .pdf");
  });
});

describe("sampleQueryString — the spec maps to params exactly", () => {
  it("omits an empty domain (all domains), keeps a given one", () => {
    expect(sampleQueryString({ date_from: "2026-07-01", date_to: "2026-07-31", n: 10, domain: "" })).toBe(
      "date_from=2026-07-01&date_to=2026-07-31&n=10",
    );
    expect(
      sampleQueryString({ date_from: "2026-07-01", date_to: "2026-07-31", n: 5, domain: "gst" }),
    ).toContain("domain=gst");
  });
});

describe("SampleResult — deterministic sample renders honestly", () => {
  const data: SampleData = {
    spec: { domain: "gst", date_from: "2026-07-01", date_to: "2026-07-31", n: 2 },
    seed: "f".repeat(64),
    population: 6,
    sample: [
      {
        voucher_id: 3,
        entry_date: "2026-07-03",
        reference: "V-3",
        description: "voucher 3",
        source: "gst",
        total_debit_paise: 123456789,
        total_credit_paise: 123456789,
        documents: [{ doc_id: "b".repeat(64), file_name: "inv.pdf", doc_type: "invoice" }],
      },
      {
        voucher_id: 5,
        entry_date: "2026-07-05",
        reference: null,
        description: null,
        source: "gst",
        total_debit_paise: 500000,
        total_credit_paise: 500000,
        documents: [],
      },
    ],
  };

  it("shows the seed (determinism is the point), lakh/crore money, and doc bundle refs", () => {
    const html = renderToStaticMarkup(<SampleResult data={data} />);
    expect(html).toContain("f".repeat(64));
    expect(html).toContain("₹12,34,567"); // 123456789 paise, lakh/crore grouped, paise-exact
    expect(html).toContain("89 paise");
    expect(html).toContain("inv.pdf");
    expect(html).toContain("b".repeat(64));
    expect(html).toContain("no vault documents linked"); // honest empty, not a blank cell
  });

  it("an empty sample states it — never a blank table", () => {
    const html = renderToStaticMarkup(<SampleResult data={{ ...data, sample: [] }} />);
    expect(html).toContain("No vouchers in the population match this spec.");
  });
});
