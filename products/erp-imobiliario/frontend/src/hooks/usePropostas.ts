import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';
import {
  Proposta,
  PropostaCreateData,
  PropostaUpdateData,
  PropostaStats,
  ContrapropostaData,
} from '@/types/propostas';

interface FiltrosPropostas {
  status?: string;
  imovel_id?: string;
  cliente_id?: string;
  page?: number;
  page_size?: number;
}

export function usePropostas(filtros?: FiltrosPropostas) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['propostas', filtros],
    queryFn: async () => {
      const result = await api.get('/api/propostas', {
        status: filtros?.status,
        imovel_id: filtros?.imovel_id,
        cliente_id: filtros?.cliente_id,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as Proposta[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

export function useProposta(id?: string) {
  return useQuery({
    queryKey: ['proposta', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/propostas/${id}`);
      return result.data as Proposta;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function usePropostaStats() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['propostas-stats'],
    queryFn: async () => {
      const result = await api.get('/api/propostas/stats');
      return result.data as PropostaStats;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateProposta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: PropostaCreateData) => {
      const result = await api.post('/api/propostas', data);
      return result.data as Proposta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['propostas'] });
      queryClient.invalidateQueries({ queryKey: ['propostas-stats'] });
      toast.success('Proposta criada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar proposta', { description: error.message });
    },
  });
}

export function useUpdateProposta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: PropostaUpdateData) => {
      const result = await api.patch(`/api/propostas/${id}`, data);
      return result.data as Proposta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['propostas'] });
      queryClient.invalidateQueries({ queryKey: ['propostas-stats'] });
      queryClient.invalidateQueries({ queryKey: ['proposta'] });
      toast.success('Proposta atualizada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar proposta', { description: error.message });
    },
  });
}

export function useContraproposta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ proposta_id, ...data }: ContrapropostaData) => {
      const result = await api.post(`/api/propostas/${proposta_id}/contraproposta`, data);
      return result.data as Proposta;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['propostas'] });
      queryClient.invalidateQueries({ queryKey: ['propostas-stats'] });
      queryClient.invalidateQueries({ queryKey: ['proposta'] });
      toast.success('Contraproposta enviada com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao enviar contraproposta', { description: error.message });
    },
  });
}

export function useDeleteProposta() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/propostas/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['propostas'] });
      queryClient.invalidateQueries({ queryKey: ['propostas-stats'] });
      toast.success('Proposta excluída com sucesso!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir proposta', { description: error.message });
    },
  });
}
