/** Parity with api/app/scheduler.py (reference values captured from the Python module). */
import { nextRun, secondsUntilNext } from './scheduler';

const at = (iso: string) => new Date(iso);

describe('scheduler tz math — parity with Python zoneinfo', () => {
  it('fires today when the local time is still ahead', () => {
    const now = at('2024-05-01T10:00:00Z');
    expect(secondsUntilNext(now, { hour: 20 })).toBe(16200);
    expect(nextRun(now, { hour: 20 }).toISOString()).toBe('2024-05-01T14:30:00.000Z');
  });

  it('rolls to tomorrow when the local time has passed', () => {
    const now = at('2024-05-01T16:00:00Z');
    expect(secondsUntilNext(now, { hour: 20 })).toBe(81000);
    expect(nextRun(now, { hour: 20 }).toISOString()).toBe('2024-05-02T14:30:00.000Z');
  });

  it('handles hour:minute', () => {
    const now = at('2024-01-01T00:00:00Z');
    expect(secondsUntilNext(now, { hour: 8, minute: 30 })).toBe(10800);
  });

  it('spring-forward day (America/New_York) uses fold=0 pre-transition offset', () => {
    const now = at('2024-03-10T04:00:00Z');
    expect(nextRun(now, { hour: 2, minute: 0, tz: 'America/New_York' }).toISOString()).toBe(
      '2024-03-10T07:00:00.000Z',
    );
  });
});
