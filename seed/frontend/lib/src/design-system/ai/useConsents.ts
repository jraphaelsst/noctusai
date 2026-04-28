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
 * `seed/frontend/framework/src/app.tsx`.
 *
 * `staleTime: 60_000` matches the cadence of user-driven toggles — a
 * minute is short enough that toggle state reflects across other tabs
 * after a soft refresh, long enough that the hook doesn't refetch on
 * every component remount.
 */
import { useQuery } from '@tanstack/react-query';
import { api } from '@noctusai/seed/infra';

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

export function useConsents() {
  return useQuery<ConsentCatalogResponse, Error>({
    queryKey: CONSENTS_QUERY_KEY,
    queryFn: async () => api.get<ConsentCatalogResponse>('/api/me/consents'),
    staleTime: 60_000,
    // Catalog is small (≤ 30 items today); retry once on transient errors.
    retry: 1,
  });
}
