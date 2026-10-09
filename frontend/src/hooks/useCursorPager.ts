import { useCallback, useState } from "react";

/** Keeps a stack of cursors so users can page forward and back through a cursor-paginated list. */
export function useCursorPager() {
  const [stack, setStack] = useState<(string | null)[]>([null]);
  const cursor = stack[stack.length - 1];
  const next = useCallback((nextCursor: string | null) => {
    if (nextCursor) setStack((s) => [...s, nextCursor]);
  }, []);
  const prev = useCallback(() => setStack((s) => (s.length > 1 ? s.slice(0, -1) : s)), []);
  const reset = useCallback(() => setStack([null]), []);
  return { cursor, page: stack.length, next, prev, reset, hasPrev: stack.length > 1 };
}
