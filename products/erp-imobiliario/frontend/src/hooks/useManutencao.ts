import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/store/authStore';
import {
  OrdemServico,
  OrdemServicoCreateData,
  OrdemServicoUpdateData,
  ResumoManutencao,
} from '@/types/manutencao';

interface FiltrosManutencao {
  status?: string;
  prioridade?: string;
  tipo?: string;
  imovel_id?: string;
  page?: number;
  page_size?: number;
}

export function useManutencao(filtros?: FiltrosManutencao) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['manutencao', filtros],
    queryFn: async () => {
      const result = await api.get('/api/manutencao', {
        status: filtros?.status,
        prioridade: filtros?.prioridade,
        tipo: filtros?.tipo,
        imovel_id: filtros?.imovel_id,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as OrdemServico[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useOrdemServico(id?: string) {
  return useQuery({
    queryKey: ['ordem-servico', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/manutencao/${id}`);
      return result.data as OrdemServico;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useResumoManutencao() {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['manutencao-resumo'],
    queryFn: async () => {
      const result = await api.get('/api/manutencao/resumo');
      return result.data as ResumoManutencao;
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateOrdemServico() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: OrdemServicoCreateData) => {
      const result = await api.post('/api/manutencao', data);
      return result.data as OrdemServico;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['manutencao'] });
      queryClient.invalidateQueries({ queryKey: ['manutencao-resumo'] });
      toast.success('Ordem de servico criada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao criar ordem de servico', { description: error.message });
    },
  });
}

export function useUpdateOrdemServico() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: OrdemServicoUpdateData) => {
      const result = await api.patch(`/api/manutencao/${id}`, data);
      return result.data as OrdemServico;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['manutencao'] });
      queryClient.invalidateQueries({ queryKey: ['manutencao-resumo'] });
      queryClient.invalidateQueries({ queryKey: ['ordem-servico'] });
      toast.success('Ordem atualizada!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar ordem', { description: error.message });
    },
  });
}

export function useDeleteOrdemServico() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/manutencao/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['manutencao'] });
      queryClient.invalidateQueries({ queryKey: ['manutencao-resumo'] });
      toast.success('Ordem excluida!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir ordem', { description: error.message });
    },
  });
}
