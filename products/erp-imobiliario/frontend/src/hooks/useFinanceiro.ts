import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';
import {
  Lancamento,
  LancamentoCreateData,
  LancamentoUpdateData,
  ResumoFinanceiro,
  FluxoCaixa,
} from '@/types/financeiro';

interface FiltrosFinanceiro {
  tipo?: string;
  status?: string;
  categoria?: string;
  data_inicio?: string;
  data_fim?: string;
  page?: number;
  page_size?: number;
}

export function useFinanceiro(filtros?: FiltrosFinanceiro) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['financeiro', filtros],
    queryFn: async () => {
      const result = await api.get('/api/financeiro', {
        tipo: filtros?.tipo,
        status: filtros?.status,
        categoria: filtros?.categoria,
        data_inicio: filtros?.data_inicio,
        data_fim: filtros?.data_fim,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as Lancamento[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useLancamento(id?: string) {
  return useQuery({
    queryKey: ['lancamento', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/financeiro/${id}`);
      return result.data as Lancamento;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useResumoFinanceiro(filtros?: { data_inicio?: string; data_fim?: string }) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['financeiro-resumo', filtros],
    queryFn: async () => {
      const result = await api.get('/api/financeiro/resumo', {
        data_inicio: filtros?.data_inicio,
        data_fim: filtros?.data_fim,
      });
      return result.data as ResumoFinanceiro;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useFluxoCaixa(meses: number = 12) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['financeiro-fluxo', meses],
    queryFn: async () => {
      const result = await api.get('/api/financeiro/fluxo-caixa', { meses });
      return (result.data || []) as FluxoCaixa[];
    },
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateLancamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: LancamentoCreateData) => {
      const result = await api.post('/api/financeiro', data);
      return result.data as Lancamento;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financeiro'] });
      queryClient.invalidateQueries({ queryKey: ['financeiro-resumo'] });
      queryClient.invalidateQueries({ queryKey: ['financeiro-fluxo'] });
      toast.success('Lançamento criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar lançamento', { description: error.message });
    },
  });
}

export function useUpdateLancamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: LancamentoUpdateData) => {
      const result = await api.patch(`/api/financeiro/${id}`, data);
      return result.data as Lancamento;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financeiro'] });
      queryClient.invalidateQueries({ queryKey: ['financeiro-resumo'] });
      queryClient.invalidateQueries({ queryKey: ['financeiro-fluxo'] });
      queryClient.invalidateQueries({ queryKey: ['lancamento'] });
      toast.success('Lançamento atualizado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar lançamento', { description: error.message });
    },
  });
}

export function useDeleteLancamento() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/financeiro/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financeiro'] });
      queryClient.invalidateQueries({ queryKey: ['financeiro-resumo'] });
      queryClient.invalidateQueries({ queryKey: ['financeiro-fluxo'] });
      toast.success('Lançamento excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir lançamento', { description: error.message });
    },
  });
}
