/**
 * Runs hooks — list processing runs + start a new one.
 *
 *   useRuns(pollMs)  → the runs list, refetched on an interval so a
 *                      running job's status flips without a manual reload
 *   startRun(payload) → POST a new run (drive URL or fake/test mode)
 *
 * The list always resolves to an array (empty on failure) so the page
 * renders an empty state rather than reasoning over `undefined`.
 */
import { useCallback, useEffect, useState } from "react";

import {
  createRun,
  listRuns,
  type CreateRunPayload,
  type CreateRunResponse,
  type Run,
} from "@/lib/api";

export function useRuns(pollMs = 4000): {
  data: Run[];
  loading: boolean;
  error: Error | null;
  reload: () => void;
} {
  const [data, setData] = useState<Run[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback(async () => {
    try {
      const resp = await listRuns();
      setData(resp?.runs ?? []);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setData([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    void refresh();
    const id = window.setInterval(() => {
      if (alive) void refresh();
    }, pollMs);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [refresh, pollMs]);

  return { data, loading, error, reload: () => void refresh() };
}

export async function startRun(
  payload: CreateRunPayload,
): Promise<CreateRunResponse> {
  return createRun(payload);
}
