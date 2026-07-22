// A stable trace id for a failure, so error-template question 4 ("send us the ID") is answerable.
//
// The first implementation built these inline as `${view}-${Date.now()}` in render, which
// regenerated on every re-render — the id changed while the user was reading it, and matched
// nothing server-side. An untraceable id is a worse answer than admitting we have none.
//
// ponytail: client-generated and correlated by time+view, not a server-issued request id. It is
// enough for support to find the window in the logs. Upgrade path: echo a request id from the
// server (e.g. an X-Request-Id response header) and prefer that when present.

import { useRef } from "react";

function mint(view: string): string {
  const rand = Math.random().toString(36).slice(2, 8);
  return `${view}-${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}-${rand}`;
}

/** Stable for the lifetime of the mounted component — does not change between renders. */
export function useTraceId(view: string): string {
  const ref = useRef<string | null>(null);
  if (ref.current === null) ref.current = mint(view);
  return ref.current;
}
