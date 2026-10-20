/**
 * Local edit buffer over a SERVER row set (Julia v2 content tabs).
 *
 * The buffer is a working copy, never truth: it is seeded from the server answer, and when the
 * server's rows move while the user holds unsaved edits the buffer is NOT overwritten — it raises
 * `serverMoved` (the optimistic-lock conflict, shown as a banner) until the user reloads.
 * `markSaved` re-bases onto what was just written; the following refetch repaints from the server.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { snapshotOf } from "@/hooks/studio/useConteudo";

export function useEditableRows<T extends { id?: string }>(
  items: T[] | undefined,
  isPlaceholderData: boolean,
  resetKey: string,
) {
  const [rows, setRows] = useState<T[]>([]);
  const [base, setBase] = useState<string | null>(null);
  const seededFor = useRef<string | null>(null);
  const serverSnap = items ? snapshotOf(items) : null;
  const dirty = base !== null && snapshotOf(rows) !== base;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  useEffect(() => {
    if (!items || isPlaceholderData || serverSnap === null) return;
    if (seededFor.current === resetKey && dirtyRef.current) return; // keep edits; conflict banner takes over
    setRows(items);
    setBase(serverSnap);
    seededFor.current = resetKey;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `items` identity is covered by serverSnap
  }, [serverSnap, isPlaceholderData, resetKey]);

  const reload = useCallback(() => {
    if (!items) return;
    setRows(items);
    setBase(serverSnap);
  }, [items, serverSnap]);

  const markSaved = useCallback((saved: T[]) => setBase(snapshotOf(saved)), []);

  return {
    rows,
    setRows,
    base: base ?? "",
    dirty,
    serverMoved: dirty && serverSnap !== null && base !== null && serverSnap !== base,
    reload,
    markSaved,
  };
}
