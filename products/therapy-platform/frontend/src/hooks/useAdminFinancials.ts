import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import { toast } from 'sonner';
import type {
  AdminFinancialSummary,
  Transaction,
  Payout,
  CommissionOverride,
  AdminWalletSummary,
} from '@/types/financial';

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useAdminSummary() {
  const { user } = useAuthStore();
  return useQuery<AdminFinancialSummary>({
    queryKey: ['admin', 'financial-summary'],
    queryFn: async () => {
      const res = await api.get('/api/admin/financials/summary');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useAdminTransactions(filters: Record<string, string>, page: number, pageSize: number) {
  const { user } = useAuthStore();
  return useQuery<{ data: Transaction[]; total: number }>({
    queryKey: ['admin', 'transactions', filters, page, pageSize],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
      return api.get(`/api/admin/financials/transactions?${params}`);
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useAdminCommissions() {
  const { user } = useAuthStore();
  return useQuery<{ global_rate_pct: number; overrides: CommissionOverride[] }>({
    queryKey: ['admin', 'commissions'],
    queryFn: async () => {
      const res = await api.get('/api/admin/financials/commissions');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useAdminWallets() {
  const { user } = useAuthStore();
  return useQuery<AdminWalletSummary[]>({
    queryKey: ['admin', 'wallets'],
    queryFn: async () => {
      const res = await api.get('/api/admin/financials/wallets');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useAdminPayouts(page: number, pageSize: number) {
  const { user } = useAuthStore();
  return useQuery<{ data: Payout[]; total: number }>({
    queryKey: ['admin', 'payouts', page, pageSize],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      return api.get(`/api/admin/financials/payouts?${params}`);
    },
    enabled: !!user,
    staleTime: 60 * 1000,
  });
}

export function useProcessPayout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => api.post(`/api/admin/financials/payouts/${id}/process`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'payouts'] });
      qc.invalidateQueries({ queryKey: ['admin', 'financial-summary'] });
      toast.success('Payout processado');
    },
    onError: () => toast.error('Erro ao processar payout'),
  });
}

export function useSaveCommission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { global_rate_pct?: number; override?: { entity_id: string; entity_type: string; rate_pct: number } }) =>
      api.post('/api/admin/financials/commissions', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'commissions'] });
      toast.success('Comissao atualizada');
    },
    onError: () => toast.error('Erro ao atualizar comissao'),
  });
}

export function useDeleteCommissionOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => api.delete(`/api/admin/financials/commissions/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'commissions'] });
      toast.success('Override removido');
    },
    onError: () => toast.error('Erro ao remover override'),
  });
}
