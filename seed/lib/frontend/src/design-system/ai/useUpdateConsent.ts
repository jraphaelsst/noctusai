/**
 * `useUpdateConsent` — TanStack mutation for granting / revoking an AI
 * consent. Backed by `PUT /api/me/consents/{key}` with body `{ granted }`.
 *
 * **Optimistic update with revert-on-error.** The flipped switch lands
 * in the cache immediately; the API call confirms (or errors). On error,
 * the cache reverts and a PT-BR toast surfaces the failure. On success
 * the response is invalidated so subsequent reads fetch fresh
 * `granted_at`/`revoked_at` timestamps + the recomputed `pending` count.
 *
 * **Pending count update logic.** When the user explicitly grants a
 * feature whose `decision_recorded` was `false`, the `pending` counter
 * decrements (the user just decided). When the user revokes a feature
 * whose decision was already recorded, `pending` is unchanged (the
 * user already had a decision; this is just flipping it).
 *
 * **Defensive mutation guard.** Backend rejects non-toggleable features
 * with `MandatoryFeatureCannotBeToggled` (HTTP 403). The frontend
 * `<AIConsentToggles/>` disables the switch for non-toggleable items,
 * but a misbehaving caller still hits the backend; the 403 surfaces
 * via the toast.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { coreApi } from '@noctusai/seed/infra';
import { toast } from 'sonner';

import { env } from '../../env';
import { CONSENTS_QUERY_KEY, type ConsentCatalogResponse } from './useConsents';

export interface UpdateConsentInput {
  key: string;
  granted: boolean;
}

interface OptimisticContext {
  prev: ConsentCatalogResponse | undefined;
}

export function useUpdateConsent() {
  const qc = useQueryClient();
  return useMutation<void, Error, UpdateConsentInput, OptimisticContext>({
    mutationFn: async ({ key, granted }) => {
      // Standalone (no Core) → `/api/me/consents/{key}` is absent.
      // No-op rather than 404-toast; mirrors `useConsents`'s
      // topology-aware degradation. The UI is hidden in this topology
      // anyway, but a misbehaving caller still must not error.
      if (!env.CORE_ATTACHED) return;
      await coreApi.put(`/api/me/consents/${encodeURIComponent(key)}`, { granted });
    },
    onMutate: async ({ key, granted }): Promise<OptimisticContext> => {
      await qc.cancelQueries({ queryKey: CONSENTS_QUERY_KEY });
      const prev = qc.getQueryData<ConsentCatalogResponse>(CONSENTS_QUERY_KEY);
      if (prev) {
        const wasUndecided = prev.items.find(
          (it) => it.key === key && !it.decision_recorded,
        );
        qc.setQueryData<ConsentCatalogResponse>(CONSENTS_QUERY_KEY, {
          ...prev,
          items: prev.items.map((it) =>
            it.key === key
              ? { ...it, granted, decision_recorded: true }
              : it,
          ),
          // Decrement pending only when the user just made their first
          // explicit decision on a previously-undecided feature.
          pending: wasUndecided ? Math.max(0, prev.pending - 1) : prev.pending,
        });
      }
      return { prev };
    },
    onError: (err, _vars, ctx) => {
      // Revert optimistic state, then surface the error.
      if (ctx?.prev) qc.setQueryData(CONSENTS_QUERY_KEY, ctx.prev);
      toast.error(err.message || 'Falha ao atualizar consentimento.');
    },
    // Always invalidate on settle so granted_at/revoked_at refresh from
    // the server (we don't synthesize them client-side; LGPD audit trail
    // requires server timestamps).
    onSettled: () => qc.invalidateQueries({ queryKey: CONSENTS_QUERY_KEY }),
  });
}
