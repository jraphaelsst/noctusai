/**
 * Example hook — placeholder data-fetching hook for the new product.
 *
 * Demonstrates the canonical shape every domain hook follows:
 *
 *   - imports `api` from `@/lib/api` (the local seam, not the seed
 *     boundary directly — keeps tests stable)
 *   - returns `{ data, loading, error, reload }` shape
 *   - typed payload from a Pydantic schema mirror in `app/schemas/`
 *   - cancellation via `AbortController` so unmount mid-fetch doesn't
 *     setState on a dead component
 *
 * Mirrors the canonical real-world shape used by yt-crawler's
 * `useVideos` / `useDashboard` hooks.
 *
 * TODO(new-product): rename `Example` → your domain (`Video`, `Order`,
 * `Goal`, …); replace the placeholder URL + type with your real
 * endpoint; add `useCreateExample` / `useUpdateExample` siblings as
 * needed. Backend mirror lives at `app/routers/example_router.py`.
 */
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";

// ─── Types (mirror backend schemas/example.py) ─────────────────────────
export interface Example {
  id: string;
  org_id: string;
  title: string;
  description: string | null;
  created_at: string;
}

export interface ExampleListResponse {
  items: Example[];
  next_cursor: string | null;
}

// ─── Hook ──────────────────────────────────────────────────────────────
export function useExamples(): {
  data: Example[] | null;
  loading: boolean;
  error: Error | null;
  reload: () => void;
} {
  const [data, setData] = useState<Example[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);
  const [tick, setTick] = useState<number>(0);

  const reload = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    const ctrl = new AbortController();
    let alive = true;
    setLoading(true);
    setError(null);

    api
      .get<ExampleListResponse>("/api/example", { signal: ctrl.signal })
      .then((resp) => {
        if (!alive) return;
        setData(resp.items);
      })
      .catch((err: unknown) => {
        if (!alive || ctrl.signal.aborted) return;
        setError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
      ctrl.abort();
    };
  }, [tick]);

  return { data, loading, error, reload };
}
