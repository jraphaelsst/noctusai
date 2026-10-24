/**
 * Shared QueryClient configuration.
 *
 * All products use the same defaults: 5 min stale time, 10 min GC,
 * no refetch on window focus, the canonical automatic-retry policy, and a
 * global error toast.
 *
 * Retry policy (`./retry`, owner request 2026-10-21): a query retries ONLY a
 * transient failure (no response / timeout / 408 / 425 / 429 / 5xx), up to
 * 3 times paced 1s → 3s → 9s (a 429/503 `Retry-After` wins when present).
 * A 4xx (401/403/404/422) is never retried — the same request gets the same
 * answer. Once the attempts run out the query is in `error` and the page
 * renders `QueryErrorState` (button → `refetch()` → the same paced attempts
 * again). The toast fires once, after the LAST attempt — never per attempt.
 * Mutations do NOT auto-retry (writes are not idempotent); a mutation opts
 * in with `...autoRetryMutationOptions()`.
 *
 * Per-query opt-out: a query whose `meta.suppressErrorToastStatuses`
 * lists an HTTP status swallows the toast for a rejection at exactly that
 * status — everything else (a genuine 5xx, a network drop) still surfaces
 * loudly. This exists for the "expected 404" shape — a hook whose own
 * `queryFn` deliberately does not retry a 404 because it is a STABLE
 * "not found" state, not a transient failure (e.g. a manually-registered
 * record that was never synced into a mirror) — see
 * `social-wiring`'s `useImovel`/`useImovelRegistro` for the first
 * consumer. It is opt-in and per-status, so every other query keeps
 * today's behaviour unchanged.
 */
import { QueryClient, QueryCache } from '@tanstack/react-query';
import { toast } from 'sonner';

import { ORG_SELECTION_REQUIRED_CODE } from './access';
import { ApiError } from './api';
import { autoRetryDelayMs, shouldAutoRetry } from './retry';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        const suppressed = query.meta?.suppressErrorToastStatuses as
          | number[]
          | undefined;
        if (
          suppressed &&
          error instanceof ApiError &&
          error.status !== null &&
          suppressed.includes(error.status)
        ) {
          return;
        }
        // 409 org_selection_required is an expected state (no org pinned yet):
        // the org picker the api layer reopens already handles it.
        if (error instanceof ApiError && error.code === ORG_SELECTION_REQUIRED_CODE) {
          return;
        }
        toast.error('Erro ao carregar dados', { description: error.message });
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000,
        gcTime: 10 * 60 * 1000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => shouldAutoRetry(failureCount, error),
        retryDelay: (failureCount, error) => autoRetryDelayMs(failureCount, error),
      },
      mutations: {
        retry: false,
      },
    },
  });
}
