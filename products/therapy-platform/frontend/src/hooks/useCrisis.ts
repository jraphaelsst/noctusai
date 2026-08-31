import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { CrisisAlert } from '@/types';

const KEYS = {
  all: ['crisis-alerts'] as const,
  list: (page: number, pageSize: number) => ['crisis-alerts', 'list', page, pageSize] as const,
};

export function useCrisisAlerts(page = 1, pageSize = 20) {
  const { user } = useAuthStore();
  return useQuery<{ data: CrisisAlert[]; total: number }>({
    queryKey: KEYS.list(page, pageSize),
    queryFn: async () => {
      const res = await api.get(`/api/crisis-alerts?page=${page}&page_size=${pageSize}`);
      return res;
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useReviewCrisisAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) => {
      return api.post(`/api/crisis-alerts/${id}/review`, { status });
    },
    // Optimistic — the alert flips to reviewed instantly instead of sitting
    // in "pending" for a full round-trip; a failure rolls every touched
    // list page back to its pre-review snapshot. Mirrors the onMutate/
    // onError rollback discipline in useCardHub.ts (social-wiring).
    onMutate: async ({ id, status }) => {
      await qc.cancelQueries({ queryKey: KEYS.all });
      const previousLists = qc.getQueriesData<{ data: CrisisAlert[]; total: number }>({
        queryKey: KEYS.all,
      });
      previousLists.forEach(([key, page]) => {
        if (!page) return;
        qc.setQueryData<{ data: CrisisAlert[]; total: number }>(key, {
          ...page,
          data: page.data.map((alert) => (alert.id === id ? { ...alert, status } : alert)),
        });
      });
      return { previousLists };
    },
    onError: (_err, _vars, context) => {
      context?.previousLists?.forEach(([key, page]) => {
        qc.setQueryData(key, page);
      });
      toast.error('Erro ao revisar alerta');
    },
    onSuccess: () => {
      toast.success('Alerta revisado');
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
    },
  });
}
