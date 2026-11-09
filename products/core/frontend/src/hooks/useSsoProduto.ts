/**
 * Public identity of the product being entered (`GET /api/sso/produto/{slug}`).
 * Contract: products/core/docs/sso-entry-contract.md. Unknown/inactive (404) and a refused
 * URL (409) are NOT retried: they are answers, not outages.
 */
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { SsoProduto } from '../lib/sso-entry';

export const ssoProdutoKeys = {
  all: ['core', 'sso-produto'] as const,
  detail: (slug: string) => [...ssoProdutoKeys.all, slug] as const,
};

export function useSsoProduto(slug: string | null) {
  const query = useQuery<SsoProduto>({
    queryKey: ssoProdutoKeys.detail(slug ?? ''),
    queryFn: () => api.get<SsoProduto>(`/api/sso/produto/${encodeURIComponent(slug as string)}`),
    enabled: !!slug,
    retry: false,
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
  return {
    ...query,
    produto: query.data,
    // Two signals off `data` (never `isLoading`).
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}
