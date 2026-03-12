/**
 * Shared QueryClient configuration.
 *
 * All products use the same defaults: 5 min stale time, 10 min GC,
 * no refetch on window focus, 1 retry, and a global error toast.
 */
import { QueryClient, QueryCache } from '@tanstack/react-query';
import { toast } from 'sonner';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
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
