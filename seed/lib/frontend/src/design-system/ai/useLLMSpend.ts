/**
 * `useLLMSpend` — TanStack query for an org's month-to-date LLM spend
 * status. Backed by `GET /api/admin/llm-spend/{org_id}` (Core endpoint).
 *
 * **Admin-gated.** The hook only fetches when `isAdmin === true` AND a
 * non-empty `orgId` is present. Non-admins get `data === undefined` and
 * the consumer (`<LLMSpendBadge/>`) null-renders. This keeps the spend
 * status — which is operational state, not user-visible content —
 * scoped to admins.
 *
 * **Polling cadence: 5 minutes.** Spend status doesn't change at
 * sub-minute granularity; long polling keeps cache warm and avoids
 * burning request budget on a layout-mounted hook that runs on every
 * page.
 *
 * Backend response shape (from `noctusai_lib.llm.budget.compute_status`):
 *   {
 *     status: 'unset' | 'ok' | 'warn' | 'hard_stop',
 *     spent_brl: number,
 *     budget_brl: number | null,    // null when no budget set
 *     used_pct: number | null,       // null when budget is null
 *     soft_pct: number,              // threshold (e.g. 0.8)
 *     hard_pct: number,              // threshold (e.g. 1.0)
 *   }
 */
import { useQuery } from '@tanstack/react-query';
import { coreApi } from '@noctusai/seed/infra';

export type SpendStatus = 'unset' | 'ok' | 'warn' | 'hard_stop';

export interface LLMSpendResponse {
  status: SpendStatus;
  spent_brl: number;
  budget_brl: number | null;
  used_pct: number | null;
  soft_pct: number;
  hard_pct: number;
}

export const LLM_SPEND_REFETCH_INTERVAL_MS = 5 * 60_000;

/**
 * `/api/admin/llm-spend/{org_id}` is a **Core-platform** endpoint. On a
 * standalone (no-Core) deploy or any product that doesn't mount the
 * admin spend router, the endpoint returns a real 404. Swallow it
 * (resolves to `null` → `<LLMSpendBadge/>` null-renders) instead of
 * surfacing as a toast — mirrors the [[useConsents]] 404-swallow
 * pattern. A transient error (500, network) still surfaces.
 *
 * MUST return `null` rather than `undefined`: TanStack Query v5 treats
 * an `undefined` `queryFn` return as a contract violation and surfaces
 * "data is undefined" — exactly the toast this hook is trying to
 * suppress (2026-05-20 bit).
 */
export function useLLMSpend(orgId: string | null | undefined, isAdmin: boolean) {
  return useQuery<LLMSpendResponse | null, Error>({
    queryKey: ['admin', 'llm-spend', orgId ?? '_none'],
    queryFn: async () => {
      try {
        // Core wraps this in the seed envelope: `{"data": {...status, org_id}}`
        // (`products/core/backend/app/routers/admin_llm_spend.py`). Reading the
        // top level made EVERY field `undefined` — including `status`, so
        // `<LLMSpendBadge/>`'s `status === 'ok' | 'unset'` early-return never
        // fired and every admin saw a permanent, content-free warning chip
        // reading `IA ?% (— / —)` on every page. Worse in the other direction:
        // a real `hard_stop` could never render as one. Observed live on
        // social.noctusai.com, 2026-09-01.
        const res = await coreApi.get<LLMSpendResponse | { data: LLMSpendResponse }>(
          `/api/admin/llm-spend/${encodeURIComponent(orgId!)}`,
        );
        const body =
          res && typeof res === 'object' && 'data' in res
            ? (res as { data: LLMSpendResponse }).data
            : (res as LLMSpendResponse);
        // A payload without a recognisable `status` is not a spend reading —
        // treat it as "nothing to say" rather than rendering a blank warning.
        return body && typeof body.status === 'string' ? body : null;
      } catch (err) {
        if (err instanceof Error && err.message.startsWith('[404]')) {
          return null;
        }
        throw err;
      }
    },
    enabled: Boolean(orgId && isAdmin),
    refetchInterval: LLM_SPEND_REFETCH_INTERVAL_MS,
    staleTime: 60_000,
    // Spend is operational telemetry; transient errors should not page
    // the user. Single retry is fine.
    retry: 1,
  });
}
