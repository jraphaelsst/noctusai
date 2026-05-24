/**
 * Methodology hook — the synthesized methodology document (if available).
 *
 * Canonical `{ data, loading, error, reload }` shape. A 404 / failure
 * degrades to the typed "unavailable" shape so the page renders an empty
 * state rather than crashing.
 */
import { useCallback, useEffect, useState } from "react";

import { getMethodology, type Methodology } from "@/lib/api";

const UNAVAILABLE: Methodology = {
  available: false,
  markdown: null,
  modules: [],
};

export function useMethodology(): {
  data: Methodology;
  loading: boolean;
  error: Error | null;
  reload: () => void;
} {
  const [data, setData] = useState<Methodology>(UNAVAILABLE);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);
  const [tick, setTick] = useState<number>(0);

  const reload = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);

    getMethodology()
      .then((resp) => {
        if (!alive) return;
        setData(resp ?? UNAVAILABLE);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setData(UNAVAILABLE);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [tick]);

  return { data, loading, error, reload };
}
