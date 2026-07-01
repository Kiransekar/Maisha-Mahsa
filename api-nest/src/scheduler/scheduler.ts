/**
 * Pure scheduling math for the daily jobs (PRD Layer 6). Faithful port of api/app/scheduler.py.
 * No IO, no global clock — `now` is injected so it is fully testable. The brief fires at a local
 * wall-clock time (e.g. 8pm IST), computed against the configured timezone.
 *
 * Uses Intl for the tz offset (no dep). Single-pass offset resolution matches Python zoneinfo's
 * default fold=0 (a non-existent spring-forward local time takes the pre-transition offset).
 */

/** ms to add to a UTC instant to get local wall-clock in `tz` (local = utc + offset). */
function tzOffsetMs(instant: number, tz: string): number {
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone: tz,
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const p: Record<string, number> = {};
  for (const { type, value } of dtf.formatToParts(new Date(instant))) {
    if (type !== 'literal') p[type] = Number(value);
  }
  // Intl renders 24:00 as hour "24" at midnight for some zones; normalize.
  const hour = p.hour === 24 ? 0 : p.hour;
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, hour, p.minute, p.second);
  return asUtc - instant;
}

/** The next UTC instant at which local `hour:minute` in `tz` occurs (today if still ahead, else
 * tomorrow). `nowUtc` is a Date (a UTC instant). Returns a Date. */
export function nextRun(nowUtc: Date, opts: { hour: number; minute?: number; tz?: string }): Date {
  const minute = opts.minute ?? 0;
  const tz = opts.tz ?? 'Asia/Kolkata';
  const now = nowUtc.getTime();

  // now's local wall-clock components in tz.
  const localNow = now + tzOffsetMs(now, tz);
  const d = new Date(localNow);
  let y = d.getUTCFullYear();
  let mo = d.getUTCMonth();
  let day = d.getUTCDate();

  // Build target = today at hour:minute local; if it's already past, roll to tomorrow.
  const targetLocalToday = Date.UTC(y, mo, day, opts.hour, minute, 0);
  let targetLocal = targetLocalToday;
  if (targetLocalToday <= localNow) {
    targetLocal = Date.UTC(y, mo, day + 1, opts.hour, minute, 0); // date math handles month rollover
  }

  // Convert the target local wall-clock back to a UTC instant (single pass; fold=0 semantics).
  const offset = tzOffsetMs(targetLocal, tz);
  return new Date(targetLocal - offset);
}

export function secondsUntilNext(nowUtc: Date, opts: { hour: number; minute?: number; tz?: string }): number {
  return (nextRun(nowUtc, opts).getTime() - nowUtc.getTime()) / 1000;
}
