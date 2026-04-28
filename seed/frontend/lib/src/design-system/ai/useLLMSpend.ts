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
import { api } from '@noctusai/seed/infra';

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

export function useLLMSpend(orgId: string | null | undefined, isAdmin: boolean) {
  return useQuery<LLMSpendResponse, Error>({
    queryKey: ['admin', 'llm-spend', orgId ?? '_none'],
    queryFn: async () => api.get<LLMSpendResponse>(`/api/admin/llm-spend/${encodeURIComponent(orgId!)}`),
    enabled: Boolean(orgId && isAdmin),
    refetchInterval: LLM_SPEND_REFETCH_INTERVAL_MS,
    staleTime: 60_000,
    // Spend is operational telemetry; transient errors should not page
    // the user. Single retry is fine.
    retry: 1,
  });
}
