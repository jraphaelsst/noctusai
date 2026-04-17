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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Alerta revisado');
    },
    onError: () => {
      toast.error('Erro ao revisar alerta');
    },
  });
}
