/**
 * KB search hook — query the vector knowledge base on demand.
 *
 * Unlike the catalog hooks this does NOT fetch on mount; the caller
 * triggers `run(query)` from the search box. State exposes the last
 * response (or null before the first search) + a `searched` flag so the
 * page can distinguish "no search yet" from "searched, zero results".
 */
import { useCallback, useState } from "react";

import { searchKb, type SearchResponse } from "@/lib/api";

export function useSearch(k = 8): {
  data: SearchResponse | null;
  loading: boolean;
  error: Error | null;
  searched: boolean;
  run: (query: string) => Promise<void>;
} {
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);
  const [searched, setSearched] = useState<boolean>(false);

  const run = useCallback(
    async (query: string) => {
      const q = query.trim();
      if (!q) return;
      setLoading(true);
      setError(null);
      setSearched(true);
      try {
        const resp = await searchKb(q, k);
        setData(resp ?? { query: q, configured: false, results: [] });
      } catch (err: unknown) {
        setError(err instanceof Error ? err : new Error(String(err)));
        setData({ query: q, configured: false, results: [] });
      } finally {
        setLoading(false);
      }
    },
    [k],
  );

  return { data, loading, error, searched, run };
}
