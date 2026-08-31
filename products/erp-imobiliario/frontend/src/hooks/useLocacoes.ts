import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';
import type {
  ContratoLocacao,
  ContratoCreateData,
  ContratoUpdateData,
  ReajusteResult,
  RenovacaoResult,
} from '@/types/locacoes';

export function useLocacoes(status?: string) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['locacoes', status],
    queryFn: async () => {
      const params: Record<string, any> = {};
      if (status && status !== 'todos') params.status = status;
      const result = await api.get('/api/locacoes', params);
      return (result.data || []) as ContratoLocacao[];
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useLocacao(id?: string) {
  return useQuery({
    queryKey: ['locacao', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/locacoes/${id}`);
      return result.data as ContratoLocacao;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateLocacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ContratoCreateData) => {
      const result = await api.post('/api/locacoes', data);
      return result.data as ContratoLocacao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['locacoes'] });
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      toast.success('Contrato de locação criado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar contrato', { description: error.message });
    },
  });
}

export function useUpdateLocacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: ContratoUpdateData) => {
      const result = await api.patch(`/api/locacoes/${id}`, data);
      return result.data as ContratoLocacao;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['locacoes'] });
      queryClient.invalidateQueries({ queryKey: ['locacao'] });
      toast.success('Contrato atualizado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar contrato', { description: error.message });
    },
  });
}

export function useDeleteLocacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/locacoes/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['locacoes'] });
      queryClient.invalidateQueries({ queryKey: ['imoveis'] });
      toast.success('Contrato excluído com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir contrato', { description: error.message });
    },
  });
}

export function useReajusteLocacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, percentual, aplicar }: { id: string; percentual?: number; aplicar: boolean }) => {
      const result = await api.post(`/api/locacoes/${id}/reajuste`, { percentual, aplicar });
      return result.data as ReajusteResult;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['locacoes'] });
      if (data.aplicado) {
        toast.success('Reajuste aplicado com sucesso!');
      }
    },
    onError: (error: Error) => {
      toast.error('Erro ao calcular reajuste', { description: error.message });
    },
  });
}

export function useRenovarLocacao() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, nova_data_fim, novo_valor }: { id: string; nova_data_fim: string; novo_valor?: number }) => {
      const result = await api.post(`/api/locacoes/${id}/renovar`, { nova_data_fim, novo_valor });
      return result.data as RenovacaoResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['locacoes'] });
      toast.success('Contrato renovado com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao renovar contrato', { description: error.message });
    },
  });
}
