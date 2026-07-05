/** Request-scoped state (AsyncLocalStorage): correlation id + who is acting (for logs + audit). */
import { AsyncLocalStorage } from 'async_hooks';

export interface RequestState {
  requestId: string;
  sub?: string;
  role?: string;
}

const als = new AsyncLocalStorage<RequestState>();

/** Bind a state object for the remainder of this request's async chain (called from middleware). */
export function enterRequest(state: RequestState): void {
  als.enterWith(state);
}

/** Attach the authenticated user to the current request (called from the guard). Mutates in place. */
export function setRequestUser(user: { sub: string; role: string }): void {
  const s = als.getStore();
  if (s) {
    s.sub = user.sub;
    s.role = user.role;
  } else {
    als.enterWith({ requestId: '-', sub: user.sub, role: user.role });
  }
}

export function currentUser(): { sub?: string; role?: string } | undefined {
  return als.getStore();
}

/** The acting user id for audit, falling back to a system identity for background jobs. */
export function currentUserId(): string {
  return als.getStore()?.sub ?? process.env.MAISHA_DEFAULT_USER_ID ?? 'system';
}

export function currentRequestId(): string {
  return als.getStore()?.requestId ?? '-';
}
