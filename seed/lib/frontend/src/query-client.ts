/**
 * Shared QueryClient configuration.
 *
 * All products use the same defaults: 5 min stale time, 10 min GC,
 * no refetch on window focus, 1 retry, and a global error toast.
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

import { ApiError } from './api';

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
        toast.error('Erro ao carregar dados', { description: error.message });
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000,
        gcTime: 10 * 60 * 1000,
        refetchOnWindowFocus: false,
        retry: 1,
      },
    },
  });
}
