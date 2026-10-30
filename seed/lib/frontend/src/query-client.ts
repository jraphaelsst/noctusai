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
import { Fragment, createElement, useEffect, useRef, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { QueryClient, QueryCache, QueryClientProvider } from '@tanstack/react-query';
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

// ---------------------------------------------------------------------------
// ONE QueryClient per org scope (in-page org swap, owner order 2026-10-29).
//
// Swapping orgs used to hard-reload so nothing cached under org A could survive
// under org B. The reload is gone; its cache guarantee is kept by giving every org
// scope its OWN client: on a swap the shell's provider is handed a brand-new client
// and the previous one is cancelled + emptied.
//
// Why a new client and not `cancelQueries()` + `clear()` on the same one: clearing
// cannot stop a closure that already holds the client. A mutation fired under org A
// whose answer lands after the swap runs its `onSuccess` (`useCacheWriteMutation`
// commits the server row with `setQueryData`) or its optimistic ROLLBACK (which
// writes org A's snapshot back) -- straight into the cleared cache, under org B.
// Org-scoped query keys would need every hook in every product to carry the org;
// they do not. With a client per scope, every pre-swap closure writes into a client
// no component observes any more: the late write is inert by construction.
// ---------------------------------------------------------------------------
let scopedClient: QueryClient | null = null;
const scopedListeners = new Set<() => void>();

/** The client of the CURRENT org scope (created on first read). */
export function getOrgScopedQueryClient(): QueryClient {
  if (scopedClient === null) scopedClient = createQueryClient();
  return scopedClient;
}

/**
 * Start the page's org scope with a fresh client (`createProductApp` calls it once).
 * Replaces any previous one, so each app instance starts from an empty cache.
 */
export function initOrgScopedQueryClient(): QueryClient {
  scopedClient = createQueryClient();
  scopedListeners.forEach((l) => l());
  return scopedClient;
}

/** True when `qc` is the org-scoped client the shell provides (so a swap can rotate it). */
export function isOrgScopedQueryClient(qc: QueryClient): boolean {
  return scopedClient !== null && qc === scopedClient;
}

function subscribeScopedClient(listener: () => void): () => void {
  scopedListeners.add(listener);
  return () => { scopedListeners.delete(listener); };
}

/**
 * Hand the provider a brand-new client for the next org scope. `seed` may prime it
 * BEFORE any component reads it (e.g. the new org's `/api/me/access` answer). The
 * provider empties the previous client once the new one is committed (`retireQueryClient`).
 */
export function rotateOrgScopedQueryClient(
  seed?: (next: QueryClient) => void,
): { previous: QueryClient; next: QueryClient } {
  const previous = getOrgScopedQueryClient();
  const next = createQueryClient();
  seed?.(next);
  scopedClient = next;
  scopedListeners.forEach((l) => l());
  return { previous, next };
}

/**
 * Stop and empty a client nobody will read again: in-flight queries are cancelled
 * (signal-aware fetches abort; any answer that still arrives is discarded by the
 * cancelled query), then every query and mutation is dropped.
 */
export async function retireQueryClient(qc: QueryClient): Promise<void> {
  await qc.cancelQueries();
  qc.getMutationCache().clear();
  qc.clear();
}

/** The shell's provider: always the current org scope's client. */
export function OrgScopedQueryClientProvider({ children }: { children?: ReactNode }) {
  const client = useSyncExternalStore(subscribeScopedClient, getOrgScopedQueryClient, getOrgScopedQueryClient);
  const shown = useRef(client);
  useEffect(() => {
    // Committed: every observer has moved to `client`. Only now may the previous scope's
    // client be emptied -- clearing it under still-mounted observers would let them
    // re-create entries in it.
    const previous = shown.current;
    shown.current = client;
    if (previous !== client) void retireQueryClient(previous);
  }, [client]);
  return createElement(QueryClientProvider, { client }, children);
}

// Generation per client: `OrgScopeBoundary` keys its subtree with it.
const generations = new WeakMap<QueryClient, number>();
let nextGeneration = 0;
function generationOf(client: QueryClient): number {
  let g = generations.get(client);
  if (g === undefined) { g = ++nextGeneration; generations.set(client, g); }
  return g;
}

/**
 * Remounts its subtree whenever the org-scoped client is replaced. REQUIRED around
 * everything that calls `useQuery`/`useMutation`: TanStack binds an observer to the
 * client it was CREATED with (`useState(() => new Observer(client))`), so a provider
 * that only changes its `client` prop leaves every mounted hook on the old cache.
 * The shell places it under the auth provider (which holds no queries), so auth and
 * the router survive a swap; the routes, the layout and the pages remount fresh.
 */
export function OrgScopeBoundary({ children }: { children?: ReactNode }) {
  const client = useSyncExternalStore(subscribeScopedClient, getOrgScopedQueryClient, getOrgScopedQueryClient);
  return createElement(Fragment, { key: generationOf(client) }, children);
}

/** Tests: forget the scoped client (the next read creates a fresh one). */
export function resetOrgScopedQueryClientForTests(): void {
  scopedClient = null;
  scopedListeners.forEach((l) => l());
}
