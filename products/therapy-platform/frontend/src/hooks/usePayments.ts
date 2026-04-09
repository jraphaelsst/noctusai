import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import { toast } from 'sonner';
import type { PaymentMethod } from '@/types/financial';

const KEYS = {
  all: ['payments'] as const,
  methods: ['payments', 'methods'] as const,
};

export function usePaymentMethods() {
  const { user } = useAuthStore();
  return useQuery<PaymentMethod[]>({
    queryKey: KEYS.methods,
    queryFn: async () => {
      const res = await api.get('/api/payments/methods');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useValidateCard() {
  return useMutation({
    mutationFn: async (data: { token: string }) => {
      return api.post('/api/payments/validate-card', data);
    },
    onSuccess: () => {
      toast.success('Cartao validado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao validar cartao');
    },
  });
}

export function useAddPaymentMethod() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: { token: string; set_default?: boolean }) => {
      return api.post('/api/payments/methods', data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Metodo de pagamento adicionado');
    },
    onError: () => {
      toast.error('Erro ao adicionar metodo de pagamento');
    },
  });
}

export function useRemovePaymentMethod() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      return api.delete(`/api/payments/methods/${id}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.all });
      toast.success('Metodo de pagamento removido');
    },
    onError: () => {
      toast.error('Erro ao remover metodo de pagamento');
    },
  });
}
