import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';

interface FiltrosPeriodo {
  periodo_inicio?: string;
  periodo_fim?: string;
}

export function useDashboardResumo() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['bi-dashboard'],
    queryFn: async () => {
      const result = await api.get('/api/bi/dashboard');
      return result.data;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useBIVendas(filtros?: FiltrosPeriodo) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['bi-vendas', filtros],
    queryFn: async () => {
      const result = await api.get('/api/bi/vendas', {
        periodo_inicio: filtros?.periodo_inicio,
        periodo_fim: filtros?.periodo_fim,
      });
      return result.data;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useBICaptacao() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['bi-captacao'],
    queryFn: async () => {
      const result = await api.get('/api/bi/captacao');
      return result.data;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useBICorretores(periodo?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['bi-corretores', periodo],
    queryFn: async () => {
      const result = await api.get('/api/bi/corretores', {
        periodo: periodo,
      });
      return result.data;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useBIImoveis() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['bi-imoveis'],
    queryFn: async () => {
      const result = await api.get('/api/bi/imoveis');
      return result.data;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useBIFinanceiro(filtros?: FiltrosPeriodo) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['bi-financeiro', filtros],
    queryFn: async () => {
      const result = await api.get('/api/bi/financeiro', {
        periodo_inicio: filtros?.periodo_inicio,
        periodo_fim: filtros?.periodo_fim,
      });
      return result.data;
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}
