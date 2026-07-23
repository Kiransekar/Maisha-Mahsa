// First-run onboarding (WS7.8): GSTIN -> bank CSV -> the first figure. Target: under 15 minutes
// to the payoff moment (research T8 + anti-pattern #8 — a migration that stalls or paywalls a step
// is the top complaint; Zoho's stuck-2-months wizard is the thing NOT to build).
//
// Every step is honest about its own state:
//   · step 1 (GSTIN) is pure client-side format validation — there is no endpoint yet to prefill
//     or persist a filer GSTIN (grep confirms no route reads/writes `settings.company_gstin`),
//     so this step says exactly that instead of faking a prefill. See wiring_needed in the ticket.
//   · step 2 (bank) reuses the REAL treasury endpoints (POST /api/treasury/accounts, POST
//     /api/treasury/accounts/{id}/import) — no bespoke onboarding-only backend.
//   · step 3 is the payoff: GET /api/domains/treasury, the SAME assembler the Treasury hub page
//     renders, so the state shown here is not a special onboarding-only fabrication.
//
// PREVIEW-THEN-CONFIRM (T3 / invariant 4) for step 2's CSV is `BankCsvImport`
// (components/BankCsvImport.tsx) — the SAME component the treasury domain screen re-import uses
// (P0-5), so the dry-run parser and the preview cannot fork between the two call sites. This file
// only owns the GSTIN step, the account-create step, and the step-3 payoff figure.
//
// A step that fails shows the server's real message and stays on that step (retry-safe) — never
// silently resets progress, never a blank panel (invariant 7, reusing ErrorState like Inbox.tsx).

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useTraceId } from "../lib/trace";
import {
  VerifiedNumber,
  isRestricted,
  type RestrictedField,
  type VerifyState,
} from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { BankCsvImport } from "../components/BankCsvImport";
import { TallyEmpty, TallyImport } from "../components/TallyImport";
import { Header, H2, Empty, MahsaDownBanner } from "./Today";
import { honestState, type DomainData, type Figure } from "./Domain";
import { DpdpNoticeCard } from "./Settings";

// Re-exported so callers (and Onboarding.test.ts) keep importing the CSV dry-run logic from this
// file's historical location, without a second copy of it existing here.
export {
  inrPrecise,
  parseCsvAmount,
  parseCsvDate,
  previewStatement,
  splitCsvRows,
} from "../components/BankCsvImport";

// ---- pure logic (tested in Onboarding.test.ts) ----------------------------------------------

const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

/** 15-char GSTIN format only — this is a format check, not a real GSTN lookup (none is wired). */
export function validateGstin(raw: string): { valid: boolean; error: string | null } {
  const v = raw.trim().toUpperCase();
  if (v === "") return { valid: false, error: "GSTIN is required." };
  if (v.length !== 15) return { valid: false, error: `Must be 15 characters — got ${v.length}.` };
  if (!GSTIN_RE.test(v)) return { valid: false, error: "Doesn't match the GSTIN format." };
  return { valid: true, error: null };
}

/** Rupees (as typed) -> integer paise. Blank = 0 (opening balance is optional). Invalid input
 * returns null rather than silently defaulting to 0 — a typo should not become a fabricated
 * opening balance (invariant 4: no invented rupee value). */
export function rupeesToPaise(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return 0;
  const n = Number(trimmed);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * 100);
}

/** The payoff figure: the first one Mahsa has actually recomputed, else the first honest one —
 * never an arbitrary pick that happens to look verified. T11: a RestrictedField has no value —
 * it can never be the payoff figure, so restricted entries are skipped, not rendered blank. */
export function pickFirstFigure(
  figures: (Figure | RestrictedField)[],
  mahsaUp: boolean,
): Figure | null {
  const visible = figures.filter((f): f is Figure => !isRestricted(f));
  if (visible.length === 0) return null;
  const verified = visible.find((f) => honestState(f.state, mahsaUp) === "verified");
  return verified ?? visible[0];
}

/** Step 3's heading must describe the figure that is ACTUALLY on screen. `pickFirstFigure` falls
 * back to an unverified figure when nothing is verified, and an unconditional "Your first verified
 * figure" would then assert a ✓ in larger type than the ◐ chip beside it can retract. */
export function figureHeading(state: VerifyState | null): string {
  if (state === "verified") return "Your first verified figure";
  if (state === "honest_pending") return "Your first figure — Mahsa hasn't sealed it yet";
  if (state === "unbacked") return "Your first figure — unbacked";
  return "Your first figure";
}

// ---- component ---------------------------------------------------------------------------

type Step = 1 | 2 | 3 | 4;

const STEP_LABEL: Record<Step, string> = {
  1: "GSTIN",
  2: "Tally books",
  3: "Bank statement",
  4: "First figure",
};

