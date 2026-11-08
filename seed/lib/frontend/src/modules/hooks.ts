/**
 * `useEnabledModules(api)` — reads `GET /api/modules` (BE `noctusai_seed.modules`): which of this product's modules the
 * caller's org has. Loading contract (`lying-loading-state.md`): `enabledKeys` is `null` until the first answer
 * (`isPending && !data`), never a guessed set; a failed read exposes `error` and keeps `enabledKeys` null (no module
 * renders on an unknown answer).
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { OrganApi } from '../organ-kit/query';

export interface ModuleEnablementItem {
  key: string;
  enablement_key: string;
  enabled: boolean;
  permissions: Record<string, 'member' | 'admin'>;
}

export const MODULES_QUERY_KEY = ['modules', 'enabled'] as const;

/** The stable machine code of the 403 a disabled module answers. */
export const MODULE_DISABLED_CODE = 'module_disabled';

export function useEnabledModules(api: Pick<OrganApi, 'get'>, enabled = true) {
  const q = useQuery<{ modules: ModuleEnablementItem[] }>({
    queryKey: MODULES_QUERY_KEY,
    queryFn: () => api.get<{ modules: ModuleEnablementItem[] }>('/api/modules'),
    staleTime: 60_000,
    enabled,
  });
  const enabledKeys = useMemo<ReadonlySet<string> | null>(
    () => (q.data ? new Set(q.data.modules.filter((m) => m.enabled).map((m) => m.enablement_key)) : null),
    [q.data],
  );
  return { enabledKeys, modules: q.data?.modules ?? [], showSkeleton: q.isPending && !q.data, isRefreshing: q.isFetching && !!q.data, error: q.error };
}
