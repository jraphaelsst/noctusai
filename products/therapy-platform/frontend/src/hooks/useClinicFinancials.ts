import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import { toast } from 'sonner';
import type { ClinicFinancials, ClinicTransfer } from '@/types/financial';

const KEYS = {
  all: ['clinic-financials'] as const,
  summary: ['clinic-financials', 'summary'] as const,
  transfers: (page?: number, pageSize?: number) =>
    ['clinic-financials', 'transfers', page, pageSize] as const,
};

export function useClinicFinancials() {
  const { user } = useAuthStore();
  return useQuery<ClinicFinancials>({
    queryKey: KEYS.summary,
    queryFn: async () => {
      const res = await api.get('/api/clinic/financials');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useClinicTransfers(page = 1, pageSize = 10) {
  const { user } = useAuthStore();
  return useQuery<{ data: ClinicTransfer[]; total: number }>({
    queryKey: KEYS.transfers(page, pageSize),
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      return api.get(`/api/clinic/financials/transfers?${params}`);
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateClinicTransfer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { therapist_id: string; amount: number; reason: string }) => {
      return api.post('/api/clinic/financials/transfers', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      qc.invalidateQueries({ queryKey: ['wallet'] });
      toast.success('Transferencia realizada com sucesso');
    },
    onError: () => {
      toast.error('Erro ao realizar transferencia');
    },
  });
}
