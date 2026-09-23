/**
 * `GET /api/website/plans` — client-only fetch (no live DB access at build
 * time, so pricing numbers cannot be prerendered; contract §3/§07 Pricing).
 *
 * Follows the two-signal loading contract (`KB § PATTERNS/frontend/
 * lying-loading-state.md`): `showSkeleton = isPending && !data`,
 * `isRefreshing = isFetching && !!data`. There is no user-keyed refetch here
 * (plans are global, not per-visitor), so `placeholderData` doesn't apply.
 */
import { useEffect, useState } from "react";
import { fetchPlans, type PlanRow } from "../lib/api";

export interface UsePlansResult {
  data: PlanRow[] | null;
  isPending: boolean;
  isFetching: boolean;
  error: string | null;
  showSkeleton: boolean;
  isRefreshing: boolean;
}

export function usePlans(): UsePlansResult {
  const [data, setData] = useState<PlanRow[] | null>(null);
  const [isPending, setIsPending] = useState(true);
  const [isFetching, setIsFetching] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsFetching(true);
    fetchPlans()
      .then((plans) => {
        if (cancelled) return;
        setData(plans);
        setError(null);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
      })
      .finally(() => {
        if (cancelled) return;
        setIsPending(false);
        setIsFetching(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return {
    data,
    isPending,
    isFetching,
    error,
    showSkeleton: isPending && !data,
    isRefreshing: isFetching && !!data,
  };
}
