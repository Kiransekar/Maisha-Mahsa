// The single, swappable seam between the SPA and the backend. Points at the CORRECT FastAPI
// (all statutory fixes + the recompute gate) via the dev proxy today; flip VITE_API_BASE to the
// NestJS API once it is brought to paisa-parity (WS4.6) — no component changes required.
//
// This is also the ONLY place the Better Auth JWT is attached, which is why every route gets it
// for free and no route can forget it (mirroring the API's own deny-by-default middleware).
import { authHeaders, clearAuthToken } from "./auth";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  status: number;
  /** FastAPI's `{"detail": "..."}` body, when the response had one — the server's OWN words
   *  (e.g. the memory-overflow char count), for callers that must render it verbatim rather
   *  than invent a per-status sentence (MEM.P0-5, §0.4: never re-derive what the server said). */
  detail?: string;
  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    credentials: "include",
    // `...init` FIRST, then `headers` — reversed (as it was), a caller passing `init.headers`
    // replaced the whole merged object, dropping content-type AND the Authorization header. That
    // silently un-authenticated every mutation, which all pass a body and thus headers.
    ...init,
    headers: {
      "content-type": "application/json",
      ...(await authHeaders()),
      ...(init?.headers || {}),
    },
  });
  // The API has rejected this token (expired, revoked, or org/role no longer valid). Drop it so
  // the next call mints a fresh one instead of replaying a credential we know is dead.
  if (res.status === 401) clearAuthToken();
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && typeof (body as { detail?: unknown }).detail === "string") {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // non-JSON or empty error body — no server detail to carry, statusText still applies
    }
    throw new ApiError(res.status, `${res.status} ${res.statusText}`, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** Authenticated binary fetch (payslip/Form 16 PDFs, ECR files) through the same seam, so a
 *  download can never forget the Authorization header any more than a JSON call can. */
export async function apiBlob(path: string): Promise<Blob> {
  const res = await fetch(`${BASE}/api${path}`, {
    credentials: "include",
    headers: { ...(await authHeaders()) },
  });
  if (res.status === 401) clearAuthToken();
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`);
  return res.blob();
}
