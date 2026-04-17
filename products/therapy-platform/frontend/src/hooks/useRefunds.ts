import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { RefundRequest } from '@/types/financial';

const KEYS = {
  all: ['refunds'] as const,
  list: (page?: number, pageSize?: number) => ['refunds', 'list', page, pageSize] as const,
};

export function useRefundRequests(page = 1, pageSize = 10) {
  const { user } = useAuthStore();
  return useQuery<{ data: RefundRequest[]; total: number }>({
    queryKey: KEYS.list(page, pageSize),
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      return api.get(`/api/refunds?${params}`);
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateRefund() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { transaction_id: string; reason: string; refund_amount: number }) => {
      return api.post('/api/refunds', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      qc.invalidateQueries({ queryKey: ['transactions'] });
      toast.success('Solicitacao de reembolso enviada');
    },
    onError: () => {
      toast.error('Erro ao solicitar reembolso');
    },
  });
}

export function useReviewRefund() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...data }: { id: string; status: 'approved' | 'denied'; review_response?: string }) => {
      return api.patch(`/api/refunds/${id}`, data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      qc.invalidateQueries({ queryKey: ['transactions'] });
      qc.invalidateQueries({ queryKey: ['wallet'] });
      toast.success('Reembolso atualizado');
    },
    onError: () => {
      toast.error('Erro ao atualizar reembolso');
    },
  });
}
