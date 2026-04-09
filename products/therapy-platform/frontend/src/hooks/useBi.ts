import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import type { BiResumo, BiSessoes, BiReceita, BiCancelamento } from '@/types';

const KEYS = {
  resumo: ['bi', 'resumo'] as const,
  sessoes: (periodo: string) => ['bi', 'sessoes', periodo] as const,
  receita: (periodo: string) => ['bi', 'receita', periodo] as const,
  cancelamentos: ['bi', 'cancelamentos'] as const,
};

export function useBiResumo() {
  const { user } = useAuthStore();
  return useQuery<BiResumo>({
    queryKey: KEYS.resumo,
    queryFn: async () => {
      const res = await api.get('/api/bi/resumo');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useBiSessoes(periodo = '30d') {
  const { user } = useAuthStore();
  return useQuery<BiSessoes[]>({
    queryKey: KEYS.sessoes(periodo),
    queryFn: async () => {
      const res = await api.get(`/api/bi/sessoes?periodo=${periodo}`);
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useBiReceita(periodo = '30d') {
  const { user } = useAuthStore();
  return useQuery<BiReceita[]>({
    queryKey: KEYS.receita(periodo),
    queryFn: async () => {
      const res = await api.get(`/api/bi/receita?periodo=${periodo}`);
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useBiCancelamentos() {
  const { user } = useAuthStore();
  return useQuery<BiCancelamento[]>({
    queryKey: KEYS.cancelamentos,
    queryFn: async () => {
      const res = await api.get('/api/bi/cancelamentos');
      return res.data ?? res;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}
