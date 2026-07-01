/**
 * Document-vault core — pure, deterministic. Faithful port of
 * api/app/domains/vault/vault_calc.py. SHA-256 content hashing (dedup + tamper check),
 * statutory retention policy, classification, full-text search, and RBAC.
 * No money here; no clock read (as-of dates are passed in as ISO strings).
 */
import { createHash } from 'crypto';

// Retention classes (PRD §1.12): statutory 7y, operational 3y, permanent (equity/legal).
export const RETENTION_YEARS: Record<string, number | null> = {
  statutory: 7,
  operational: 3,
  permanent: null,
};

// doc_type -> retention class. Order preserved from the Python literals so classify() is
// deterministic when a name matches more than one key (statutory checked before permanent).
const STATUTORY_TYPES = [
  'invoice',
  'bill',
  'gst_return',
  'tds_return',
  'challan',
  'payslip',
  'form16',
  'contract',
  'certificate',
  'return',
  'ecr',
];
const PERMANENT_TYPES = [
  'share_certificate',
  'cap_table',
  'board_resolution',
  'moa',
  'aoa',
  'incorporation',
];

export function sha256Hex(content: string | Buffer): string {
  return createHash('sha256').update(content).digest('hex');
}

export function retentionClass(docType: string): string {
  if (PERMANENT_TYPES.includes(docType)) return 'permanent';
  if (STATUTORY_TYPES.includes(docType)) return 'statutory';
  return 'operational';
}

/** ISO date until which the document must be retained, or null for permanent records. */
export function retentionUntil(uploadDate: string, docType: string): string | null {
  const years = RETENTION_YEARS[retentionClass(docType)];
  if (years === null) return null;
  const [y, m, d] = uploadDate.split('-').map((x) => parseInt(x, 10));
  const targetYear = y + years;
  // clamp Feb-29 uploads to Feb-28 on the target year (mirrors Python's ValueError fallback)
  const isFeb29 = m === 2 && d === 29;
  const day = isFeb29 && !isLeapYear(targetYear) ? 28 : d;
  return `${targetYear}-${pad2(m)}-${pad2(day)}`;
}

function isLeapYear(y: number): boolean {
  return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
}
function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** Document ids eligible for auto-archive: their retention_until has passed. Permanent
 * records (retention_until null) are never archived. */
export function toArchive(documents: Record<string, any>[], asOf: string): string[] {
  return documents
    .filter((d) => d.retention_until && d.retention_until <= asOf)
    .map((d) => d.id);
}

/** Case-insensitive substring search over file name, OCR text and tags. */
export function search(documents: Record<string, any>[], query: string): Record<string, any>[] {
  const q = query.toLowerCase();
  return documents.filter((doc) => {
    const haystack = ['file_name', 'ocr_text', 'tags']
      .map((f) => String(doc[f] ?? ''))
      .join(' ')
      .toLowerCase();
    return haystack.includes(q);
  });
}

/** True iff the current content still hashes to the stored digest. */
export function verifyIntegrity(storedSha256: string, currentContent: string | Buffer): boolean {
  return sha256Hex(currentContent) === storedSha256;
}

/** Group document ids by content hash; entries with >1 id are duplicates. */
export function findDuplicates(documents: Record<string, any>[]): Record<string, string[]> {
  const byHash: Record<string, string[]> = {};
  for (const doc of documents) {
    (byHash[doc.sha256] ??= []).push(doc.id);
  }
  const out: Record<string, string[]> = {};
  for (const [h, ids] of Object.entries(byHash)) {
    if (ids.length > 1) out[h] = ids;
  }
  return out;
}

/** True if a non-permanent document is past its retention date (eligible for archival). */
export function isRetentionOverdue(retentionUntilIso: string | null, asOf: string): boolean {
  if (retentionUntilIso === null || retentionUntilIso === undefined) return false;
  return retentionUntilIso < asOf; // ISO dates compare lexicographically
}

/** Best-effort doc_type from an explicit hint or the file name keywords. */
export function classify(fileName: string, hint?: string | null): string {
  if (hint) return hint;
  const name = fileName.toLowerCase().replace(/_/g, '').replace(/-/g, '');
  for (const key of [...STATUTORY_TYPES, ...PERMANENT_TYPES]) {
    if (name.includes(key.replace(/_/g, ''))) return key;
  }
  return 'other';
}

// ---- RBAC access control --------------------------------------------------------------

const ROLE_PERMISSIONS: Record<string, string[]> = {
  owner: ['read', 'write', 'delete', 'export', 'manage_access'],
  accountant: ['read', 'write', 'export'],
  auditor: ['read', 'export'],
  viewer: ['read'],
};
const ROLE_RANK: Record<string, number> = { viewer: 0, auditor: 1, accountant: 1, owner: 2 };
const SENSITIVITY_MIN_RANK: Record<string, number> = {
  public: 0,
  internal: 0,
  confidential: 1,
  restricted: 2,
};

const SENSITIVITY_BY_TYPE: Record<string, string> = {
  board_resolution: 'restricted',
  cap_table: 'restricted',
  share_certificate: 'restricted',
  moa: 'confidential',
  aoa: 'confidential',
  incorporation: 'confidential',
  contract: 'confidential',
  payslip: 'confidential',
  form16: 'confidential',
};

export function rolePermissions(role: string): string[] {
  return [...(ROLE_PERMISSIONS[role] ?? [])];
}

/** Map a document type to its access sensitivity (default 'internal'). */
export function documentSensitivity(docType: string): string {
  return SENSITIVITY_BY_TYPE[docType] ?? 'internal';
}

/** RBAC check: the role must grant `action` and out-rank the document sensitivity. */
export function canAccess(role: string, action: string, sensitivity = 'internal'): boolean {
  const perms = ROLE_PERMISSIONS[role];
  if (perms === undefined || !perms.includes(action)) return false;
  return (ROLE_RANK[role] ?? -1) >= (SENSITIVITY_MIN_RANK[sensitivity] ?? 99);
}

/** Vault health signals: duplicate count and retention-overdue count. Integrity failures
 * are detected on access (need file content), so default 0 here. */
export function buildMetrics(
  documents: Record<string, any>[],
  asOf: string,
): Record<string, number> {
  const dupes = findDuplicates(documents);
  const overdue = documents.filter((d) => isRetentionOverdue(d.retention_until, asOf)).length;
  return {
    documents_count: documents.length,
    duplicate_groups: Object.keys(dupes).length,
    retention_overdue: overdue,
    integrity_failures: 0,
  };
}
