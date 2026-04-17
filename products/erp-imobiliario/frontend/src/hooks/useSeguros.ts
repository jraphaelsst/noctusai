import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, useAuthStore } from '@noctusai/seed/infra';
import {
  Seguro,
  SeguroCreateData,
  SeguroUpdateData,
  ResumoSeguros,
} from '@/types/seguros';

interface FiltrosSeguros {
  status?: string;
  imovel_id?: string;
  tipo_cobertura?: string;
  page?: number;
  page_size?: number;
}

export function useSeguros(filtros?: FiltrosSeguros) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['seguros', filtros],
    queryFn: async () => {
      const result = await api.get('/api/seguros', {
        status: filtros?.status,
        imovel_id: filtros?.imovel_id,
        tipo_cobertura: filtros?.tipo_cobertura,
        page: filtros?.page || 1,
        page_size: filtros?.page_size || 50,
      });
      return {
        data: (result.data || []) as Seguro[],
        pagination: result.pagination,
      };
    },
    enabled: !!user,
    staleTime: 3 * 60 * 1000,
  });
}

export function useSeguro(id?: string) {
  return useQuery({
    queryKey: ['seguro', id],
    queryFn: async () => {
      if (!id) return null;
      const result = await api.get(`/api/seguros/${id}`);
      return result.data as Seguro;
    },
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  });
}

export function useVencimentosSeguros(dias: number = 30) {
  const { user } = useAuthStore();

  return useQuery({
    queryKey: ['seguros-vencimentos', dias],
    queryFn: async () => {
      const result = await api.get('/api/seguros/vencimentos', { dias });
      return (result.data || []) as Seguro[];
    },
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCreateSeguro() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: SeguroCreateData) => {
      const result = await api.post('/api/seguros', data);
      return result.data as Seguro;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seguros'] });
      queryClient.invalidateQueries({ queryKey: ['seguros-vencimentos'] });
      toast.success('Seguro cadastrado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao cadastrar seguro', { description: error.message });
    },
  });
}

export function useUpdateSeguro() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, ...data }: SeguroUpdateData) => {
      const result = await api.patch(`/api/seguros/${id}`, data);
      return result.data as Seguro;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seguros'] });
      queryClient.invalidateQueries({ queryKey: ['seguros-vencimentos'] });
      queryClient.invalidateQueries({ queryKey: ['seguro'] });
      toast.success('Seguro atualizado!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao atualizar seguro', { description: error.message });
    },
  });
}

export function useDeleteSeguro() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/api/seguros/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['seguros'] });
      queryClient.invalidateQueries({ queryKey: ['seguros-vencimentos'] });
      toast.success('Seguro excluído!');
    },
    onError: (error: Error) => {
      toast.error('Erro ao excluir seguro', { description: error.message });
    },
  });
}
