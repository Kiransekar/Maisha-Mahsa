import { consolidate } from './memory.service';

describe('memory consolidation (dedupe)', () => {
  it('drops empty lines and trims', () => {
    expect(consolidate('  a \n\n  b  \n')).toBe('a\nb');
  });
  it('dedupes case-insensitively, ignoring bullet prefixes, first occurrence wins', () => {
    expect(consolidate('- Conservative appetite\nconservative appetite\n* Conservative Appetite')).toBe('- Conservative appetite');
  });
  it('preserves distinct lines and their order', () => {
    expect(consolidate('regime: 115BAA\nDPIIT startup\nregime: 115BAA')).toBe('regime: 115BAA\nDPIIT startup');
  });
  it('empty in, empty out', () => {
    expect(consolidate('')).toBe('');
    expect(consolidate('\n  \n')).toBe('');
  });
});
