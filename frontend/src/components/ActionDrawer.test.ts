// P0-2 — the load-bearing branch of the action drawer: preview-then-confirm ORDERING.
//
// Which mutation each test kills (INVARIANT 9 — no silent mutation):
//   · commitPayload returning a body for an un-previewed drawer → "no commit without preview"
//     fails. That IS the preview gate; delete it and the drawer becomes a one-click write.
//   · commitPayload reading the live inputs instead of the server's normalized echo → the
//     "commits the PREVIEWED values" test fails (edit-after-preview would silently commit
//     values the user never saw previewed).
//   · editField keeping the preview alive across an edit → the invalidation test fails.

import { describe, expect, it } from "vitest";
import {
  addRow,
  chordAction,
  commitPayload,
  controlType,
  editField,
  emptyRow,
  enterAdvance,
  figureRow,
  initialValues,
  isConfirmKey,
  lineEnterAdvance,
  parseLines,
  setCell,
  type ActionPreviewData,
  type DrawerPhase,
} from "./ActionDrawer";
import type { ActionSpec, FieldSpec, Figure } from "../routes/Domain";

const spec: ActionSpec = {
  key: "create-account",
  label: "Create account",
  fields: [
    { name: "code", label: "Account code", type: "text", required: true, placeholder: "1000", options: [] },
    { name: "name", label: "Name", type: "text", required: true, placeholder: "Cash", options: [] },
    { name: "account_type", label: "Type", type: "select", required: true, placeholder: "", options: ["asset", "liability"] },
  ],
};

const preview: ActionPreviewData = {
  domain: "ledger",
  key: "create-account",
  committed: false,
  normalized: { code: "1000", name: "Cash", account_type: "asset" },
  will_create: "Account 1000 — Cash created.",
  figures: [],
  preview_token: "tok-abc",
};

describe("the form is derived from the schema", () => {
  it("initialValues has exactly one slot per schema field", () => {
    expect(Object.keys(initialValues(spec)).sort()).toEqual(["account_type", "code", "name"]);
    expect(Object.values(initialValues(spec)).every((v) => v === "")).toBe(true);
  });

  it("controlType maps the backend types and falls to text on anything unknown", () => {
    expect(controlType("number")).toBe("number");
    expect(controlType("date")).toBe("date");
    expect(controlType("select")).toBe("select");
    expect(controlType("text")).toBe("text");
    expect(controlType("richtext-from-the-future")).toBe("text"); // never a crash, never a guess
  });
});

describe("preview-then-confirm ordering is structural", () => {
  it("NO commit body exists without a live preview — the preview gate itself", () => {
    const editing: DrawerPhase = { step: "editing", values: { code: "1000" } };
    expect(commitPayload(editing)).toBeNull();
    const committed: DrawerPhase = {
      step: "committed",
      values: {},
      result: {
        domain: "ledger", key: "create-account", committed: true,
        created: "done", normalized: {}, after_figures: [],
      },
    };
    expect(commitPayload(committed)).toBeNull(); // no double-fire from the success panel
  });

  it("a commit sends the SERVER's previewed echo + token, never the live inputs", () => {
    // Live inputs deliberately differ from the preview echo: the echo must win.
    const previewed: DrawerPhase = {
      step: "previewed",
      values: { code: "9999", name: "Slush fund", account_type: "asset" },
      preview,
    };
    expect(commitPayload(previewed)).toEqual({
      values: { code: "1000", name: "Cash", account_type: "asset" },
      preview_token: "tok-abc",
    });
  });

  it("editing ANY field drops the preview — its token no longer describes the screen", () => {
    const previewed: DrawerPhase = { step: "previewed", values: preview.normalized, preview };
    const after = editField(previewed, "name", "Cash reserve");
    expect(after.step).toBe("editing");
    expect(after.values.name).toBe("Cash reserve");
    expect(commitPayload(after)).toBeNull(); // and therefore no commit until re-previewed
  });

  it("after a commit, typing starts a fresh form, not a mutation of the committed one", () => {
    const committed: DrawerPhase = {
      step: "committed",
      values: {},
      result: {
        domain: "ledger", key: "create-account", committed: true,
        created: "done", normalized: { code: "1000" }, after_figures: [],
      },
    };
    expect(editField(committed, "code", "2000")).toEqual({
      step: "editing",
      values: { code: "2000" },
    });
  });
});

