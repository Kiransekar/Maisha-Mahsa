/** Parity with api/app/core/money.py (reference values captured from the Python module). */
import { paiseFromRupees, formatInr } from './money';

describe('money — parity with Python Paise', () => {
  it('paiseFromRupees (half-up)', () => {
    expect(paiseFromRupees('150.50')).toBe(15050);
    expect(paiseFromRupees('0.1')).toBe(10);
    expect(paiseFromRupees('12345.67')).toBe(1234567);
    expect(paiseFromRupees('1')).toBe(100);
  });

  it('formatInr (Indian grouping)', () => {
    expect(formatInr(15050)).toBe('₹150.50');
    expect(formatInr(123456700)).toBe('₹12,34,567.00');
    expect(formatInr(-500000)).toBe('-₹5,000.00');
    expect(formatInr(100)).toBe('₹1.00');
    expect(formatInr(0)).toBe('₹0.00');
    expect(formatInr(999)).toBe('₹9.99');
  });
});
