/**
 * Hook for fetching AI outputs against a given entity reference.
 *
 *   const { data: outputs, isLoading } = useAIOutputFor('ativo', imovel.id);
 *
 * Mirrors the backend `/api/ai/outputs?ref_type=&ref_id=` endpoint shipped
 * by the `ai_outputs` standard router (Tier 2 Phase 3).
 *
 * Auto-disables when `refId` is null/undefined; returns empty until the
 * entity exists.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from '@noctusai/seed/infra';

import type { AIOutput } from './types';

interface AIOutputsResponse {
  data?: AIOutput[];
  count?: number;
}

export interface UseAIOutputForOptions {
  /** Override staleTime; default 60s. */
  staleTime?: number;
  /** Cap server-side; default 50. */
  limit?: number;
  /** Disable the query without unmounting (e.g. behind a feature flag). */
  enabled?: boolean;
}

export function useAIOutputFor(
  refType: string | null | undefined,
  refId: string | null | undefined,
  options: UseAIOutputForOptions = {},
) {
  const { staleTime = 60_000, limit = 50, enabled = true } = options;

  return useQuery({
    queryKey: ['ai_outputs', refType, refId, limit],
    queryFn: async () => {
      const qs = new URLSearchParams({
        ref_type: refType!,
        ref_id: refId!,
        limit: String(limit),
      });
      const response = (await api.get(
        `/api/ai/outputs?${qs}`,
      )) as AIOutputsResponse;
      return response?.data ?? [];
    },
    enabled: enabled && !!refType && !!refId,
    staleTime,
    // Keyed on `refId` — switching entities (e.g. clicking the next kanban
    // card) is a key change, not a background refetch, so `data` would
    // otherwise go `undefined` for a tick and the consumer's AI-output panel
    // would flash empty every navigation.
    placeholderData: keepPreviousData,
  });
}