describe("keyboard flow (Altitude-2 groundwork)", () => {
  it("Enter advances fields and the LAST field fires the preview, never a commit", () => {
    expect(enterAdvance(0, 3)).toBe(1);
    expect(enterAdvance(1, 3)).toBe(2);
    expect(enterAdvance(2, 3)).toBe("preview");
  });

  it("only Cmd/Ctrl+Enter is the confirm chord — plain Enter can never confirm", () => {
    expect(isConfirmKey({ key: "Enter", metaKey: true, ctrlKey: false })).toBe(true);
    expect(isConfirmKey({ key: "Enter", metaKey: false, ctrlKey: true })).toBe(true);
    expect(isConfirmKey({ key: "Enter", metaKey: false, ctrlKey: false })).toBe(false);
    expect(isConfirmKey({ key: "a", metaKey: true, ctrlKey: false })).toBe(false);
  });

  it("the chord previews the form and confirms the preview — never a confirm while editing", () => {
    // Kills: mapping "editing" to "confirm", which would let the chord skip the preview step.
    expect(chordAction("editing")).toBe("preview");
    expect(chordAction("previewed")).toBe("confirm");
    expect(chordAction("committed")).toBe("none"); // no double-fire from the success panel
  });
});

// ── P0-3 — lines fields (multi-row entry: invoice items, journal lines) ─────────

const journalCols: FieldSpec[] = [
  { name: "account_id", label: "Account ID", type: "number", required: true, placeholder: "1", options: [] },
  { name: "debit", label: "Debit (₹)", type: "number", required: false, placeholder: "0", options: [] },
  { name: "credit", label: "Credit (₹)", type: "number", required: false, placeholder: "0", options: [] },
];

const linesSpec: ActionSpec = {
  key: "journal-entry",
  label: "Journal entry",
  fields: [
    { name: "entry_date", label: "Entry date", type: "date", required: true, placeholder: "", options: [] },
    { name: "lines", label: "Lines", type: "lines", required: true, placeholder: "", options: [], columns: journalCols },
  ],
};

describe("lines fields (WS7.4: Enter drives the whole grid, arrays add rows)", () => {
  it("a lines field starts as ONE empty row in canonical JSON, scalars stay empty strings", () => {
    const v = initialValues(linesSpec);
    expect(v.entry_date).toBe("");
    expect(parseLines(v.lines)).toEqual([{ account_id: "", debit: "", credit: "" }]);
  });

  it("Enter advances cell → row → GROWS the array from the last cell", () => {
    // Kills: Enter on the last cell doing nothing (the operator would need the mouse).
    expect(lineEnterAdvance(0, 0, 2, 3)).toEqual({ row: 0, col: 1 });
    expect(lineEnterAdvance(0, 2, 2, 3)).toEqual({ row: 1, col: 0 });
    expect(lineEnterAdvance(1, 2, 2, 3)).toBe("addRow");
  });

  it("setCell writes through the JSON value and materializes phantom rows", () => {
    // Kills: editing the visually-rendered empty row losing the keystroke because the
    // row did not exist in the value yet.
    const afterEdit = setCell("", journalCols, 0, "debit", "100");
    expect(parseLines(afterEdit)).toEqual([{ account_id: "", debit: "100", credit: "" }]);
    const afterAdd = addRow(afterEdit, journalCols);
    expect(parseLines(afterAdd)).toHaveLength(2);
    expect(parseLines(afterAdd)[1]).toEqual({ account_id: "", debit: "", credit: "" });
  });

  it("garbage in the value parses to [] — never a crash, never invented rows", () => {
    expect(parseLines("not json")).toEqual([]);
    expect(parseLines('{"a":1}')).toEqual([]);
    expect(emptyRow(journalCols)).toEqual({ account_id: "", debit: "", credit: "" });
  });

  it("editing a lines value drops a held preview like any other field", () => {
    const previewed: DrawerPhase = { step: "previewed", values: preview.normalized, preview };
    const after = editField(previewed, "lines", '[{"debit":"100"}]');
    expect(after.step).toBe("editing");
    expect(commitPayload(after)).toBeNull();
  });
});

describe("preview figures render from the SERVER payload, never client math (§0.4)", () => {
  const tdsFigure: Figure = {
    key: "tds_on_payment",
    label: "TDS deducted",
    value: "₹6,000.00",
    raw: 600000,
    state: "verified",
  };

  it("the TDS badge row is the payload verbatim: value untouched, state through the gate", () => {
    // Kills: re-formatting/recomputing the amount client-side, or defaulting state to ✓.
    const seen: string[] = [];
    const badge = (s: string) => {
      seen.push(s);
      return s === "verified" ? ("verified" as const) : ("unbacked" as const);
    };
    const row = figureRow(tdsFigure, badge);
    expect(row.value).toBe("₹6,000.00"); // exact server string — never re-grouped or re-computed client-side
    expect(row.state).toBe("verified");
    expect(seen).toEqual(["verified"]); // the state was DERIVED from the payload state
  });

  it("an unknown payload state cannot become a ✓ — it is whatever the gate says", () => {
    const row = figureRow({ ...tdsFigure, state: "who-knows" }, () => "unbacked" as const);
    expect(row.state).toBe("unbacked");
  });
});
