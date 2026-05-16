/**
 * `useConsents` — TanStack query for the user's per-feature AI consent
 * catalog. Backed by `GET /api/me/consents` (Core platform endpoint).
 *
 * Shape from `noctusai_lib.ai.consent.list_user_consent_view`:
 *   {
 *     items: [{
 *       key, title, rationale, product, default_granted, toggleable,
 *       granted, decision_recorded, granted_at, revoked_at,
 *     }, ...],
 *     pending: number,        // count of !decision_recorded && toggleable
 *   }
 *
 * `pending` powers the `<PendingConsentBadge/>` in the layout's `aiBadge`
 * slot. The seed framework auto-mounts `/settings/ai` (consuming this
 * hook) so products write zero consent-UI code — see
 * `seed/framework/frontend/src/app.tsx`.
 *
 * `staleTime: 60_000` matches the cadence of user-driven toggles — a
 * minute is short enough that toggle state reflects across other tabs
 * after a soft refresh, long enough that the hook doesn't refetch on
 * every component remount.
 */
import { useQuery } from '@tanstack/react-query';
import { api } from '@noctusai/seed/infra';
import { env } from '../../env';

export interface ConsentItem {
  key: string;
  title: string;
  rationale: string;
  product: string | null;
  default_granted: boolean;
  toggleable: boolean;
  granted: boolean;
  decision_recorded: boolean;
  granted_at: string | null;
  revoked_at: string | null;
}

export interface ConsentCatalogResponse {
  items: ConsentItem[];
  pending: number;
}

export const CONSENTS_QUERY_KEY = ['me', 'consents'] as const;

/** Empty catalog — what a standalone (no-Core) deploy degrades to. */
const EMPTY_CATALOG: ConsentCatalogResponse = { items: [], pending: 0 };

/**
 * `/api/me/consents` is a **Core-platform** endpoint. Two seed-owned
 * degradations so a standalone product deploy stops toasting a
 * backend-down error on every page load:
 *
 * 1. **Topology-aware (primary).** When `env.CORE_ATTACHED` is false
 *    the hook is disabled and resolves to an empty catalog — the
 *    consent UI simply has nothing to show (it is a Core feature).
 * 2. **404-swallow (floor).** Even Core-attached, a 404 (endpoint
 *    genuinely absent) resolves to the empty catalog instead of
 *    surfacing an error — degrade silently, never toast "servidor
 *    indisponível" for a structurally-absent Core surface.
 *
 * A real transient error (500, network) still surfaces so genuine
 * outages are not masked.
 */
export function useConsents() {
  const coreAttached = env.CORE_ATTACHED;
  return useQuery<ConsentCatalogResponse, Error>({
    queryKey: CONSENTS_QUERY_KEY,
    queryFn: async () => {
      try {
        return await api.get<ConsentCatalogResponse>('/api/me/consents');
      } catch (err) {
        // The shared api client throws `Error("[404] ...")`. Treat a
        // 404 as "no consent catalog here" (structurally absent on
        // standalone), not as a failure.
        if (err instanceof Error && err.message.startsWith('[404]')) {
          return EMPTY_CATALOG;
        }
        throw err;
      }
    },
    // Topology gate: no Core → don't even fire the request.
    enabled: coreAttached,
    initialData: coreAttached ? undefined : EMPTY_CATALOG,
    staleTime: 60_000,
    // Catalog is small (≤ 30 items today); retry once on transient errors.
    retry: 1,
  });
}
