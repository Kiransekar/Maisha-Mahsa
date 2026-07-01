/**
 * Faithfulness check: every expected value here was produced by the Python
 * reference (api/app/domains/vault/vault_calc.py). If the TS port drifts, this fails.
 */
import * as v from './vault.calc';

describe('vault.calc — parity with Python reference', () => {
  it('sha256 content hash', () => {
    expect(v.sha256Hex('hello')).toBe(
      '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',
    );
  });

  it('retention class', () => {
    expect(v.retentionClass('invoice')).toBe('statutory');
    expect(v.retentionClass('cap_table')).toBe('permanent');
    expect(v.retentionClass('random')).toBe('operational');
  });

  it('retention until (7y / 3y / permanent, leap clamp)', () => {
    expect(v.retentionUntil('2024-05-15', 'invoice')).toBe('2031-05-15');
    expect(v.retentionUntil('2024-05-15', 'random')).toBe('2027-05-15');
    expect(v.retentionUntil('2024-05-15', 'cap_table')).toBeNull();
    expect(v.retentionUntil('2024-02-29', 'invoice')).toBe('2031-02-28');
  });

  it('classify (hint wins; statutory before permanent)', () => {
    expect(v.classify('foo.pdf', 'bill')).toBe('bill');
    expect(v.classify('my_invoice_2024.pdf')).toBe('invoice');
    expect(v.classify('share-certificate.pdf')).toBe('certificate');
    expect(v.classify('vacation.jpg')).toBe('other');
  });

  it('find duplicates (groups with >1 id)', () => {
    const docs = [
      { id: 'a', sha256: 'h1' },
      { id: 'b', sha256: 'h1' },
      { id: 'c', sha256: 'h2' },
    ];
    expect(v.findDuplicates(docs)).toEqual({ h1: ['a', 'b'] });
  });

  it('search (case-insensitive over name/ocr/tags)', () => {
    const docs = [
      { id: '1', file_name: 'Invoice ABC', ocr_text: 'total 500', tags: 'urgent' },
      { id: '2', file_name: 'other', ocr_text: 'nothing', tags: null },
    ];
    expect(v.search(docs, 'ABC').map((d) => d.id)).toEqual(['1']);
    expect(v.search(docs, '500').map((d) => d.id)).toEqual(['1']);
  });

  it('integrity verification', () => {
    const stored = v.sha256Hex('hello');
    expect(v.verifyIntegrity(stored, 'hello')).toBe(true);
    expect(v.verifyIntegrity(stored, 'world')).toBe(false);
  });

  it('retention overdue + auto-archive', () => {
    expect(v.isRetentionOverdue('2020-01-01', '2024-01-01')).toBe(true);
    expect(v.isRetentionOverdue('2030-01-01', '2024-01-01')).toBe(false);
    expect(v.isRetentionOverdue(null, '2024-01-01')).toBe(false);
    const docs = [
      { id: 'x', retention_until: '2020-01-01' },
      { id: 'y', retention_until: '2030-01-01' },
      { id: 'z', retention_until: null },
    ];
    expect(v.toArchive(docs, '2024-01-01')).toEqual(['x']);
  });

  it('RBAC permissions + access checks', () => {
    expect(v.rolePermissions('owner').sort()).toEqual([
      'delete',
      'export',
      'manage_access',
      'read',
      'write',
    ]);
    expect(v.rolePermissions('nope')).toEqual([]);
    expect(v.documentSensitivity('board_resolution')).toBe('restricted');
    expect(v.documentSensitivity('invoice')).toBe('internal');
    expect(v.canAccess('owner', 'delete', 'restricted')).toBe(true);
    expect(v.canAccess('viewer', 'delete', 'public')).toBe(false);
    expect(v.canAccess('accountant', 'read', 'restricted')).toBe(false);
    expect(v.canAccess('accountant', 'read', 'confidential')).toBe(true);
    expect(v.canAccess('viewer', 'read', 'confidential')).toBe(false);
  });

  it('vault health metrics snapshot', () => {
    const docs = [
      { id: 'a', sha256: 'h1', retention_until: '2020-01-01' },
      { id: 'b', sha256: 'h1', retention_until: '2030-01-01' },
      { id: 'c', sha256: 'h2', retention_until: null },
    ];
    expect(v.buildMetrics(docs, '2024-01-01')).toEqual({
      documents_count: 3,
      duplicate_groups: 1,
      retention_overdue: 1,
      integrity_failures: 0,
    });
  });
});
