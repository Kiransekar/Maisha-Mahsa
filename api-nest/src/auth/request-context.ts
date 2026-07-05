/** Request-scoped identity (AsyncLocalStorage) so audit entries record *who* acted, not a constant. */
import { AsyncLocalStorage } from 'async_hooks';

export interface RequestUser {
  sub: string;
  role: string;
}

const als = new AsyncLocalStorage<RequestUser>();

/** Set the current user for the remainder of this request's async chain (called from the guard). */
export function setRequestUser(user: RequestUser): void {
  als.enterWith(user);
}

export function currentUser(): RequestUser | undefined {
  return als.getStore();
}

/** The acting user id for audit, falling back to a system identity for background jobs. */
export function currentUserId(): string {
  return als.getStore()?.sub ?? process.env.MAISHA_DEFAULT_USER_ID ?? 'system';
}