export function Onboarding() {
  const [step, setStep] = useState<Step>(1);

  // Step 1 — pure client-side, nothing written yet.
  const [gstin, setGstin] = useState("");
  const gstinCheck = validateGstin(gstin);

  // Step 2 — real writes.
  const [bankName, setBankName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [ifsc, setIfsc] = useState("");
  const [opening, setOpening] = useState("");
  const [accountId, setAccountId] = useState<number | null>(null);
  const openingPaise = rupeesToPaise(opening);

  const accountTrace = useTraceId("onboarding-account");
  const figureTrace = useTraceId("onboarding-figure");

  const createAccount = useMutation({
    mutationFn: (body: {
      bank_name: string;
      account_number: string;
      ifsc: string;
      opening_balance_paise: number;
    }) => api<{ id: number }>("/treasury/accounts", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (res) => setAccountId(res.id),
  });

  // Step 4 — the payoff, only fetched once a statement has actually been imported.
  const domainQuery = useQuery({
    queryKey: ["onboarding-treasury"],
    queryFn: () => api<DomainData>("/domains/treasury"),
    enabled: step === 4,
  });

  const submitBank = () => {
    if (!bankName || !accountNumber || !ifsc || openingPaise === null) return;
    createAccount.mutate({
      bank_name: bankName,
      account_number: accountNumber,
      ifsc,
      opening_balance_paise: openingPaise,
    });
  };

  const figure = domainQuery.data
    ? pickFirstFigure(domainQuery.data.figures, domainQuery.data.mahsa_up)
    : null;
  const figureState =
    figure && domainQuery.data ? honestState(figure.state, domainQuery.data.mahsa_up) : null;

  return (
    <section style={{ maxWidth: 620 }}>
      <Header title="Get started" />
      {/* WS10.1 consent capture point: the in-force DPDP notice (if one is published) is
          surfaced before data entry begins — the SAME card Settings→Privacy renders, so the
          two surfaces cannot disagree. Renders nothing while no notice is published. */}
      <DpdpNoticeCard />
      <div
        style={{
          display: "flex",
          gap: 8,
          marginBottom: 24,
          color: "var(--color-ink-muted)",
          fontSize: 12,
        }}
      >
        {([1, 2, 3, 4] as Step[]).map((s) => (
          <span
            key={s}
            style={{
              padding: "4px 10px",
              borderRadius: 4,
              border: `1px solid ${
                s === step ? "var(--color-border-strong)" : "var(--color-border)"
              }`,
              background: s === step ? "var(--color-surface-sunk)" : "transparent",
              color: s === step ? "var(--color-ink)" : "var(--color-ink-muted)",
              fontWeight: 400,
            }}
          >
            {s}. {STEP_LABEL[s]}
          </span>
        ))}
      </div>

      {step === 1 && (
        <div>
          <H2>Your GSTIN</H2>
          <Empty>
            There is no lookup wired yet to prefill this — Maisha does not have a GSTN
            connection, so nothing here is guessed. Type your 15-character GSTIN below.
          </Empty>
          <input
            className="ident"
            value={gstin}
            onChange={(e) => setGstin(e.target.value.toUpperCase())}
            placeholder="22AAAAA0000A1Z5"
            maxLength={15}
            aria-label="GSTIN"
            style={{
              width: "100%",
              marginTop: 12,
              padding: "10px 12px",
              borderRadius: 4,
              border: "1px solid var(--color-border-strong)",
              background: "var(--color-surface)",
              color: "var(--color-ink)",
              fontSize: 14,
              fontWeight: 400,
            }}
          />
          {gstin && !gstinCheck.valid && (
            <div style={{ color: "var(--color-verify-unbacked)", fontSize: 12, marginTop: 6 }}>
              {gstinCheck.error}
            </div>
          )}
          <div style={{ color: "var(--color-ink-faint)", fontSize: 11, marginTop: 8 }}>
            This is held for this session only — there is no save endpoint for it yet
            (see wiring_needed).
          </div>
          <StepButtons onNext={() => setStep(2)} nextDisabled={!gstinCheck.valid} />
        </div>
      )}

      {/* WS9.1 — the Tally step: optional, skippable, and the SAME parse-report -> mapping ->
          typed-confirm component the /d/ledger screen uses (components/TallyImport.tsx), so the
          migration flow cannot fork. Skipping writes nothing. */}
      {step === 2 && (
        <div>
          <H2>Coming from Tally?</H2>
          <TallyEmpty />
          <div style={{ marginTop: 12 }}>
            <TallyImport traceNamespace="onboarding-tally" />
          </div>
          <StepButtons
            onNext={() => setStep(3)}
            nextLabel="Continue"
            onBack={() => setStep(1)}
          />
          <div style={{ color: "var(--color-ink-faint)", fontSize: 11, marginTop: 8 }}>
            Don't use Tally? Continue — nothing on this step is required.
          </div>
        </div>
      )}

      {step === 3 && (
        <div>
          <H2>Bank account</H2>
          {accountId === null ? (
            <>
              <Field label="Bank name" value={bankName} onChange={setBankName} />
              <Field label="Account number" value={accountNumber} onChange={setAccountNumber} />
              <Field label="IFSC" value={ifsc} onChange={setIfsc} mono />
              <Field
                label="Opening balance (₹, optional)"
                value={opening}
                onChange={setOpening}
                placeholder="0"
              />
              {opening && openingPaise === null && (
                <div style={{ color: "var(--color-verify-unbacked)", fontSize: 12 }}>
                  Not a valid amount.
                </div>
              )}
              {/* A failed account-create is a WRITE: the row may or may not have been committed
                  before the response failed, so read copy ("nothing was changed") would be a
                  claim we cannot make. `committed` is deliberately not passed — the server
                  reported no count, and we do not invent one. */}
              {createAccount.isError && (
                <ErrorState
                  error={createAccount.error}
                  traceId={accountTrace}
                  operation="write"
                  onRetry={() => createAccount.reset()}
                />
              )}
              <StepButtons
                onNext={submitBank}
                nextLabel={createAccount.isPending ? "Creating…" : "Create account"}
                nextDisabled={
                  !bankName || !accountNumber || !ifsc || openingPaise === null || createAccount.isPending
                }
                onBack={() => setStep(2)}
              />
            </>
          ) : (
            <>
              <div style={{ color: "var(--color-ink-muted)", fontSize: 13, marginBottom: 12 }}>
                Account created. Choose your bank statement CSV — you'll see exactly what it
                contains before anything is imported. Nothing is written until you confirm.
              </div>
              <BankCsvImport
                accountId={accountId}
                traceNamespace="onboarding-import"
                footer={() => (
                  <StepButtons onNext={() => setStep(4)} nextLabel="See your first figure" />
                )}
              />
              <div style={{ marginTop: 12 }}>
                <button
                  onClick={() => setStep(2)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--color-ink-muted)",
                    fontSize: 12,
                    fontFamily: "inherit",
                    cursor: "pointer",
                    padding: 0,
                  }}
                >
                  ← Back
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {step === 4 && (
        <div>
          <H2>{figureHeading(figureState)}</H2>
          {domainQuery.isLoading && (
            <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>Loading…</p>
          )}
          {domainQuery.error && (
            <ErrorState
              error={domainQuery.error}
              traceId={figureTrace}
              onRetry={() => void domainQuery.refetch()}
            />
          )}
          {domainQuery.data && !domainQuery.data.mahsa_up && <MahsaDownBanner />}
          {domainQuery.data && figure && figureState && (
            <>
              <VerifiedNumber
                label={figure.label}
                value={figure.value}
                state={figureState}
                asOf={domainQuery.data.as_of}
              />
              <div style={{ marginTop: 20 }}>
                <Link
                  to="/d/treasury"
                  style={{
                    color: "var(--color-accent)",
                    fontSize: 13,
                    textDecoration: "none",
                  }}
                >
                  Go to the Treasury hub →
                </Link>
              </div>
            </>
          )}
          {domainQuery.data && !figure && (
            <Empty>
              The import completed, but Treasury published no figures on this response. From here we
              can't tell whether they simply haven't been computed yet or whether no figure source
              is registered for this domain — so we won't assert either. Open the Treasury hub,
              which reads the same endpoint, or send us this reference:{" "}
              <span className="ident">{figureTrace}</span>.
            </Empty>
          )}
        </div>
      )}
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: "block", fontSize: 12, color: "var(--color-ink-muted)", marginBottom: 4 }}>
        {label}
        <input
          className={mono ? "ident" : undefined}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          style={{
            width: "100%",
            marginTop: 4,
            padding: "9px 12px",
            borderRadius: 4,
            border: "1px solid var(--color-border-strong)",
            background: "var(--color-surface)",
            color: "var(--color-ink)",
            fontSize: 14,
            fontWeight: 400,
          }}
        />
      </label>
    </div>
  );
}

function StepButtons({
  onNext,
  onBack,
  nextDisabled,
  nextLabel = "Next",
}: {
  onNext: () => void;
  onBack?: () => void;
  nextDisabled?: boolean;
  nextLabel?: string;
}) {
  return (
    <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
      {onBack && (
        <button
          onClick={onBack}
          style={{
            background: "transparent",
            border: "1px solid var(--color-border-strong)",
            color: "var(--color-ink)",
            padding: "8px 16px",
            borderRadius: 4,
            fontSize: 13,
            fontWeight: 400,
            fontFamily: "inherit",
            cursor: "pointer",
          }}
        >
          Back
        </button>
      )}
      <button
        onClick={onNext}
        disabled={nextDisabled}
        style={{
          background: "var(--color-accent)",
          color: "var(--color-on-accent)",
          border: "none",
          padding: "8px 16px",
          borderRadius: 4,
          fontSize: 13,
          fontWeight: 400,
          fontFamily: "inherit",
          cursor: nextDisabled ? "not-allowed" : "pointer",
          opacity: nextDisabled ? 0.5 : 1,
        }}
      >
        {nextLabel}
      </button>
    </div>
  );
}
