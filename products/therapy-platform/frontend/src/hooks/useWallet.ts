import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { toast } from 'sonner';
import type { Wallet, WalletMovement } from '@/types/financial';

const KEYS = {
  all: ['wallet'] as const,
  detail: ['wallet', 'me'] as const,
  movements: (page?: number, pageSize?: number) => ['wallet', 'movements', page, pageSize] as const,
};

export function useWallet() {
  const { user } = useAuthStore();
  return useQuery<Wallet>({
    queryKey: KEYS.detail,
    queryFn: async () => {
      const res = await api.get('/api/wallets/me');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useWalletMovements(page = 1, pageSize = 10) {
  const { user } = useAuthStore();
  return useQuery<{ data: WalletMovement[]; total: number }>({
    queryKey: KEYS.movements(page, pageSize),
    queryFn: async () => {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      return api.get(`/api/wallets/me/movements?${params}`);
    },
    placeholderData: (prev) => prev,
    enabled: !!user,
    staleTime: 30 * 1000,
  });
}

export function useTopUp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { amount: number; payment_method_id?: string; method?: string }) => {
      return api.post('/api/wallets/top-up', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Creditos adicionados com sucesso');
    },
    onError: () => {
      toast.error('Erro ao adicionar creditos');
    },
  });
}

export function useWithdraw() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { amount: number }) => {
      return api.post('/api/wallets/withdraw', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Saque solicitado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao solicitar saque');
    },
  });
}
