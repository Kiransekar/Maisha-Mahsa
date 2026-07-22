// WhatsApp brief/alert templates (WS7.9). STRINGS ONLY. Sending a WhatsApp message (Business
// API, Twilio, whatever) is external send infra and is explicitly Human's job — nothing in this
// file talks to a network. It exists so the copy is written once, in the product's voice
// (docs/BRAND_THEME.md — flat declaratives, name the statute/domain, exact numbers, never a
// fabricated ₹), instead of being improvised ad hoc wherever a message gets composed.
//
// Every message links back into the SPA rather than acting inside WhatsApp. Approval is the
// typed-confirm flow on /approvals (WS7.6) — a WhatsApp "quick reply" that approved something
// directly would bypass that gate, so these templates deliberately only ever deep-link to a
// screen the user still has to confirm in, never a button that decides anything.

export type DailyBriefVars = {
  ownerName: string;
  asOf: string;
  /** Already formatted at the call site via lib/money.ts (inr()) — never format money here. */
  cashLabel: string;
  needsYouCount: number;
  troubleCount: number;
  /** App origin, e.g. "https://app.maisha-mahsa.example" — no trailing slash. */
  appUrl: string;
};

export function dailyBriefMessage(v: DailyBriefVars): string {
  return [
    `Maisha·Mahsa — ${v.asOf}`,
    `Hi ${v.ownerName}. Cash: ${v.cashLabel}.`,
    `${v.needsYouCount} item(s) need your sign-off · ${v.troubleCount} deadline/risk in view.`,
    `Open Today: ${v.appUrl}/today`,
  ].join("\n");
}

export type ApprovalAlertVars = {
  domain: string;
  /** e.g. "3 figures recomputed, all verified" — plain language, no adjectives standing in for a number. */
  headline: string;
  /** inrOrPending() output at the call site — "—" is a valid, honest value here, never "₹0". */
  amountLabel: string;
  appUrl: string;
};

export function approvalAlertMessage(v: ApprovalAlertVars): string {
  return [
    `${v.domain}: ${v.headline}`,
    `Amount: ${v.amountLabel}`,
    `Review and confirm in the app — WhatsApp cannot approve this: ${v.appUrl}/approvals`,
  ].join("\n");
}

export type TroubleAlertVars = {
  what: string;
  when: string;
  /** "₹ impact not yet known — we don't guess" is a valid, honest value here (Today.tsx §invariant 2). */
  consequenceLabel: string;
  appUrl: string;
};

export function troubleAlertMessage(v: TroubleAlertVars): string {
  return [
    `Trouble radar — ${v.what}`,
    `${v.when}. ${v.consequenceLabel}.`,
    `Open: ${v.appUrl}/today`,
  ].join("\n");
}
