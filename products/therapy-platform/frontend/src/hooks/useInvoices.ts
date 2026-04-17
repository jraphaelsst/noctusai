import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { Invoice } from '@/types';

const KEYS = {
  all: ['invoices'] as const,
  list: (page: number, pageSize: number) => ['invoices', 'list', page, pageSize] as const,
};

export function useInvoices(page = 1, pageSize = 10) {
  const { user } = useAuthStore();
  return useQuery<{ data: Invoice[]; total: number }>({
    queryKey: KEYS.list(page, pageSize),
    queryFn: async () => {
      const res = await api.get(`/api/invoices?page=${page}&page_size=${pageSize}`);
      return res;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useGenerateInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { transaction_id: string; descricao?: string }) => {
      return api.post('/api/invoices', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Recibo gerado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao gerar recibo');
    },
  });
}
